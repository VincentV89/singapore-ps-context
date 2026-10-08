"""Lambda HTTP API entrypoint and a local development HTTP runner."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from engine import InputError, SCENARIO, analyze

ROOT = Path(__file__).resolve().parent
MAX_BODY_BYTES = 16000


def response(status, body, content_type="application/json"):
    return {"statusCode": status, "headers": {"content-type": content_type + "; charset=utf-8", "cache-control": "no-store", "x-content-type-options": "nosniff"}, "body": json.dumps(body, ensure_ascii=False) if content_type == "application/json" else body}


def dispatch(method, path, body=None, query=None):
    path = path.rstrip("/") or "/"
    if method == "OPTIONS":
        return response(204, "", "text/plain")
    if method == "GET" and path == "/api/health":
        return response(200, {"status": "ok", "graph": "RDF / SPARQL", "scenario": "life-events-navigator", "synthetic": True})
    if method == "GET" and path == "/api/scenario":
        return response(200, SCENARIO)
    if method == "GET" and path == "/api/ontology":
        kind = (query or {}).get("kind", "")
        if kind in {"schema", "instances"}:
            filename = "ontology.ttl" if kind == "schema" else "instances.ttl"
            result = response(200, (ROOT / "data" / filename).read_text(), "text/turtle")
            result["headers"]["content-disposition"] = f'attachment; filename="life-events-{kind}.ttl"'
            return result
        return response(200, {"schema": (ROOT / "data" / "ontology.ttl").read_text(), "instances": (ROOT / "data" / "instances.ttl").read_text(), "format": "text/turtle", "schemaOnly": True, "provenance": "COA upstream serializer v0.3.4; fictional Life Events schema and separate synthetic instances."})
    if method == "POST" and path == "/api/analyze":
        try:
            if body is None or len(body.encode("utf-8")) > MAX_BODY_BYTES:
                raise InputError("Request body is missing or exceeds the demo size limit.")
            payload = json.loads(body, parse_constant=lambda _: (_ for _ in ()).throw(InputError("Non-finite JSON numbers are unsupported.")))
            return response(200, analyze(payload))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return response(400, {"error": "Request body must be valid JSON."})
        except InputError as exc:
            return response(400, {"error": str(exc)})
        except Exception:
            # Never expose exception values, tracebacks, credentials or SDK
            # messages in the public response.
            return response(500, {"error": "The demo could not complete this analysis. Please retry."})
    return response(404, {"error": "API route not found."})


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod", "GET")
    path = event.get("rawPath") or event.get("path", "/")
    body = event.get("body")
    if event.get("isBase64Encoded") and body:
        try:
            body = base64.b64decode(body, validate=True).decode("utf-8")
        except Exception:
            return response(400, {"error": "Request body encoding is invalid."})
    return dispatch(method, path, body, event.get("queryStringParameters") or {})


class LocalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        parts = urlsplit(self.path)
        body = None
        if self.command == "POST":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_BODY_BYTES or length < 0:
                    result = response(413, {"error": "Request exceeds the demo size limit."})
                    self.send_result(result)
                    return
                body = self.rfile.read(length).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                self.send_result(response(400, {"error": "Request body encoding is invalid."}))
                return
        self.send_result(dispatch(self.command, parts.path, body, {key: values[0] for key, values in parse_qs(parts.query).items()}))

    def send_result(self, result):
        self.send_response(result["statusCode"])
        for key, value in result["headers"].items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(result["body"].encode("utf-8"))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Life Events API listening at http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), LocalHandler).serve_forever()
