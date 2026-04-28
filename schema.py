"""Pydantic schema for the dashboard's output JSON.

Single source of truth for the shape of `docs/data/sites.json`. Importable
from `refresh.py` (validation before write) and from tests.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SiteRecord(BaseModel):
    """One Superfund (or future brownfield) site record."""

    model_config = ConfigDict(extra="forbid")

    epa_id: Optional[str]
    name: Optional[str]
    acreage: Optional[float] = Field(
        default=None,
        description="Acres. None means area unknown / non-areal feature.",
    )
    npl_status_code: Optional[str]
    npl_status: str
    federal_facility: Optional[str] = Field(
        default=None, description="Raw single-letter code, decoded label, or None."
    )
    federal_facility_code: Optional[str] = Field(
        default=None, description="Raw single-letter code, kept for filtering."
    )
    region: Optional[int]
    address: Optional[str]
    city: Optional[str]
    county: Optional[str]
    state: Optional[str]
    zip: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    profile_url: Optional[str]
    last_updated: Optional[int] = Field(
        default=None, description="Epoch ms from EPA layer; None if missing."
    )
    parent_epa_id: Optional[str] = Field(
        default=None,
        description="If this site is a sub-site (NPL status 'A'), the parent's EPA_ID.",
    )

    # Backlog placeholders — kept on the record so the frontend can render
    # explicit N/A rather than failing on missing keys.
    current_owner: Optional[str] = None
    historical_owners: Optional[list[str]] = None
    encumbrances: Optional[list[str]] = None
    remediation_detail: Optional[dict] = None
    proximity: Optional[dict] = None


class Payload(BaseModel):
    """Top-level shape of sites.json."""

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
