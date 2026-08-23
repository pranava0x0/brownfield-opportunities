# Spec 08: DOE "Cleanup to Clean Energy" & Mine Land (CEML) Federal Portfolio Overlay

**Status:** Proposed  
**Priority:** Medium (Impact: 4/5, Size: 2/5, Completeness: 5/5)  
**Target Version:** v1.15.0  
**Lead Component:** `scripts/build_federal_clean_energy_sites.py`, `docs/data/federal-clean-energy.json`, `docs/app.js`

---

## 1. Executive Summary & Value Proposition

Under the Department of Energy's **"Cleanup to Clean Energy"** initiative (managed by the Office of Environmental Management / EM) and the **"Clean Energy on Mine Lands" (CEML)** demonstration program (managed by the Office of Clean Energy Demonstrations / OCED), the federal government is leasing hundreds of thousands of acres of legacy nuclear weapons complex land and former mining lands for gigawatt-scale clean energy generation, advanced nuclear deployments, and AI data centers.

Key anchor installations include:
- **Savannah River Site (SRS)**, South Carolina (Amentum partnership: 1 GW data center + ~2 GW clean generation).
- **Idaho National Laboratory (INL)**, Idaho (Advanced nuclear testing grounds, SMR pilots).
- **Hanford Site**, Washington (~8,000 acres released for clean energy).
- **Waste Isolation Pilot Plant (WIPP)**, New Mexico.
- **Nevada National Security Site (NNSS)**, Nevada.
- Large-scale Appalachian & Western surface coal mine lands (OSMRE / BLM AML inventory).

Currently, these high-priority federal initiatives are referenced only in narrative notes. This initiative establishes a first-class curated dataset (`docs/data/federal-clean-energy.json`) and interactive map layer, joining them with our infrastructure proximity index.

---

## 2. Dataset Schema & Curated Portfolio

```python
class FederalCleanEnergySite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    site_id: str = Field(description="Unique identifier e.g. 'doe-em-srs'")
    site_name: str
    managing_office: Literal["DOE-EM", "DOE-OCED", "BLM", "OSMRE", "DOD-AFCEC", "DOD-ANPI"]
    state: str = Field(min_length=2, max_length=2)
    county: str
    latitude: float
    longitude: float
    available_acreage: float = Field(ge=0.0)
    target_technologies: list[Literal["nuclear_smr", "nuclear_micro", "datacenter_ai", "solar_utility", "battery_storage", "geothermal"]]
    program_stage: Literal["RFI_Issued", "RFQ_Awarded", "Lease_Executed", "Pre_Application", "Construction"]
    commercial_partner: Optional[str] = None
    solicitation_url: HttpUrl
    nepa_review_document_url: Optional[HttpUrl] = None
    key_advantages: list[str]
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
