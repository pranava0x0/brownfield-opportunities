"""Tiny dev server for local preview of docs/. Run from repo root.

    python scripts/serve.py            # default 8765
    python scripts/serve.py 8080       # custom port
"""
import http.server
import os
import socketserver
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
DOCS = Path(__file__).resolve().parent.parent / "docs"

os.chdir(DOCS)
with socketserver.TCPServer(("127.0.0.1", PORT), http.server.SimpleHTTPRequestHandler) as httpd:
    print(f"serving {DOCS} on http://127.0.0.1:{PORT}")
    httpd.serve_forever()
