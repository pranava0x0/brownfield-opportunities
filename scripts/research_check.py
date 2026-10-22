#!/usr/bin/env python3
"""Script-first change detection for the daily site-research routine.

The routine used to start a model session that searched the web for every site
whether or not anything had changed (~1.7M weighted tokens a run). This script
does the looking; the model is only started when the report says CHANGES.

For each site due for work it reads two public sources and compares the result
URLs to what it saw last time (`.cache/research_check/state.json`, gitignored):

  federalregister.gov  full-text API, quoted site name, newest first
  Bing News RSS        quoted site name (links decoded from the apiclick redirect)

It also reads the rolling PR's unanswered review comments (`routine_ctl.py comments`).

Exit status (and the last line, `STATUS: ...`):
  0   no changes      every source was read and nothing is new
  10  changes         the report lists exactly what the model has to look at
  2   unread          nothing new found, but at least one source failed to load:
                      this is NOT "no changes"; nothing was marked as seen

A fetch failure is always "unread", never "no changes". A source that failed is
not marked seen, so its results still show as new on the next run.

Usage (after `routine_ctl.py sync`):
  research_check.py --root "$WT" [--out DIR] [--max-sites 2] [--max-dossier-checks 8]
  research_check.py ack SITE_ID ...     mark a site's reported leads as handled
"""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import importlib.util
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

SCRIPT_DIR = Path(__file__).resolve().parent
MAIN = SCRIPT_DIR.parent
STATE_PATH = MAIN / ".cache" / "research_check" / "state.json"
USER_AGENT = "brownfield-opportunities research_check (+https://github.com/pranava0x0/brownfield-opportunities)"
HOST_DELAY_S = 1.5
TIMEOUT_S = 20
FR_URL = "https://www.federalregister.gov/api/v1/documents.json"
BING_URL = "https://www.bing.com/news/search"
SOURCES = ("federalregister", "bing-news")
STALE_ESCALATE_DAYS = 45      # overdue this long with no leads: send for a full model review anyway
MAX_LEADS_PER_SOURCE = 15
MAX_LEADS_SHOWN = 8           # per site in the report; the rest are counted
FIRST_WINDOW_DAYS = 365       # lookback for a site with no dossier

STATUS_NO_CHANGES, STATUS_CHANGES, STATUS_UNREAD = "no-changes", "changes", "unread"
EXIT = {STATUS_NO_CHANGES: 0, STATUS_CHANGES: 10, STATUS_UNREAD: 2}

Fetch = Callable[[str], str]


# ---- fetching -------------------------------------------------------------

_last_hit: dict[str, float] = {}


def http_fetch(url: str) -> str:
    """GET with an informative User-Agent and a 1.5 s floor between hits to one host."""
    host = urllib.parse.urlsplit(url).netloc
    wait = HOST_DELAY_S - (time.monotonic() - _last_hit.get(host, -1e9))
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return resp.read().decode("utf-8", "replace")


# ---- names and parsing ----------------------------------------------------

GENERIC = {"the", "and", "of", "site", "area", "inc", "co", "corp", "company", "llc"}


def search_name(raw: str) -> str:
    """Corpus name -> the phrase to search: drop '(USARMY)' codes, keep the first '/' part."""
    name = re.sub(r"\([^)]*\)", " ", raw or "")
    name = name.split("/")[0]
    name = re.sub(r"\bRES\.?$", "Reservation", name.strip(), flags=re.I)
    return re.sub(r"\s+", " ", name).strip().title()


def tokens(phrase: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", phrase.lower()) if len(t) > 2 and t not in GENERIC]


def mentions(phrase: str, text: str) -> bool:
    """True when most distinctive words of the phrase occur in the text."""
    want = tokens(phrase)
    if not want:
        return False
    low = text.lower()
    hits = sum(t in low for t in want)
    return hits >= max(1, round(0.7 * len(want)))


def parse_federal_register(body: str) -> list[dict]:
    data = json.loads(body)
    if "results" not in data:
        if data.get("count") == 0:       # the API omits `results` entirely when nothing matches
            return []
        raise ValueError("Federal Register response has neither 'results' nor count 0")
    return [{"url": r["html_url"], "title": r.get("title", ""), "date": r.get("publication_date"),
             "source": "federalregister"}
            for r in data["results"] if r.get("html_url")][:MAX_LEADS_PER_SOURCE]


def _real_url(link: str) -> str:
    """Bing wraps results in /news/apiclick?...&url=<real>; return the real URL."""
    qs = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)
    return qs["url"][0] if qs.get("url") else link


