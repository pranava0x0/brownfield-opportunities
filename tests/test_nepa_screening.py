"""Unit tests for the shared nepa-mcp screening machinery.

Runs on the project's Python 3.9 floor — nepa_screening only imports
nepa-mcp inside functions, so everything here exercises the pure logic
(normalizers, caching, failure isolation) with fixtures captured from LIVE
nepa-mcp 0.1.1 responses (probed 2026-08-24 at the Columbia Generating
Station point). If an upgrade changes a response shape, update the fixture
AND the normalizer together.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "nepa_screening.py"


def _load():
    spec = importlib.util.spec_from_file_location("nepa_screening", MODULE)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def screening():
    return _load()


# ---------------------------------------------------------------------------
# Normalizers — fixtures mirror the live 0.1.1 response shapes.
# ---------------------------------------------------------------------------

def test_noaa_normalizer_keeps_listing_entities(screening):
    live_shape = {
        "total": 2,
        "species_count": 2,
        "designation_count": 2,
        "habitats": [
            {
                "common_name": "Salmon, Chinook",
                "listed_entity": "Salmon, Chinook [Upper Columbia River spring-run ESU]",
                "listing_status": "Endangered",
                "ch_status": "Final",
            }
        ],
        "warnings": [],
    }
    out = screening.normalize_noaa_habitat(live_shape)
    assert out["count"] == 2
    assert out["habitats"][0]["listing_status"] == "Endangered"
    assert out["species_count"] == 2


def test_efh_normalizer_uses_watershed_rows(screening):
    live_shape = {
        "total": 2,
        "watersheds": [
            {"huc_8": 17030003, "huc_8_name": "Lower Yakima", "chinook_efh": "Yes", "coho_efh": "Yes"}
        ],
        "warnings": [],
    }
    out = screening.normalize_efh_salmon(live_shape)
    assert out["count"] == 2
    assert out["watersheds"][0]["huc_8_name"] == "Lower Yakima"


def test_flood_normalizer_distinguishes_unmapped_from_flood_free(screening):
    """Zero zones must survive as an explicit count (much of Hanford is
    simply unmapped in NFHL) — never be dropped or coerced to a claim."""
    live_shape = {
        "total_zones": 0,
        "zones": [],
        "summary": {"sfha_count": 0, "sfha_percentage": 0.0, "zone_counts": {}},
        "truncated": False,
        "warnings": [],
    }
    out = screening.normalize_flood_zones(live_shape)
    assert out["count"] == 0
    assert out["sfha_count"] == 0
    assert out["truncated"] is False


def test_gbif_normalizer_summarizes_by_species_not_by_sighting(screening):
    live_shape = {
        "total_occurrences": 5,
        "unique_species": 2,
        "occurrences": [
            {"scientific_name": "Charadrius vociferus", "common_name": ""},
            {"scientific_name": "Charadrius vociferus", "common_name": ""},
            {"scientific_name": "Charadrius vociferus", "common_name": ""},
            {"scientific_name": "Haliaeetus leucocephalus", "common_name": "Bald Eagle"},
            {"scientific_name": "Haliaeetus leucocephalus", "common_name": "Bald Eagle"},
        ],
        "summary": {"by_threat_status": {"NT": 5}},
    }
    out = screening.normalize_gbif(live_shape)
    assert out["occurrence_count"] == 5
    assert out["species_count"] == 2
    # One well-photographed killdeer must not read as many species.
    assert out["top_species"][0]["occurrences"] == 3


def test_usace_normalizer_carries_the_no_jurisdiction_limitation(screening):
    out = screening.normalize_usace(
        {
            "regulatory_districts": {"districts": [{"district_name": "Walla Walla"}]},
            "wetland_regions": {"regions": []},
            "wetland_subregions": {"subregions": []},
        }
    )
    assert "does not show wetland presence" in out["limitation"]
    assert "jurisdictional determination" in out["limitation"]


def test_padus_factory_stamps_its_query_buffer(screening):
    normalize = screening.make_normalize_padus(0.1)
    out = normalize({"total_records": 1, "records": [{"owner_type": "FED", "gis_acres": 5}]})
    assert out["query_buffer_miles"] == 0.1
    assert out["owner_types"] == {"FED": 1}


# ---------------------------------------------------------------------------
# Source matrix runner — caching + failure isolation, no network.
# ---------------------------------------------------------------------------

class _FakeModule:
    """Stands in for a loaded nepa-mcp server module."""

    def __init__(self, fn):
        self.query = fn


def _defs(screening, fn, key="demo", server="demo_server"):
    return [
        screening.SourceDef(
            key, server, "query", lambda d: {"value": d["v"]},
            lambda f, site: f(site["id"]),
        )
    ]


def test_matrix_caches_success_and_reuses_it(tmp_path, screening):
    calls = []

    def fn(site_id):
        calls.append(site_id)
        return {"v": site_id.upper()}

    loader = lambda name: _FakeModule(fn)  # noqa: E731
    cache_fn = lambda sid, key: tmp_path / f"{sid}--{key}.json"  # noqa: E731
    sites = [{"id": "a"}, {"id": "b"}]

    first = screening.run_source_matrix(sites, _defs(screening, fn), cache_fn, True, loader)
    assert first["a"]["demo"]["value"] == "A"
    assert first["a"]["demo"]["status"] == "ok"
    assert calls == ["a", "b"]

    # Second run must be served entirely from disk.
    second = screening.run_source_matrix(sites, _defs(screening, fn), cache_fn, True, loader)
    assert calls == ["a", "b"]
    assert second["b"]["demo"]["value"] == "B"


def test_one_site_failure_never_kills_the_batch(tmp_path, screening):
    def fn(site_id):
        if site_id == "bad":
            raise TimeoutError("upstream stalled")
        return {"v": "ok"}

    loader = lambda name: _FakeModule(fn)  # noqa: E731
    cache_fn = lambda sid, key: tmp_path / f"{sid}--{key}.json"  # noqa: E731
    out = screening.run_source_matrix(
        [{"id": "bad"}, {"id": "good"}], _defs(screening, fn), cache_fn, True, loader
    )
    assert out["bad"]["demo"]["status"] == "unavailable"
    assert "stalled" in out["bad"]["demo"]["error"]
    assert out["good"]["demo"]["status"] == "ok"
    # The failure is cached as explicit unavailability, not silence.
    cached = json.loads((tmp_path / "bad--demo.json").read_text())
    assert cached["status"] == "unavailable"


def test_missing_server_marks_every_site_unavailable(tmp_path, screening):
    def loader(name):
        raise ImportError(f"no server {name}")

    cache_fn = lambda sid, key: tmp_path / f"{sid}--{key}.json"  # noqa: E731
    out = screening.run_source_matrix(
        [{"id": "x"}], _defs(screening, lambda s: {"v": 1}), cache_fn, True, loader
    )
    assert out["x"]["demo"]["status"] == "unavailable"


def test_cache_error_at_persists_explicit_unavailability(tmp_path, screening):
    path = tmp_path / "site--src.json"
    result = screening.cache_error_at(path, RuntimeError("boom"))
    assert result["status"] == "unavailable"
    assert json.loads(path.read_text())["error"] == "boom"


def test_map_package_summary_counts_layer_statuses(screening):
    geojson = {
        "features": [1, 2, 3],
        "metadata": {"layers": {
            "roi": {"status": "ok"},
            "tribal_lands": {"status": "empty"},
            "eis_boundaries": {"status": "failed"},
        }},
    }
    out = screening.summarize_map_package(geojson)
    assert out == {"feature_count": 3, "layers_ok": 2, "layers_partial": 0, "layers_failed": 1}


def test_loader_failure_serves_existing_cache_instead_of_clobbering(tmp_path, screening):
    """A transient server-load failure must never overwrite previously
    collected evidence with 'unavailable' (Codex PR #22 round 2, P1)."""
    good = {"value": "evidence", "status": "ok", "retrieved_at": "2026-08-24T00:00:00Z"}
    cached_path = tmp_path / "a--demo.json"
    cached_path.write_text(json.dumps(good))

    def loader(name):
        raise ImportError("uv env broke this run")

    cache_fn = lambda sid, key: tmp_path / f"{sid}--{key}.json"  # noqa: E731
    out = screening.run_source_matrix(
        [{"id": "a"}, {"id": "b"}],
        _defs(screening, lambda s: {"v": 1}),
        cache_fn, True, loader,
    )
    # Site with prior evidence keeps it — on disk AND in the result.
    assert out["a"]["demo"] == good
    assert json.loads(cached_path.read_text()) == good
    # Site with nothing yet records explicit unavailability.
    assert out["b"]["demo"]["status"] == "unavailable"


def test_corrupt_cache_is_a_miss_not_a_permanent_unavailable(tmp_path, screening):
    """A truncated cache file (killed mid-write, pre-atomic caches) must
    degrade to 'query again', not to a cached parse error (round 2, P2)."""
    path = tmp_path / "a--demo.json"
    path.write_text('{"value": "evide')  # truncated JSON
    calls = []

    def fn(site_id):
        calls.append(site_id)
        return {"v": "fresh"}

    loader = lambda name: _FakeModule(fn)  # noqa: E731
    cache_fn = lambda sid, key: tmp_path / f"{sid}--{key}.json"  # noqa: E731
    out = screening.run_source_matrix([{"id": "a"}], _defs(screening, fn), cache_fn, True, loader)
    assert calls == ["a"]  # re-queried despite a cache file being present
    assert out["a"]["demo"]["status"] == "ok"
    assert json.loads(path.read_text())["value"] == "A" or json.loads(path.read_text())["status"] == "ok"


def test_cache_writes_are_atomic_no_tmp_leftovers(tmp_path, screening):
    path = tmp_path / "x--demo.json"
    screening.cache_error_at(path, RuntimeError("boom"))
    assert path.exists()
    assert not list(tmp_path.glob("*.tmp")), "atomic write left a temp file behind"
