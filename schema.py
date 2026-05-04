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
    proximity: Optional[dict] = None

    # Related federal documents per site (RODs, ESDs, Five Year Reviews,
    # fact sheets, technical reports). Populated by enrichment connectors
    # such as `epa-superfund-docs`. Each entry is a small dict — the
    # frontend renders title + date + link in the detail panel.
    documents: Optional[list[dict]] = Field(
        default=None,
        description="Related federal documents (title, url, date, category, "
                    "doc_id, ou_id, size, pages).",
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
