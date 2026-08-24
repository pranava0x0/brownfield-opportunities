# Spec 08: DOE "Cleanup to Clean Energy" & Mine Land (CEML) Federal Portfolio Overlay

**Status:** v1 shipped 2026-08-23 (10-site curated overlay + map layer); facts re-verified same day against the [2026-08 industry sweep](../../research/industry-topical-2026-08.md)  
**Priority:** Medium (Impact: 4/5, Size: 2/5, Completeness: 5/5)  
**Target Version:** v1.15.0  
**Lead Component:** `scripts/build_federal_clean_energy_sites.py`, `docs/data/federal-clean-energy.json`, `docs/app.js`

---

## 1. Executive Summary & Value Proposition

Under the Department of Energy's **"Cleanup to Clean Energy"** initiative (Office of Environmental Management / EM), the **AI-data-centers-on-federal-land site selections** (Jul 2025 →), and the **"Clean Energy on Mine Lands" (CEML)** demonstration program (Office of Clean Energy Demonstrations / OCED), the federal government is leasing hundreds of thousands of acres of legacy nuclear weapons complex land and former mining lands for gigawatt-scale clean energy generation, advanced nuclear deployments, and AI data centers.

Anchor facts as of 2026-08 (each row in the dataset carries its own `source_url` + `verified_at`):
- **Paducah Gaseous Diffusion Plant (KY)** — DOE selected **Brookfield Asset Management** (Jul 2026) to develop the AI/HPC campus; **NextEra** to build **2 GW of new gas generation, transmission upgrades, and up to 2.6 GW of BESS** supporting a **1.8-GW** campus. The furthest-along award.
- **Savannah River Site (SC)** — **Amentum** selected to negotiate the lease for an AI data center + on-site power.
- **Idaho National Laboratory** and **Oak Ridge Reservation (ETTP)** — the other two of the four Jul-2025 flagship selections; ORR also hosts Kairos Hermes (lease executed via CROET).
- **Portsmouth (OH)** — parallel announcement Mar 2026 (not one of the four flagships).
- **Hanford, WIPP, NNSS** — the original 2023 Cleanup-to-Clean-Energy five (with INL and SRS); NNSS is **NNSA-managed** (label it so — not DOE-EM).
- **CEML mine-lands awards** — **Mineral Basin Solar** (Swift Current, 402 MW, ~2,700 ac, Clearfield County PA) and **Lewis Ridge** (**Rye Development, 266 MW pumped-storage hydro** per the FERC Final License Application (earlier filings said 287 MW) — *not* solar, *not* EDF; FLA filed 2025, EIS NOI May 2026).

Currently, these high-priority federal initiatives are referenced only in narrative notes. This initiative establishes a first-class curated dataset (`docs/data/federal-clean-energy.json`) and interactive map layer, joining them with our infrastructure proximity index.

**Re-audit cadence:** quarterly. These programs move on political timelines (the Jul-2026 Paducah
award landed 12 months after site selection), and program branding may change with administrations —
verify the solicitation URLs still resolve at each audit (the evidence-panel rule: a citation must
resolve to the claim).

---

## 2. Dataset Schema & Curated Portfolio

```python
class FederalCleanEnergySite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    site_id: str = Field(description="Unique identifier e.g. 'doe-em-srs'")
    site_name: str
    managing_office: Literal["DOE-EM", "DOE-NNSA", "DOE-OCED", "BLM", "OSMRE", "DOD-AFCEC", "DOD-ANPI"]
    state: str = Field(min_length=2, max_length=2)
    county: str
    latitude: float
    longitude: float
    available_acreage: float = Field(ge=0.0)
    target_technologies: list[Literal["nuclear_smr", "nuclear_micro", "datacenter_ai", "solar_utility", "battery_storage", "pumped_storage", "geothermal", "advanced_mfg", "gas_generation"]]
    program_stage: Literal["RFI_Issued", "RFQ_Awarded", "Lease_Executed", "Pre_Application", "Construction"]
    commercial_partner: Optional[str] = None
    solicitation_url: HttpUrl        # must be a real, resolving URL — never a guessed slug
    nepa_review_document_url: Optional[HttpUrl] = None
    key_advantages: list[str]
    verified_at: str                 # REQUIRED YYYY-MM-DD per-row audit stamp
```

---

## 3. UI/UX Integration

1. **Dedicated Map Marker & Overlay**:
   - Distinctive federal clean energy marker symbol (🏛 / ⚡) rendered on the map.
   - Click opens detailed modal with acreage, target technology mix, solicitation deadlines, and SAM.gov / DOE solicitation deep links.
2. **Tab Integration**:
   - Appears in both the **Data Center Candidates** and **Nuclear Siting** tabs as first-class scored rows.

---

## 4. Verification Plan

- **Schema Validation (`scripts/validate_data.py`)**:
  - Validates `docs/data/federal-clean-energy.json` against `FederalCleanEnergySite`.
- **E2E Playwright Tests (`tests/e2e/test_federal_sites.py`)**:
  - Verifies all 10+ federal flagship sites render with accurate acreage and functional solicitation URLs.
