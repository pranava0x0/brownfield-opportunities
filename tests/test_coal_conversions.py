"""Tests for coal conversions dataset and spatial proximity index.

Verifies:
  - Coal conversion catalog assets have valid structures, coordinates, and capacities
  - Stranded asset valuation formula accounts for grid, water, rail, and distance decay
  - Proximity index matches sites within radius
  - Output files exist and adhere to schema
"""
import json
import unittest
from pathlib import Path

from scripts.build_coal_conversions import (
    COAL_PLANTS_CATALOG,
    calculate_stranded_asset_valuation,
)

ROOT = Path(__file__).resolve().parent.parent


class TestCoalConversions(unittest.TestCase):
    def test_coal_catalog_sanity(self):
        self.assertGreaterEqual(len(COAL_PLANTS_CATALOG), 15)
        for plant in COAL_PLANTS_CATALOG:
            self.assertIn("plant_name", plant)
            self.assertIn("latitude", plant)
            self.assertTrue(20 <= plant["latitude"] <= 55)
            self.assertTrue(-130 <= plant["longitude"] <= -60)
            self.assertGreaterEqual(plant["nameplate_coal_mw"], 100.0)
            self.assertIn(plant["switchyard_kv"], (69.0, 115.0, 138.0, 161.0, 230.0, 345.0, 500.0, 765.0))
            self.assertIsInstance(plant["has_water_intake"], bool)
            self.assertIsInstance(plant["has_rail"], bool)

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

        prox = json.loads(prox_path.read_text(encoding="utf-8"))
        self.assertEqual(prox["count"], len(prox["matches"]))
        self.assertGreater(prox["count"], 0)

        for match in prox["matches"]:
            self.assertIn("id", match)
            self.assertIn("coal_conversion_plant_name", match)
            self.assertLessEqual(match["coal_conversion_plant_mi"], 10.0)
            self.assertGreaterEqual(match["coal_conversion_mw"], 100.0)
            self.assertGreater(match["coal_conversion_stranded_val_usd"], 0)
            if match["coal_conversion_plant_mi"] <= 1.5:
                self.assertTrue(match["coal_conversion_queue_fasttrack"])


if __name__ == "__main__":
    unittest.main()
