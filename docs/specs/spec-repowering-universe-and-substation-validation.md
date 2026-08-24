# Spec 06: EPA RE-Powering 190,000-Site Screened Universe & Substation Validation Join

**Status:** Proposed  
**Priority:** High (Impact: 4/5, Size: 3/5, Completeness: 4/5)  
**Target Version:** v1.15.0  
**Lead Component:** `connectors/repowering_universe.py`, `scripts/validate_against_sources.py`, `docs/app.js`

---

## 1. Executive Summary & Value Proposition

Currently, our platform integrates only the **1,905-record** `RedevelopmentAppSitePoints` layer from EPA's RE-Powering America's Land initiative, which covers Superfund and prominent brownfield redevelopment sites. However, EPA also publishes a comprehensive screening dataset of over **190,000 contaminated sites, landfills, mine sites, and RCRA/brownfield parcels** evaluated for renewable energy, energy storage, and industrial re-use potential.

This initiative accomplishes two major objectives:
1. **~100x Coverage Expansion & Cross-Program Discovery**: Ingests the full 190k screened site dataset with reported acreages, renewable energy capacity potentials, and state incentives.
2. **Independent Substation Distance Cross-Validation**: The EPA RE-Powering dataset includes EPA's independently measured `distance_to_nearest_substation` field. Joining this dataset across our existing 46,759 sites provides the definitive external ground-truth validation for our HIFLD/OSM spatial index (`substation_mi`), directly addressing the primary external validation gap identified in repository data audits.

---

## 2. Dataset Profile & Architecture

| Attribute | Specification |
|---|---|
| **Upstream Publisher** | US EPA Office of Brownfields and Land Revitalization / NREL |
| **Dataset Source** | EPA RE-Powering Screening Data (XLSX / Esri FileGeodatabase / ArcGIS REST) |
| **Record Count** | 190,000+ screened sites across all 50 states + territories |
| **Key Attributes** | `EPA_ID`, `SITE_NAME`, `PROGRAM`, `ACREAGE`, `LATITUDE`, `LONGITUDE`, `DISTANCE_TO_SUBSTATION_MI`, `SOLAR_MW_POTENTIAL`, `WIND_MW_POTENTIAL`, `BATTERY_STORAGE_FIT` |
| **License** | US Public Domain / Open Government Data |

---

## 3. Data Schema & Contracts

### 3.1 Python Data Schema (`schema.py`)

```python
class EpaRepoweringScreenedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    repowering_site_id: str = Field(description="Unique EPA RE-Powering identifier")
    site_name: str
    program_category: Literal["Superfund", "Brownfields", "RCRA", "Landfill", "Mining", "Abandoned Mine Land", "Other"]
    state: str = Field(min_length=2, max_length=2)
    county: str
    latitude: float
    longitude: float
    screened_acreage: Optional[float] = Field(ge=0.0)
    epa_substation_distance_mi: Optional[float] = Field(ge=0.0)
    solar_utility_mw: Optional[float] = None
    wind_utility_mw: Optional[float] = None
    battery_storage_candidate: bool = False
    clean_energy_on_mine_lands: bool = False
```

### 3.2 Substation Distance Cross-Validation Contract

```python
class SubstationValidationReport(BaseModel):
    total_matched_sites: int
    mean_absolute_difference_mi: float
    p50_difference_mi: float
    p95_difference_mi: float
    agreement_within_0_5_mi_pct: float
    divergent_sites: list[dict]  # Sites where |d_our - d_epa| > 3.0 mi for manual review
```

---

## 4. Implementation Steps

0. **Liveness probe first (2026-08 sweep note).** EPA program pages have been reorganized under the
   current administration (see the HIFLD 2025 migration and `acres6` login-gating precedents in
   CLAUDE.md). Before building the connector, verify the RE-Powering screening dataset is still
   published at its documented location and record the probe in `data-source-research.md` — if the
   XLSX/geodatabase has moved behind a login, this spec's Completeness drops from 4/5 and the spec
   should be re-ranked rather than half-built.
1. **Connector Development (`connectors/repowering_universe.py`)**:
   - Parses the bulk EPA RE-Powering dataset into a compressed parquet / TopoJSON spatial index.
   - Performs a spatial join (tolerance $\le 0.1\text{ mi}$) against our 46,759 corpus to attach `epa_substation_distance_mi` and `solar_utility_mw`.
2. **Validation Integration (`scripts/validate_against_sources.py`)**:
   - Implements `--only repowering-substation-audit` measuring difference distribution:
     $$\Delta_{\text{substation}}(s) = |s.\text{substation\_mi} - s.\text{epa\_substation\_distance\_mi}|$$
3. **Frontend Presentation (`docs/app.js`)**:
   - Adds "EPA RE-Powering Solar/Wind Potential" to the detail panel and shows cross-validated grid proximity status.

---

## 5. Verification & Test Plan

- **Automated Validation (`scripts/validate_data.py`)**:
  - Assert that $\ge 90\%$ of matched sites exhibit $\Delta_{\text{substation}} \le 1.0\text{ mi}$.
- **Unit Tests (`tests/test_repowering_universe.py`)**:
  - Test record deduplication, acreage normalization, and coordinate precision.
- **E2E Playwright Tests (`tests/e2e/test_repowering_layer.py`)**:
  - Verify detail panel displays EPA RE-Powering renewable metrics when present.
---

## NEPA-MCP expansion (2026-08-24)

- **Verdict unchanged, now with receipts:** nepa-mcp offers nothing for the
  190k-site bulk ingest (its tools are per-ROI; the capability census
  confirms no bulk endpoint), so this spec stays a normal-connector build.
- Once the universe lands, its top decile becomes a Spec 10 R2/R3 customer:
  screen the newly-surfaced high-scorers before promoting any into curated
  overlays — the screening ritual is exactly the QA step a 100× coverage
  expansion needs so junk coordinates don't become ranked candidates.
