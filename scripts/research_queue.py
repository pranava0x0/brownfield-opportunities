#!/usr/bin/env python3
"""Bookkeeping for the daily site-research queue (backlog.md section 6).

The routine used to edit the queue table with ad hoc inline Python each run.
This script does those edits the same way every time:

  next [N]                 print the next N site ids to research (default 2):
                           overdue dossiers first, then queued/retry rows top-down
  mark ID done             set the row to "done <today>"; Last researched and Next due
                           are read back from docs/data/site-research.json
  mark ID retry REASON     set the row to retry and append the reason to "Why queued"
  add ID REASON            add a queued row (the id must exist in the corpus)
  log TEXT                 append one line to the run log
  sync                     copy Last researched / Next due from the dossiers onto done rows
  check                    exit 1 if the queue breaks a rule (fewer than 10 queued,
                           a done row whose Next due differs from the dossier, unknown ids)

Rows are written back in a fixed order: queued/retry rows first (table order),
then done rows newest first.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "backlog.md"
RESEARCH = ROOT / "docs" / "data" / "site-research.json"
PROGRAM_FILES = ["superfund-npl.json", "epa-acres.json", "dod-fuds.json", "dod-brac.json"]
MIN_QUEUED = 10
COLUMNS = ["#", "Status", "Site id", "Name", "St", "Why queued", "Last researched", "Next due"]


def today() -> str:
    return dt.date.today().isoformat()


def read_table(text: str) -> tuple[int, int, list[dict]]:
    """Return (start, end, rows) for the queue table inside section 6."""
    lines = text.split("\n")
    sec = next(i for i, l in enumerate(lines) if l.startswith("## 6."))
    head = next(i for i in range(sec, len(lines)) if lines[i].startswith("| # | Status"))
    end = head + 2
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    rows = []
    for line in lines[head + 2:end]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(dict(zip(COLUMNS, cells)))
    return head, end, rows


def write_table(text: str, head: int, end: int, rows: list[dict]) -> str:
    def done_key(r):  # newest done first
        m = re.search(r"\d{4}-\d{2}-\d{2}", r["Status"])
        return m.group(0) if m else ""
    open_rows = [r for r in rows if not r["Status"].startswith("done")]
    done_rows = sorted((r for r in rows if r["Status"].startswith("done")), key=done_key, reverse=True)
    lines = text.split("\n")
    body = ["| " + " | ".join(r[c] for c in COLUMNS) + " |" for r in open_rows + done_rows]
    return "\n".join(lines[:head + 2] + body + lines[end:])


def dossiers() -> dict:
    data = json.loads(RESEARCH.read_text())
    items = data.get("sites", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        return items
    return {d["id"]: d for d in items}


def corpus_ids() -> set[str]:
    ids = set()
    for name in PROGRAM_FILES:
        ids |= {s["id"] for s in json.loads((ROOT / "docs" / "data" / name).read_text())["sites"]}
    return ids


def site_name(sid: str) -> tuple[str, str]:
    for name in PROGRAM_FILES:
        for s in json.loads((ROOT / "docs" / "data" / name).read_text())["sites"]:
            if s["id"] == sid:
                return s.get("name", ""), s.get("state", "")
    raise SystemExit(f"unknown site id: {sid}")


def cmd_next(rows: list[dict], n: int) -> list[str]:
    ds = dossiers()
    due = [sid for sid, d in ds.items() if (d.get("next_review") or "9999") <= today()]
    picks = sorted(due, key=lambda sid: ds[sid]["next_review"])
    picks += [r["Site id"] for r in rows if r["Status"] in ("queued", "retry") and r["Site id"] not in picks]
    return picks[:n]


def cmd_mark(rows: list[dict], sid: str, status: str, reason: str = "") -> None:
    row = next((r for r in rows if r["Site id"] == sid), None)
    if row is None:
        raise SystemExit(f"{sid} is not in the queue table")
    if status == "done":
        d = dossiers().get(sid)
        if not d:
            raise SystemExit(f"{sid} has no dossier in site-research.json; merge it first")
        row["Status"] = f"done {today()}"
        row["Last researched"] = d.get("researched_at", today())
        row["Next due"] = d.get("next_review", "—")
    else:
        row["Status"] = "retry"
        if reason:
            row["Why queued"] = f"{row['Why queued']}; {today()}: {reason}"


def cmd_add(rows: list[dict], sid: str, reason: str) -> None:
    if any(r["Site id"] == sid for r in rows):
        raise SystemExit(f"{sid} is already in the queue")
    name, state = site_name(sid)
    num = max(int(r["#"]) for r in rows if r["#"].isdigit()) + 1
    # Title-case for the table, but keep agency codes in parentheses: "(USARMY)".
    pretty = re.sub(r"\((\w+)\)", lambda m: f"({m.group(1).upper()})", name.title())
    rows.append(dict(zip(COLUMNS, [str(num), "queued", sid, pretty, state, reason, "—", "—"])))


def cmd_check(rows: list[dict]) -> list[str]:
    problems = []
    queued = sum(r["Status"] == "queued" for r in rows)
    if queued < MIN_QUEUED:
        problems.append(f"only {queued} queued rows (minimum {MIN_QUEUED})")
    ids, ds = corpus_ids(), dossiers()
    for r in rows:
        if r["Site id"] not in ids:
            problems.append(f"{r['Site id']}: not in the corpus")
        if r["Status"].startswith("done"):
            want = ds.get(r["Site id"], {}).get("next_review")
            if want and r["Next due"] != want:
                problems.append(f"{r['Site id']}: Next due {r['Next due']} != dossier next_review {want}")
    return problems


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    text = BACKLOG.read_text()
    head, end, rows = read_table(text)
    cmd = argv[0]
    if cmd == "next":
        print("\n".join(cmd_next(rows, int(argv[1]) if len(argv) > 1 else 2)))
        return 0
    if cmd == "check":
        problems = cmd_check(rows)
        print("\n".join(problems) or "queue ok")
        return 1 if problems else 0
    if cmd == "mark":
        cmd_mark(rows, argv[1], argv[2], " ".join(argv[3:]))
    elif cmd == "sync":
        ds = dossiers()
        for r in rows:
            d = ds.get(r["Site id"])
            if r["Status"].startswith("done") and d:
                r["Last researched"], r["Next due"] = d.get("researched_at", r["Last researched"]), d.get("next_review", r["Next due"])
    elif cmd == "add":
        cmd_add(rows, argv[1], " ".join(argv[2:]))
    elif cmd == "log":
        text = write_table(text, head, end, rows)
        marker = "### Run log"
        sec_end = text.index("## 7.")
        block = text[text.index(marker):sec_end].rstrip("\n")
        text = text.replace(block, block + f"\n- {today()} · " + " ".join(argv[1:]), 1)
        BACKLOG.write_text(text)
        return 0
    else:
        raise SystemExit(f"unknown command {cmd!r}; see --help")
    BACKLOG.write_text(write_table(text, head, end, rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
