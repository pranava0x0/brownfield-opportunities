#!/usr/bin/env python3
"""UAT harness: clicks to reach each leaf interaction, and load performance, per viewport.

For every task below the page is loaded fresh, then the listed clicks are made
in order. Reported per task and viewport: clicks needed, milliseconds from the
first click to the leaf being visible, and whether the leaf was reached. A task
over MAX_CLICKS, or not reached, is flagged.

Load performance per viewport (mobile and tablet run with CPU and network
throttling; desktop runs unthrottled):
  app ready (`__APP_READY__`), DOMContentLoaded, load, LCP, long-task time,
  request count, bytes on the wire (the dev server gzips like GitHub Pages), DOM node count.

Usage:
  .venv/bin/python scripts/uat_depth.py                 # all tasks, all viewports
  .venv/bin/python scripts/uat_depth.py --viewport mobile --task nuclear
  .venv/bin/python scripts/uat_depth.py --json data/validation/uat-report.json
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MAX_CLICKS = 4          # a leaf deeper than this is flagged
READY_BUDGET_MS = {"desktop": 4000, "tablet": 9000, "mobile": 12000}

VIEWPORTS = {
    "mobile": {"size": {"width": 390, "height": 844}, "mobile": True, "cpu": 4, "net": (1.6 * 1024 * 1024 / 8, 150)},
    "tablet": {"size": {"width": 820, "height": 1180}, "mobile": True, "cpu": 2, "net": (4 * 1024 * 1024 / 8, 70)},
    "desktop": {"size": {"width": 1440, "height": 900}, "mobile": False, "cpu": 1, "net": None},
}

# Each task: ordered click selectors, then the selector that proves the leaf is on screen.
TASKS: dict[str, dict[str, Any]] = {
    "screens-top-dc": {"what": "See the best data-center sites and the checks each meets",
                       "clicks": [], "leaf": "#candidates-table tbody tr .screen-score"},
    "screens-switch-use": {"what": "Switch to the nickel-refinery ranking",
                           "clicks": ['[data-cand-lens="nickel"]'], "leaf": '[data-cand-lens="nickel"].active'},
    "screens-cited-rule": {"what": "Read the cited source behind a ranking rule",
                           "clicks": [], "leaf": "#screen-method .method-list a[href^='https://']"},
    "screens-site-evidence": {"what": "Open a ranked site's evidence and its verify-on-map link",
                              "clicks": ["#candidates-table tbody tr .site-evidence-open"], "leaf": ".verify-map-link a"},
    "nuclear-rank": {"what": "See installations ranked for a large reactor",
                     "clicks": ["#tab-ap1000"], "leaf": ".ap1000-row .screen-score"},
    "nuclear-source": {"what": "Open one installation's evidence and reach a cited source",
                       "clicks": ["#tab-ap1000", ".ap1000-expand", ".ap1000-detail:not([hidden]) .evidence-category summary"],
                       "leaf": ".ap1000-detail:not([hidden]) .evidence-category[open] a[href^='https://']"},
    "nuclear-verify": {"what": "Reach the verify-on-map link for an installation",
                       "clicks": ["#tab-ap1000", ".ap1000-expand"], "leaf": ".ap1000-detail:not([hidden]) .verify-map-link a"},
    "nuclear-other-class": {"what": "Re-rank for a small modular reactor and open a row",
                            "clicks": ["#tab-ap1000", '[data-reactor-class="smr"]', ".ap1000-expand"], "leaf": ".ap1000-detail:not([hidden])"},
    "coal-rank": {"what": "See coal plants ranked for reuse", "clicks": ["#tab-coal"], "leaf": ".coal-ranked-table tbody tr .screen-score"},
    "coal-verify": {"what": "Reach the map that re-measures a coal plant's grid distance", "clicks": ["#tab-coal"],
                    "leaf": ".coal-ranked-table tbody tr a[href^='verify.html']"},
    "retired-rank": {"what": "See retired industrial sites ranked", "clicks": ["#tab-retired"], "leaf": ".retired-table tbody tr .screen-score"},
    "retired-verify": {"what": "Reach the EPA record and the verify map for a retired facility", "clicks": ["#tab-retired"],
                       "leaf": ".retired-table tbody tr a[href^='verify.html']"},
    "doe-fit-matrix": {"what": "Read why a DOE land unit fits or fails a facility type",
                       "clicks": ["#tab-hanford", ".doe-fit-cell-btn"], "leaf": ".doe-fit-reason, .doe-fit-reasoning"},
    "doe-switch-site": {"what": "Switch to another DOE site and open a unit",
                        "clicks": ["#tab-hanford", '.doe-pill[data-doe-site="paducah"]', ".doe-parcel-card"], "leaf": "#doe-drawer:not([hidden])"},
    "methods-sources": {"what": "Find the data sources and methods", "clicks": ["#tab-about"], "leaf": "#view-about .about-wrap"},
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server() -> tuple[subprocess.Popen, str]:
    port = free_port()
    import os
    proc = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "serve.py"), str(port)], cwd=str(DOCS),
                            env={**os.environ, "SERVE_GZIP": "1"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/index.html", timeout=1).read()
            return proc, url
        except Exception:  # noqa: BLE001 - server not up yet
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("server did not start")


def new_page(browser, name: str):
    v = VIEWPORTS[name]
    ctx = browser.new_context(viewport=v["size"], is_mobile=v["mobile"], has_touch=v["mobile"], device_scale_factor=2 if v["mobile"] else 1)
    page = ctx.new_page()
    if v["cpu"] > 1 or v["net"]:
        cdp = ctx.new_cdp_session(page)
        if v["cpu"] > 1:
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": v["cpu"]})
        if v["net"]:
            cdp.send("Network.enable")
            cdp.send("Network.emulateNetworkConditions", {"offline": False, "downloadThroughput": v["net"][0],
                                                          "uploadThroughput": v["net"][0] / 2, "latency": v["net"][1]})
    page.add_init_script("""
      window.__lt = 0; window.__lcp = 0;
      try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt += e.duration; }).observe({type: 'longtask', buffered: true}); } catch (e) {}
      try { new PerformanceObserver(l => { const x = l.getEntries(); window.__lcp = x[x.length - 1].startTime; }).observe({type: 'largest-contentful-paint', buffered: true}); } catch (e) {}
    """)
    return ctx, page


def measure_load(page: Page, base: str, viewport: str) -> dict[str, Any]:
    t0 = time.time()
    page.goto(f"{base}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=120_000)
    ready_ms = round((time.time() - t0) * 1000)
    data = page.evaluate("""() => {
      const nav = performance.getEntriesByType('navigation')[0];
      const res = performance.getEntriesByType('resource');
      return {dcl: Math.round(nav.domContentLoadedEventEnd), load: Math.round(nav.loadEventEnd),
        lcp: Math.round(window.__lcp), longTaskMs: Math.round(window.__lt), requests: res.length + 1,
        rawBytes: res.reduce((a, r) => a + (r.decodedBodySize || 0), 0) + (nav.decodedBodySize || 0),
        wireBytes: res.reduce((a, r) => a + (r.encodedBodySize || 0), 0) + (nav.encodedBodySize || 0),
        urls: res.map(r => r.name), nodes: document.querySelectorAll('*').length};
    }""")
    data.pop("urls")
    data.update(readyMs=ready_ms, readyBudgetMs=READY_BUDGET_MS[viewport],
                overBudget=ready_ms > READY_BUDGET_MS[viewport])
    return data


def run_task(page: Page, base: str, name: str, task: dict) -> dict[str, Any]:
    page.goto(f"{base}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=120_000)
    page.wait_for_selector("#candidates-table tbody tr", timeout=60_000)
    start = time.time()
    clicks = 0
    try:
        for sel in task["clicks"]:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=30_000)
            loc.scroll_into_view_if_needed()
            loc.click()
            clicks += 1
        page.locator(task["leaf"]).first.wait_for(state="visible", timeout=30_000)
        reached, err = True, None
    except Exception as exc:  # noqa: BLE001 - a failed task is a finding, not a crash
        reached, err = False, f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}"
    ms = round((time.time() - start) * 1000)
    return {"task": name, "what": task["what"], "clicks": clicks, "ms": ms, "reached": reached, "error": err,
            "tooDeep": clicks > MAX_CLICKS}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--viewport", choices=list(VIEWPORTS), action="append")
    ap.add_argument("--task", action="append", help="Task name prefix to run (repeatable).")
    ap.add_argument("--json", type=Path, default=ROOT / "data" / "validation" / "uat-report.json")
    args = ap.parse_args()
    names = args.viewport or list(VIEWPORTS)
    tasks = {k: v for k, v in TASKS.items() if not args.task or any(k.startswith(t) for t in args.task)}
    if not tasks:
        print(f"no task matches {args.task}; known: {', '.join(TASKS)}", file=sys.stderr)
        return 2
    proc, base = start_server()
    report: dict[str, Any] = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "max_clicks": MAX_CLICKS, "viewports": {}}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for vp in names:
                ctx, page = new_page(browser, vp)
                load = measure_load(page, base, vp)
                results = []
                for name, task in tasks.items():
                    r = run_task(page, base, name, task)
                    results.append(r)
                    flag = "" if r["reached"] and not r["tooDeep"] else "  <-- " + ("NOT REACHED " + str(r["error"]) if not r["reached"] else "too deep")
                    print(f"{vp:8} {name:24} {r['clicks']} click(s) {r['ms']:>6} ms{flag}")
                report["viewports"][vp] = {"load": load, "tasks": results}
                print(f"{vp:8} LOAD ready {load['readyMs']} ms (budget {load['readyBudgetMs']}), LCP {load['lcp']} ms, long tasks {load['longTaskMs']} ms, "
                      f"{load['requests']} requests, {load['wireBytes'] / 1e6:.1f} MB on the wire ({load['rawBytes'] / 1e6:.1f} MB decoded), {load['nodes']} DOM nodes")
                ctx.close()
            browser.close()
    finally:
        proc.terminate()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=1))
    bad = [(vp, t["task"]) for vp, d in report["viewports"].items() for t in d["tasks"] if not t["reached"] or t["tooDeep"]]
    bad += [(vp, "load-budget") for vp, d in report["viewports"].items() if d["load"]["overBudget"]]
    print(f"\n{len(bad)} problem(s): {bad}" if bad else "\nall tasks reached within budget")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
