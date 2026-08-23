"""Tests for coal conversions dataset and spatial proximity index.

Verifies:
  - Coal conversion catalog assets have valid structures, coordinates, capacities,
    and the per-row provenance pair (source_url + verified_at) the spec requires
  - Status vocabulary matches schema.CoalConversionAsset and years cohere with status
  - Stranded asset valuation formula accounts for grid, water, rail, and distance decay
  - queue_transfer_eligible is DERIVED (never true for an operating plant)
  - Proximity index matches sites within radius; fasttrack flag derives from
    distance AND plant eligibility
  - Output files exist and adhere to schema
"""
import json
import re
import unittest
from pathlib import Path

from scripts.build_coal_conversions import (
    COAL_PLANTS_CATALOG,
    build_assets,
    calculate_stranded_asset_valuation,
)

ROOT = Path(__file__).resolve().parent.parent

VALID_STATUSES = {"operating", "retired", "planned_retirement", "converted_gas"}
KV_CLASSES = (69.0, 115.0, 138.0, 161.0, 230.0, 345.0, 500.0, 765.0)


class TestCoalConversions(unittest.TestCase):
    def test_coal_catalog_sanity(self):
        self.assertGreaterEqual(len(COAL_PLANTS_CATALOG), 15)
        for plant in COAL_PLANTS_CATALOG:
            self.assertIn("plant_name", plant)
            self.assertIn("latitude", plant)
            self.assertTrue(20 <= plant["latitude"] <= 55)
            self.assertTrue(-130 <= plant["longitude"] <= -60)
            self.assertGreaterEqual(plant["nameplate_coal_mw"], 100.0)
            self.assertIn(plant["switchyard_kv"], KV_CLASSES)
            self.assertIsInstance(plant["has_water_intake"], bool)
            self.assertIsInstance(plant["has_rail"], bool)
            self.assertIn(plant["status"], VALID_STATUSES)

    def test_catalog_provenance_contract(self):
        """Every curated row cites a resolving-looking source and carries an
        audit stamp — the STATE_DC_INCENTIVES discipline (spec 04 §3.1)."""
        for asset in build_assets():
            self.assertTrue(
                asset["source_url"].startswith("https://"),
                f"{asset['plant_name']} missing https source_url",
            )
            self.assertRegex(asset["verified_at"], r"^\d{4}-\d{2}-\d{2}$")

    def test_status_year_coherence(self):
        for asset in build_assets():
            if asset["status"] == "retired":
                self.assertIsNotNone(asset.get("retired_year"), asset["plant_name"])
            if asset["status"] == "planned_retirement":
                self.assertIsNotNone(asset.get("planned_retirement_year"), asset["plant_name"])
            if asset["status"] == "operating":
                self.assertIsNone(asset.get("retired_year"), asset["plant_name"])
                self.assertIsNone(asset.get("planned_retirement_year"), asset["plant_name"])

    def test_queue_eligibility_is_derived(self):
        """POI-reuse eligibility is derived, never hand-set: false for
        operating plants (POI not transferable), for gas conversions, AND for
        retired plants whose POI is occupied by an on-site successor
        (John Sevier / Paradise) — spec 04 §4.2, Codex review P1."""
        for asset in build_assets():
            self.assertEqual(
                asset["queue_transfer_eligible"],
                asset["status"] in ("retired", "planned_retirement")
                and not asset.get("poi_occupied", False),
                asset["plant_name"],
            )
        by_name = {a["plant_name"]: a for a in build_assets()}
        self.assertFalse(by_name["John Sevier Fossil Plant"]["queue_transfer_eligible"])
        self.assertFalse(by_name["Paradise Fossil Plant"]["queue_transfer_eligible"])

    def test_stranded_asset_valuation(self):
        val_0 = calculate_stranded_asset_valuation(1000.0, has_water=True, has_rail=True, distance_mi=0.0)
        self.assertEqual(val_0, 225_000_000.0)

        val_no_infra = calculate_stranded_asset_valuation(1000.0, has_water=False, has_rail=False, distance_mi=0.0)
        self.assertEqual(val_no_infra, 188_000_000.0)

        val_2 = calculate_stranded_asset_valuation(1000.0, has_water=True, has_rail=True, distance_mi=2.0)
        self.assertTrue(135_000_000.0 < val_2 < 140_000_000.0)

    def test_coal_conversions_data_files(self):
        catalog_path = ROOT / "docs" / "data" / "coal-conversions.json"
        prox_path = ROOT / "docs" / "data" / "coal-conversions-proximity.json"

        self.assertTrue(catalog_path.exists(), "coal-conversions.json missing")
        self.assertTrue(prox_path.exists(), "coal-conversions-proximity.json missing")

        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(catalog["count"], len(catalog["assets"]))
        self.assertGreaterEqual(catalog["count"], 15)
        eligible_by_name = {
            a["plant_name"]: a["queue_transfer_eligible"] for a in catalog["assets"]
        }

        prox = json.loads(prox_path.read_text(encoding="utf-8"))
        self.assertEqual(prox["count"], len(prox["matches"]))
        self.assertGreater(prox["count"], 0)

        for match in prox["matches"]:
            self.assertIn("id", match)
            self.assertIn("coal_conversion_plant_name", match)
            self.assertLessEqual(match["coal_conversion_plant_mi"], 10.0)
            self.assertGreaterEqual(match["coal_conversion_mw"], 100.0)
            self.assertGreater(match["coal_conversion_stranded_val_usd"], 0)
            want_fasttrack = (
                match["coal_conversion_plant_mi"] <= 1.5
                and eligible_by_name.get(match["coal_conversion_plant_name"], False)
            )
            self.assertEqual(match["coal_conversion_queue_fasttrack"], want_fasttrack, match["id"])

    def test_sweep_corrections_hold(self):
        """Regression-pin the facts the 2026-08 industry sweep corrected —
        these shipped wrong once (research/industry-topical-2026-08.md §T5)."""
        by_name = {a["plant_name"]: a for a in build_assets()}
        # Colstrip is a life-extension asset, not a retirement.
        colstrip = by_name["Colstrip Steam Plant"]
        self.assertEqual(colstrip["status"], "operating")
        self.assertNotIn("planned_retirement_year", colstrip)
        # Cumberland too: TVA's board voted 2026-02-11 to keep it running
        # past the scheduled dates (domain review 2026-08-23).
        cumberland = by_name["Cumberland Fossil Plant"]
        self.assertEqual(cumberland["status"], "operating")
        self.assertNotIn("planned_retirement_year", cumberland)
        self.assertFalse(cumberland["queue_transfer_eligible"])
        # Montour is a completed coal-to-gas conversion.
        self.assertEqual(by_name["Montour Steam Electric Station"]["status"], "converted_gas")
        # The Natrium town is Kemmerer, never "Kemper".
        self.assertTrue(any("Kemmerer" in n for n in by_name))
        self.assertFalse(any(re.search(r"Kemper\b", n) for n in by_name))


if __name__ == "__main__":
    unittest.main()
