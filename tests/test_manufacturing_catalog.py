"""Manufacturing catalog: adjudication, place points, the shipped file, and the shared distance stamp."""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import manufacturing_catalog as mc  # noqa: E402
from schema import ManufacturingCatalog  # noqa: E402

OUT = ROOT / "docs" / "data" / "manufacturing-facilities.json"
FAC = {"name": "Example Transformer Plant", "company": "Ex", "product": "transformers", "status": "expansion",
       "city": "South Boston", "state": "VA", "investment_usd": 457000000, "jobs": 825,
       "source_url": "https://example.com/a", "quote": "invest $457 million in South Boston", "published": "2025-09"}


def research(*facilities, requirements=()):
    return {"topic": "transformer", "facilities": list(facilities), "requirements": list(requirements)}


def test_no_verdict_is_never_shipped():
    rows = mc.adjudicate_rows(research(FAC), None, check=lambda u, q: "quote_found")
    assert rows[0]["status"] == "rejected"


def test_supported_and_quote_found_is_accepted():
    v = {"rows": [{"kind": "facility", "index": 0, "source_url": FAC["source_url"], "verdict": "supported"}]}
    assert mc.adjudicate_rows(research(FAC), v, check=lambda u, q: "quote_found")[0]["status"] == "accepted"


def test_a_verdict_for_another_url_is_not_borrowed():
    v = {"rows": [{"kind": "facility", "index": 0, "source_url": "https://other.example/x", "verdict": "supported"}]}
    assert mc.adjudicate_rows(research(FAC), v, check=lambda u, q: "quote_found")[0]["status"] == "rejected"


def test_corrections_apply_and_the_corrected_quote_is_the_one_checked():
    seen = {}
    v = {"rows": [{"kind": "facility", "index": 0, "source_url": FAC["source_url"], "verdict": "supported",
                   "corrections": {"jobs": 500, "quote": "corrected words on the page", "lat": 1.0}}]}
    rows = mc.adjudicate_rows(research(FAC), v, check=lambda u, q: seen.setdefault("q", q) and "quote_found")
    assert seen["q"] == "corrected words on the page"
    assert rows[0]["row"]["jobs"] == 500 and "lat" not in rows[0]["row"]      # only listed fields are correctable


def test_supported_but_quote_missing_is_a_dispute():
    v = {"rows": [{"kind": "facility", "index": 0, "source_url": FAC["source_url"], "verdict": "supported"}]}
    assert mc.adjudicate_rows(research(FAC), v, check=lambda u, q: "quote_missing")[0]["status"] == "disputed"


def test_place_point_handles_census_suffixes_and_saint():
    gaz = {("VA", "South Boston town"): (36.7, -78.9), ("MO", "St. Louis city"): (38.6, -90.2)}
    assert mc.place_point(gaz, "South Boston", "VA")[0] == "South Boston town"
    assert mc.place_point(gaz, "Saint Louis", "MO")[0] == "St. Louis city"
    assert mc.place_point(gaz, "Nowhere", "VA") is None


def test_to_facility_builds_a_valid_row_and_holds_back_an_unknown_place():
    gaz = {("VA", "South Boston town"): (36.7, -78.9)}
    rec, why = mc.to_facility("transformer", FAC, "accepted", gaz, "2026-11-02")
    assert why is None and rec["id"].startswith("MFG-transformer-") and rec["locality"] == "South Boston town"
    rec, why = mc.to_facility("transformer", {**FAC, "city": "Nowhere"}, "accepted", gaz, "2026-11-02")
    assert rec is None and "Census place" in why


