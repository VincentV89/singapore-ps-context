#!/usr/bin/env python3
"""Fetch and verify public Singapore policy sources, then export ingestion assets.

Uses only the Python standard library. Network requests retain the configured proxy
and CA trust. The seeds file is a reviewed source catalogue, not an eligibility
rules engine. Exact source excerpts are checked before publishing any export.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / "data" / "official"
DISCLAIMER = (
    "Public Singapore agency policy information, captured as dated source snapshots. "
    "This independent AWS demonstration is not a Singapore Government service. "
    "Applicant profiles are hypothetical. Programme discovery does not establish "
    "eligibility or approval; verify full criteria, current calls and application "
    "requirements with the administering agency."
)
OFFICIAL_HOSTS = {
    "www.msf.gov.sg", "www.chas.sg", "chas.moh.gov.sg", "www.moh.gov.sg",
    "www.myskillsfuture.gov.sg", "www.ecda.gov.sg", "www.moe.gov.sg",
    "www.enterprisesg.gov.sg", "www.ncss.gov.sg", "www.nac.gov.sg",
    "www.nrf.gov.sg", "www.a-star.edu.sg", "www.rgp.gov.sg",
    "oursggrants.gov.sg", "www.bizsg.gov.sg", "apply.gov.sg",
    "supportgowhere.life.gov.sg",
}


def single_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class PolicyHTMLParser(HTMLParser):
    """Extract visible policy text; prefer main, excluding navigation and scripts."""

    EXCLUDE = {"script", "style", "nav", "header", "footer", "noscript", "svg"}

    def __init__(self, main_only: bool = True):
        super().__init__(convert_charrefs=True)
        self.main_only = main_only
        self.in_main = False
        self.seen_main = False
        self.in_title = False
        self.title: list[str] = []
        self.lines: list[str] = []
        self.excluded: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "main":
            self.in_main = True
            self.seen_main = True
        if tag == "title":
            self.in_title = True
        if tag in self.EXCLUDE:
            self.excluded.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "main":
            self.in_main = False
        if tag == "title":
            self.in_title = False
        if tag in self.excluded:
            position = len(self.excluded) - 1 - self.excluded[::-1].index(tag)
            del self.excluded[position:]

    def handle_data(self, data: str) -> None:
        text = single_line(data)
        if not text:
            return
        if self.in_title:
            self.title.append(text)
        if not self.excluded and (self.in_main or not self.main_only):
            self.lines.append(text)


def extract_html(raw: bytes) -> tuple[str, str]:
    html = raw.decode("utf-8", errors="replace")
    parser = PolicyHTMLParser()
    parser.feed(html)
    if not parser.seen_main:
        parser = PolicyHTMLParser(main_only=False)
        parser.feed(html)
    return single_line(" ".join(parser.title)), "\n".join(parser.lines)


def exact_excerpt(text: str, selector: str | list[str]) -> str:
    """Select a checked verbatim sentence or start/end span after whitespace cleanup."""
    content = single_line(text)
    if not selector:
        return ""
    if isinstance(selector, str):
        quote = single_line(selector)
        if quote not in content:
            raise ValueError(f"Source sentence is missing: {quote[:100]}")
        return quote
    start, end = map(single_line, selector)
    a = content.index(start)
    b = content.index(end, a + len(start))
    return content[a:b].strip()


def check_official_url(url: str) -> None:
    parts = urlparse(url)
    if parts.scheme != "https" or parts.hostname not in OFFICIAL_HOSTS:
        raise ValueError(f"Unexpected non-official HTTPS destination: {url}")


def fetch_url(url: str) -> tuple[bytes, dict]:
    check_official_url(url)
    request = Request(url, headers={
        "User-Agent": "SingaporeSupportNavigatorDemo/1.0 (public policy source capture)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urlopen(request, timeout=40) as response:
        check_official_url(response.url)
        content_type = response.headers.get("Content-Type", "")
        if response.status != 200 or "html" not in content_type:
            raise ValueError(f"Expected policy HTML, got {response.status} {content_type}")
        raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError("Policy page exceeds the source snapshot size limit")
        metadata = {
            "requestedUrl": url, "finalUrl": response.url,
            "httpStatus": response.status, "contentType": content_type,
            "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "sourceHash": hashlib.sha256(raw).hexdigest(),
        }
    _, text = extract_html(raw)
    if len(single_line(text)) < 150 or any(
        phrase in single_line(text).lower()
        for phrase in ("verify you are human", "you need to enable javascript to run this app")
    ):
        raise ValueError("Source is an application shell or challenge page, without policy content")
    return raw, metadata


def load_seeds(root: Path) -> dict:
    return json.loads((root / "seeds.json").read_text())


def refresh(root: Path) -> None:
    seeds = load_seeds(root)
    urls = sorted({scheme["sourceUrl"] for scheme in seeds["schemes"]})
    captures: dict[str, tuple[bytes, dict]] = {}
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_url, url): url for url in urls}
        for future in concurrent.futures.as_completed(futures):
            url = futures[future]
            try:
                captures[url] = future.result()
            except Exception as error:
                errors.append({"url": url, "error": str(error)})
    # Validate all reviewed excerpts before replacing the last complete snapshot.
    for scheme in seeds["schemes"]:
        if scheme["sourceUrl"] in captures:
            _, text = extract_html(captures[scheme["sourceUrl"]][0])
            try:
                for key in ("eligibility", "benefit", "lifecycleQuote"):
                    exact_excerpt(text, scheme.get(key, ""))
            except (ValueError, IndexError) as error:
                errors.append({"scheme": scheme["id"], "url": scheme["sourceUrl"], "error": str(error)})
    if errors:
        print(json.dumps({"refreshFailed": errors, "existingSnapshotPreserved": True}, indent=2))
        raise SystemExit(1)
    (root / "raw").mkdir(exist_ok=True)
    manifest = {"schemaVersion": 1, "sources": [], "unavailableSources": seeds.get("unavailableSources", [])}
    for scheme in seeds["schemes"]:
        raw, metadata = captures[scheme["sourceUrl"]]
        path = f"raw/{scheme['id']}.html"
        (root / path).write_bytes(raw)
        manifest["sources"].append({"id": scheme["id"], "path": path, **metadata})
    (root / "sources.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    export(root)
    verify(root)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: single_line(str(row.get(key, ""))) for key in fields} for row in rows)


def export(root: Path) -> None:
    seeds = load_seeds(root)
    manifest = json.loads((root / "sources.json").read_text())
    sources = {source["id"]: source for source in manifest["sources"]}
    agencies = {agency["id"]: agency for agency in seeds["agencies"]}
    schemes, scheme_rows, evidence_rows = [], [], []
    (root / "documents").mkdir(exist_ok=True)
    (root / "structured").mkdir(exist_ok=True)
    for seed in seeds["schemes"]:
        sid = seed["id"]
        source = sources[sid]
        raw = (root / source["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sourceHash"]:
            raise ValueError(f"Source hash mismatch for {sid}")
        title, text = extract_html(raw)
        scheme = {
            **{key: seed[key] for key in ("id", "name", "persona", "categories", "summary", "applicationUrl", "status")},
            "agency": agencies[seed["agencyId"]], "sourceUrl": source["finalUrl"],
            "sourceTitle": title, "fetchedAt": source["fetchedAt"],
            "sourceHash": source["sourceHash"],
            "eligibilityText": exact_excerpt(text, seed["eligibility"]),
            "benefitText": exact_excerpt(text, seed["benefit"]),
            "lifecycleText": exact_excerpt(text, seed.get("lifecycleQuote", "")),
            "documents": [f"{sid}.md"], "verified": True,
        }
        check_official_url(scheme["applicationUrl"])
        schemes.append(scheme)
        scheme_rows.append({
            "scheme_id": sid, "scheme_name": scheme["name"], "persona": scheme["persona"],
            "categories": "|".join(scheme["categories"]), "agency_id": seed["agencyId"],
            "status": scheme["status"], "summary": scheme["summary"],
            "eligibility_text": scheme["eligibilityText"], "benefit_text": scheme["benefitText"],
            "application_url": scheme["applicationUrl"], "source_url": scheme["sourceUrl"],
            "source_title": title, "fetched_at": scheme["fetchedAt"], "source_hash": scheme["sourceHash"],
        })
        for kind in ("eligibility", "benefit", "lifecycle"):
            quote = scheme[f"{kind}Text"]
            if quote:
                evidence_rows.append({
                    "evidence_id": f"{sid}-{kind}", "scheme_id": sid, "agency_id": seed["agencyId"],
                    "evidence_type": kind, "excerpt": quote, "source_url": scheme["sourceUrl"],
                    "source_title": title, "fetched_at": scheme["fetchedAt"], "source_hash": scheme["sourceHash"],
                })
        document = (
            f"# {scheme['name']}\n\n"
            f"Agency: {scheme['agency']['name']} ({scheme['agency']['abbreviation']})\n\n"
            f"Audience: {scheme['persona']}\n\n"
            f"Source: [{title}]({scheme['sourceUrl']})\n\n"
            f"Captured at: {scheme['fetchedAt']}\n\n"
            f"Source snapshot SHA-256: {scheme['sourceHash']}\n\n"
            f"Application information: {scheme['applicationUrl']}\n\n"
            f"Demonstration note: {DISCLAIMER}\n\n"
            f"## Curated programme summary\n\n{scheme['summary']}\n\n"
            f"## Verbatim eligibility or applicant scope excerpt\n\n"
            f"{scheme['eligibilityText'] or 'No complete eligibility criteria are published on this captured overview page. Consult the agency’s detailed call or programme guidance.'}\n\n"
            f"## Verbatim support excerpt\n\n{scheme['benefitText']}\n\n"
        )
        if scheme["lifecycleText"]:
            document += f"## Verbatim programme lifecycle update\n\n{scheme['lifecycleText']}\n\n"
        document += f"## Extracted public source text\n\n{text}\n"
        (root / "documents" / f"{sid}.md").write_text(document)
    catalogue = {
        "schemaVersion": 1, "fetchedAt": max(scheme["fetchedAt"] for scheme in schemes),
        "disclaimer": DISCLAIMER, "schemes": schemes,
    }
    (root / "catalogue.json").write_text(json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n")
    write_csv(root / "structured" / "schemes.csv", scheme_rows, list(scheme_rows[0]))
    write_csv(root / "structured" / "agencies.csv", [
        {"agency_id": agency["id"], "agency_name": agency["name"], "abbreviation": agency["abbreviation"], "agency_url": agency["url"]}
        for agency in seeds["agencies"]
    ], ["agency_id", "agency_name", "abbreviation", "agency_url"])
    write_csv(root / "structured" / "evidence.csv", evidence_rows, list(evidence_rows[0]))


def verify(root: Path) -> None:
    catalogue = json.loads((root / "catalogue.json").read_text())
    ids = set()
    agencies = set()
    for scheme in catalogue["schemes"]:
        sid = scheme["id"]
        if sid in ids or not re.fullmatch(r"[a-z][a-z0-9-]+", sid):
            raise ValueError(f"Duplicate or malformed scheme ID: {sid}")
        ids.add(sid)
        agencies.add(scheme["agency"]["id"])
        raw = (root / "raw" / f"{sid}.html").read_bytes()
        if hashlib.sha256(raw).hexdigest() != scheme["sourceHash"] or scheme["verified"] is not True:
            raise ValueError(f"Unverified snapshot: {sid}")
        _, text = extract_html(raw)
        for key in ("eligibilityText", "benefitText", "lifecycleText"):
            if scheme[key] and scheme[key] not in single_line(text):
                raise ValueError(f"Unmatched source excerpt: {sid}/{key}")
        check_official_url(scheme["sourceUrl"])
        check_official_url(scheme["applicationUrl"])
        if not (root / "documents" / f"{sid}.md").is_file():
            raise ValueError(f"Missing policy document: {sid}")
    for table in ("schemes", "agencies", "evidence"):
        with (root / "structured" / f"{table}.csv").open(newline="") as handle:
            for row in csv.DictReader(handle):
                if any("\n" in value or "\r" in value for value in row.values()):
                    raise ValueError(f"Multiline CSV value in {table}; Athena CSV does not support it")
                if "scheme_id" in row and row["scheme_id"] not in ids:
                    raise ValueError(f"Unknown scheme foreign key in {table}")
                if "agency_id" in row and row["agency_id"] not in agencies:
                    raise ValueError(f"Unknown agency foreign key in {table}")
    print(json.dumps({
        "verifiedSchemes": len(ids), "verifiedAgencies": len(agencies),
        "personas": sorted({scheme["persona"] for scheme in catalogue["schemes"]}),
        "fetchedAt": catalogue["fetchedAt"],
    }))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["refresh", "export", "verify"])
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    {"refresh": refresh, "export": export, "verify": verify}[args.command](args.root)


if __name__ == "__main__":
    main()
