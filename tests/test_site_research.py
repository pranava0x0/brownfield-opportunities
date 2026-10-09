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


def test_archived_summary_keeps_its_citations(tmp_path):
    """Regression (PR #38 review): history dropped the old summary_sources."""
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    sr.add_entries([_entry()], path=out, data_dir=data, today=TODAY)
    sr.add_entries([_entry(summary="A replacement summary about Paducah that differs from the first one entirely.")],
                   path=out, data_dir=data, today=TODAY)
    site = json.loads(out.read_text())["sites"][0]
    assert site["history"][0]["summary_sources"][0]["url"] == "https://www.energy.gov/pppo/paducah"


def test_an_older_file_does_not_replace_a_newer_dossier(tmp_path):
    """Regression (PR #37 review): the last file added became current even when older."""
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    newer = _entry(summary="The newer summary, researched in September after the lease vote was held.",
                   next_review="2026-10-25")
    older = _entry(researched_at="2026-08-01", search_window_start="2026-05-01",
                   summary="An older summary from the August pass, before the lease vote happened.",
                   summary_sources=[_src(published="2026-07-30")],
                   items=[{"kind": "news", "date": "2026-07-30", "title": "Earlier DOE Paducah update",
                           "summary": "DOE described the land transfer schedule in July.",
                           "sources": [_src("https://www.energy.gov/pppo/paducah-july", "2026-07-30")]}],
                   next_review="2026-08-31")
    older["summary_sources"][0]["accessed"] = "2026-08-01"
    older["items"][0]["sources"][0]["accessed"] = "2026-08-01"
    sr.add_entries([newer], path=out, data_dir=data, today=TODAY)
    sr.add_entries([older], path=out, data_dir=data, today=TODAY)
    site = json.loads(out.read_text())["sites"][0]
    assert site["researched_at"] == "2026-09-25"
    assert site["summary"].startswith("The newer summary")
    assert site["next_review"] == "2026-10-25"
    assert site["search_window_start"] == "2026-05-01"  # earlier window covers the older item
    assert [h["researched_at"] for h in site["history"]] == ["2026-08-01"]
    assert {i["date"] for i in site["items"]} == {"2026-09-10", "2026-07-30"}  # older item still unioned in


def test_history_is_never_truncated(tmp_path):
    """Regression (PR #38 review): history was sliced to 12 entries."""
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    past = [{"researched_at": f"2025-{m:02d}-01", "summary": f"Archived summary number {m}."} for m in range(1, 13)]
    sr.add_entries([_entry(history=past)], path=out, data_dir=data, today=TODAY)
    sr.add_entries([_entry(summary="A thirteenth summary that pushes the first twelve into longer history.")],
                   path=out, data_dir=data, today=TODAY)
    site = json.loads(out.read_text())["sites"][0]
    assert len(site["history"]) == 13
    assert site["history"][-1]["researched_at"] == "2025-01-01"


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
        sr.add_entries([_entry(), _entry(id="ACRES-1", researched_at="2026-10-30")],
                       path=out, data_dir=data, today=TODAY)
    assert not out.exists()  # the valid first entry was not written either


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


def _write_raw(data: Path, entry: dict) -> Path:
    out = data / "site-research.json"
    out.write_text(json.dumps({"schema_version": 1, "generated_at": "2026-09-25T00:00:00Z",
                               "source": sr.SOURCE_LABEL, "count": 1, "sites": [entry]}))
    return out


def test_add_sets_next_review_from_the_cadence_rule(tmp_path):
    """Regression (PR #39 review, four findings): researchers kept writing +30
    days for sites whose newest development was older than 90 days."""
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    old_item = dict(_entry()["items"][0], date="2026-05")  # > 90 days before 2026-09-25
    sr.add_entries([_entry(items=[old_item], search_window_start="2025-09-25", next_review="2026-10-25")],
                   path=out, data_dir=data, today=TODAY)
    assert json.loads(out.read_text())["sites"][0]["next_review"] == "2026-12-24"
    sr.add_entries([_entry(next_review="2026-12-24")], path=out, data_dir=data, today=TODAY)  # recent item
    assert json.loads(out.read_text())["sites"][0]["next_review"] == "2026-10-25"


