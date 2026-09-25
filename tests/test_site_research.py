"""scripts/site_research.py: the only writer of docs/data/site-research.json."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("site_research", ROOT / "scripts" / "site_research.py")
sr = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sr)

TODAY = dt.date(2026, 9, 25)


def _corpus(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    for name, ids in (("superfund-npl.json", ["KY8890008982"]), ("epa-acres.json", ["ACRES-1"]),
                      ("dod-fuds.json", []), ("dod-brac.json", [])):
        (data / name).write_text(json.dumps({"sites": [{"id": i, "name": i} for i in ids]}))
    return data


def _src(url: str = "https://www.energy.gov/pppo/paducah", published: str | None = "2026-09-10") -> dict:
    s = {"title": "Paducah site update", "url": url, "publisher": "DOE", "accessed": "2026-09-25"}
    if published:
        s["published"] = published
    return s


def _entry(**over) -> dict:
    e = {
        "id": "KY8890008982",
        "name": "Paducah Gaseous Diffusion Plant (USDOE)",
        "researched_at": "2026-09-25",
        "search_window_start": "2026-06-25",
        "summary": "DOE's former uranium enrichment plant in western Kentucky, now in decommissioning with parts of the reservation offered for reuse.",
        "summary_sources": [_src()],
        "items": [{"kind": "news", "date": "2026-09-10", "title": "DOE update on Paducah land transfer",
                   "summary": "DOE described progress on the land transfer to the local reuse authority.",
                   "sources": [_src()]}],
        "next_review": "2026-10-25",
    }
    e.update(over)
    return e


def test_first_entry_creates_the_file(tmp_path):
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    payload = sr.add_entries([_entry()], path=out, data_dir=data, today=TODAY)
    assert payload["count"] == 1
    saved = json.loads(out.read_text())
    assert saved["sites"][0]["id"] == "KY8890008982"
    assert sr.validate_file(out, data, TODAY) == 1


def test_readding_keeps_prior_summary_in_history_and_unions_developments(tmp_path):
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    sr.add_entries([_entry()], path=out, data_dir=data, today=TODAY)
    newer = _entry(summary="A newer two-sentence summary about Paducah reflecting a reuse authority vote this month.",
                   items=[{"kind": "hearing", "date": "2026-09-20", "title": "Reuse authority votes on parcel lease",
                           "summary": "The local reuse authority approved a lease for part of the transferred land.",
                           "sources": [_src("https://example-news.test.gov/paducah-vote", "2026-09-20")]}])
    sr.add_entries([newer], path=out, data_dir=data, today=TODAY)
    site = json.loads(out.read_text())["sites"][0]
    assert site["summary"].startswith("A newer")
    assert site["history"][0]["summary"].startswith("DOE's former")
    assert [i["kind"] for i in site["items"]] == ["hearing", "news"]  # newest first, nothing dropped


def test_same_development_is_not_duplicated(tmp_path):
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    sr.add_entries([_entry()], path=out, data_dir=data, today=TODAY)
    sr.add_entries([_entry()], path=out, data_dir=data, today=TODAY)
    assert len(json.loads(out.read_text())["sites"][0]["items"]) == 1


def test_unknown_site_id_is_rejected_and_nothing_is_written(tmp_path):
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    with pytest.raises(sr.ResearchError, match="not a shipped site id"):
        sr.add_entries([_entry(id="XX0000000000")], path=out, data_dir=data, today=TODAY)
    assert not out.exists()


def test_batch_is_all_or_nothing(tmp_path):
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    with pytest.raises(sr.ResearchError):
        sr.add_entries([_entry(), _entry(id="ACRES-1", next_review="2026-09-01")],
                       path=out, data_dir=data, today=TODAY)
    assert not out.exists()


def test_future_dates_are_rejected(tmp_path):
    data = _corpus(tmp_path)
    bad = _entry()
    bad["items"][0]["date"] = "2026-12-01"
    with pytest.raises(sr.ResearchError, match="in the future"):
        sr.add_entries([bad], path=data / "site-research.json", data_dir=data, today=TODAY)


def test_future_dated_history_is_rejected(tmp_path):
    """Regression (PR #38 review): history dates skipped the future-date check."""
    data = _corpus(tmp_path)
    bad = _entry(history=[{"researched_at": "2027-01-01", "summary": "A summary dated after today."}])
    with pytest.raises(sr.ResearchError, match=r"history\[0\].researched_at=2027-01-01 is in the future"):
        sr.add_entries([bad], path=data / "site-research.json", data_dir=data, today=TODAY)
    assert not (data / "site-research.json").exists()


def test_a_development_without_a_citation_fails_the_schema(tmp_path):
    data = _corpus(tmp_path)
    bad = _entry()
    bad["items"][0]["sources"] = []
    with pytest.raises(sr.ResearchError, match="schema"):
        sr.add_entries([bad], path=data / "site-research.json", data_dir=data, today=TODAY)


def test_http_citations_are_rejected(tmp_path):
    data = _corpus(tmp_path)
    bad = _entry(summary_sources=[_src("http://insecure.example/page")])
    with pytest.raises(sr.ResearchError, match="schema"):
        sr.add_entries([bad], path=data / "site-research.json", data_dir=data, today=TODAY)


def test_empty_developments_must_be_declared(tmp_path):
    """An empty list could mean 'searched, nothing new' or 'never searched'.
    The entry must say which."""
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    with pytest.raises(sr.ResearchError, match="no_new_developments"):
        sr.add_entries([_entry(items=[])], path=out, data_dir=data, today=TODAY)
    sr.add_entries([_entry(items=[], no_new_developments=True)], path=out, data_dir=data, today=TODAY)
    assert json.loads(out.read_text())["sites"][0]["no_new_developments"] is True


def test_next_review_must_follow_research_date(tmp_path):
    data = _corpus(tmp_path)
    with pytest.raises(sr.ResearchError, match="next_review"):
        sr.add_entries([_entry(next_review="2026-09-25")], path=data / "site-research.json",
                       data_dir=data, today=TODAY)


def test_shipped_file_validates():
    """Guard for the real artifact once it exists."""
    if not sr.OUTPUT.exists():
        pytest.skip("site-research.json not generated yet")
    assert sr.validate_file() >= 1