def parse_bing_rss(body: str, phrase: str) -> list[dict]:
    root = ET.fromstring(body)
    if root.find("channel") is None:
        raise ValueError("Bing response is not an RSS channel")
    leads = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        desc = item.findtext("description") or ""
        link = _real_url((item.findtext("link") or "").strip())
        if not link.startswith("https://") or not mentions(phrase, f"{title} {desc}"):
            continue
        pub = item.findtext("pubDate")
        date = None
        if pub:
            try:
                date = email.utils.parsedate_to_datetime(pub).date().isoformat()
            except (TypeError, ValueError):
                date = None
        leads.append({"url": link, "title": title, "date": date, "source": "bing-news"})
    return leads[:MAX_LEADS_PER_SOURCE]


def fr_url(phrase: str, since: str) -> str:
    q = [("conditions[term]", f'"{phrase}"'), ("conditions[publication_date][gte]", since),
         ("order", "newest"), ("per_page", str(MAX_LEADS_PER_SOURCE))]
    return FR_URL + "?" + urllib.parse.urlencode(q)


def bing_url(phrase: str) -> str:
    return BING_URL + "?" + urllib.parse.urlencode({"format": "rss", "q": f'"{phrase}"'})


# ---- state ----------------------------------------------------------------

def load_state(path: Path = STATE_PATH) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"sites": {}}


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    tmp.replace(path)


def ack(state: dict, site_ids: list[str]) -> list[str]:
    done = []
    for sid in site_ids:
        s = state["sites"].get(sid)
        if s:
            for url, date in s.get("pending", {}).items():
                s.setdefault("seen", {})[url] = date
            s["pending"] = {}
            done.append(sid)
    return done


# ---- the per-site check ---------------------------------------------------

def window_start(dossier: dict | None, today: dt.date) -> str:
    if dossier and dossier.get("researched_at"):
        return dossier["researched_at"][:10]
    return (today - dt.timedelta(days=FIRST_WINDOW_DAYS)).isoformat()


def check_site(site: dict, dossier: dict | None, state: dict, fetch: Fetch, today: dt.date) -> dict:
    """Read both sources for one site. Returns {new, read, unread, ...}; updates state in place.

    A source that fails to load is recorded as unread and contributes nothing to `seen`.
    """
    sid = site["id"]
    first_look = sid not in state["sites"]
    st = state["sites"].setdefault(sid, {"seen": {}, "pending": {}, "unread_streak": 0})
    phrase = search_name(site.get("name", ""))
    since = window_start(dossier, today)
    fetched: list[dict] = []
    read, unread = [], []
    jobs = {
        "federalregister": (fr_url(phrase, since), lambda b: parse_federal_register(b)),
        "bing-news": (bing_url(phrase), lambda b: parse_bing_rss(b, phrase)),
    }
    for source, (url, parse) in jobs.items():
        try:
            fetched += parse(fetch(url))
            read.append(source)
        except Exception as exc:  # any failure to load or parse is "unread", reported by name
            unread.append(f"{source}: {type(exc).__name__}: {str(exc)[:120]}")
    # Bing's pubDate is unreliable (MSN reposts of 2020 stories carry today's date), so for a
    # dossier site the first look only records what Bing already shows; later runs report arrivals.
    baseline_only = lambda l: first_look and dossier is not None and l["source"] == "bing-news"
    new = [l for l in fetched
           if l["url"] not in st["seen"] and not baseline_only(l)
           and (l["date"] is None or l["date"] > since)]
    # Everything fetched came from a source that loaded, so its non-new results are safe
    # to remember even when the other source failed. Skipping that on a failed first look
    # would lose the Bing baseline, and the next run would report old reposts as new.
    for l in fetched:
        if l not in new:
            st["seen"][l["url"]] = l["date"]
    st["unread_streak"] = 0 if not unread else st.get("unread_streak", 0) + 1
    for l in new:
        st["pending"][l["url"]] = l["date"]    # stays reported until `ack`
    st["last_checked"] = today.isoformat()
    return {"id": sid, "name": site.get("name", ""), "phrase": phrase, "since": since,
            "new": sorted(new, key=lambda l: l["date"] or "", reverse=True),
            "read": read, "unread": unread, "streak": st["unread_streak"]}


