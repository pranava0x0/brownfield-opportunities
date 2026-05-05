"""Unit tests for the EPA ECHO enrichment connector.

Covers normalize_enforcement(), the response-envelope extractor, the
status filter, and the safe coercion helpers. No network calls.
"""
from __future__ import annotations

from connectors.epa_echo import (
    EpaEcho,
    _safe_date,
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


def test_safe_date_normalizes_mmddyyyy_from_get_qid():
    """ECHO `get_qid` ships dates as MM/DD/YYYY; the connector must
    re-emit them as ISO so the frontend renders consistently across
    enrichment-source mixes."""
    assert _safe_date("12/20/2025") == "2025-12-20"
    assert _safe_date("9/3/2024") == "2024-09-03"


def test_safe_date_passthrough_for_iso_and_unknown():
    assert _safe_date("2025-01-15") == "2025-01-15"
    assert _safe_date(None) is None
    assert _safe_date("--") is None


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


# ---- bot-block detection ----

def test_detect_bot_block_top_level_error():
    """ECHO's robotic-query rejection ships at top-level Error on
    `get_facilities`. Detector must catch that shape, not just the
    nested `Results.Error` shape."""
    data = {"Error": {"ErrorMessage": (
        "Your query has been identified as a robotic or programmed query, "
        "and has been blocked. ECHO is not designed to support large scale "
        "data transfers or robotic queries."
    )}}
    msg = EpaEcho._detect_bot_block(data)
    assert msg is not None
    assert "robotic" in msg.lower()


def test_detect_bot_block_nested_in_results():
    """And catch the nested shape returned by `get_qid`."""
    data = {"Results": {"Error": {"ErrorMessage": "Robotic query blocked."}}}
    msg = EpaEcho._detect_bot_block(data)
    assert msg is not None


def test_detect_bot_block_ignores_unrelated_errors():
    """Real ECHO errors (e.g. queryset limit) must not be misclassified
    as bot-blocks — they have their own legit handling path."""
    data = {"Results": {"Error": {"ErrorMessage":
        "Rows Returned would be 5619057. Queryset Limit would be exceeded."
    }}}
    assert EpaEcho._detect_bot_block(data) is None


def test_detect_bot_block_handles_clean_response():
    """A normal success response must not flag as bot-blocked."""
    assert EpaEcho._detect_bot_block({"Results": {"QueryID": "1", "Facilities": []}}) is None
    assert EpaEcho._detect_bot_block({}) is None


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


def test_normalize_enforcement_handles_get_qid_object_names():
    """`get_qid` is the canonical row-data endpoint and ships ObjectName
    keys (`FacInspectionCount`, `FacComplianceStatus`, ...). Ensure those
    map through correctly and that MM/DD/YYYY dates get ISO-normalized."""
    facility = {
        "RegistryID": "110071102523",
        "FacName": "NAVAL REACTORS FACILITY",
        "FacState": "ID",
        "FacComplianceStatus": "No Violation Identified",
        "FacInspectionCount": "9",
        "FacInformalCount": "6",
        "FacFormalActionCount": "3",
        "FacTotalPenalties": "$466,600",
        "FacDateLastInspection": "12/20/2025",
        "FacDateLastFormalAction": "9/13/2024",
        "FacPenaltyCount": "1",
        "FacDateLastPenalty": "8/1/2024",
    }
    enf = EpaEcho.normalize_enforcement(facility)
    assert enf is not None
    assert enf["registry_id"] == "110071102523"
    assert enf["inspections_5yr"] == 9
    assert enf["informal_actions_5yr"] == 6
    assert enf["formal_actions_5yr"] == 3
    assert enf["penalties_5yr_usd"] == 466600.0
    assert enf["current_compliance"] == "No Violation Identified"
    # MM/DD/YYYY → ISO (frontend joins these to other ISO date fields).
    assert enf["last_inspection_date"] == "2025-12-20"
    assert enf["last_formal_action_date"] == "2024-09-13"


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
