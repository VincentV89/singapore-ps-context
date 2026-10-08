#!/usr/bin/env python3
"""Verify a deployed full COA platform against its actual Singapore sources.

Uses the same --metadata/--credentials/--state files as full_platform_ingest.py.
Reports real API results and execution traces; never substitutes authored data
for retrieved content. --check all runs schema, graph, SQL, Ontop and document
checks. --check deep additionally exercises the AgentCore SSE reasoning path.
The deep check can take several minutes and prints progress as events arrive.
Dependencies: boto3, rdflib, pycognito.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from full_platform_ingest import ROOT, PlatformClient, REFERENCE_BASE, field, load_corpus, redact, save_private, unwrap, utc_now


def serialized(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def successful_step(trace, *terms):
    return any(str(step.get("status", "")).lower() in {"ok", "success", "completed", "succeeded"} and any(term in str(step.get("step", "")).lower() for term in terms) for step in trace)


def graph_relationships(graph):
    """v0.3.4 Serve nests edges on entities; direct traverse uses flat edges."""
    if not isinstance(graph, dict):
        return []
    return list(graph.get("relationships") or []) + [edge for entity in graph.get("entities", []) for edge in (entity.get("relationships") or [])]


class Checks:
    def __init__(self, args):
        self.args = args
        self.client = PlatformClient(args.metadata, args.credentials)
        self.state = json.loads(args.state.read_text())
        self.catalogue, self.tables, digest = load_corpus(args.corpus)
        if digest != self.state["corpusHash"]:
            raise ValueError("Local catalogue differs from the actual staged source snapshot.")
        self.ns = self.state["namespaceId"]
        self.path = "/namespaces/" + self.ns
        self.document_provenance = {}
        self.report = {"checkedAt": utc_now(), "namespaceId": self.ns, "corpusHash": digest, "checks": []}

    def check(self, name, function):
        started = time.monotonic()
        print(f"Checking {name}...", flush=True)
        try:
            evidence = function()
            entry = {"check": name, "passed": True, "evidence": redact(evidence)}
            print(f"PASS {name}", flush=True)
        except Exception as exc:
            entry = {"check": name, "passed": False, "error": redact(str(exc)), "errorType": type(exc).__name__}
            print(f"FAIL {name}: {redact(str(exc))}", flush=True)
        entry["durationMs"] = round((time.monotonic() - started) * 1000)
        self.report["checks"].append(entry)
        self.report["passed"] = all(c["passed"] for c in self.report["checks"])
        save_private(self.args.output, self.report)

    def sources(self):
        namespace = self.client.request("GET", self.path)
        sources = self.client.paginate(self.path + "/sources")
        database = self.state["sources"]["database"]["sourceId"]
        matching = [s for s in sources if field(s, "sourceId") == database]
        if len(matching) != 1 or matching[0]["status"] != "APPROVED":
            raise AssertionError("Structured source has not completed real Scan and steward approval.")
        documents = [s for s in sources if s.get("sourceType") == "DOCUMENTS"]
        if not documents or any(s["status"] != "COMPLETED" for s in documents):
            raise AssertionError("Document ingestion is incomplete.")
        details = []
        for source in documents:
            detail = self.client.request("GET", self.path + "/sources/" + field(source, "sourceId"))
            doc = detail.get("documentDetails", {})
            if doc.get("filesErrored", 0) or doc.get("errorMessage") or doc.get("filesSkipped", 0):
                raise AssertionError("A document source completed with preprocessing errors.")
            if doc.get("documentsProcessed") is not None and doc["documentsProcessed"] <= 0:
                raise AssertionError("A completed document source did not process any actual documents.")
            details.append(redact(detail))
        s3 = self.client.aws.client("s3")
        block = s3.get_public_access_block(Bucket=self.state["bucket"])["PublicAccessBlockConfiguration"]
        if not all(block.values()):
            raise AssertionError("Official snapshot S3 bucket lacks complete public access blocking.")
        return {"namespace": namespace, "sources": sources, "documentDetails": details, "privateSourceBucket": self.state["bucket"], "publicAccessBlock": block}

    def schema(self):
        response = self.client.request("GET", self.path + "/schema?maxResults=500")
        classes = response.get("classes", unwrap(response).get("classes", []))
        uris = {field(c, "uri") for c in classes}
        missing = {REFERENCE_BASE + name for name in ("Scheme", "Agency", "Audience", "SupportCategory", "PolicyDocument", "EligibilityStatement", "SourceVersion")} - uris
        if missing:
            raise AssertionError("Published schema is missing reference classes: " + ", ".join(sorted(missing)))
        model = self.state.get("model", {})
        proposal_id = model.get("proposalId")
        if not proposal_id:
            raise AssertionError("No real induction proposal was recorded.")
        proposal = self.client.request("GET", self.path + "/proposals/" + proposal_id)
        if proposal.get("status") != "accepted":
            raise AssertionError("Actual induced proposal has not completed acceptance.")
        validation = model.get("validation", {}).get("report", {})
        if not validation.get("passed") or not model.get("localReview", {}).get("triplesMapCount"):
            raise AssertionError("Missing recorded proposal validation/mapping review.")
        return {"classCount": len(classes), "referenceClassUris": sorted(uris & {REFERENCE_BASE + name for name in ("Scheme", "Agency", "Audience", "SupportCategory", "PolicyDocument", "EligibilityStatement", "SourceVersion")}), "proposalId": proposal_id, "proposalStatus": proposal["status"], "localMappingReview": model["localReview"], "platformValidation": validation, "response": response}

    def graph(self):
        response = self.client.request("POST", self.path + "/graph/traverse", {"startUri": REFERENCE_BASE + "Scheme", "maxDepth": 2, "direction": "both", "maxResults": 60})
        graph = unwrap(response)
        entities, relationships = graph.get("entities", []), graph.get("relationships", [])
        if not entities or not relationships:
            raise AssertionError("Actual namespace graph traversal returned no relationships.")
        if not any(REFERENCE_BASE in serialized(item) for item in entities):
            raise AssertionError("Traversal does not reference the published Singapore support ontology.")
        return {"entityCount": len(entities), "relationshipCount": len(relationships), "response": response}

    def direct_athena(self):
        """Independent actual-row check; separate from Serve's SQL proof."""
        ns = self.client.request("GET", self.path)
        ns = ns.get("namespace", ns)
        workgroup = field(ns, "athenaWorkgroupName")
        if not workgroup:
            raise AssertionError("Namespace did not expose its actual Athena workgroup.")
        query = f'SELECT scheme_id, agency_id FROM "{self.state["database"]}"."schemes" ORDER BY scheme_id'
        athena = self.client.aws.client("athena")
        result = athena.start_query_execution(QueryString=query, WorkGroup=workgroup, QueryExecutionContext={"Database": self.state["database"], "Catalog": "AwsDataCatalog"})
        identifier = result["QueryExecutionId"]
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            execution = athena.get_query_execution(QueryExecutionId=identifier)["QueryExecution"]
            status = execution["Status"]["State"]
            if status == "SUCCEEDED":
                break
            if status in {"FAILED", "CANCELLED"}:
                raise AssertionError("Actual Athena row check failed: " + execution["Status"].get("StateChangeReason", status))
            time.sleep(2)
        else:
            raise TimeoutError("Athena query is still running; query ID is " + identifier)
        rows = athena.get_query_results(QueryExecutionId=identifier)["ResultSet"]["Rows"][1:]
        pairs = {(row["Data"][0].get("VarCharValue"), row["Data"][1].get("VarCharValue")) for row in rows}
        expected = {(r["scheme_id"], r["agency_id"]) for r in self.tables["schemes"]}
        if pairs != expected:
            raise AssertionError("Athena returned rows different from the attributed source catalogue, or included the CSV header.")
        return {"queryExecutionId": identifier, "workgroup": workgroup, "actualRowCount": len(pairs), "dataScannedBytes": execution.get("Statistics", {}).get("DataScannedInBytes"), "query": query}

    def structured(self, strategy):
        prompt = "List all published Singapore support schemes with their scheme identifier, scheme name and agency identifier from the schemes table. Return source rows; do not infer applicant eligibility."
        response = self.client.request("POST", self.path + "/query", {"query": prompt, "mode": "standard", "tierOverride": 2, "strategy": strategy, "execute": True, "includeSupporting": True, "includeDebugInfo": True, "maxResults": 50, "timeoutMs": 26000})
        result = unwrap(response)
        rows, trace = field(result, "resultRows", []), result.get("trace", [])
        if result.get("tier") != 2 or not rows:
            raise AssertionError("Pinned structured query did not return actual Tier-2 source rows.")
        query = field(result, "queryUsed", "")
        if not query or not successful_step(trace, "sql.execute", "vkg.execute", "query.execute", "query_execute", "query-execute"):
            raise AssertionError("Structured result lacks executed SQL evidence in its real trace.")
        row_text = serialized(rows).lower()
        matched_ids = [s["id"] for s in self.catalogue["schemes"] if s["id"].lower() in row_text]
        if not matched_ids:
            raise AssertionError("Structured rows do not contain identifiers from the actual official catalogue.")
        if strategy == "ontop":
            if not field(result, "sparqlGenerated") or not successful_step(trace, "vkg.compile", "vkg_compile", "vkg-compile"):
                raise AssertionError("Ontop check lacks actual SPARQL-to-SQL compilation; a fallback does not pass this check.")
        return {"strategy": strategy, "matchedSchemeIds": matched_ids, "rowCount": len(rows), "actualResponse": response}

    def citation_matches(self, chunks):
        """Match retrieved chunk provenance/content, never generated answer URLs."""
        matches = []
        for chunk in chunks:
            text = serialized(chunk)
            document_id = field(chunk, "sourceDocumentId") or field(chunk, "sourceDoc")
            for scheme in self.catalogue["schemes"]:
                direct = scheme["sourceUrl"] in text or f"{scheme['id']}.md" in text
                known = bool(document_id and self.document_provenance.get(document_id, {}).get("schemeId") == scheme["id"])
                if direct or known:
                    proof = {"schemeId": scheme["id"], "officialSourceUrl": scheme["sourceUrl"], "sourceHash": scheme["sourceHash"], "chunkId": field(chunk, "chunkId"), "documentId": document_id, "documentName": field(chunk, "sourceDocumentName"), "match": "official URL or staged document filename in actual retrieved content/provenance" if direct else "same document ID as an actual KBSearch chunk with verified staged filename/source URL"}
                    matches.append(proof)
                    if direct and document_id:
                        self.document_provenance[document_id] = proof
        return matches

    def documents(self):
        scheme_id = self.state["documentBatches"][0]["schemeIds"][0]
        scheme = next(s for s in self.catalogue["schemes"] if s["id"] == scheme_id)
        prompt = f"What published eligibility information does {scheme['agency']['name']} provide for {scheme['name']}?"
        search = self.client.request("POST", self.path + "/kb/search", {"query": prompt, "topK": 8})
        chunks = search.get("chunks", unwrap(search).get("chunks", []))
        matches = self.citation_matches(chunks)
        if not chunks or not matches:
            raise AssertionError("Knowledge-base search has no retrieved chunk with matched official source provenance.")
        response = self.client.request("POST", self.path + "/query", {"query": prompt + " Cite the published source and describe missing information. Do not decide an applicant's eligibility.", "mode": "standard", "tierOverride": 3, "includeSupporting": True, "maxResults": 8, "timeoutMs": 26000})
        result = unwrap(response)
        supporting = field(result, "supportingContent", [])
        answer_matches = self.citation_matches(supporting)
        if result.get("tier") != 3 or not supporting or not answer_matches or not field(result, "synthesizedAnswer"):
            raise AssertionError("Serve's answer lacks actual retrieved and attributed official supporting content.")
        graph = field(result, "graphContext", {})
        if not graph.get("entities") or not graph_relationships(graph):
            raise AssertionError("Serve returned retrieved documents without graph context relationships.")
        return {"knowledgeBaseSearch": search, "retrievedCitationMatches": matches, "answerCitationMatches": answer_matches, "actualResponse": response}

    def deep(self):
        arn = self.client.metadata.get("serveRuntimeArn")
        if not arn:
            raise ValueError("Metadata does not include the deployed Serve AgentCore runtime ARN.")
        endpoint = f"https://bedrock-agentcore.{self.client.region}.amazonaws.com/runtimes/{quote(arn, safe='')}/invocations?qualifier=DEFAULT"
        session = "sgsupport-check-" + hashlib.sha256((self.client.username + self.ns).encode()).hexdigest()
        prompt = "Compare official Singapore support for an SME seeking transformation and a community organisation seeking capability building. Use the approved catalogue and retrieved agency document evidence, show the agency relationships, and cite sources. Do not infer applicant eligibility or funding approval."
        # The v0.3.4 synthesis response preserves document IDs but omits display
        # filenames. Resolve those IDs through real KBSearch metadata first.
        provenance_search = self.client.request("POST", self.path + "/kb/search", {"query": prompt, "topK": 20})
        self.citation_matches(provenance_search.get("chunks", []))
        body = {"query": prompt, "namespace": self.ns, "options": {"mode": "deep-reasoning", "includeSupporting": True, "includeDebugInfo": True}, "stream": True}
        request = Request(endpoint, data=json.dumps(body).encode(), method="POST", headers={"Authorization": "Bearer " + self.client.id_token, "Content-Type": "application/json", "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session})
        events, event_name, data_lines = [], "message", []
        done = None
        try:
            with urlopen(request, timeout=190) as response:
                for raw in response:
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if not line:
                        if data_lines:
                            data = json.loads("\n".join(data_lines))
                            # AgentCore wraps yielded dictionaries in data: lines;
                            # the upstream emitter carries type/payload in JSON.
                            kind = data.get("type", event_name)
                            payload = data.get("payload", data)
                            events.append({"event": kind, "data": redact(payload)})
                            if kind in {"step", "error", "done"}:
                                print(f"AgentCore event {kind}: {redact(payload.get('stepName', payload.get('status', 'received')))}", flush=True)
                            if kind == "error":
                                raise RuntimeError("AgentCore emitted an actual error: " + str(redact(payload)))
                            if kind == "done":
                                done = payload
                            data_lines = []
                        event_name = "message"
                    elif line.startswith("event:"):
                        event_name = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
        except HTTPError as exc:
            raise RuntimeError(f"AgentCore returned HTTP {exc.code}: {redact(exc.read().decode(errors='replace'))[:1000]}") from None
        except URLError as exc:
            raise RuntimeError("AgentCore streaming request failed: " + type(exc.reason).__name__) from None
        if not done:
            raise AssertionError("AgentCore stream ended without a done event.")
        result = unwrap(done)
        supporting = field(result, "supportingContent", [])
        matches = self.citation_matches(supporting)
        graph = field(result, "graphContext", {})
        if not matches or not graph_relationships(graph) or not result.get("trace"):
            raise AssertionError("Deep reasoning did not return inspected official citations, graph relationships and actual trace together.")
        return {"runtimeArn": arn, "provenanceSearch": provenance_search, "citationMatches": matches, "actualDoneEvent": done, "actualEvents": events}

    def run(self):
        mapping = {"sources": self.sources, "schema": self.schema, "graph": self.graph, "athena": self.direct_athena, "sql": lambda: self.structured("nl_to_sql"), "ontop": lambda: self.structured("ontop"), "documents": self.documents, "deep": self.deep}
        names = list(mapping)[:-1] if self.args.check == "all" else [self.args.check]
        for name in names:
            self.check(name, mapping[name])
        print(f"Actual validation report: {self.args.output}", flush=True)
        return 0 if self.report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=ROOT / "artifacts" / "full-platform-ingest.local.json")
    parser.add_argument("--corpus", type=Path, default=ROOT / "data" / "official")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "full-platform-checks.local.json")
    parser.add_argument("--check", choices=("all", "sources", "schema", "graph", "athena", "sql", "ontop", "documents", "deep"), default="all")
    return Checks(parser.parse_args()).run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Validation stopped: {type(exc).__name__}: {redact(str(exc))}", file=sys.stderr)
        sys.exit(1)