# ---- candidate selection --------------------------------------------------

def load_module(root: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, root / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def corpus_sites(root: Path, rq, ids: set[str]) -> dict[str, dict]:
    found = {}
    for fname in rq.PROGRAM_FILES:
        for s in json.loads((root / "docs" / "data" / fname).read_text())["sites"]:
            if s["id"] in ids:
                found[s["id"]] = s
    return found


def pick_candidates(root: Path, state: dict, today: dt.date, max_dossier_checks: int, baseline_n: int):
    """Return (dossier_checks, baseline_rows, dossiers) for this run."""
    rq = load_module(root, "research_queue")
    _, _, rows = rq.read_table((root / "backlog.md").read_text())
    dossiers = rq.dossiers()
    overdue = [sid for sid, d in dossiers.items() if (d.get("next_review") or "9999") <= today.isoformat()]
    overdue.sort(key=lambda sid: (state["sites"].get(sid, {}).get("last_checked", ""), dossiers[sid]["next_review"]))
    # Sites with leads left over from an earlier run come back first, whatever their rank.
    overdue.sort(key=lambda sid: not state["sites"].get(sid, {}).get("pending"))
    checks = overdue[:max_dossier_checks]
    baseline = [r for r in rows if r["Status"] in ("queued", "retry") and r["Site id"] not in dossiers][:baseline_n]
    # A queued/retry row that already has a dossier is a re-check; treat it as an overdue one.
    for r in rows:
        if r["Status"] in ("queued", "retry") and r["Site id"] in dossiers and r["Site id"] not in checks:
            checks.append(r["Site id"])
    ids = set(checks) | {r["Site id"] for r in baseline}
    return checks, baseline, dossiers, corpus_sites(root, rq, ids)


def pr_comments(main: Path = MAIN) -> tuple[list[dict] | None, str]:
    """Unanswered PR review comments, or (None, reason) if they could not be read."""
    try:
        out = subprocess.run([sys.executable, str(main / "scripts" / "routine_ctl.py"), "comments"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{type(exc).__name__}"
    if out.returncode:
        return None, (out.stderr.strip().splitlines() or ["routine_ctl comments failed"])[-1][:160]
    return json.loads(out.stdout or "[]"), ""


# ---- the run --------------------------------------------------------------

def run(root: Path, fetch: Fetch, state: dict, today: dt.date, *, max_sites: int = 2,
        max_dossier_checks: int = 8, baseline_per_run: int = 2,
        comments: tuple[list[dict] | None, str] | None = None) -> dict:
    checks, baseline, dossiers, sites = pick_candidates(root, state, today, max_dossier_checks, baseline_per_run)
    results, skipped = [], []
    for sid in checks + [r["Site id"] for r in baseline]:
        if sid not in sites:
            skipped.append(f"{sid}: not in the corpus")
            continue
        results.append(check_site(sites[sid], dossiers.get(sid), state, fetch, today))
    by_id = {r["id"]: r for r in results}

    work, quiet = [], []
    for sid in checks:
        r = by_id.get(sid)
        if not r:
            continue
        d = dossiers[sid]
        days_over = (today - dt.date.fromisoformat(d["next_review"])).days
        if r["new"]:
            work.append({**r, "why": f"{len(r['new'])} new lead(s) since {r['since']}; review overdue {days_over}d"})
        elif days_over >= STALE_ESCALATE_DAYS and not r["unread"]:
            work.append({**r, "why": f"no new leads, but review overdue {days_over}d (>= {STALE_ESCALATE_DAYS}): full review"})
        elif not r["unread"]:
            quiet.append(r)
    work.sort(key=lambda w: (not w["new"], -len(w["new"])))
    for row in baseline:
        r = by_id.get(row["Site id"])
        if r:
            work.append({**r, "why": f"never researched ({row['Status']}): {row['Why queued'][:140]}", "baseline": True})
    deferred = work[max_sites:]
    work = work[:max_sites]

    sources_planned = 2 * len(results)
    sources_read = sum(len(r["read"]) for r in results)
    unread = [f"{r['id']} {u}" for r in results for u in r["unread"]]
    cm, cm_err = comments if comments is not None else (None, "not requested")
    if comments is not None:
        sources_planned += 1
        if cm is None:
            unread.append(f"PR comments: {cm_err}")
        else:
            sources_read += 1
    pr_work = bool(cm)
    if work or pr_work or deferred:
        status = STATUS_CHANGES
    elif unread:
        status = STATUS_UNREAD
    else:
        status = STATUS_NO_CHANGES
    return {"date": today.isoformat(), "status": status, "work": work, "deferred": deferred,
            "quiet": quiet, "comments": cm or [], "unread": unread, "skipped": skipped,
            "sources_read": sources_read, "sources_planned": sources_planned,
            "sites_checked": len(results), "unread_streaks": {r["id"]: r["streak"] for r in results if r["streak"] >= 3}}


def render(res: dict) -> str:
    out = [f"research_check {res['date']}: read {res['sources_read']} of {res['sources_planned']} sources "
           f"({res['sites_checked']} sites + PR comments)"]
    if res["unread"]:
        out.append(f"UNREAD ({len(res['unread'])}) - these sources were NOT checked:")
        out += [f"  - {u}" for u in res["unread"]]
    for sid, n in res["unread_streaks"].items():
        out.append(f"  ! {sid} unread {n} runs in a row")
    if res["skipped"]:
        out += [f"skipped: {s}" for s in res["skipped"]]
    if res["comments"]:
        out.append(f"PR: {len(res['comments'])} unanswered review comment(s): run routine_ctl.py comments")
    for w in res["work"]:
        out.append(f"SITE {w['id']} {w['name']}: {w['why']}")
        for l in w["new"][:MAX_LEADS_SHOWN]:
            out.append(f"  + {l['date'] or 'undated'} [{l['source']}] {l['title'][:110]} <{l['url']}>")
        if len(w["new"]) > MAX_LEADS_SHOWN:
            out.append(f"  (+{len(w['new']) - MAX_LEADS_SHOWN} more leads)")
    if res["deferred"]:
        out.append("deferred to a later run (cap reached): " + ", ".join(w["id"] for w in res["deferred"]))
    if res["quiet"]:
        out.append(f"no new leads, not yet due for full review: {len(res['quiet'])} site(s)")
    if res["status"] == STATUS_NO_CHANGES:
        out.append("no changes")
    out.append(f"STATUS: {res['status']}")
    return "\n".join(out)


def write_seed(res: dict, root: Path, outdir: Path) -> None:
    """SEED.md and per-site context files, in the shape the researcher prompt expects."""
    outdir.mkdir(parents=True, exist_ok=True)
    lines = []
    for w in res["work"]:
        lines.append(f"## {w['id']} {w['name']} ({w['why']})")
        lines += [f"- {l['date'] or 'undated'} {l['title']} - {l['url']}" for l in w["new"]]
        ctx = subprocess.run([sys.executable, str(root / "scripts" / "site_research.py"), "context", w["id"]],
                             cwd=root, capture_output=True, text=True)
        (outdir / f"{w['id']}.context.json").write_text(ctx.stdout if ctx.returncode == 0 else "{}")
    (outdir / "SEED.md").write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", choices=["ack"], help="ack SITE_ID ...")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--root", type=Path, default=MAIN, help="checkout holding backlog.md and docs/data (the routine worktree)")
    ap.add_argument("--state", type=Path, default=STATE_PATH)
    ap.add_argument("--out", type=Path, help="write SEED.md and <ID>.context.json for the sites needing work")
    ap.add_argument("--max-sites", type=int, default=2, help="cap on sites handed to the model per run")
    ap.add_argument("--max-dossier-checks", type=int, default=8)
    ap.add_argument("--baseline-per-run", type=int, default=2, help="never-researched queue rows examined per run")
    ap.add_argument("--no-pr", action="store_true", help="skip the PR review-comment read")
    ap.add_argument("--dry-run", action="store_true", help="do not write state")
    args = ap.parse_args(argv)

    state = load_state(args.state)
    if args.command == "ack":
        done = ack(state, args.ids)
        save_state(state, args.state)
        print("acked: " + (", ".join(done) or "nothing"))
        return 0
    comments = None if args.no_pr else pr_comments()
    res = run(args.root, http_fetch, state, dt.date.today(), max_sites=args.max_sites,
              max_dossier_checks=args.max_dossier_checks, baseline_per_run=args.baseline_per_run,
              comments=comments)
    if not args.dry_run:
        save_state(state, args.state)
    if args.out and res["work"]:
        write_seed(res, args.root, args.out)
    print(render(res))
    return EXIT[res["status"]]


if __name__ == "__main__":
    sys.exit(main())
