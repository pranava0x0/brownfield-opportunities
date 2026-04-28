"""Pydantic schema for the dashboard's output JSON.

Single source of truth for the shape of `docs/data/sites.json`. Importable
from `refresh.py` (validation before write) and from tests.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ProgramLiteral = Literal["superfund", "brownfield"]


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

    # Future enrichment slots — None today, dropped from JSON via exclude_none.
    current_owner: Optional[str] = None
    historical_owners: Optional[list[str]] = None
    encumbrances: Optional[list[str]] = None
    remediation_detail: Optional[dict] = None
    proximity: Optional[dict] = None


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
