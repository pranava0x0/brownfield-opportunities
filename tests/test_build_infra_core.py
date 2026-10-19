"""The startup infrastructure file is an exact subset of the full one."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_infra_core import CORE_FIELDS, core_payload  # noqa: E402


def test_core_keeps_distances_and_drops_asset_catalogs():
    full = {"generated_at": "2026-10-18", "source_metadata": {"transmission": {"source_url": "u", "assets_by_id": {"x": {}}}, "pending": ["a"]},
            "sites": [{"id": "S1", "program": "superfund", "transmission_mi": 1.2, "transmission_kv": 138.0,
                       "transmission_asset_id": "x", "infra_evidence": {"k": 1}, "in_sfha": False}]}
    core = core_payload(full)
    assert core["sites"] == [{"id": "S1", "transmission_mi": 1.2, "transmission_kv": 138.0, "in_sfha": False}]
    assert core["source_metadata"] == {"transmission": {"source_url": "u"}, "pending": ["a"]}
    assert core["generated_at"] == "2026-10-18"
    assert "in_sfha" in CORE_FIELDS
