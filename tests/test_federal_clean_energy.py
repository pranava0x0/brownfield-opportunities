"""Tests for the federal clean energy sites overlay (Spec 08).

The value-domain tuples below mirror schema.FederalCleanEnergySite's Literals
— if the schema gains a value, update both together (the build script
validates against the schema, so drift fails the build before it fails here).
"""
import json
import unittest
from pathlib import Path

from scripts.build_federal_clean_energy_sites import FEDERAL_SITES_CATALOG, build_sites

ROOT = Path(__file__).resolve().parent.parent

VALID_OFFICES = ("DOE-EM", "DOE-NNSA", "DOE-OCED", "BLM", "OSMRE", "DOD-AFCEC", "DOD-ANPI")
VALID_STAGES = ("RFI_Issued", "RFQ_Awarded", "Lease_Executed", "Pre_Application", "Construction")


class TestFederalCleanEnergy(unittest.TestCase):
    def test_federal_sites_catalog_sanity(self):
        self.assertGreaterEqual(len(FEDERAL_SITES_CATALOG), 8)
        for site in FEDERAL_SITES_CATALOG:
            self.assertIn("site_id", site)
            self.assertIn("site_name", site)
            self.assertIn(site["managing_office"], VALID_OFFICES)
            self.assertIn("latitude", site)
            self.assertTrue(20 <= site["latitude"] <= 55)
            self.assertTrue(-130 <= site["longitude"] <= -65)
            self.assertGreater(site["available_acreage"], 0)
            self.assertIsInstance(site["target_technologies"], list)
            self.assertGreater(len(site["target_technologies"]), 0)
            self.assertIn(site["program_stage"], VALID_STAGES)
            self.assertIsInstance(site["key_advantages"], list)
            self.assertGreater(len(site["key_advantages"]), 0)

    # The two guessed slugs the v1 draft shipped — both 404'd. Pinned so the
    # regression is impossible to reintroduce silently (URL liveness itself
    # is checked network-side by scripts/pr_gate.sh step 3).
    KNOWN_DEAD_URLS = {
        "https://www.energy.gov/em/cleanup-clean-energy",
        "https://www.energy.gov/oced/clean-energy-demonstrations-current-and-former-mine-land",
    }

    def test_provenance_contract(self):
        """Every row cites a REAL solicitation URL and carries an audit stamp;
        the v1 draft's two fabricated energy.gov slugs must never return."""
        for site in build_sites():
            self.assertTrue(site["solicitation_url"].startswith("https://"), site["site_id"])
            self.assertNotIn(site["solicitation_url"], self.KNOWN_DEAD_URLS, site["site_id"])
            self.assertNotIn(site.get("nepa_review_document_url"), self.KNOWN_DEAD_URLS, site["site_id"])
            self.assertRegex(site["verified_at"], r"^\d{4}-\d{2}-\d{2}$")

    def test_sweep_corrections_hold(self):
        """Regression-pin the 2026-08 sweep corrections (§T6)."""
        by_id = {s["site_id"]: s for s in build_sites()}
        # Paducah's Jul-2026 award: Brookfield develops, NextEra powers.
        self.assertEqual(by_id["doe-em-paducah"]["program_stage"], "RFQ_Awarded")
        self.assertIn("Brookfield", by_id["doe-em-paducah"]["commercial_partner"])
        # Lewis Ridge is Rye Development's PUMPED STORAGE project, not solar.
        lr = by_id["doe-oced-lewis-ridge"]
        self.assertIn("pumped_storage", lr["target_technologies"])
        self.assertNotIn("solar_utility", lr["target_technologies"])
        self.assertIn("Rye Development", lr["commercial_partner"])
        # NNSS is NNSA-managed.
        self.assertEqual(by_id["doe-nnsa-nnss"]["managing_office"], "DOE-NNSA")

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
