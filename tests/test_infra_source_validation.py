"""Independent source checks must not endorse incomplete spatial results."""
import pytest
from scripts import validate_against_sources as audit


def test_source_validation_rejects_transfer_limit(monkeypatch):
    monkeypatch.setattr(audit, "get_json", lambda *a: {"features": [], "exceededTransferLimit": True})
    with pytest.raises(ValueError, match="Incomplete"):
        audit._measure(60, -150, {"url":"https://example.test/query"}, 10)


def test_source_measurement_independent_of_production_search_radius(monkeypatch):
    monkeypatch.setattr(audit, "get_json", lambda *a: {"features":[{"geometry":{"paths":[[[-147.7,60],[-147.7,60.1]]]}}]})
    distance, count = audit._measure(60, -150, {"url":"https://example.test/query"}, 100)
    assert 79 < distance < 80 and count == 1


@pytest.mark.parametrize("status", ["MISMATCH", "ERROR", "EMPTY"])
def test_validation_cli_fails_when_source_check_fails(monkeypatch,status):
    monkeypatch.setattr("sys.argv",["validate_against_sources.py","--ids","X","--only","infra"])
    monkeypatch.setattr(audit,"force_ipv4",lambda:None)
    monkeypatch.setattr(audit,"load_universe",lambda:{"X":{"id":"X"}})
    monkeypatch.setattr(audit,"check_infra",lambda *a:[{"id":"X","field":"transmission_mi","status":status,"detail":"test failure"}])
    assert audit.main() == 1
