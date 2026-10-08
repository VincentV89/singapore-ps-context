#!/usr/bin/env python3
"""Stage attributed Singapore sources through COA v0.3.4's real Scan/Model APIs.

Dependencies: boto3, rdflib, pycognito. Run with a deployment metadata JSON and
a private *.local.json containing {"username": "...", "password": "..."}.
Metadata: region, accountId, prefix, apiUrl, cognito.{userPoolId,clientId}; optional
serveRuntimeArn. AWS credentials come from the normal SDK environment only.

Each invocation polls briefly and checkpoints asynchronous jobs. A pending run
exits 2; rerun the same command to resume. --stage stage uploads private S3/Glue
data only; scan also registers/reviews sources; model also imports/induces OWL.
No direct Neptune writes, fabricated induction, or authoritative eligibility
rules are installed. Data comes from the reviewed catalogue and source snapshots.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import boto3
from botocore.exceptions import ClientError
from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ID = "urn:sgsupport:singapore-support:v1"
REFERENCE_BASE = "https://vincentv89.github.io/singapore-ps-context/ontology/support#"
INDUCED_BASE = "https://vincentv89.github.io/singapore-ps-context/ontology/induced/"
RR = Namespace("http://www.w3.org/ns/r2rml#")
COA = Namespace("http://coa.amazon.com/vocab/coa#")
SCHEMAS = {
    "schemes": ["scheme_id", "scheme_name", "persona", "categories", "agency_id", "status", "summary", "eligibility_text", "benefit_text", "application_url", "source_url", "source_title", "fetched_at", "source_hash"],
    "agencies": ["agency_id", "agency_name", "abbreviation", "agency_url"],
    "evidence": ["evidence_id", "scheme_id", "agency_id", "evidence_type", "excerpt", "source_url", "source_title", "fetched_at", "source_hash"],
}
TABLE_DESCRIPTIONS = {
    "schemes": "Public Singapore agency support programme catalogue. Summaries and attributed eligibility text were curated from timestamped official source snapshots. No applicant records or approval decisions.",
    "agencies": "Official administering bodies attributed by the published Singapore programme pages. Agency identifiers join to the public scheme and evidence catalogues.",
    "evidence": "Attributed excerpts from published official Singapore agency pages, with source URL, title, retrieval timestamp, and SHA-256 of the exact snapshot. Evidence is not an executable eligibility rule.",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def field(obj, name, default=None):
    """Some v0.3.4 ontology routes return snake_case despite Smithy aliases."""
    if not isinstance(obj, dict):
        return default
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return obj.get(name, obj.get(snake, default))


def unwrap(obj):
    return obj.get("result", obj) if isinstance(obj, dict) else obj


def redact(value):
    """Remove credentials and signed URLs from reports, including nested trace."""
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if not re.search(r"password|token|secret|authorization|presign|uploadurl|ontologyurl|r2rmlurl|matchesurl|constraintsurl", k.replace("_", ""), re.I)}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"https?://[^\s\"<>]+(?:X-Amz-[^\s\"<>]+)", "[signed URL omitted]", value, flags=re.I)
        value = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[JWT omitted]", value)
        return value
    return value


def save_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(redact(value), stream, indent=2, default=str)
        stream.write("\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


class APIError(RuntimeError):
    def __init__(self, status, path, body):
        self.status = status
        self.path = path
        super().__init__(f"HTTP {status} for {path}: {str(redact(body))[:1000]}")


class PlatformClient:
    def __init__(self, metadata_path, credentials_path):
        self.metadata = json.loads(metadata_path.read_text())
        self.region = self.metadata.get("region", "us-east-1")
        self.prefix = self.metadata.get("prefix", "sgsupport")
        self.account = str(self.metadata.get("accountId", "879594333699"))
        if self.region != "us-east-1" or self.account != "879594333699" or self.prefix != "sgsupport":
            raise ValueError("Metadata must identify the authorized sgsupport deployment in account 879594333699, us-east-1.")
        self.api_url = self.metadata["apiUrl"].rstrip("/")
        parsed = urlparse(self.api_url)
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".execute-api.us-east-1.amazonaws.com"):
            raise ValueError("apiUrl must be the full deployment's us-east-1 API Gateway HTTPS endpoint.")
        self.aws = boto3.Session(region_name=self.region)
        identity = self.aws.client("sts").get_caller_identity()
        if identity["Account"] != self.account:
            raise ValueError("Current AWS credentials do not match the authorized account.")
        credentials = json.loads(credentials_path.read_text())
        self.username = credentials["username"]
        if credentials_path.stat().st_mode & 0o077:
            raise ValueError("Login file must be private (chmod 600).")
        auth = self.metadata["cognito"]
        pool_id, client_id = auth["userPoolId"], auth["clientId"]
        if credentials.get("idToken"):
            self.id_token = credentials["idToken"]
        else:
            try:
                from pycognito.aws_srp import AWSSRP
            except ImportError as exc:
                raise RuntimeError("Install pycognito for the deployed Cognito USER_SRP_AUTH flow.") from exc
            result = AWSSRP(username=self.username, password=credentials["password"], pool_id=pool_id, client_id=client_id, client=self.aws.client("cognito-idp")).authenticate_user()
            if not result.get("AuthenticationResult", {}).get("IdToken"):
                raise RuntimeError("Cognito requires an additional login challenge; complete administrator setup before ingestion.")
            self.id_token = result["AuthenticationResult"]["IdToken"]
        payload = self.id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if claims.get("token_use") != "id" or claims.get("aud") != client_id or claims.get("iss") != f"https://cognito-idp.{self.region}.amazonaws.com/{pool_id}" or claims.get("exp", 0) <= time.time():
            raise ValueError("The supplied Cognito session does not match this deployment or has expired.")

    def request(self, method, path, body=None, timeout=35):
        data = None if body is None else json.dumps(body).encode()
        req = Request(self.api_url + path, data=data, method=method, headers={"Authorization": "Bearer " + self.id_token, "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise APIError(exc.code, path, detail) from None
        except URLError as exc:
            raise RuntimeError(f"Network request failed for {path}: {type(exc.reason).__name__}") from None

    def fetch_signed(self, url):
        if urlparse(url).scheme != "https":
            raise ValueError("Artifact download URL is not HTTPS.")
        try:
            with urlopen(url, timeout=30) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError):
            raise RuntimeError("Cannot download the proposal's signed S3 artifact; refresh the proposal and retry.") from None

    def put_signed(self, url, data):
        req = Request(url, data=data, method="PUT", headers={"Content-Type": "text/turtle"})
        try:
            with urlopen(req, timeout=30) as response:
                response.read()
        except (HTTPError, URLError):
            raise RuntimeError("The signed ontology upload failed; obtain a fresh upload URL and retry.") from None

    def paginate(self, path, keys=("items",)):
        items, token = [], None
        while True:
            suffix = ("&" if "?" in path else "?") + "nextToken=" + quote(token, safe="") if token else ""
            result = self.request("GET", path + suffix)
            if isinstance(result, list):
                return items + result
            if result.get("skippedAssets"):
                raise RuntimeError("Source table listing is partial; resolve skipped DataZone assets before review.")
            for key in keys:
                if key in result:
                    items.extend(result[key])
                    break
            token = field(result, "nextToken")
            if not token:
                return items


def load_corpus(root):
    catalogue = json.loads((root / "catalogue.json").read_text())
    schemes = catalogue["schemes"]
    if not schemes or {s["persona"] for s in schemes} != {"individuals", "businesses", "community", "research"}:
        raise ValueError("Official catalogue must cover all four audiences.")
    ids = set()
    for scheme in schemes:
        identifier = scheme["id"]
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,80}", identifier) or identifier in ids:
            raise ValueError("Invalid or duplicate official scheme identifier.")
        ids.add(identifier)
        if scheme.get("verified") is not True or not re.fullmatch(r"[0-9a-f]{64}", scheme["sourceHash"]):
            raise ValueError(f"Source provenance has not been verified for {identifier}.")
        for key in ("sourceUrl", "applicationUrl"):
            if urlparse(scheme[key]).scheme != "https":
                raise ValueError(f"Expected HTTPS official provenance for {identifier}.")
        raw = root / "raw" / f"{identifier}.html"
        if not raw.exists() or hashlib.sha256(raw.read_bytes()).hexdigest() != scheme["sourceHash"]:
            raise ValueError(f"Exact snapshot digest does not match catalogue for {identifier}.")
        document = root / "documents" / f"{identifier}.md"
        if not document.exists() or scheme["sourceUrl"] not in document.read_text():
            raise ValueError(f"Ingest document lacks explicit official provenance for {identifier}.")
    tables = {}
    for name, columns in SCHEMAS.items():
        with (root / "structured" / f"{name}.csv").open(newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != columns:
                raise ValueError(f"CSV header mismatch for {name}: {reader.fieldnames}")
            rows = list(reader)
        pk = {"schemes": "scheme_id", "agencies": "agency_id", "evidence": "evidence_id"}[name]
        if not rows or len({r[pk] for r in rows}) != len(rows) or any(not r[pk] for r in rows):
            raise ValueError(f"Missing or duplicate primary keys in {name}.")
        if any(set(r) != set(columns) or any(v is None or "\n" in v or "\r" in v for v in r.values()) for r in rows):
            raise ValueError(f"Malformed or multiline CSV row in {name}.")
        tables[name] = rows
    agency_ids = {r["agency_id"] for r in tables["agencies"]}
    if {r["scheme_id"] for r in tables["schemes"]} != ids:
        raise ValueError("Structured schemes differ from the verified source catalogue.")
    for name in ("schemes", "evidence"):
        if any(r["agency_id"] not in agency_ids or (name == "evidence" and r["scheme_id"] not in ids) for r in tables[name]):
            raise ValueError(f"Dangling foreign key in {name}.")
    by_id = {s["id"]: s for s in schemes}
    for name in ("schemes", "evidence"):
        for row in tables[name]:
            scheme = by_id[row["scheme_id"]]
            if row["source_url"] != scheme["sourceUrl"] or row["source_hash"] != scheme["sourceHash"]:
                raise ValueError(f"Structured provenance differs from snapshot for {row['scheme_id']}.")
    files = [root / "catalogue.json"] + sorted((root / "structured").glob("*.csv"))
    digest = hashlib.sha256(b"".join(p.read_bytes() for p in files)).hexdigest()
    return catalogue, tables, digest


def ordered_documents(schemes):
    queues = [deque(s["id"] for s in schemes if s["persona"] == persona) for persona in ("individuals", "businesses", "community", "research")]
    result = []
    while any(queues):
        for queue in queues:
            if queue:
                result.append(queue.popleft())
    return result


class IngestRun:
    def __init__(self, args):
        self.args = args
        self.client = PlatformClient(args.metadata, args.credentials)
        self.catalogue, self.tables, digest = load_corpus(args.corpus)
        self.state = json.loads(args.state.read_text()) if args.state.exists() else {"version": 1, "prefix": self.client.prefix, "accountId": self.client.account, "createdAt": utc_now()}
        if self.state.get("corpusHash", digest) != digest:
            raise ValueError("The staged corpus changed. Review and rescan explicitly; do not silently replace an approved snapshot.")
        self.state["corpusHash"] = digest
        self.state["catalogueFetchedAt"] = self.catalogue["fetchedAt"]
        self.state["rowCounts"] = {k: len(v) for k, v in self.tables.items()}
        self.pending = []
        self.retried = set()

    def checkpoint(self):
        self.state["updatedAt"] = utc_now()
        save_private(self.args.state, self.state)

    def log(self, step, status):
        print(f"{step}: {status}", flush=True)

    def namespace(self):
        if self.state.get("namespaceId"):
            result = self.client.request("GET", "/namespaces/" + self.state["namespaceId"])
            detail = result.get("namespace", result)
            if detail.get("name") != "sg-support":
                raise ValueError("Saved namespace does not identify sg-support.")
            self.state["namespace"] = redact(detail)
            return
        namespaces = self.client.paginate("/namespaces", ("namespaces", "items"))
        found = [n for n in namespaces if n.get("name") == "sg-support"]
        if len(found) > 1:
            raise RuntimeError("More than one sg-support namespace exists; resolve this before ingestion.")
        result = found[0] if found else self.client.request("POST", "/namespaces", {"name": "sg-support", "displayName": "Singapore Support Navigator", "description": "Published Singapore agency support information for individuals, enterprises, community organisations, and researchers. Attributed public snapshots; no applicant personal data or authoritative eligibility decisions.", "owner": self.client.username})["namespace"]
        self.state["namespaceId"] = field(result, "namespaceId")
        if not self.state["namespaceId"]:
            raise RuntimeError("Namespace response omitted its identifier.")
        self.state["namespace"] = redact(result)
        self.checkpoint()
        self.log("Namespace", self.state["namespaceId"])

    def stage(self):
        document_ids = ordered_documents(self.catalogue["schemes"])
        if self.args.document_limit:
            document_ids = document_ids[:self.args.document_limit]
        if self.state.get("stagedDocumentIds") == document_ids and self.state.get("stagedAt"):
            self.log("Private S3/Glue staging", "verified snapshot already staged")
            return
        s3, glue = self.client.aws.client("s3"), self.client.aws.client("glue")
        bucket = f"{self.client.prefix}-demo-official-{self.client.account}-{self.client.region}"
        tags = {"Project": "sgsupport", "Demo": "singapore-official-support", "sgsupport:namespace": self.state["namespaceId"]}
        try:
            s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=self.client.account)
            try:
                current = {t["Key"]: t["Value"] for t in s3.get_bucket_tagging(Bucket=bucket)["TagSet"]}
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "NoSuchTagSet":
                    raise
                current = {}
            if current.get("Project") != "sgsupport" or current.get("Demo") != tags["Demo"]:
                raise ValueError("Refusing to modify an existing bucket without this demo's ownership tags.")
        except ClientError as exc:
            if str(exc.response["Error"]["Code"]) not in {"404", "NoSuchBucket"}:
                raise
            s3.create_bucket(Bucket=bucket)
        s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in tags.items()]})
        s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
        s3.put_bucket_ownership_controls(Bucket=bucket, OwnershipControls={"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]})
        s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})
        s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
        db = "sgsupport_official"
        try:
            existing = glue.get_database(Name=db)["Database"]
            if existing.get("Parameters", {}).get("Project") != "sgsupport":
                raise ValueError("Refusing to modify an existing Glue database without demo ownership metadata.")
        except glue.exceptions.EntityNotFoundException:
            glue.create_database(DatabaseInput={"Name": db, "Description": "Timestamped public Singapore agency catalogue and attributed source evidence for the COA demo.", "Parameters": tags})
        glue.tag_resource(ResourceArn=f"arn:aws:glue:{self.client.region}:{self.client.account}:database/{db}", TagsToAdd=tags)
        for name, columns in SCHEMAS.items():
            source = self.args.corpus / "structured" / f"{name}.csv"
            s3.put_object(Bucket=bucket, Key=f"structured/{name}/part-000.csv", Body=source.read_bytes(), ContentType="text/csv", ServerSideEncryption="AES256", Metadata={"source-catalogue-sha256": self.state["corpusHash"]})
            table = {"Name": name, "Description": TABLE_DESCRIPTIONS[name], "TableType": "EXTERNAL_TABLE", "Parameters": {"classification": "csv", "skip.header.line.count": "1", "EXTERNAL": "TRUE", "Project": "sgsupport"}, "StorageDescriptor": {"Columns": [{"Name": column, "Type": "string", "Comment": column.replace("_", " ")} for column in columns], "Location": f"s3://{bucket}/structured/{name}/", "InputFormat": "org.apache.hadoop.mapred.TextInputFormat", "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat", "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.serde2.OpenCSVSerde", "Parameters": {"separatorChar": ",", "quoteChar": '"', "escapeChar": "\\"}}}}
            try:
                old = glue.get_table(DatabaseName=db, Name=name)["Table"]
                if old.get("Parameters", {}).get("Project") != "sgsupport":
                    raise ValueError(f"Refusing to modify an existing unowned Glue table: {name}.")
                glue.update_table(DatabaseName=db, TableInput=table)
            except glue.exceptions.EntityNotFoundException:
                glue.create_table(DatabaseName=db, TableInput=table)
        batches = []
        for offset in range(0, len(document_ids), 6):
            batch_ids = document_ids[offset:offset + 6]
            batch_name = f"batch-{offset // 6 + 1:02d}"
            for identifier in batch_ids:
                data = (self.args.corpus / "documents" / f"{identifier}.md").read_bytes()
                s3.put_object(Bucket=bucket, Key=f"documents/{batch_name}/{identifier}.md", Body=data, ContentType="text/markdown", ServerSideEncryption="AES256", Metadata={"source-scheme-id": identifier, "source-catalogue-sha256": self.state["corpusHash"]})
            batches.append({"name": batch_name, "prefix": f"documents/{batch_name}/", "schemeIds": batch_ids})
        s3.put_object(Bucket=bucket, Key="provenance/catalogue.json", Body=(self.args.corpus / "catalogue.json").read_bytes(), ContentType="application/json", ServerSideEncryption="AES256")
        self.state.update({"bucket": bucket, "database": db, "documentBatches": batches, "stagedDocumentIds": document_ids, "stagedAt": utc_now()})
        self.checkpoint()
        self.log("Private S3/Glue staging", f"{sum(self.state['rowCounts'].values())} rows, {len(document_ids)} official documents")

    def source_path(self, source_id):
        return f"/namespaces/{self.state['namespaceId']}/sources/{quote(source_id, safe='')}"

    def register(self, key, name, payload):
        sources = self.state.setdefault("sources", {})
        if key not in sources:
            found = [s for s in self.client.paginate(f"/namespaces/{self.state['namespaceId']}/sources") if s.get("name") == name]
            if len(found) > 1:
                raise RuntimeError(f"Duplicate source names for {name}; inspect before proceeding.")
            result = found[0] if found else self.client.request("POST", f"/namespaces/{self.state['namespaceId']}/sources", payload)
            sources[key] = {"sourceId": field(result, "sourceId"), "name": name, "registeredAt": utc_now(), "sourceType": payload["sourceType"]}
            self.checkpoint()
        record = sources[key]
        actual = self.client.request("GET", self.source_path(record["sourceId"]))
        record.update({"status": actual["status"], "lastObservedAt": utc_now(), "details": redact(actual)})
        self.checkpoint()
        self.log(name, actual["status"])
        if actual["status"] == "SCAN_FAILED" and self.args.retry_failed and key not in self.retried:
            record.setdefault("failedAttempts", []).append({"observedAt": utc_now(), "details": redact(actual)})
            self.retried.add(key)
            result = self.client.request("POST", self.source_path(record["sourceId"]) + "/rescan", {})
            record["status"] = result.get("status", "SCANNING")
            self.checkpoint()
            self.log(name, "Retry submitted after diagnosed scan failure")
            return record
        if actual["status"] in {"SCAN_FAILED", "REJECTED", "DELETE_FAILED", "DELETED"}:
            raise RuntimeError(f"Source {name} reached {actual['status']}: {redact(actual.get('documentDetails', actual.get('databaseDetails', {})))}")
        return record

    def review_database(self, source):
        if source["status"] == "APPROVED" and self.state.get("scanReview"):
            return
        if source["status"] not in {"PENDING_REVIEW", "RESCAN_REVIEW", "APPROVAL_FAILED", "APPROVED"}:
            self.pending.append("Database scan/review")
            return
        base = self.source_path(source["sourceId"])
        summaries = self.client.paginate(base + "/tables")
        found = {t["name"]: t for t in summaries}
        if set(found) != set(SCHEMAS):
            raise ValueError(f"Actual scan tables differ from the controlled public corpus: {sorted(found)}.")
        report = {"reviewedAt": utc_now(), "reviewScope": "Controlled public schema, keys, relationships and provenance; no legal policy adjudication", "tables": []}
        for name, columns in SCHEMAS.items():
            table_id = found[name]["tableId"]
            path = base + "/tables/" + quote(table_id, safe="")
            table = self.client.request("GET", path)
            actual_columns = [c["name"] for c in table["columns"]]
            if set(actual_columns) != set(columns) or table.get("pendingDeletion") or table.get("database") != self.state["database"]:
                raise ValueError(f"Actual discovered columns differ from validated CSV in {name}.")
            report["tables"].append({"tableId": table_id, "scannedMetadata": redact(table), "validatedColumns": columns, "validatedRowCount": len(self.tables[name])})
            pk = {"schemes": "scheme_id", "agencies": "agency_id", "evidence": "evidence_id"}[name]
            fks = []
            if name in {"schemes", "evidence"}:
                fks.append({"column": "agency_id", "targetTable": found["agencies"]["tableId"], "targetColumn": "agency_id", "source": "STEWARD_SPECIFIED", "provenance": "Exact join validated against the public source CSV rows."})
            if name == "evidence":
                fks.append({"column": "scheme_id", "targetTable": found["schemes"]["tableId"], "targetColumn": "scheme_id", "source": "STEWARD_SPECIFIED", "provenance": "Exact join validated against the public source CSV rows."})
            self.client.request("PATCH", path + "/keys", {"primaryKey": {"columns": [pk]}, "foreignKeys": fks})
            self.client.request("PATCH", path + "/metadata", {"overrides": {"description": TABLE_DESCRIPTIONS[name], "tags": ["public-official-source", "attributed-snapshot", "singapore"]}})
            self.client.request("PUT", path + "/review", {"decision": "APPROVED"})
            reviewed = self.client.request("GET", path)
            if reviewed["reviewStatus"] != "APPROVED" or any(c.get("businessMetadata", {}).get("reviewStatus") != "APPROVED" for c in reviewed["columns"]):
                raise RuntimeError(f"Review did not approve every validated column in {name}.")
        self.state["scanReview"] = report
        self.checkpoint()
        if source["status"] != "APPROVED":
            self.client.request("POST", base + "/approve", {})
            source["status"] = "APPROVING"
            self.pending.append("Database approval")
            self.checkpoint()

    def scan(self):
        name = "Singapore official public support catalogue"
        source = self.register("database", name, {"sourceType": "DATABASE", "databaseSource": {"name": name, "glueConfiguration": {"catalogId": self.client.account, "region": self.client.region, "databaseName": self.state["database"]}, "metadataEnrichmentEnabled": True}})
        self.review_database(source)
        for batch in self.state["documentBatches"]:
            name = "Singapore official agency documents " + batch["name"]
            source = self.register(batch["name"], name, {"sourceType": "DOCUMENTS", "documentSource": {"name": name, "sourceBucketArn": f"arn:aws:s3:::{self.state['bucket']}", "s3Prefixes": [batch["prefix"]], "extractionConfig": {"preferredEntityClassifications": ["Scheme", "Agency", "Audience", "SupportCategory", "EligibilityStatement", "PolicyDocument", "SourceVersion"], "useBatchInference": False}}})
            if source["status"] != "COMPLETED":
                self.pending.append("Documents " + batch["name"])
            else:
                # The upstream KG task can complete with partial extraction
                # failures. A completed status alone does not prove all files
                # became retrievable source documents.
                details = source["details"].get("documentDetails", {})
                expected = len(batch["schemeIds"])
                if details.get("filesErrored", 0) or details.get("filesSkipped", 0) or details.get("errorMessage"):
                    raise RuntimeError(f"Document batch {batch['name']} completed with preprocessing failures: {redact(details)}")
                if details.get("filesTotal") != expected or details.get("documentsProcessed") != expected:
                    raise RuntimeError(f"Document batch {batch['name']} has incomplete extraction evidence: expected {expected}, filesTotal={details.get('filesTotal')}, documentsProcessed={details.get('documentsProcessed')}. Inspect actual KG task logs before rescanning.")
                if not details.get("chunksEmbed") or not details.get("chunksGraph"):
                    raise RuntimeError(f"Document batch {batch['name']} has no confirmed vector/graph chunk writes.")

    def reference_ontology(self):
        ns = self.state["namespaceId"]
        record = self.state.setdefault("referenceOntology", {"ontologyId": REFERENCE_ID})
        path = f"/namespaces/{ns}/ontologies/{quote(REFERENCE_ID, safe='')}"
        if not record.get("jobId"):
            turtle = (ROOT / "platform" / "singapore-support-ontology.ttl").read_bytes()
            graph = Graph().parse(data=turtle.decode(), format="turtle")
            if len(set(graph.subjects(RDF.type, OWL.Class))) < 7:
                raise ValueError("Reference ontology is missing its published support vocabulary.")
            upload = self.client.request("POST", f"/namespaces/{ns}/ontologies/upload-url", {"filename": "singapore-support-ontology.ttl", "contentType": "text/turtle", "ontologyId": REFERENCE_ID, "title": "Singapore Support Navigator reference ontology"})
            self.client.put_signed(field(upload, "uploadUrl"), turtle)
            result = unwrap(self.client.request("POST", path + "/ingest-from-s3", {"s3Key": field(upload, "s3Key"), "format": "turtle", "title": "Singapore Support Navigator reference ontology", "ontologyType": "user_created"}))
            record.update({"jobId": field(result, "jobId"), "status": result["status"], "sha256": hashlib.sha256(turtle).hexdigest()})
            self.checkpoint()
        result = unwrap(self.client.request("GET", path + "/ingest-status/" + record["jobId"]))
        record["status"] = result["status"]
        record["error"] = redact(result.get("error"))
        self.checkpoint()
        self.log("Reference ontology ingest", result["status"])
        if result["status"] == "failed":
            raise RuntimeError("Reference ontology ingest failed: " + str(redact(result.get("error"))) + ". Inspect its registration for partial writes before removing the failed registration and referenceOntology checkpoint to re-import.")
        if result["status"] != "completed":
            self.pending.append("Reference ontology")
            return False
        return True

    def inspect_proposal(self, proposal, source_id):
        turtle = field(proposal, "ontologyTurtle") or self.client.fetch_signed(field(proposal, "ontologyUrl"))
        mappings = field(proposal, "r2rmlTurtle") or self.client.fetch_signed(field(proposal, "r2rmlUrl"))
        ontology, r2rml = Graph().parse(data=turtle, format="turtle"), Graph().parse(data=mappings, format="turtle")
        classes = set(ontology.subjects(RDF.type, OWL.Class)) | set(ontology.subjects(RDF.type, RDFS.Class))
        if not classes or any(not str(c).startswith((REFERENCE_BASE, INDUCED_BASE)) for c in classes if isinstance(c, URIRef)):
            raise ValueError("Induced ontology has absent or unexpected class identifiers; inspect the proposal before accepting.")
        maps = list(r2rml.subjects(RDF.type, RR.TriplesMap))
        if len(maps) != len(SCHEMAS):
            raise ValueError("Induced R2RML did not map all three actual scanned tables.")
        map_tables = {tmap: str(r2rml.value(r2rml.value(tmap, RR.logicalTable), RR.tableName) or "").replace('"', '').split(".")[-1] for tmap in maps}
        expected_joins = {("schemes", "agency_id", "agencies", "agency_id"), ("evidence", "agency_id", "agencies", "agency_id"), ("evidence", "scheme_id", "schemes", "scheme_id")}
        actual_joins = set()
        reviewed_tables = []
        for tmap in maps:
            lt = r2rml.value(tmap, RR.logicalTable)
            table = str(r2rml.value(lt, RR.tableName) or "")
            table_name = table.replace('"', '').split(".")[-1]
            if table_name not in SCHEMAS or r2rml.value(lt, RR.sqlQuery):
                raise ValueError("R2RML contains an unexpected logical table or SQL override.")
            ds = str(r2rml.value(tmap, COA.datasourceId) or "").removeprefix("DS#")
            if ds != source_id.removeprefix("DS#"):
                raise ValueError("R2RML datasource provenance does not match the actual approved source.")
            subject_map = r2rml.value(tmap, RR.subjectMap)
            mapped_class = r2rml.value(subject_map, RR["class"])
            if mapped_class not in classes:
                raise ValueError("R2RML points to a class absent from the induced ontology.")
            template = str(r2rml.value(subject_map, RR.template) or "")
            if not template.startswith(INDUCED_BASE):
                raise ValueError("R2RML instance identifier template uses an unexpected authority.")
            pk = {"schemes": "scheme_id", "agencies": "agency_id", "evidence": "evidence_id"}[table_name]
            template_columns = [c.replace('"', '') for c in re.findall(r"\{([^}]+)\}", template)]
            if template_columns != [pk]:
                raise ValueError("R2RML subject template does not use the verified table primary key.")
            for pom in r2rml.objects(tmap, RR.predicateObjectMap):
                om = r2rml.value(pom, RR.objectMap)
                column = r2rml.value(om, RR.column)
                if column and str(column).replace('"', '') not in SCHEMAS[table_name]:
                    raise ValueError("R2RML references a column absent from the verified source CSV.")
                parent = r2rml.value(om, RR.parentTriplesMap)
                if parent is not None:
                    if parent not in map_tables:
                        raise ValueError("R2RML join points to an absent table mapping.")
                    joins = list(r2rml.objects(om, RR.joinCondition))
                    if len(joins) != 1:
                        raise ValueError("R2RML join does not match a single-column reviewed foreign key.")
                    child = str(r2rml.value(joins[0], RR.child) or "").replace('"', '')
                    parent_column = str(r2rml.value(joins[0], RR.parent) or "").replace('"', '')
                    actual_joins.add((table_name, child, map_tables[parent], parent_column))
            reviewed_tables.append({"table": table, "classUri": str(mapped_class), "datasourceId": ds})
        if {t["table"].replace('"', '').split(".")[-1] for t in reviewed_tables} != set(SCHEMAS):
            raise ValueError("R2RML tables contain duplicates or omissions.")
        if actual_joins != expected_joins:
            raise ValueError("Induced R2RML joins differ from the three reviewed public catalogue relationships.")
        report = {"reviewedAt": utc_now(), "ontologySha256": hashlib.sha256(turtle.encode()).hexdigest(), "r2rmlSha256": hashlib.sha256(mappings.encode()).hexdigest(), "classCount": len(classes), "triplesMapCount": len(maps), "tables": reviewed_tables, "validatedJoins": sorted(actual_joins), "reviewScope": "RDF syntax, class authorities, actual scanned tables/columns, source IDs, verified primary/foreign keys and catalogue provenance. No legal policy adjudication."}
        save_private(self.args.state.parent / "full-platform-proposal-review.local.json", report)
        return report

    def model(self):
        if not self.reference_ontology():
            return
        source = self.state.get("sources", {}).get("database")
        if not source or source["status"] != "APPROVED":
            self.pending.append("Approved structured source before induction")
            return
        ns = self.state["namespaceId"]
        record = self.state.setdefault("model", {})
        if record.get("status") == "failed" and self.args.retry_failed and "induction" not in self.retried:
            self.state.setdefault("failedModelAttempts", []).append(dict(record))
            self.retried.add("induction")
            record.clear()
            self.checkpoint()
        if not record.get("jobId"):
            # A lost HTTP response can leave a real job running before our local
            # checkpoint exists. Recover its server-written 1:1 proposal stub.
            proposals = self.client.paginate(f"/namespaces/{ns}/proposals")
            existing = [p for p in proposals if field(p, "ontologyId") == INDUCED_BASE and field(p.get("metadata", {}), "datasourceIds") == [source["sourceId"]] and p.get("metadata", {}).get("label") == "Published Singapore agency support catalogue" and p.get("status") not in {"failed", "rejected", "cancelled"}]
            if existing:
                existing.sort(key=lambda p: str(field(p, "createdAt", "")), reverse=True)
                record.update({"jobId": field(existing[0], "proposalId"), "status": "pending", "recoveredServerProposal": True})
            else:
                response = self.client.request("POST", f"/namespaces/{ns}/induce", {"datasource_ids": [source["sourceId"]], "ontology_uri_prefix": INDUCED_BASE, "label": "Published Singapore agency support catalogue", "strategy": "table_to_ontology", "grounding_ontology_ids": [REFERENCE_ID], "grounding_mode": "ENHANCED", "rerank_max_tokens": 3000})
                record.update({"jobId": field(response, "jobId"), "status": response.get("status", "pending"), "startedAt": utc_now()})
            self.checkpoint()
        job = self.client.request("GET", f"/namespaces/{ns}/induce/jobs/{record['jobId']}")
        record.update({"status": job["status"], "report": redact(job.get("report")), "error": redact(job.get("error"))})
        self.checkpoint()
        self.log("Actual ontology induction", job["status"])
        if job["status"] == "failed":
            raise RuntimeError("Actual induction failed: " + str(redact(job.get("error"))))
        if job["status"] != "completed":
            self.pending.append("Actual ontology induction")
            return
        if field(job.get("report") or {}, "droppedTables", []):
            raise ValueError("Induction dropped a source table; inspect its report before accepting.")
        proposal_id = field(job, "duplicateOf") or field(job, "proposalId") or field(job.get("report") or {}, "inducedOntologyId") or record["jobId"]
        record["proposalId"] = proposal_id
        path = f"/namespaces/{ns}/proposals/{proposal_id}"
        proposal = self.client.request("GET", path)
        record["proposalStatus"] = proposal["status"]
        record["proposalError"] = redact(field(proposal, "acceptError"))
        self.checkpoint()
        if proposal["status"] == "accepted" and record.get("localReview") and record.get("validation", {}).get("report", {}).get("passed"):
            record["ontologyId"] = field(proposal, "ontologyId")
            record["acceptedAt"] = record.get("acceptedAt", utc_now())
            self.checkpoint()
            self.log("Published induced ontology", "accepted")
            return
        if proposal["status"] in {"failed", "rejected", "cancelled"} or (proposal["status"] == "accept_failed" and (not self.args.retry_failed or "publication" in self.retried)):
            raise RuntimeError(f"Proposal reached {proposal['status']}: {redact(field(proposal, 'acceptError'))}")
        if proposal["status"] in {"accepting", "embeddings_sync"}:
            self.pending.append("Ontology publication/vector sync")
            return
        if not record.get("localReview"):
            record["localReview"] = self.inspect_proposal(proposal, source["sourceId"])
            self.checkpoint()
        if record.get("validation", {}).get("status") == "failed" and self.args.retry_failed and "validation" not in self.retried:
            record.setdefault("failedValidations", []).append(record.pop("validation"))
            record.pop("validationJobId", None)
            self.retried.add("validation")
            self.checkpoint()
        if not record.get("validationJobId"):
            response = self.client.request("POST", path + "/validate", {"tiers": ["tier1_blocking"]})
            record["validationJobId"] = field(response, "jobId")
            self.checkpoint()
        validation = self.client.request("GET", path + "/validate/jobs/" + record["validationJobId"])
        record["validation"] = redact(validation)
        self.checkpoint()
        if validation["status"] == "failed":
            raise RuntimeError("Proposal validation failed: " + str(redact(validation.get("error"))))
        if validation["status"] != "completed":
            self.pending.append("Platform blocking validators")
            return
        if not validation.get("report", {}).get("passed"):
            raise ValueError("Proposal has blocking validation findings; inspect the checkpoint before accepting.")
        # Re-inspect current artifacts so a changed proposal cannot reuse old review.
        current_review = self.inspect_proposal(self.client.request("GET", path), source["sourceId"])
        if current_review["ontologySha256"] != record["localReview"]["ontologySha256"] or current_review["r2rmlSha256"] != record["localReview"]["r2rmlSha256"]:
            raise ValueError("Proposal artifacts changed after review; inspect and validate again.")
        if proposal["status"] == "accepted":
            record.update({"ontologyId": field(proposal, "ontologyId"), "acceptedAt": utc_now()})
            self.checkpoint()
            return
        if proposal["status"] == "accept_failed":
            self.retried.add("publication")
        self.client.request("POST", path + "/accept", {})
        record["proposalStatus"] = "accepting"
        self.checkpoint()
        self.pending.append("Ontology publication/vector sync")

    def run(self):
        self.namespace()
        self.stage()
        deadline = time.monotonic() + self.args.wait_seconds
        while True:
            self.pending = []
            if self.args.stage in {"scan", "model", "all"}:
                self.scan()
            if self.args.stage in {"model", "all"}:
                self.model()
            self.state["pending"] = self.pending
            self.checkpoint()
            if not self.pending or time.monotonic() >= deadline:
                break
            time.sleep(min(5, max(0, deadline - time.monotonic())))
        self.log("Checkpoint", str(self.args.state))
        if self.pending:
            self.log("Pending asynchronous work; rerun to resume", "; ".join(self.pending))
            return 2
        self.log("Requested ingestion stage", "completed")
        return 0


def parser():
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("--metadata", type=Path, required=True)
    result.add_argument("--credentials", type=Path, required=True)
    result.add_argument("--state", type=Path, default=ROOT / "artifacts" / "full-platform-ingest.local.json")
    result.add_argument("--corpus", type=Path, default=ROOT / "data" / "official")
    result.add_argument("--stage", choices=("stage", "scan", "model", "all"), default="all")
    result.add_argument("--document-limit", type=int, default=6, help="Initial bounded corpus, covering all four audiences; 0 stages every document in batches of six.")
    result.add_argument("--wait-seconds", type=int, choices=range(0, 61), default=0, metavar="0..60")
    result.add_argument("--retry-failed", action="store_true", help="After diagnosing the cause, retry failed scan/induction/validator/publication jobs. Failed reference imports require inspection for partial writes first.")
    return result


def main():
    args = parser().parse_args()
    if args.document_limit < 0 or (args.document_limit and args.document_limit < 4):
        raise ValueError("Document limit must be 0 (all) or at least 4 to cover every audience.")
    return IngestRun(args).run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Ingestion stopped: {type(exc).__name__}: {redact(str(exc))}", file=sys.stderr)
        sys.exit(1)
