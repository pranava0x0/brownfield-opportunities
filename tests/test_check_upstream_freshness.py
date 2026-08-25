"""Pure-logic tests for scripts/check_upstream_freshness.py (no network)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_upstream_freshness.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_upstream_freshness", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_registry_covers_every_infra_layer_and_producer():
    mod = _load()
    names = {s["name"] for s in mod.SOURCES}
    for expected in (
        "superfund-npl", "epa-acres", "dod-fuds (layer 1)", "dod-brac",
        "epa-redev", "transmission (HIFLD)", "gas pipelines (HIFLD)",
        "power plants (HIFLD)", "substations (OSM Overpass)",
        "flood zones (FEMA NFHL)", "opportunity zones (HUD)",
        "FEMA NRI counties", "EIA-860M workbook",
    ):
        assert expected in names, f"registry missing {expected}"
    # Sources with no exposed edit date must SAY so, never silently skip.
    for s in mod.SOURCES:
        if s["kind"] == "none":
            assert s.get("note"), f"{s['name']}: kind=none needs an explanatory note"


def test_verdict_logic(monkeypatch):
    mod = _load()
    today = dt.date(2026, 8, 24)

    def run(kind, ours, upstream, error=False):
        src = {"name": "x", "file": "x.json", "kind": kind, "url": "https://example.test/x"}
        monkeypatch.setattr(mod, "our_date", lambda f: ours)
        if kind == "arcgis":
            if error:
                monkeypatch.setattr(mod, "arcgis_last_edit", lambda u: (_ for _ in ()).throw(RuntimeError("boom")))
            else:
                monkeypatch.setattr(mod, "arcgis_last_edit", lambda u: upstream)
        return mod.check_source(src, today)

    # Upstream newer than ours -> STALE
    assert run("arcgis", dt.date(2026, 5, 12), dt.date(2026, 8, 22))["verdict"] == "STALE"
    # Ours newer or equal -> current
    assert run("arcgis", dt.date(2026, 8, 22), dt.date(2026, 8, 22))["verdict"] == "current"
    # No upstream signal (incl. errors) -> UNKNOWN, never current
    assert run("none", dt.date(2026, 5, 12), None)["verdict"] == "UNKNOWN"
    assert run("arcgis", dt.date(2026, 5, 12), None, error=True)["verdict"] == "UNKNOWN"
    # Upstream exists but we have no stamp -> STALE (we must pull)
    assert run("arcgis", None, dt.date(2026, 8, 22))["verdict"] == "STALE"


def test_eia_workbook_month_reads_the_connector_url_not_generated_at():
    """First live run hid a real staleness: our generated_at (a June re-run)
    postdated the May workbook, but the connector PARSES the April workbook.
    The comparison must use the workbook month in EIA_860M_URL."""
    mod = _load()
    month = mod.our_eia_workbook_month()
    assert month is not None
    assert month.day == 1
    # Must match the month named in the connector source, not any file date.
    src = (ROOT / "connectors" / "eia_retired_plants.py").read_text()
    assert f"{mod._EIA_MONTHS[month.month - 1]}_generator{month.year}.xlsx" in src