@pytest.mark.skipif(not OUT.exists(), reason="catalog not built")
def test_shipped_catalog_validates_and_every_row_is_cited_and_checked():
    payload = json.loads(OUT.read_text())
    ManufacturingCatalog.model_validate(payload)
    assert payload["count"] == len(payload["sites"]) > 0
    for row in payload["sites"] + payload["requirements"]:
        assert row["source_url"].startswith("https://") and len(row["quote"]) >= 12
        assert row["check"] in ("accepted", "accepted_code_only", "accepted_model_only")
    assert len({s["id"] for s in payload["sites"]}) == len(payload["sites"])
    assert {s["sector"] for s in payload["sites"]} == {"robotics", "turbine", "transformer", "minerals"}


def _haversine(a1, o1, a2, o2):
    r = math.radians
    h = math.sin(r(a2 - a1) / 2) ** 2 + math.cos(r(a1)) * math.cos(r(a2)) * math.sin(r(o2 - o1) / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(h))


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_stamp_takes_the_nearest_active_plant_and_uses_real_coordinates():
    facilities = [
        {"sector": "turbine", "status": "operating", "name": "Near", "lat": 34.85, "lon": -82.39},
        {"sector": "turbine", "status": "cancelled", "name": "Cancelled", "lat": 35.0, "lon": -82.0},
        {"sector": "turbine", "status": "announced", "name": "Far", "lat": 42.8, "lon": -73.9},
    ]
    sites = [{"id": "a", "lat": 35.0, "lon": -82.0},
             {"id": "ak", "lat": 25.0, "lon": -120.0, "lat_real": 61.2, "lon_real": -149.9}]
    js = ("const S=require(process.argv[1]);const out=S.stampManufacturing(JSON.parse(process.argv[2]),JSON.parse(process.argv[3]));"
          "process.stdout.write(JSON.stringify(out))")
    out = json.loads(subprocess.run(["node", "-e", js, str(ROOT / "docs" / "screens.js"), json.dumps(sites), json.dumps(facilities)],
                                    capture_output=True, text=True, check=True).stdout)
    assert out[0]["mfg_turbine_name"] == "Near"
    assert out[0]["mfg_turbine_mi"] == pytest.approx(_haversine(35.0, -82.0, 34.85, -82.39), abs=0.06)
    # Alaska is measured from its real point, not the inset box.
    assert out[1]["mfg_turbine_mi"] == pytest.approx(min(_haversine(61.2, -149.9, 34.85, -82.39),
                                                         _haversine(61.2, -149.9, 42.8, -73.9)), abs=0.06)
    assert out[0]["mfg_robotics_mi"] is None                       # no plant of that sector: unknown, not zero


def test_build_merges_one_plant_reported_by_two_topics(tmp_path, monkeypatch):
    plant = {"name": "Syrah Vidalia anode plant", "company": "Syrah Technologies", "product": "graphite anode", "status": "operating",
             "city": "Vidalia", "state": "LA", "source_url": "https://example.com/plant", "quote": "the Vidalia plant makes anode material"}
    award = {**plant, "name": "Syrah Technologies Vidalia facility", "source_url": "https://example.com/award",
             "quote": "DOE grant of up to $220 million for Vidalia",
             "doe_award": {"program": "Battery Materials Processing", "agency": "DOE", "amount_usd": 220e6}}
    row = lambda r: {"kind": "facility", "index": 0, "row": r, "status": "accepted"}
    work = tmp_path / "work"; work.mkdir()
    (work / "adjudicated.json").write_text(json.dumps({"minerals": [row(plant)], "doe_awards": [row(award)]}))
    monkeypatch.setattr(mc, "WORK", work)
    monkeypatch.setattr(mc, "OUTPUT", tmp_path / "out.json")
    monkeypatch.setattr(mc, "_gazetteer", lambda: {("LA", "Vidalia town"): (31.56, -91.43)})
    assert mc.cmd_build(None) == 0
    out = json.loads((tmp_path / "out.json").read_text())
    assert out["count"] == 1
    s = out["sites"][0]
    assert s["source_url"] == "https://example.com/plant" and s["award_source_url"] == "https://example.com/award"
    assert s["federal_award"]["amount_usd"] == 220e6
