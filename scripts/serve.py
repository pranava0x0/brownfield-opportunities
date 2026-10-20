"""Tiny dev server for docs/. Run from anywhere.

    python scripts/serve.py            # default 8765
    python scripts/serve.py 8080       # custom port

Threaded, with a deep accept queue: a page load fires ~15 data fetches at
once, and Python's stock http.server (backlog 5) resets connections under that
load, which made the e2e suite flaky. tests/e2e/conftest.py uses this server.
"""
import functools
import http.server
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
DOCS = Path(__file__).resolve().parent.parent / "docs"


class Server(http.server.ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep test output clean
        pass


handler = functools.partial(QuietHandler, directory=str(DOCS))
with Server(("127.0.0.1", PORT), handler) as httpd:
    print(f"serving {DOCS} on http://127.0.0.1:{PORT}", flush=True)
    httpd.serve_forever()
