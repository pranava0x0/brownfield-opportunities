"""Queue bookkeeping round-trips the backlog table without rewriting it."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_queue as rq  # noqa: E402

TABLE = """# Plan
## 6. Daily site-refresh queue
| # | Status | Site id | Name | St | Why queued | Last researched | Next due |
|---|---|---|---|---|---|---|---|
| 2 | done 2026-10-01 | B1 | Bee | NY | reason b | 2026-10-01 | 2026-12-30 |
| 3 | queued | C1 | Cee | TX | reason c | — | — |
| 1 | retry | A1 | Aye | CA | reason a | — | — |

### Run log
- 2026-10-01 · run
## 7. Decisions
"""


def test_round_trip_keeps_rows_and_orders_open_rows_first():
    head, end, rows = rq.read_table(TABLE)
    assert [r["Site id"] for r in rows] == ["B1", "C1", "A1"]
    out = rq.write_table(TABLE, head, end, rows)
    _, _, again = rq.read_table(out)
    assert [r["Site id"] for r in again] == ["C1", "A1", "B1"]
    assert out.endswith("## 7. Decisions\n")


def test_mark_retry_appends_reason_and_keeps_row(monkeypatch):
    _, _, rows = rq.read_table(TABLE)
    monkeypatch.setattr(rq, "today", lambda: "2026-10-18")
    rq.cmd_mark(rows, "C1", "retry", "pages blocked")
    row = next(r for r in rows if r["Site id"] == "C1")
    assert row["Status"] == "retry" and row["Why queued"].endswith("2026-10-18: pages blocked")


def test_mark_done_reads_dates_from_the_dossier(monkeypatch):
    _, _, rows = rq.read_table(TABLE)
    monkeypatch.setattr(rq, "dossiers", lambda: {"C1": {"researched_at": "2026-10-18", "next_review": "2027-01-16"}})
    monkeypatch.setattr(rq, "today", lambda: "2026-10-18")
    rq.cmd_mark(rows, "C1", "done")
    row = next(r for r in rows if r["Site id"] == "C1")
    assert (row["Status"], row["Last researched"], row["Next due"]) == ("done 2026-10-18", "2026-10-18", "2027-01-16")


def test_check_reports_short_queue_and_date_drift(monkeypatch):
    _, _, rows = rq.read_table(TABLE)
    monkeypatch.setattr(rq, "corpus_ids", lambda: {"A1", "B1", "C1"})
    monkeypatch.setattr(rq, "dossiers", lambda: {"B1": {"next_review": "2027-01-01"}})
    problems = rq.cmd_check(rows)
    assert any("queued rows" in p for p in problems)
    assert any("B1: Next due" in p for p in problems)
