#!/usr/bin/env python3
"""Read-only HTTPS checks for the deployed site, strict CORS and API authentication."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def request(url, headers=None, method="GET"):
    req = Request(url, headers=headers or {}, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.headers, response.read()
    except HTTPError as response:
        return response.code, response.headers, response.read()


def check(condition, description):
    if not condition:
        raise RuntimeError(description)
    print(f"PASS {description}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", type=Path, default=ROOT / "deployment.json")
    args = parser.parse_args()
    metadata = json.loads(args.deployment.read_text())
    result = metadata["outputs"]
    site = result["WebsiteUrl"]
    status, headers, body = request(site)
    check(status == 200 and b'<div id="root"' in body, "Website loads through CloudFront")
    csp = headers.get("content-security-policy", "")
    check(result["ApiUrl"] in csp and result["CognitoDomain"] in csp and "script-src 'self';" in csp, "CSP restricts scripts and permits the exact API/Cognito endpoints")
    check(bool(headers.get("strict-transport-security")), "HSTS is enabled")
    status, headers, body = request(site + "/config.json")
    config = json.loads(body)
    check(status == 200 and config["localPreview"] is False and config["apiUrl"] == result["ApiUrl"], "Deployed config requires Cognito and targets the deployed API")
    check("no-store" in headers.get("cache-control", ""), "Runtime config is not cached")
    status, _, body = request(site + "/auth/callback")
    check(status == 200 and b'<div id="root"' in body, "OAuth callback route resolves to the SPA")
    status, _, _ = request(site + "/assets/does-not-exist.js")
    check(status in {403, 404}, "Missing JavaScript assets retain an error response")
    api = result["ApiUrl"] + "/api/health"
    status, _, _ = request(api)
    check(status == 401, "Unauthenticated API request is rejected")
    status, _, _ = request(api, {"Authorization": "Bearer fabricated.invalid.signature"})
    check(status == 401, "Fabricated bearer token is rejected")
    preflight = {"Origin": site, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"}
    status, headers, _ = request(api, preflight, method="OPTIONS")
    check(status in {200, 204} and headers.get("access-control-allow-origin") == site, "CORS accepts the deployed frontend origin")
    preflight["Origin"] = "https://untrusted.invalid"
    _, headers, _ = request(api, preflight, method="OPTIONS")
    check(not headers.get("access-control-allow-origin"), "CORS rejects other origins")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Deployment check failed: {exc}", file=sys.stderr)
        sys.exit(1)
