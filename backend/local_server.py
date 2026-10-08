"""Development runner. API authentication is provided by Cognito in AWS."""
import os
from http.server import ThreadingHTTPServer
from app import LocalHandler

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Life Events API listening at http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), LocalHandler).serve_forever()
