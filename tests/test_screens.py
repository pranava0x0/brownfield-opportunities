"""Siting screens (docs/screens.js): missing data never passes, ranks are
reproducible, and every threshold names its source."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def node(expr: str, *args):
    script = "const S=require('./docs/screens.js'); const a=process.argv.slice(1).map(JSON.parse); console.log(JSON.stringify(" + expr + "));"
    out = subprocess.run(["node", "-e", script, *map(json.dumps, args)], cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def evaluate(site, key):
    return node("S.evaluate(a[0], a[1])", site, key)


def test_empty_site_is_all_unknown_never_pass():
    for key in node("Object.keys(S.SCREENS)"):
        ev = evaluate({}, key)
        assert ev["met"] == 0, key
        assert all(r["status"] in ("unknown", "fail") for r in ev["results"]), key


def test_line_without_voltage_is_unknown_not_pass():
    ev = evaluate({"transmission_mi": 0.5}, "dc")
    assert next(r for r in ev["results"] if r["id"] == "grid")["status"] == "unknown"
    ev = evaluate({"transmission_mi": 0.5, "transmission_kv": 69}, "dc")
    assert next(r for r in ev["results"] if r["id"] == "grid")["status"] == "fail"
    ev = evaluate({"transmission_mi": 7, "transmission_kv": 500}, "dc")
    assert next(r for r in ev["results"] if r["id"] == "grid")["status"] == "fail"


def test_line_check_uses_nearest_qualifying_line_not_nearest_line():
    grid = lambda site, key="dc": next(r for r in evaluate(site, key)["results"] if r["id"] == "grid")
    # Nearest line is 69 kV, but a 230 kV line is 2 mi away: the ≥115 kV check passes.
    site = {"transmission_mi": 0.4, "transmission_kv": 69, "transmission_115kv_mi": 2.0}
    assert grid(site)["status"] == "pass" and grid(site)["value"] == "115+ kV · 2.0 mi"
    # No qualifying line within 5 mi, and every nearer line has a voltage: fail.
    assert grid({"transmission_mi": 0.4, "transmission_kv": 69, "transmission_115kv_mi": 8.0})["status"] == "fail"
    # A line with no reported voltage inside the radius could qualify: unknown.
    site = {"transmission_mi": 0.4, "transmission_kv": 69, "transmission_115kv_mi": 8.0, "transmission_unknown_kv_mi": 3.0}
    assert grid(site)["status"] == "unknown"


def test_coal_line_check_reads_line_fields():
    plant = {"line_mi": 0.3, "line_kv": 115, "line_230kv_mi": 1.5}
    ev = evaluate(plant, "coal")
    assert next(r for r in ev["results"] if r["id"] == "grid")["status"] == "pass"


def test_flagged_acreage_counts_as_unknown():
    big = {"acreage": 310173}
    assert next(r for r in evaluate(big, "solar")["results"] if r["id"] == "land")["status"] == "pass"
    flagged = {"acreage": 310173, "acreage_flag": "county_outline"}
    assert next(r for r in evaluate(flagged, "solar")["results"] if r["id"] == "land")["status"] == "unknown"


def test_parcel_acreage_fills_missing_site_acreage():
    ev = evaluate({"parcel_acreage": 40}, "solar")
    assert next(r for r in ev["results"] if r["id"] == "land")["status"] == "pass"


def test_rank_orders_by_met_then_unknown_then_tiebreak():
    sites = [
        {"id": "a", "name": "A", "acreage": 50},                                         # 1 met, 3 unknown
        {"id": "b", "name": "B", "acreage": 50, "transmission_mi": 1, "transmission_kv": 115,
         "highway_mi": 1, "in_sfha": False},                                              # 4 met
        {"id": "c", "name": "C", "acreage": 500, "transmission_mi": 1, "transmission_kv": 115,
         "highway_mi": 1, "in_sfha": False},                                              # 4 met, larger
        {"id": "d", "name": "D", "acreage": 10, "transmission_mi": 1, "transmission_kv": 115},  # 1 met, 1 fail
    ]
    order = node("S.rank(a[0],'solar').map(r=>r.site.id)", sites)
    assert order == ["c", "b", "a", "d"] or order == ["c", "b", "d", "a"]
    assert order[:2] == ["c", "b"]  # solar tie-break: larger acreage first


def test_every_criterion_cites_an_https_source_and_a_kind():
    specs = node("Object.values(S.SCREENS).map(s=>({k:s.key,tb:s.tieBreak&&s.tieBreak.label,c:s.criteria.map(c=>({id:c.id,kind:c.kind,url:c.source.url,title:c.source.title,rule:c.rule}))}))")
    for spec in specs:
        assert spec["tb"], spec["k"]
        assert 2 <= len(spec["c"]) <= 6, spec["k"]
        for c in spec["c"]:
            assert c["kind"] in ("R", "P"), (spec["k"], c["id"])
            assert c["url"].startswith("https://"), (spec["k"], c["id"])
            assert c["title"] and c["rule"], (spec["k"], c["id"])


def test_cli_counts_are_deterministic():
    run = lambda: subprocess.run(["node", "scripts/screen.js", "counts"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    first = run()
    assert first == run()
    assert "dc" in first and "solar" in first


def test_army_selection_drives_the_microreactor_screen():
    sites = json.loads((ROOT / "docs/data/ap1000-sites.json").read_text())["sites"]
    ranked = node("S.rank(a[0],'micro').map(r=>[r.site.id, r.ev.results[0].status])", sites)
    assert len(ranked) == 9  # the Janus candidates only
    selected = {sid for sid, status in ranked if status == "pass"}
    assert selected == {"fort-bragg-nc", "fort-campbell-ky", "fort-hood-tx", "fort-benning-ga", "fort-drum-ny"}
    assert [sid for sid, _ in ranked[:5]] and set(sid for sid, _ in ranked[:5]) == selected


def test_parcel_area_still_counts_when_program_acreage_is_flagged():
    ev = evaluate({"acreage": 310173, "acreage_flag": "county_outline", "parcel_acreage": 40}, "solar")
    land = next(r for r in ev["results"] if r["id"] == "land")
    assert land["status"] == "pass" and land["value"] == "40 ac"


def test_parcel_area_does_not_count_for_a_shared_geocode():
    # The parcel under a point shared by many sites is not any one site's parcel.
    ev = evaluate({"parcel_acreage": 40, "coord_flags": ["shared_point"]}, "solar")
    land = next(r for r in ev["results"] if r["id"] == "land")
    assert land["status"] == "unknown" and land["value"] == "location approximate"
