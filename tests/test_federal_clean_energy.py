import json
import unittest
from pathlib import Path

from scripts.build_federal_clean_energy_sites import FEDERAL_SITES_CATALOG

ROOT = Path(__file__).resolve().parent.parent


class TestFederalCleanEnergy(unittest.TestCase):
    def test_federal_sites_catalog_sanity(self):
        self.assertGreaterEqual(len(FEDERAL_SITES_CATALOG), 8)
        for site in FEDERAL_SITES_CATALOG:
            self.assertIn("site_id", site)
            self.assertIn("site_name", site)
            self.assertIn(site["managing_office"], ("DOE-EM", "DOE-OCED"))
            self.assertIn("latitude", site)
            self.assertTrue(20 <= site["latitude"] <= 55)
            self.assertTrue(-130 <= site["longitude"] <= -65)
            self.assertGreater(site["available_acreage"], 0)
            self.assertIsInstance(site["target_technologies"], list)
            self.assertGreater(len(site["target_technologies"]), 0)
            self.assertIn(site["program_stage"], ("RFI_Issued", "RFQ_Awarded", "Pre_Application", "Negotiations", "Lease_Executed"))
            self.assertIsInstance(site["key_advantages"], list)
            self.assertGreater(len(site["key_advantages"]), 0)

    def test_federal_clean_energy_json(self):
        path = ROOT / "docs" / "data" / "federal-clean-energy.json"
        self.assertTrue(path.exists(), "federal-clean-energy.json missing")

        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["count"], len(data["sites"]))
        self.assertGreaterEqual(data["count"], 8)

        for site in data["sites"]:
            self.assertTrue(site["site_id"])
            self.assertTrue(site["site_name"])
            self.assertGreaterEqual(site["available_acreage"], 100)


if __name__ == "__main__":
    unittest.main()
