"""Schema validation tests — guards against connector drift."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from schema import Payload, SiteRecord


def _minimal_site(**overrides) -> dict:
    base = {
        "epa_id": "TEST00000001",
        "name": "Test Site",
        "acreage": 100.0,
        "npl_status_code": "F",
        "npl_status": "Currently on the Final NPL",
        "federal_facility": "N",
        "federal_facility_code": "N",
        "region": 5,
        "address": "1 Main St",
        "city": "Springfield",
        "county": "Sangamon",
        "state": "IL",
        "zip": "62701",
        "lat": 39.78,
        "lon": -89.65,
        "profile_url": None,
        "last_updated": 1700000000000,
    }
    base.update(overrides)
    return base


def test_minimal_record_valid():
    SiteRecord(**_minimal_site())


def test_acreage_optional_for_no_area_bucket():
    """Phase 3 — sites without acreage must validate."""
    SiteRecord(**_minimal_site(acreage=None))


def test_extra_field_rejected():
    """Catches connectors emitting fields the frontend doesn't know about."""
    with pytest.raises(ValidationError):
        SiteRecord(**_minimal_site(rogue_field="oops"))


def test_payload_round_trip():
    p = Payload(
        generated_at="2026-04-27T12:00:00Z",
        source="EPA NPL",
        source_url="https://example.com",
        limit=100,
        count=1,
        sites=[_minimal_site()],
    )
    serialized = p.model_dump_json()
    reparsed = Payload.model_validate_json(serialized)
    assert reparsed.count == 1
    assert reparsed.sites[0].epa_id == "TEST00000001"


def test_payload_unlimited():
    """limit=None means 'all features' — Phase 3."""
    p = Payload(
        generated_at="2026-04-27T12:00:00Z",
        source="EPA NPL",
        source_url="https://example.com",
        limit=None,
        count=0,
        sites=[],
    )
    assert p.limit is None
