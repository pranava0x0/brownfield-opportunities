"""Unit tests for the EPA ECHO enrichment connector.

Covers normalize_enforcement(), the response-envelope extractor, the
status filter, and the safe coercion helpers. No network calls.
"""
from __future__ import annotations

from connectors.epa_echo import (
    EpaEcho,
    _safe_float,
    _safe_int,
    _safe_str,
)


# ---- safe coercion helpers ----

def test_safe_int_handles_typical_inputs():
    assert _safe_int("12") == 12
    assert _safe_int(12) == 12
    assert _safe_int("1,234") == 1234
    assert _safe_int(" 5 ") == 5


def test_safe_int_returns_none_for_blanks_and_dashes():
    for v in (None, "", "--", "abc"):
        assert _safe_int(v) is None


def test_safe_float_strips_dollar_and_commas():
    assert _safe_float("$1,234.50") == 1234.5
    assert _safe_float("0") == 0.0


def test_safe_float_returns_none_for_blanks():
    for v in (None, "", "--", "n/a"):
        assert _safe_float(v) is None


def test_safe_str_trims_and_drops_dashes():
    assert _safe_str("  Significant  ") == "Significant"
    assert _safe_str("--") is None
    assert _safe_str("") is None
    assert _safe_str(None) is None


# ---- envelope extractor ----

def test_extract_results_finds_facilities_list():
    data = {"Results": {"Facilities": [{"RegistryID": "1"}, {"RegistryID": "2"}]}}
    rows = EpaEcho._extract_results(data)
    assert len(rows) == 2
    assert rows[0]["RegistryID"] == "1"


def test_extract_results_handles_alternate_shape():
    data = {"Results": {"Results": [{"RegistryID": "9"}]}}
    rows = EpaEcho._extract_results(data)
    assert rows == [{"RegistryID": "9"}]


def test_extract_results_empty_envelope_returns_empty_list():
    assert EpaEcho._extract_results({}) == []
    assert EpaEcho._extract_results({"Results": {}}) == []


# ---- status filter ----

def test_status_filter_parses_csv():
    assert EpaEcho._parse_status_filter("F,D") == {"F", "D"}


def test_status_filter_all_returns_none():
    assert EpaEcho._parse_status_filter("all") is None


def test_status_filter_empty_returns_none():
    assert EpaEcho._parse_status_filter("") is None
    assert EpaEcho._parse_status_filter(None) is None


# ---- normalize_enforcement ----

def test_normalize_enforcement_happy_path():
    facility = {
        "RegistryID": "110000123456",
        "Insp5yr": "4",
        "FEA5yr": "1",
        "IEA5yr": "2",
        "Penalties": "$25,000.00",
        "LastViolation": "2024-08-15",
        "LastInspection": "2025-02-01",
        "CurrentCompliance": "Significant Violation",
        "Programs": "CWA, RCRA, CERCLIS",
    }
    enf = EpaEcho.normalize_enforcement(facility)
    assert enf is not None
    assert enf["registry_id"] == "110000123456"
    assert enf["dfr_url"].endswith("?fid=110000123456")
    assert enf["inspections_5yr"] == 4
    assert enf["formal_actions_5yr"] == 1
    assert enf["informal_actions_5yr"] == 2
    assert enf["penalties_5yr_usd"] == 25000.0
    assert enf["last_violation_date"] == "2024-08-15"
    assert enf["last_inspection_date"] == "2025-02-01"
    assert enf["current_compliance"] == "Significant Violation"
    assert enf["programs"] == ["CWA", "RCRA", "CERCLIS"]


def test_normalize_enforcement_returns_none_when_all_signals_empty():
    """Bare facility row (registry id only, no enforcement context) → drop."""
    assert EpaEcho.normalize_enforcement({"RegistryID": "1"}) is None
    assert EpaEcho.normalize_enforcement({}) is None


def test_normalize_enforcement_handles_alternate_field_names():
    """ECHO returns different column names across endpoints — the normalizer
    has to be tolerant of `EpaInspections` vs `Insp5yr`, etc."""
    facility = {
        "RegistryID": "1",
        "EpaInspections": "3",
        "EpaFormalActions": "0",
        "EpaInformalActions": "1",
        "PenaltyAmount": "100",
        "DateLastInspection": "2025-01-01",
    }
    enf = EpaEcho.normalize_enforcement(facility)
    assert enf is not None
    assert enf["inspections_5yr"] == 3
    assert enf["formal_actions_5yr"] == 0
    assert enf["informal_actions_5yr"] == 1
    assert enf["penalties_5yr_usd"] == 100.0
    assert enf["last_inspection_date"] == "2025-01-01"


def test_normalize_enforcement_drops_empty_dashes():
    """ECHO commonly ships `--` for "no data on file" — must coerce to None
    rather than treating it as a valid string compliance bucket."""
    facility = {
        "RegistryID": "1",
        "Insp5yr": "--",
        "Penalties": "--",
        "CurrentCompliance": "Significant Violation",
    }
    enf = EpaEcho.normalize_enforcement(facility)
    assert enf is not None
    assert "inspections_5yr" not in enf
    assert "penalties_5yr_usd" not in enf
    assert enf["current_compliance"] == "Significant Violation"


def test_normalize_enforcement_omits_empty_program_list():
    """Comma-only or empty program field shouldn't emit an empty list."""
    facility = {"RegistryID": "1", "Insp5yr": "1", "Programs": ", , , "}
    enf = EpaEcho.normalize_enforcement(facility)
    assert enf is not None
    assert "programs" not in enf


def test_normalize_enforcement_zero_actions_still_emitted():
    """Zero formal actions is a meaningful signal (clean recent record),
    not the same as 'no enforcement on file' — should round-trip."""
    facility = {"RegistryID": "1", "FEA5yr": "0", "IEA5yr": "0"}
    enf = EpaEcho.normalize_enforcement(facility)
    assert enf is not None
    assert enf["formal_actions_5yr"] == 0
    assert enf["informal_actions_5yr"] == 0


def test_normalize_enforcement_rounds_penalties_to_cents():
    enf = EpaEcho.normalize_enforcement(
        {"RegistryID": "1", "Penalties": "1234.5678"}
    )
    assert enf is not None
    assert enf["penalties_5yr_usd"] == 1234.57


def test_normalize_enforcement_no_registry_id_still_emits_enforcement():
    """If ECHO ships partial data without a registry id, we still surface
    the enforcement signal — just without the DFR deep-link."""
    enf = EpaEcho.normalize_enforcement({"Insp5yr": "2"})
    assert enf is not None
    assert "registry_id" not in enf
    assert "dfr_url" not in enf
    assert enf["inspections_5yr"] == 2
