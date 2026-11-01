"""Tiny dev server for docs/. Run from anywhere.

    python scripts/serve.py            # default 8765
    python scripts/serve.py 8080       # custom port

Threaded, with a deep accept queue: a page load fires ~15 data fetches at
once, and Python's stock http.server (backlog 5) resets connections under that
load, which made the e2e suite flaky. tests/e2e/conftest.py uses this server.

SERVE_GZIP=1 compresses text responses the way GitHub Pages does, so load-time
measurements (scripts/uat_depth.py) reflect what a visitor actually downloads.
"""
import functools
import gzip
import http.server
import mimetypes
import os
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
DOCS = Path(__file__).resolve().parent.parent / "docs"


class Server(http.server.ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True


GZIP = os.environ.get("SERVE_GZIP") == "1"
COMPRESSIBLE = {".json", ".js", ".css", ".html", ".svg", ".txt", ".geojson"}
_gz_cache: dict = {}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep test output clean
        pass

    def do_GET(self):
        path = Path(self.translate_path(self.path.split("?", 1)[0]))
        if (GZIP and "gzip" in self.headers.get("Accept-Encoding", "") and path.suffix in COMPRESSIBLE and path.is_file()):
            key = (str(path), path.stat().st_mtime_ns)
            body = _gz_cache.get(key)
            if body is None:
                body = _gz_cache[key] = gzip.compress(path.read_bytes(), 6)
            self.send_response(200)
            self.send_header("Content-Type", (mimetypes.guess_type(str(path))[0] or "application/octet-stream") + "; charset=utf-8"
                             if path.suffix in {".json", ".js", ".css", ".html", ".txt"} else mimetypes.guess_type(str(path))[0] or "application/octet-stream")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


handler = functools.partial(QuietHandler, directory=str(DOCS))
with Server(("127.0.0.1", PORT), handler) as httpd:
    print(f"serving {DOCS} on http://127.0.0.1:{PORT}", flush=True)
    httpd.serve_forever()
