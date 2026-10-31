"""Deterministic parts of the local-records pipeline: quote matching, the adjudication
table, and the shipped-file schema. No network, no model."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import local_records as lr  # noqa: E402
from schema import LocalFact, LocalRecordSet  # noqa: E402


def test_html_to_text_drops_scripts_styles_and_tags():
    page = "<html><style>.a{x:y}</style><script>var q='deed';</script><p>Deed recorded <b>May 3</b>, 2021</p></html>"
    assert "deed recorded may 3" in lr.normalize_text(lr.html_to_text(page))
    assert "var q" not in lr.html_to_text(page)


@pytest.mark.parametrize("quote,page", [
    ("Quitclaim deed recorded May 3, 2021", "The  Quitclaim\ndeed  recorded May 3, 2021 by the county."),
    ("owner’s name — Smith Holdings", "Owner's name - Smith Holdings LLC"),     # curly quote and em dash
    ("SOLD FOR $120,000", "parcel sold for $120,000 in june"),                   # case
])
def test_quote_matches_despite_formatting(quote, page):
    assert lr.quote_in_text(quote, page)


def test_quote_must_actually_appear():
    assert not lr.quote_in_text("Quitclaim deed recorded May 3, 2021", "Warranty deed recorded May 4, 2021")


def test_very_short_quote_never_matches():
    assert not lr.quote_in_text("deed", "a deed was recorded")


@pytest.mark.parametrize("code,verifier,expected", [
    ("quote_found", "supported", "accepted"),
    ("quote_found", "unverifiable", "accepted_code_only"),   # the words are real; nobody judged the summary against them
    ("quote_found", "unsupported", "disputed"),
    ("quote_found", "contradicted", "disputed"),
    ("quote_missing", "supported", "disputed"),
    ("quote_missing", "unsupported", "rejected"),
    ("quote_missing", "contradicted", "rejected"),
    ("unfetchable", "supported", "accepted_model_only"),
    ("non_text", "supported", "accepted_model_only"),
    ("unfetchable", "unsupported", "rejected"),
    ("unfetchable", "unverifiable", "rejected"),
    ("dead", "supported", "rejected"),       # a 404 is never "unreadable by code"
    ("dead", "unverifiable", "rejected"),
    ("quote_found", None, "rejected"),       # nothing ships that no second model read
    ("quote_missing", None, "rejected"),
])
def test_adjudication_table(code, verifier, expected):
    assert lr.decide(code, verifier)[0] == expected


def test_a_fact_with_a_non_https_source_is_refused():
    with pytest.raises(ValidationError):
        LocalFact(kind="deed", summary="Deed recorded in 2021.", source_url="http://county.example/x", quote="deed recorded 2021")


def test_unknown_fact_kind_is_refused():
    with pytest.raises(ValidationError):
        LocalFact(kind="rumor", summary="Deed recorded in 2021.", source_url="https://county.example/x", quote="deed recorded 2021")


def test_record_set_requires_a_named_researcher():
    with pytest.raises(ValidationError):
        LocalRecordSet(id="X1", name="Site", researched_at="2026-10-31", researchers=[])


def test_http_portals_are_upgraded_and_bad_facts_are_flagged_not_fatal():
    assert lr.https_url("http://county.example/a") == "https://county.example/a"
    assert lr.invalid_fact({"kind": "deed", "summary": "Deed recorded.", "source_url": "http://c.example/x", "quote": "deed recorded 2021"}) is None
    assert lr.invalid_fact({"kind": "deed", "summary": "Deed recorded."}) is not None          # no source or quote
    assert lr.invalid_fact({"kind": "rumor", "summary": "Deed recorded.", "source_url": "https://c.example", "quote": "deed recorded 2021"})
    assert lr.invalid_portal({"kind": "assessor", "name": "Assessor", "url": "https://c.example", "access": "free_search"}) is False
    assert lr.invalid_portal({"kind": "assessor", "name": "Assessor", "url": "https://c.example", "access": "maybe"}) is True


def test_a_verdict_binds_only_to_the_exact_fact_it_was_written_for():
    a = {"kind": "deed", "summary": "Deed recorded.", "source_url": "https://a.example/x", "quote": "deed recorded 2021"}
    b = {**a, "summary": "Deed recorded for $1."}                       # same URL and quote, different claim
    reviewed = {"facts": {"0": lr.fact_fingerprint(a)}}
    verdicts = [{"index": 0, "verdict": "supported"}]
    assert set(lr._bind_verdicts([a], verdicts, reviewed)) == {0}
    assert lr._bind_verdicts([b], verdicts, reviewed) == {}              # summary edited after review: verdict withheld
    assert lr._bind_verdicts([b, a], verdicts, reviewed) == {}           # reordered: index 0 is now a different fact
    assert lr._bind_verdicts([a], verdicts, None) == {}                  # never stamped: nothing is trusted
    assert lr._bind_verdicts([a], [{"index": 0, "source_url": "https://z.example/", "verdict": "supported"}], reviewed) == {}


def test_non_parcel_ids_are_found_with_search_not_match():
    from connectors.parcel_owner import NON_PARCEL_ID
    assert NON_PARCEL_ID.search("39113-ROW") and NON_PARCEL_ID.search("27123-County RoW")
