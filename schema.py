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
    rau_status: Optional[str] = Field(
        default=None,
        description="EPA Sitewide Ready for Anticipated Use (SWRAU) status — "
                    "whether all of the site's land is ready for its anticipated "
                    "use. One of 'Meets the Measure', 'Does Not Meet the Measure', "
                    "'Does Not Meet the Measure (Retracted)', "
                    "'Meets the Measure (Formerly Retracted)', or null.",
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
    power_plant_retired: Optional[bool] = Field(
        default=None,
        description="True when the nearest plant's HIFLD Status is RE/OA/OS (retired "
                    "/ out of service). False when operating/standby. None when the "
                    "Status field wasn't available (older cache). A retired plant "
                    "within 1 mi is the Conesville / Widows Creek pattern: inherited "
                    "transmission connection without competing for active capacity.",
    )

    # EIA-860M retired-plant proximity (eia-retired-plants enrichment connector).
    # Source: EIA Preliminary Monthly Electric Generator Inventory "Retired" sheet.
    # Only populated when a large (≥100 MW) dispatchable retired plant exists
    # within MAX_DISTANCE_MI (5 mi).  Scoring fires at ≤1 mi.
    retired_plant_mi: Optional[float] = Field(
        default=None,
        description="Miles to the nearest large (≥100 MW) RETIRED dispatchable "
                    "power plant from EIA-860M.  Within 1 mi = Conesville / Widows "
                    "Creek pattern: inherited transmission + stranded interconnect "
                    "agreement, no competing active load.",
    )
    retired_plant_mw: Optional[float] = Field(
        default=None,
        description="Total nameplate MW of the nearest large retired plant.",
    )
    retired_plant_fuel: Optional[str] = Field(
        default=None,
        description="EIA energy-source code of the nearest retired plant "
                    "(e.g. 'BIT' = bituminous coal, 'NG' = natural gas, "
                    "'NUC' = nuclear). Non-dispatchable (SUN/WND) plants "
                    "are excluded from the index.",
    )
    retired_plant_year: Optional[int] = Field(
        default=None,
        description="Retirement year of the nearest plant (latest year "
                    "across generating units at the plant).",
    )
    retired_plant_name: Optional[str] = Field(
        default=None,
        description="Name of the nearest retired power plant.",
    )

    # EIA-860M PLANNED-retirement proximity (planned-retirements enrichment
    # connector). Source: EIA Preliminary Monthly Electric Generator Inventory
    # "Operating" sheet, `Planned Retirement Year` column — plants ≥100 MW
    # dispatchable with an ANNOUNCED shutdown date. The forward-looking
    # counterpart to retired_plant_*: the interconnect frees on a KNOWN date,
    # and repowering / co-location deals are struck BEFORE shutdown (the
    # Homer City pattern). Populated when such a plant exists within 5 mi.
    planned_retirement_mi: Optional[float] = Field(
        default=None,
        description="Miles to the nearest large (≥100 MW) dispatchable OPERATING "
                    "plant with an announced retirement year (EIA-860M). Within "
                    "1 mi = the plant property itself frees up on a known date.",
    )
    planned_retirement_mw: Optional[float] = Field(
        default=None,
        description="Total MW retiring at the nearest planned-retirement plant.",
    )
    planned_retirement_fuel: Optional[str] = Field(
        default=None,
        description="Fuel of the nearest planned-retirement plant (e.g. 'coal', "
                    "'natural gas'). Non-dispatchable plants are excluded.",
    )
    planned_retirement_year: Optional[int] = Field(
        default=None,
        description="Announced retirement year of the nearest planned-retirement "
                    "plant (the LAST retiring unit's year at multi-unit plants).",
    )
    planned_retirement_name: Optional[str] = Field(
        default=None,
        description="Name of the nearest planned-retirement power plant.",
    )

    # Coal-to-Clean (Nuclear & Data Center) Conversion fields (Spec 04)
    coal_conversion_plant_name: Optional[str] = Field(
        default=None,
        description="Name of the nearest coal plant conversion asset (active or retired ≥100 MW).",
    )
    coal_conversion_plant_mi: Optional[float] = Field(
        default=None,
        description="Miles to the nearest coal plant conversion asset.",
    )
    coal_conversion_mw: Optional[float] = Field(
        default=None,
        description="Nameplate coal capacity in MW of the nearest coal conversion asset.",
    )
    coal_conversion_switchyard_kv: Optional[float] = Field(
        default=None,
        description="Interconnect switchyard voltage (kV) of the nearest coal conversion asset.",
    )
    coal_conversion_rail: Optional[bool] = Field(
        default=None,
        description="Whether the coal conversion asset has active rail loop/siding.",
    )
    coal_conversion_water: Optional[bool] = Field(
        default=None,
        description="Whether the coal conversion asset has dedicated water intake / NPDES discharge.",
    )
    coal_conversion_stranded_val_usd: Optional[float] = Field(
        default=None,
        description="Estimated stranded infrastructure replacement value (USD) derived from grid/water/rail assets.",
    )
    coal_conversion_queue_fasttrack: Optional[bool] = Field(
        default=None,
        description="Whether site is eligible for ISO/RTO generator replacement fast-track queue transfer (within 1.5 mi).",
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
    in_aiannha_area: Optional[bool] = Field(
        default=None,
        description="True when the site point falls in a Census TIGERweb "
                    "American Indian, Alaska Native, or Native Hawaiian Area. "
                    "Screening context only; not land title or a consultation conclusion.",
    )
    aiannha_area_count: Optional[int] = Field(
        default=None,
        description="Number of overlapping TIGERweb AIANNHA mapped geographies.",
    )
    aiannha_areas: Optional[list[dict[str, Optional[str]]]] = Field(
        default=None,
        description="Compact name, GEOID, and category records for containing AIANNHA areas.",
    )
    county_labor_force: Optional[int] = Field(
        default=None, description="ACS 5-Year county civilian labor force estimate."
    )
    county_construction_employment: Optional[int] = Field(
        default=None, description="ACS 5-Year county construction-industry employment estimate."
    )
    county_median_household_income: Optional[int] = Field(
        default=None, description="ACS 5-Year county median household income estimate."
    )
    workforce_county: Optional[str] = Field(
        default=None, description="County name used for the ACS workforce join."
    )
    workforce_data_year: Optional[int] = Field(
        default=None, description="ACS vintage used for county workforce estimates."
    )
    in_energy_community: Optional[bool] = Field(
        default=None,
        description="True if the site sits inside an IRA (Inflation Reduction "
                    "Act) 'energy community' — a coal-closure census tract "
                    "(coal mine closed after 1999 or coal generator retired "
                    "after 2009, plus adjacent tracts) OR a fossil-fuel-"
                    "employment statistical area (MSA/non-MSA with >=0.17% "
                    "direct fossil-fuel employment and unemployment >= the "
                    "national average). Clean-energy projects built on an "
                    "energy community earn a +10 percentage-point ITC/PTC "
                    "bonus under IRA sec. 45/48 — a material IRR lever for "
                    "behind-the-meter generation paired with a data center. "
                    "Source: DOE NETL energy-community layers (2024 edition).",
    )
    energy_community_type: Optional[str] = Field(
        default=None,
        description="Which IRA energy-community category the site qualifies "
                    "under: 'coal_closure' (census-tract level; the more "
                    "localized, higher-confidence signal — takes precedence) "
                    "or 'fossil_fuel_employment' (county / statistical-area "
                    "level). The brownfield category (CERCLA sec. 101(39)) is "
                    "deliberately NOT auto-asserted here: it excludes NPL "
                    "sites and carries BFPP nuances our program flag can't "
                    "cleanly resolve, so we only assert the two unambiguous "
                    "geographic categories.",
    )
    energy_community_detail: Optional[str] = Field(
        default=None,
        description="For coal_closure communities, why the tract qualifies: "
                    "'Mine closure', 'Generator closure', or 'Adjacent to "
                    "closure'. For fossil_fuel_employment, the MSA / non-MSA "
                    "area name. Human-readable provenance for the detail panel.",
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

    # FEMA National Risk Index (county-level, fema-nri enrichment connector).
    # Composite + per-hazard natural-hazard risk. For DC siting the marquee
    # operational hazards are wildfire (direct threat / insurability),
    # drought (cooling-water availability), and heat wave (cooling load).
    nri_risk_score: Optional[float] = Field(
        default=None,
        description="FEMA National Risk Index composite score (0-100 national "
                    "percentile) for the county containing the site. Higher = "
                    "more natural-hazard risk.",
    )
    nri_risk_rating: Optional[str] = Field(
        default=None,
        description="FEMA NRI composite rating bucket: 'Very Low', "
                    "'Relatively Low', 'Relatively Moderate', 'Relatively "
                    "High', 'Very High', or 'Insufficient Data'.",
    )
    nri_wildfire_rating: Optional[str] = Field(
        default=None,
        description="FEMA NRI wildfire risk rating (same bucket scale). The "
                    "marquee climate hazard for data-center siting — drives "
                    "insurability and the climate penalty in dc-score.js.",
    )
    nri_drought_rating: Optional[str] = Field(
        default=None,
        description="FEMA NRI drought risk rating (same bucket scale). Proxy "
                    "for cooling-water availability stress.",
    )
    nri_heatwave_rating: Optional[str] = Field(
        default=None,
        description="FEMA NRI heat-wave risk rating (same bucket scale). "
                    "Higher heat-wave risk raises cooling load / lowers "
                    "free-cooling hours. Displayed for context; not penalized.",
    )

    # Ownership / transfer / history. Most are still None for most programs;
    # FUDS populates `current_owner` directly from the source.
    # Coordinate-quality flags from the `coord-quality` connector. Absent
    # means no known problem — the field only appears on records where the
    # location is demonstrably less trustworthy than the marker implies.
    coord_flags: Optional[list[str]] = Field(
        default=None,
        description="Any of: state_mismatch (point outside its own state's "
                    "polygon), outside_us, placeholder (whole/half degree), "
                    "shared_point (>=3 records on one coordinate — geocoder "
                    "centroid), low_precision (<=2 decimal places).",
    )
    coord_actual_state: Optional[str] = Field(
        default=None,
        description="For state_mismatch: the state the coordinate actually "
                    "falls in, per the us-states.json polygons.",
    )
    coord_state_gap_mi: Optional[float] = Field(
        default=None,
        description="For state_mismatch: miles from the point to the nearest "
                    "boundary of the state the record claims.",
    )
    coord_shared_count: Optional[int] = Field(
        default=None,
        description="For shared_point: how many records sit on this exact "
                    "coordinate.",
    )

    current_owner: Optional[str] = None
    current_owner_source: Optional[str] = Field(
        default=None,
        description="Provenance label for current_owner (e.g. 'USACE FUDS', "
                    "'EPA ACRES PPF') so the UI can cite without ambiguity.",
    )
    parcel_acreage: Optional[float] = Field(
        default=None,
        description="GIS acreage of the cadastral parcel the site falls on, "
                    "from the matched statewide parcel layer (parcel-owner "
                    "connector). Answers 'how many acres are actually available "
                    "for development' at the parcel level — and is the ONLY "
                    "land-size signal for ACRES brownfields, whose source has no "
                    "acreage column at all (see CLAUDE.md gap #1). Distinct from "
                    "`acreage` (the program's own reported site boundary area).",
    )
    parcel_id: Optional[str] = Field(
        default=None,
        description="Parcel identifier (APN / PIN) from the matched statewide "
                    "parcel layer, for provenance / cross-reference to the "
                    "county assessor record.",
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
                    "last_inspection_date, has_npdes_permit (bool — CWA/NPDES "
                    "permit holder, proxy for legacy industrial water access), "
                    "programs (list).",
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


class CoalConversionAsset(BaseModel):
    """One coal plant facility evaluated for nuclear or data center conversion (Spec 04).

    Provenance contract: every row carries `source_url` (verified resolving) +
    `verified_at` (YYYY-MM-DD audit stamp, STATE_DC_INCENTIVES discipline).
    Fields no public document supports (intake GPM, NPDES IDs) stay None —
    absent means unverified. `queue_transfer_eligible` is DERIVED from status
    (true only for retired / planned_retirement: an operating plant's
    interconnection is not transferable, and a gas-converted plant's POI is
    occupied by its successor units), never hand-set.
    """

    model_config = ConfigDict(extra="forbid")

    eia_plant_id: Optional[int] = Field(
        default=None,
        description="EIA Plant Code — set only when verified against EIA-860M, never hand-typed.",
    )
    plant_name: str
    utility_operator: str
    state: str = Field(min_length=2, max_length=2)
    county: str
    latitude: float
    longitude: float
    status: Literal["operating", "retired", "planned_retirement", "converted_gas"]
    retired_year: Optional[int] = None
    planned_retirement_year: Optional[int] = None
    nameplate_coal_mw: float = Field(ge=0.0)
    switchyard_kv: float = Field(ge=0.0)
    has_rail: bool
    has_water_intake: bool
    intake_flow_gpm: Optional[float] = None
    npdes_permit_id: Optional[str] = None
    site_acreage: Optional[float] = None
    iso_rto: str
    poi_occupied: bool = Field(
        default=False,
        description="True when a successor plant on-site already uses the interconnection "
        "(e.g. a coal-to-gas CC) — the coal units may be retired but the POI is NOT free; "
        "at best there is Order-845 surplus headroom.",
    )
    queue_transfer_eligible: bool
    est_stranded_asset_value_usd: float = Field(
        description="MODELED estimate (spec 04 §4.1 formula) — label as such in every UI surface."
    )
    conversion_suitability: Literal["nuclear_preferred", "datacenter_preferred", "dual_feasible"]
    note: Optional[str] = Field(
        default=None, description="Deal context (life extension, conversion project, consent decree)."
    )
    source_url: str = Field(description="Per-row citation; must resolve.")
    verified_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class CoalConversionProximityRecord(BaseModel):
    """Proximity link from a tracked brownfield to an adjacent coal conversion asset."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Tracked brownfield site ID")
    coal_conversion_plant_name: str
    coal_conversion_plant_mi: float = Field(ge=0.0)
    coal_conversion_mw: float = Field(ge=0.0)
    coal_conversion_switchyard_kv: float = Field(ge=0.0)
    coal_conversion_rail: bool
    coal_conversion_water: bool
    coal_conversion_stranded_val_usd: float = Field(ge=0.0)
    coal_conversion_queue_fasttrack: bool


class FederalCleanEnergySite(BaseModel):
    """One flagship DOE 'Cleanup to Clean Energy' / AI-data-center / Mine Lands
    federal clean-energy site (Spec 08). Same provenance contract as
    CoalConversionAsset: `solicitation_url` must be a real resolving URL
    (never a guessed slug) and every row carries a `verified_at` audit stamp.
    Re-audit quarterly — these programs move on political timelines."""

    model_config = ConfigDict(extra="forbid")

    site_id: str = Field(description="Unique identifier e.g. 'doe-em-srs'")
    site_name: str
    managing_office: Literal["DOE-EM", "DOE-NNSA", "DOE-OCED", "BLM", "OSMRE", "DOD-AFCEC", "DOD-ANPI"]
    state: str = Field(min_length=2, max_length=2)
    county: str
    latitude: float
    longitude: float
    available_acreage: float = Field(
        ge=0.0,
        description="Full reservation/withdrawal acreage (reference scale of the federal site).",
    )
    offered_acreage: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Acreage actually identified/offered for development when the program "
        "has named one (e.g. INL's ~44k ac for AI infrastructure of the 570k-ac site) — "
        "the actionable figure; render it alongside, never conflate with available_acreage.",
    )
    target_technologies: list[str]
    program_stage: Literal["RFI_Issued", "RFQ_Awarded", "Lease_Executed", "Pre_Application", "Construction"]
    commercial_partner: Optional[str] = None
    solicitation_url: str
    nepa_review_document_url: Optional[str] = None
    key_advantages: list[str]
    verified_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")



class HanfordSourceLink(BaseModel):
    """One labeled citation link on a Hanford parcel row."""

    model_config = ConfigDict(extra="forbid")

    label: str
    url: str = Field(pattern=r"^https://")


class HanfordOpportunity(BaseModel):
    """One curated opportunity assessment on a Hanford parcel.

    `fit` is an editorial judgement with a cited rationale — screening
    evidence informs it, it is never computed from a score. The four values:
    anchored (already committed/operating), strong (pursue now), conditional
    (a named gate must clear), precluded (designation/mission forecloses it —
    saying so out loud is the point).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "solar_storage", "advanced_nuclear", "ai_datacenter",
        "advanced_manufacturing", "battery_storage", "research_campus",
        "conservation", "heritage_tourism",
    ]
    fit: Literal["anchored", "strong", "conditional", "precluded"]
    rationale: str


class HanfordFacilityFit(BaseModel):
    """One row of the data-center-vs-reactor-class comparison on a Hanford
    parcel — distinct from HanfordOpportunity's single combined
    "advanced_nuclear" kind because each reactor tier has a different
    licensing pathway, water draw, and footprint. Same fit vocabulary and
    editorial-judgement contract as HanfordOpportunity.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["data_center", "lwr_pwr", "smr", "microreactor"]
    fit: Literal["anchored", "strong", "conditional", "precluded"]
    rationale: str


class HanfordParcel(BaseModel):
    """One named sub-area of the Hanford Site in the E2E NEPA dossier.

    'Parcel' means a named land unit of the 580 sq mi site — never a
    cadastral parcel; coordinates are representative points, not boundaries.
    Same provenance contract as CoalConversionAsset: every row carries
    `source_url` (verified resolving) + `verified_at` (YYYY-MM-DD audit
    stamp). The screening/geojson/corpus fields are generated by
    scripts/build_hanford_e2e.py, not curated; they are typed loosely here
    because their shape belongs to nepa-mcp and to the corpus join, while
    extra="forbid" still catches curated-field typos.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    kind: Literal[
        "cleanup_area", "cleanup_core", "transferred", "leased_energy",
        "conservation", "cultural", "context_campus",
    ]
    lat: float
    lon: float
    coord_note: str
    approx_acres: float = Field(ge=0.0)
    corpus_site_id: Optional[str] = Field(
        default=None,
        description="Join key into the dashboard corpus (the four Hanford NPL EPA IDs).",
    )
    clup_designation: Optional[str] = Field(
        default=None,
        description="DOE/EIS-0222-F land-use designation when unambiguous; None = confirm on the CLUP map.",
    )
    clup_note: str
    status: str
    availability: str
    source_url: str = Field(pattern=r"^https://")
    extra_sources: Optional[list[HanfordSourceLink]] = None
    verified_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    opportunities: list[HanfordOpportunity]
    facility_fit: list[HanfordFacilityFit]
    # Generated (never curated) fields, present in the emitted JSON:
    screening: Optional[dict] = None
    geojson_url: Optional[str] = None
    map_summary: Optional[dict] = None
    corpus_record: Optional[dict] = None
    nearby_tracked: Optional[list[dict]] = None
