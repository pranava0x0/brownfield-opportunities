#!/usr/bin/env python3
"""Re-check the links a plain HTTP client could not judge, with a real browser engine.

`audit_tabs.py citations` marks HTTP 403/429/503 as INCONCLUSIVE because bot
protection answers a script differently from a person. That leaves the very
links most likely to be stale unjudged: nrc.gov reorganised its site and the
old COL/ESP/advanced-reactor pages now show "Page not found", but a script only
ever saw a 403. This loads each one in headless Chromium and reads the page.

Verdicts: OK (loaded, title is not an error page), DEAD (HTTP 4xx/5xx for the page, or a
"not found" title/heading), BLOCKED (still refused: judge by hand), ERROR.

Usage:
  .venv/bin/python scripts/check_links_browser.py                    # INCONCLUSIVE rows of audit-network.json
  .venv/bin/python scripts/check_links_browser.py --urls URL [URL ...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data" / "validation" / "audit-network.json"
OUT = ROOT / "data" / "validation" / "browser-links.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
NOT_FOUND = re.compile(r"page not found|\\b404\\b|not found|no longer available|has been moved|doesn.t exist", re.I)


def _went_to_homepage(requested: str, final: str) -> bool:
    from urllib.parse import urlparse
    r, f = urlparse(requested), urlparse(final)
    return r.path.strip("/") != "" and f.path.strip("/") == ""


def judge(page, url: str) -> dict:
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(800)
        status = resp.status if resp else None
        title = (page.title() or "")[:120]
        h1 = (page.evaluate("document.querySelector('h1')?.textContent || ''") or "").strip()[:120]
        final = page.url
        if status and status >= 400 and status not in (401, 403, 405, 429, 503):
            verdict = "DEAD"
        elif NOT_FOUND.search(title) or NOT_FOUND.search(h1):
            verdict = "DEAD"
        elif _went_to_homepage(url, final):
            verdict = "DEAD"          # a retired path redirected to the site root: a soft 404
        elif status in (401, 403, 405, 429, 503):
            verdict = "BLOCKED"
        else:
            verdict = "OK"
        return {"url": url, "verdict": verdict, "status": status, "title": title, "h1": h1, "final_url": final}
    except Exception as exc:  # noqa: BLE001 - a failed load is a verdict, not a crash
        return {"url": url, "verdict": "ERROR", "status": None, "title": "", "h1": "", "final_url": url, "error": f"{type(exc).__name__}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--urls", nargs="*")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    if args.urls:
        urls = args.urls
        owners = {}
    else:
        rows = [r for r in json.loads(AUDIT.read_text()) if r["check"] == "citations" and r["status"] == "INCONCLUSIVE"]
        urls = list(dict.fromkeys(r["field"] for r in rows))
        owners = {r["field"]: r["id"] for r in rows}
    out = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        for u in urls:
            r = judge(page, u)
            r["owner"] = owners.get(u)
            out.append(r)
            print(f"{r['verdict']:8} {u[:100]}  {r['title'][:50]}")
            time.sleep(1.5)
        browser.close()
    args.out.write_text(json.dumps(out, indent=1))
    from collections import Counter
    print(dict(Counter(r["verdict"] for r in out)))
    return 1 if any(r["verdict"] == "DEAD" for r in out) else 0


if __name__ == "__main__":
    sys.exit(main())
