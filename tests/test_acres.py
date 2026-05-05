"""Unit tests for the EPA ACRES (brownfield) connector.

Covers normalize() — the pure function that converts an ArcGIS feature dict
into the dashboard's record schema. No network calls.
"""
from __future__ import annotations

from connectors.epa_acres import EpaAcres


def _feature(attrs=None, geom=None):
    base = {
        "PROPERTY_ID": 122062,
        "PROPERTY_NAME": "Bates Mill #5",
        "RS_REGION_ID_1000": 1,
        "LABEL_STATE": "ME",
        "ADDRESS1": "15 Canal Street",
        "CITY": "Lewiston",
        "COUNTY": "Androscoggin",
        "ZIP_CODE": "04240",
        "LATITUDE_MEASURE": 44.098393,
        "LONGITUDE_MEASURE": -70.218544,
    }
    base.update(attrs or {})
    return {
        "attributes": base,
        "geometry": geom if geom is not None else {"x": -70.218544, "y": 44.098393},
    }


def test_normalize_happy_path():
    rec = EpaAcres.normalize(_feature())
    assert rec is not None
    assert rec["id"] == "ACRES-122062"
    assert rec["program"] == "brownfield"
    assert rec["name"] == "Bates Mill #5"
    assert rec["state"] == "ME"
    assert rec["region"] == 1
    assert rec["lat"] == 44.098393
    assert rec["lon"] == -70.218544
    assert rec["profile_url"].endswith("122062.html")
    # ACRES has no acreage / NPL fields.
    assert "acreage" not in rec
    assert "npl_status_code" not in rec
    assert "federal_facility" not in rec


def test_normalize_falls_back_to_attribute_lat_lon():
    """If geometry is missing, use the attribute lat/lon."""
    rec = EpaAcres.normalize(_feature(geom={}))
    assert rec is not None
    assert rec["lat"] == 44.098393
    assert rec["lon"] == -70.218544


def test_normalize_drops_record_with_no_property_id():
    rec = EpaAcres.normalize(_feature(attrs={"PROPERTY_ID": None}))
    assert rec is None


def test_normalize_drops_null_island():
    """Lat=0, lon=0 is almost always a geocoder failure — discard."""
    f = _feature(attrs={"LATITUDE_MEASURE": 0.0, "LONGITUDE_MEASURE": 0.0},
                 geom={"x": 0.0, "y": 0.0})
    assert EpaAcres.normalize(f) is None


def test_normalize_drops_out_of_range_coords():
    f = _feature(geom={"x": 999.0, "y": 999.0},
                 attrs={"LATITUDE_MEASURE": 999.0, "LONGITUDE_MEASURE": 999.0})
    assert EpaAcres.normalize(f) is None


def test_normalize_handles_string_coords():
    """Source occasionally returns numeric values as strings."""
    f = _feature(geom={"x": "-70.5", "y": "44.5"})
    rec = EpaAcres.normalize(f)
    assert rec is not None
    assert rec["lat"] == 44.5
    assert rec["lon"] == -70.5


def test_id_namespace_unique():
    """ACRES IDs must not collide with EPA_IDs (which look like 'XYZ12345678')."""
    rec = EpaAcres.normalize(_feature())
    assert rec["id"].startswith("ACRES-")


# ----- offline TIGER county fill -----


def test_fill_missing_county_uses_tiger_lookup(monkeypatch):
    """The post-normalize step should reverse-geocode lat/lon → county for
    records the source omits, leaving already-populated rows untouched.

    Stubs the TIGER index so the test stays hermetic — `test_county_lookup.py`
    covers the real-file decode path.
    """
    from connectors import epa_acres

    class FakeIndex:
        def lookup(self, lat, lon, expected_state=None):
            # Map a single test coordinate to a known county.
            if abs(lat - 44.10) < 0.1 and abs(lon - -70.22) < 0.1:
                return "Androscoggin"
            return None

    monkeypatch.setattr(epa_acres.CountyIndex, "from_path",
                        classmethod(lambda cls, p: FakeIndex()))

    records = [
        {"id": "ACRES-1", "state": "ME", "lat": 44.10, "lon": -70.22, "county": None},
        # Pre-populated county must not be overwritten.
        {"id": "ACRES-2", "state": "ME", "lat": 44.10, "lon": -70.22,
         "county": "Original"},
        # Point with no TIGER match (ocean) stays None.
        {"id": "ACRES-3", "state": "MA", "lat": 40.0, "lon": -65.0, "county": None},
    ]
    EpaAcres._fill_missing_county(records)
    assert records[0]["county"] == "Androscoggin"
    assert records[1]["county"] == "Original"
    assert records[2].get("county") is None


def test_fill_missing_county_skips_when_no_records_need_fill(monkeypatch):
    """Avoid building the index when every record already has county —
    saves the ~100ms decode cost on a fully-populated source."""
    from connectors import epa_acres

    calls: list[str] = []

    def fake_from_path(cls, p):
        calls.append("loaded")
        raise AssertionError("should not load index when nothing needs filling")

    monkeypatch.setattr(epa_acres.CountyIndex, "from_path",
                        classmethod(fake_from_path))

    records = [{"id": "ACRES-1", "state": "ME", "lat": 1, "lon": 2, "county": "X"}]
    EpaAcres._fill_missing_county(records)
    assert calls == []