def test_add_rejects_a_development_older_than_the_window(tmp_path):
    """Regression (PR #39 review): "developments since <date>" was false when an
    item predated search_window_start. Widening the window silently would claim
    a search that never happened, so the entry is rejected instead."""
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    early = dict(_entry()["items"][0], date="2025-07")
    with pytest.raises(sr.ResearchError, match="predates"):
        sr.add_entries([_entry(items=[early], search_window_start="2025-10-03")],
                       path=out, data_dir=data, today=TODAY)
    assert not out.exists()


def test_month_only_development_counts_as_recent_if_the_month_may_be(tmp_path):
    """A "2026-07" item may be 2026-07-31, inside 90 days of 2026-10-09."""
    assert sr.expected_next_review("2026-10-09", ["2026-07"]) == "2026-11-08"
    assert sr.expected_next_review("2026-10-09", ["2026-06"]) == "2027-01-07"


def test_merging_an_older_file_keeps_window_and_cadence_consistent(tmp_path):
    """An older entry's items predate the newer window; the merged dossier must
    still validate (window = earlier of the two, cadence recomputed)."""
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    sr.add_entries([_entry(researched_at="2026-09-25", search_window_start="2026-06-25")],
                   path=out, data_dir=data, today=TODAY)
    older_item = dict(_entry()["items"][0], date="2026-03-02",
                      sources=[_src("https://example-news.test.gov/older", "2026-03-02")])
    older = _entry(researched_at="2026-04-01", search_window_start="2025-04-01", items=[older_item])
    for src in older["summary_sources"]:
        src["accessed"] = "2026-04-01"
    for src in older_item["sources"]:
        src["accessed"] = "2026-04-01"
    sr.add_entries([older], path=out, data_dir=data, today=TODAY)
    site = json.loads(out.read_text())["sites"][0]
    assert site["researched_at"] == "2026-09-25"
    assert site["search_window_start"] == "2025-04-01"
    assert site["next_review"] == "2026-10-25"  # the 2026-09-10 item is still recent
    assert sr.validate_file(out, data, TODAY) == 1


def test_next_review_may_be_omitted_and_is_derived(tmp_path):
    """Regression (PR #40 review): the field is derived, so researchers need not supply it."""
    data = _corpus(tmp_path)
    out = data / "site-research.json"
    entry = _entry()
    del entry["next_review"]
    sr.add_entries([entry], path=out, data_dir=data, today=TODAY)
    assert json.loads(out.read_text())["sites"][0]["next_review"] == "2026-10-25"


def test_development_after_the_research_date_is_rejected(tmp_path):
    """Regression (PR #40 review): a backfilled dossier with an item dated after
    its own researched_at had a negative age and counted as recent."""
    data = _corpus(tmp_path)
    late = dict(_entry()["items"][0], date="2026-09-20")
    with pytest.raises(sr.ResearchError, match="after researched_at"):
        sr.add_entries([_entry(researched_at="2026-09-15", items=[late])],
                       path=data / "site-research.json", data_dir=data, today=TODAY)


def test_malformed_items_raise_research_error(tmp_path):
    data = _corpus(tmp_path)
    for items in ([None], ["text"]):
        with pytest.raises(sr.ResearchError, match="schema"):
            sr.add_entries([_entry(items=items)], path=data / "site-research.json", data_dir=data, today=TODAY)


def test_malformed_dates_raise_research_error_not_a_traceback(tmp_path):
    data = _corpus(tmp_path)
    with pytest.raises(sr.ResearchError, match="schema"):
        sr.add_entries([_entry(researched_at="2026-9-25")], path=data / "site-research.json",
                       data_dir=data, today=TODAY)
    bad_item = dict(_entry()["items"][0], date="garbage")
    with pytest.raises(sr.ResearchError, match="schema"):
        sr.add_entries([_entry(items=[bad_item])], path=data / "site-research.json",
                       data_dir=data, today=TODAY)


def test_validate_rejects_a_hand_edited_cadence_or_window(tmp_path):
    data = _corpus(tmp_path)
    with pytest.raises(sr.ResearchError, match="cadence"):
        sr.validate_file(_write_raw(data, _entry(next_review="2026-12-24")), data, TODAY)
    early = dict(_entry()["items"][0], date="2025-07")
    with pytest.raises(sr.ResearchError, match="predates"):
        sr.validate_file(_write_raw(data, _entry(items=[early], search_window_start="2025-10-03",
                                                 next_review="2026-12-24")), data, TODAY)


def test_shipped_file_validates():
    """Guard for the real artifact once it exists."""
    if not sr.OUTPUT.exists():
        pytest.skip("site-research.json not generated yet")
    assert sr.validate_file() >= 1
