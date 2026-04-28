"""Schema validation tests — guards against connector drift."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from schema import Payload, SiteRecord


def _minimal_site(**overrides) -> dict:
    base = {
        "id": "TEST00000001",
        "program": "superfund",
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


def test_brownfield_record_minimal():
    """ACRES record: program='brownfield', no NPL fields, no acreage."""
    SiteRecord(
        id="ACRES-1234",
        program="brownfield",
        name="Old Mill",
        state="ME",
        lat=44.0, lon=-70.0,
    )


def test_program_validates():
    """program must be one of the two literals."""
    with pytest.raises(ValidationError):
        SiteRecord(id="X", program="rcra", lat=0, lon=0)


def test_exclude_none_drops_placeholders():
    """The serializer must drop None fields so the combined JSON stays small."""
    rec = SiteRecord(id="ACRES-1", program="brownfield", name="X", lat=1, lon=2)
    js = rec.model_dump_json(exclude_none=True)
    # Future enrichment slots should not appear at all in the wire format.
    assert "current_owner" not in js
    assert "encumbrances" not in js
    assert "remediation_detail" not in js
    assert "proximity" not in js
    assert "children" not in js


def test_combined_payload_with_programs():
    p = Payload(
        generated_at="2026-04-27T00:00:00Z",
        source="combined",
        source_url="",
        count=2,
        sites=[
            _minimal_site(),
            _minimal_site(id="ACRES-9", program="brownfield",
                          epa_id=None, npl_status_code=None, npl_status=None,
                          federal_facility=None, federal_facility_code=None,
                          last_updated=None, acreage=None),
        ],
        programs={"superfund": 1, "brownfield": 1},
    )
    assert p.programs == {"superfund": 1, "brownfield": 1}
