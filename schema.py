"""Pydantic schema for the dashboard's output JSON.

Single source of truth for the shape of `docs/data/sites.json`. Importable
from `refresh.py` (validation before write) and from tests.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ProgramLiteral = Literal["superfund", "brownfield", "fuds", "brac"]


class SiteRecord(BaseModel):
    """One Superfund or ACRES (brownfield) site record.

    Optional fields default to None and are dropped from the serialized JSON
    via `model_dump(exclude_none=True)` to keep the payload compact —
    important now that ACRES adds ~36k records to the combined output.
    """

    model_config = ConfigDict(extra="forbid")

    # Stable cross-source ID. Superfund uses raw EPA_ID; ACRES uses
    # `ACRES-<PROPERTY_ID>` to avoid namespace collision.
    id: str
    program: ProgramLiteral = Field(
        description="Which inventory the record belongs to."
    )

    # Legacy aliases — kept on Superfund records so existing diff.py and
    # tests keep working. Optional on ACRES.
    epa_id: Optional[str] = None

    name: Optional[str] = None
    acreage: Optional[float] = Field(
        default=None,
        description="Acres. None means area unknown / non-areal feature (always None for ACRES).",
    )
    npl_status_code: Optional[str] = None
    npl_status: Optional[str] = None
    federal_facility: Optional[str] = Field(
        default=None, description="Decoded federal-facility label or raw code."
    )
    federal_facility_code: Optional[str] = Field(
        default=None, description="Raw single-letter federal-facility code."
    )
    region: Optional[int] = None
    address: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    profile_url: Optional[str] = None
    last_updated: Optional[int] = Field(
        default=None, description="Epoch ms from source layer; None if missing."
    )
    parent_epa_id: Optional[str] = Field(
        default=None,
        description="If this site is a sub-site (NPL status 'A'), the parent's EPA_ID.",
    )
    children: Optional[list[dict[str, Optional[str]]]] = Field(
        default=None,
        description="Compact `{id, name}` records for status-'A' sub-sites rolled up under this parent.",
    )

    # FUDS-specific fields
    eligibility: Optional[str] = Field(
        default=None, description="FUDS eligibility: Eligible, Ineligible, Categorical Exclusion."
    )
    fuds_status: Optional[str] = Field(
        default=None, description="FUDS property status (e.g. 'Properties with projects')."
    )
    has_projects: Optional[str] = Field(
        default=None, description="Whether the FUDS property has projects: yes/no/tbd."
    )
    congressional_district: Optional[str] = None

    # BRAC-specific fields
    component: Optional[str] = Field(
        default=None, description="Military component (e.g. 'Army Active', 'Navy Active')."
    )

    # EPA Superfund Redevelopment infrastructure-proximity fields
    near_electric_transmission: Optional[str] = Field(
        default=None, description="Proximity to electrical transmission line."
    )
    near_highway: Optional[str] = None
    near_railroad: Optional[str] = None
    near_water_supply: Optional[str] = Field(
        default=None, description="Within municipal water service area."
    )
    near_wastewater: Optional[str] = None
    near_water_body: Optional[str] = None
    pop_density: Optional[str] = Field(
        default=None, description="Urban/rural classification."
    )
    in_opp_zone: Optional[str] = Field(
        default=None, description="Within a Federal Opportunity Zone."
    )
    in_reuse: Optional[str] = Field(
        default=None, description="Whether site is already in reuse."
    )
    data_center_reuse_candidate: Optional[bool] = Field(
        default=None,
        description="Computed: meets EPA data-center siting criteria (power, water, acreage).",
    )

    # Universal infrastructure-proximity distances in miles, computed from
    # HIFLD + Census TIGER at refresh time by the `infra-proximity`
    # enrichment connector. Available across all programs (Superfund,
    # ACRES, FUDS, BRAC). Distances >100 mi are dropped (out-of-CONUS).
    transmission_mi: Optional[float] = Field(
        default=None,
        description="Miles to nearest HIFLD electric power transmission line.",
    )
    transmission_kv: Optional[float] = Field(
        default=None,
        description="Nominal kV of the nearest HIFLD transmission line "
                    "(VOLTAGE field, or VOLT_CLASS lower-bound when VOLTAGE "
                    "is HIFLD's null sentinel). Drives the data-center "
                    "scoring tiers (≥230 kV for hyperscale, ≥500 kV for "
                    "AI mega-campus).",
    )
    rail_mi: Optional[float] = Field(
        default=None,
        description="Miles to nearest Census TIGER rail line.",
    )
    highway_mi: Optional[float] = Field(
        default=None,
        description="Miles to nearest Census TIGER primary road (Interstate / major US/state).",
    )
    gas_pipeline_mi: Optional[float] = Field(
        default=None,
        description="Miles to nearest HIFLD natural-gas pipeline (interstate + "
                    "intrastate + gathering, EIA-sourced). <2 mi enables "
                    "behind-the-meter gas-turbine viability for hyperscale DCs.",
    )
    substation_mi: Optional[float] = Field(
        default=None,
        description="Miles to nearest electric substation (OpenStreetMap "
                    "power=substation, ways centered + nodes). Pairs with "
                    "transmission_mi: a 500 kV line within 0.5 mi is only "
                    "actionable if a substation is close enough to interconnect.",
    )
    substation_kv: Optional[float] = Field(
        default=None,
        description="Highest nominal kV reported on the nearest OSM substation "
                    "(voltage tag, max across `;`-separated values, converted "
                    "from volts). None when the tag is missing or unparseable.",
    )
    power_plant_mi: Optional[float] = Field(
        default=None,
        description="Miles to nearest HIFLD power plant (EIA-860 sourced). "
                    "Co-location with existing generation is a strong DC siting "
                    "signal — implies PPA / behind-the-meter potential and "
                    "demonstrated local grid capacity.",
    )
    power_plant_mw: Optional[float] = Field(
        default=None,
        description="Total nameplate MW of the nearest power plant.",
    )
    power_plant_fuel: Optional[str] = Field(
        default=None,
        description="Primary fuel of the nearest power plant (HIFLD `PrimSource` "
                    "field — e.g. 'natural gas', 'nuclear', 'coal', 'wind', 'solar').",
    )
    flood_zone: Optional[str] = Field(
        default=None,
        description="FEMA NFHL flood-zone code at the site (`A`, `AE`, `V`, `VE`, "
                    "`X`, `D`, etc.). None when the site lies outside any mapped "
                    "FEMA flood study area. Different from `in_sfha` which is "
                    "the boolean rollup.",
    )
    in_sfha: Optional[bool] = Field(
        default=None,
        description="True if the site sits inside a Special Flood Hazard Area "
                    "(1% annual chance / 100-yr floodplain — FEMA `SFHA_TF=T`). "
                    "A site in an SFHA effectively can't be permitted as "
                    "critical infrastructure without expensive elevation / "
                    "flood-proofing work.",
    )
    in_opportunity_zone: Optional[bool] = Field(
        default=None,
        description="True if the site sits inside a Treasury-designated "
                    "Qualified Opportunity Zone (QOZ). Universal nationwide "
                    "coverage from HUD's Opportunity_Zones FeatureServer "
                    "(8,765 census tracts). Distinct from the legacy "
                    "`in_opp_zone` field which is populated from EPA "
                    "RE-Powering qualitative data for Superfund sites only.",
    )
    oz_tract_geoid: Optional[str] = Field(
        default=None,
        description="GEOID10 of the Qualified Opportunity Zone census tract "
                    "containing this site (11-digit state+county+tract). "
                    "Used for hyperlinking to canonical Treasury / HUD "
                    "tract-level resources.",
    )
    oz_rural: Optional[bool] = Field(
        default=None,
        description="True if the OZ tract is designated as Rural (per the "
                    "HUD Rural flag on the Opportunity_Zones layer). Rural "
                    "OZs are a small subset (~700 tracts) but matter for "
                    "USDA-aligned investment programs.",
    )
    iso_rto: Optional[str] = Field(
        default=None,
        description="Regional transmission organization / independent system "
                    "operator containing this site, e.g. PJM, MISO, ERCOT, "
                    "CAISO, SPP, NYISO, ISO-NE, or non-RTO when the site is "
                    "in the lower-48 but outside an EIA/HIFLD RTO polygon.",
    )
    climate_zone: Optional[str] = Field(
        default=None,
        description="IECC / ASHRAE climate zone by county, e.g. 5B or 3A. "
                    "Derived from DOE Building America / PNNL county climate "
                    "zone boundaries.",
    )

    # Ownership / transfer / history. Most are still None for most programs;
    # FUDS populates `current_owner` directly from the source.
    current_owner: Optional[str] = None
    current_owner_source: Optional[str] = Field(
        default=None,
        description="Provenance label for current_owner (e.g. 'USACE FUDS', "
                    "'EPA ACRES PPF') so the UI can cite without ambiguity.",
    )
    historical_owners: Optional[list[str]] = None
    encumbrances: Optional[list[str]] = None
    remediation_detail: Optional[dict] = None

    # Related federal documents per site (RODs, ESDs, Five Year Reviews,
    # fact sheets, technical reports). Populated by enrichment connectors
    # such as `epa-superfund-docs`. Each entry is a small dict — the
    # frontend renders title + date + link in the detail panel.
    documents: Optional[list[dict]] = Field(
        default=None,
        description="Related federal documents (title, url, date, category, "
                    "doc_id, ou_id, size, pages).",
    )

    # EPA ECHO (Enforcement & Compliance History Online) summary.
    # Populated by the `epa-echo` enrichment connector. Open enforcement,
    # recent violations, or unpaid penalties make a site materially
    # untransactable — high-signal field for due diligence.
    enforcement: Optional[dict] = Field(
        default=None,
        description="ECHO enforcement summary: registry_id, dfr_url, "
                    "inspections_5yr, formal_actions_5yr, informal_actions_5yr, "
                    "penalties_5yr_usd, current_compliance, last_violation_date, "
                    "last_inspection_date, programs (list).",
    )

    # EPA ACRES cleanup status + grant history (acres-cleanup enrichment).
    # Only populated for brownfield (ACRES) records; null for other programs.
    cleanup_status: Optional[str] = Field(
        default=None,
        description="ACRES cleanup activity status: 'Completed', 'In Progress', or 'Not Started'.",
    )
    cleanup_complete_date: Optional[str] = Field(
        default=None,
        description="ISO date (YYYY-MM-DD) when cleanup was marked Completed.",
    )
    grant_total_usd: Optional[int] = Field(
        default=None,
        description="Sum of all EPA brownfield grant awards for this property (USD).",
    )
    grant_count: Optional[int] = Field(
        default=None,
        description="Number of individual EPA brownfield grant awards.",
    )
    grant_types: Optional[list[str]] = Field(
        default=None,
        description="Unique grant types awarded: Assessment, Cleanup, RLF, etc.",
    )

    # AI-generated plain-English site summary (Claude Haiku). Populated by
    # the `ai-summary` enrichment connector. Cached by content-hash of the
    # source fields so re-runs only re-bill when the underlying data
    # actually changes. Synthesizes name, status, acreage, documents, infra,
    # and enforcement into a 3-paragraph buyer-oriented narrative.
    summary: Optional[str] = Field(
        default=None,
        description="3-paragraph plain-English narrative generated by Claude Haiku.",
    )
    summary_meta: Optional[dict] = Field(
        default=None,
        description="Provenance for `summary`: model, hash, generated_at (ISO8601).",
    )


class Payload(BaseModel):
    """Top-level shape of sites.json (single-source) or sites.json (combined)."""

    model_config = ConfigDict(extra="forbid")

    generated_at: str
    source: str
    source_url: str
    limit: Optional[int] = Field(
        default=None,
        description="None = unlimited (all features). Int = top-N truncation.",
    )
    count: int
    sites: list[SiteRecord]
    # Set on the combined sites.json: lists per-program counts so the frontend
    # can render a source filter without scanning the full record list.
    programs: Optional[dict[str, int]] = None
