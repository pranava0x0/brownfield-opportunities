#!/usr/bin/env python3
"""Comprehensive offline validation of every file in `docs/data/`.

Runs without network access. Three families of checks:

  struct  — envelope shape, schema conformance, id uniqueness/namespace,
            enrichment→universe join integrity, value domains.
  geo     — coordinate sanity, point-in-state and point-in-county agreement
            with the record's own `state` / `county` fields, coordinate
            duplication (a geocoder falling back to a city centroid), and
            precision.
  infra   — plausibility of the enrichment distances. The load-bearing check
            is `infra-lipschitz`: nearest-feature distance is 1-Lipschitz in
            position, so for any two sites A and B,
                |d(A) - d(B)| <= dist(A, B)
            must hold for EVERY nearest-X distance field. A violation is a
            proof of a bug (bad index, stale join, or wrong coordinates) — it
            needs no external source to establish. Alongside it we exactly
            recompute the distances whose source geometry we hold locally
            (planned retirements, nuclear proximity, retired-industrial join).

Output is a compact one-line-per-check report; `--json` writes the full
offending-id detail so the terminal stays readable.

Usage:
    python3 scripts/validate_data.py
    python3 scripts/validate_data.py --only geo --json /tmp/geo.json
    python3 scripts/validate_data.py --list
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
sys.path.insert(0, str(ROOT))

from connectors.county_lookup import CountyIndex  # noqa: E402
from connectors.spatial import PolygonIndex, haversine_mi  # noqa: E402

# --------------------------------------------------------------------------
# Reference domains
# --------------------------------------------------------------------------

PROGRAM_FILES = {
    "superfund": "superfund-npl.json",
    "brownfield": "epa-acres.json",
    "fuds": "dod-fuds.json",
    "brac": "dod-brac.json",
}

# Enrichment files that carry SiteRecord-shaped partials keyed by `id`.
ENRICHMENT_FILES = [
    "acres-cleanup.json",
    "ai-summary.json",
    "climate-zone.json",
    "eia-retired-plants.json",
    "epa-echo.json",
    "epa-redev.json",
    "epa-superfund-docs.json",
    "fema-nri.json",
    "infra-proximity.json",
    "ira-energy-community.json",
    "iso-rto.json",
    "opportunity-zone.json",
    "parcel-owner.json",
    "planned-retirements-proximity.json",
]

# Overlay files: NOT SiteRecords, own shapes, validated separately.
OVERLAY_FILES = [
    "ap1000-sites.json",
    "coal-conversions.json",
    "coal-conversions-proximity.json",
    "coal-nepa.json",
    "federal-clean-energy.json",
    "hanford-e2e.json",
    "microreactor-fleet.json",
    "nuclear-brownfield-proximity.json",
    "nuclear-civilian-sites.json",
    "planned-retirements.json",
    "reference-campuses.json",
    "retired-industrial.json",
]

STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
TERRITORIES = {"PR", "VI", "GU", "MP", "AS", "FM", "MH", "PW", "UM"}
ALL_STATE_CODES = STATES | TERRITORIES

NPL_STATUS_CODES = {"F", "P", "D", "A", "N", "R", "W", "O", "S", "C"}
PROGRAMS = set(PROGRAM_FILES)
NRI_RATINGS = {
    "Very Low",
    "Relatively Low",
    "Relatively Moderate",
    "Relatively High",
    "Very High",
    "Insufficient Data",
    "No Rating",
    "Not Applicable",
}
ENERGY_COMMUNITY_TYPES = {"coal_closure", "fossil_fuel_employment"}
ISO_RTOS = {"PJM", "MISO", "ERCOT", "CAISO", "SPP", "NYISO", "ISO-NE", "non-RTO"}

# Distances are emitted rounded to 0.1 mi and capped at 100 mi by the
# infra-proximity connector.
MAX_DISTANCE_MI = 100.0
DISTANCE_FIELDS = [
    "transmission_mi",
    "rail_mi",
    "highway_mi",
    "gas_pipeline_mi",
    "substation_mi",
    "power_plant_mi",
]
# Distance fields with their own (smaller) search radius, set by their own
# connector rather than infra-proximity.
RADIUS_CAPPED_FIELDS = {
    "retired_plant_mi": 5.0,
    "planned_retirement_mi": 5.0,
}

# Continental US plus the territory boxes we legitimately carry.
REGION_BOXES = {
    "conus": (24.0, -125.5, 49.5, -66.5),
    "AK": (51.0, -180.0, 72.0, -129.0),
    # Western Aleutians (Attu, Shemya, Kiska) sit past the antimeridian and
    # carry POSITIVE longitudes. Real FUDS properties live here.
    "AK-west": (51.0, 172.0, 54.0, 180.0),
    # Main Hawaiian chain plus the Northwestern Hawaiian Islands (Kure,
    # Midway) — FUDS carries real WWII-era properties out there.
    "HI": (18.5, -178.5, 28.5, -154.5),
    "PR": (17.8, -67.5, 18.6, -65.2),
    "VI": (17.6, -65.1, 18.5, -64.5),
    "GU": (13.2, 144.6, 13.7, 145.0),
    "MP": (14.0, 145.1, 20.6, 146.1),
    # Tutuila/Manu'a plus Swains Island, which sits ~200 mi to the north.
    "AS": (-14.6, -171.2, -10.9, -168.1),
    "FM": (1.0, 137.0, 10.0, 163.5),
    "MH": (4.5, 160.0, 15.0, 172.5),
    "UM": (-1.0, -178.0, 29.0, 167.0),
}

# --------------------------------------------------------------------------
# Result plumbing
# --------------------------------------------------------------------------


class Finding:
    """One check's outcome."""

    def __init__(
        self,
        check: str,
        family: str,
        level: str,
        checked: int,
        bad: int,
        message: str,
        examples: Optional[list[Any]] = None,
        detail: Optional[dict] = None,
    ) -> None:
        self.check = check
        self.family = family
        self.level = level  # PASS | INFO | WARN | FAIL
        self.checked = checked
        self.bad = bad
        self.message = message
        self.examples = examples or []
        self.detail = detail or {}

        if self.level == "FAIL" and check in UPSTREAM_QUALITY_CHECKS:
            self.level = "WARN"

    def line(self) -> str:
        rate = f"{self.bad}/{self.checked}" if self.checked else f"{self.bad}/-"
        ex = ""
        if self.examples:
            shown = ", ".join(str(e) for e in self.examples[:4])
            more = f" (+{len(self.examples) - 4})" if len(self.examples) > 4 else ""
            ex = f"  e.g. {shown}{more}"
        return f"[{self.level:4}] {self.check:34} {rate:>13}  {self.message}{ex}"

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "family": self.family,
            "level": self.level,
            "checked": self.checked,
            "bad": self.bad,
            "message": self.message,
            "examples": self.examples[:200],
            "detail": self.detail,
        }


# Checks whose failure means an UPSTREAM data-quality problem rather than a
# defect in our pipeline. These stay visible as WARN so CI can gate on FAIL
# without being permanently red over things EPA / USACE control. Promote one
# to FAIL only once we actually own the invariant.
UPSTREAM_QUALITY_CHECKS = {
    "join-orphans",          # EPA RE-Powering covers sites the boundary layer lacks
    "coord-in-region",       # source coordinates outside the US
    "point-in-state",        # source state attribute disagrees with source geometry
    "point-in-county",
    "coord-placeholder",     # whole-degree coordinates from the source
    "coord-duplicates",
    "coord-precision",
    "text-sentinels",
    "oz-geoid-vs-county",    # downstream of the bad coordinates above
    "redev-coord-agreement",
    "redev-acreage-agreement",
    "ai-summary-consistency",
    "infra-substation-vs-line",
}


def verdict(bad: int, warn_only: bool = False) -> str:
    if bad == 0:
        return "PASS"
    return "WARN" if warn_only else "FAIL"


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


class Corpus:
    """Every data file, loaded once and indexed."""

    def __init__(self) -> None:
        self.raw: dict[str, dict] = {}
        self.sites: dict[str, list[dict]] = {}  # filename -> records
        self.universe: dict[str, dict] = {}  # id -> program-file record
        self.id_program: dict[str, str] = {}
        self.merged: dict[str, dict] = {}  # id -> program record + enrichments
        self._states: Optional[PolygonIndex] = None
        self._counties: Optional[CountyIndex] = None

        for fname in list(PROGRAM_FILES.values()) + ENRICHMENT_FILES + OVERLAY_FILES:
            path = DATA / fname
            if not path.exists():
                continue
            payload = json.loads(path.read_text())
            self.raw[fname] = payload
            self.sites[fname] = _records_of(payload)

        for program, fname in PROGRAM_FILES.items():
            for rec in self.sites.get(fname, []):
                sid = rec.get("id")
                if sid is None:
                    continue
                self.universe[sid] = rec
                self.id_program[sid] = rec.get("program", program)

        # Merged view = what the browser actually ends up holding. Every
        # `ensure*Loaded()` join in app.js is FILL-IF-EMPTY: it never
        # overwrites a value the program file already supplied. Modelling
        # that faithfully matters — epa-redev ships an 11M-acre value for a
        # site whose NPL acreage is 1,357, and the only reason users never
        # see it is that `existing.acreage == null` gates the patch.
        self.merged = {k: dict(v) for k, v in self.universe.items()}
        for fname in ENRICHMENT_FILES:
            for rec in self.sites.get(fname, []):
                sid = rec.get("id")
                target = self.merged.get(sid)
                if target is None:
                    continue
                for key, val in rec.items():
                    if key in ("id", "program") or val is None:
                        continue
                    if target.get(key) is None:
                        target[key] = val

    @property
    def states(self) -> PolygonIndex:
        if self._states is None:
            idx = PolygonIndex(cell_deg=0.5)
            geo = json.loads((DATA / "us-states.json").read_text())
            for feat in geo["features"]:
                name = feat["properties"].get("name")
                geom = feat["geometry"]
                if geom["type"] == "Polygon":
                    polys = [geom["coordinates"]]
                else:
                    polys = geom["coordinates"]
                for rings in polys:
                    idx.add_polygon(rings, attr=name)
            self._states = idx
        return self._states

    @property
    def counties(self) -> CountyIndex:
        if self._counties is None:
            self._counties = CountyIndex.from_path(DATA / "us-counties-topo.json")
        return self._counties


def _records_of(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    for key in ("sites", "records", "campuses", "data", "matches", "assets"):
        val = payload.get(key)
        if isinstance(val, list):
            return val
    return []


STATE_NAME_TO_CODE = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Puerto Rico": "PR", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}

# --------------------------------------------------------------------------
# Check registry
# --------------------------------------------------------------------------

CHECKS: list[tuple[str, str, Callable[[Corpus], Iterable[Finding]]]] = []


def check(check_id: str, family: str):
    def deco(fn):
        CHECKS.append((check_id, family, fn))
        return fn

    return deco


# --------------------------------------------------------------------------
# STRUCT
# --------------------------------------------------------------------------


@check("envelope", "struct")
def c_envelope(c: Corpus):
    bad, examples = 0, []
    checked = 0
    for fname, payload in c.raw.items():
        if not isinstance(payload, dict):
            continue
        checked += 1
        recs = c.sites[fname]
        if "generated_at" not in payload:
            bad += 1
            examples.append(f"{fname}:no-generated_at")
        declared = payload.get("count")
        if declared is not None and declared != len(recs):
            bad += 1
            examples.append(f"{fname}:count={declared}!=len={len(recs)}")
        if fname not in OVERLAY_FILES and "source_url" not in payload:
            bad += 1
            examples.append(f"{fname}:no-source_url")
    yield Finding(
        "envelope", "struct", verdict(bad), checked, bad,
        "envelope keys present and count matches record length", examples,
    )


@check("schema", "struct")
def c_schema(c: Corpus):
    try:
        from schema import SiteRecord
    except Exception as exc:  # pragma: no cover
        yield Finding("schema", "struct", "WARN", 0, 1, f"pydantic import failed: {exc}")
        return
    bad, examples, checked = 0, [], 0
    for fname in list(PROGRAM_FILES.values()) + ENRICHMENT_FILES:
        for rec in c.sites.get(fname, []):
            checked += 1
            try:
                SiteRecord.model_validate(rec)
            except Exception as exc:
                bad += 1
                if len(examples) < 200:
                    msg = str(exc).splitlines()[1] if "\n" in str(exc) else str(exc)
                    examples.append(f"{fname}:{rec.get('id')}:{msg[:70]}")
    yield Finding(
        "schema", "struct", verdict(bad), checked, bad,
        "every program/enrichment record validates against SiteRecord (extra=forbid)",
        examples,
    )


@check("id-unique", "struct")
def c_id_unique(c: Corpus):
    bad, examples, checked = 0, [], 0
    for fname in list(PROGRAM_FILES.values()) + ENRICHMENT_FILES:
        seen = Counter(r.get("id") for r in c.sites.get(fname, []))
        checked += sum(seen.values())
        for sid, n in seen.items():
            if n > 1:
                bad += n - 1
                if len(examples) < 200:
                    examples.append(f"{fname}:{sid}x{n}")
    yield Finding(
        "id-unique", "struct", verdict(bad), checked, bad,
        "no duplicate ids within any single file", examples,
    )


@check("id-namespace", "struct")
def c_id_namespace(c: Corpus):
    patterns = {
        "superfund": re.compile(r"^[A-Z0-9]{9,15}$"),
        "brownfield": re.compile(r"^ACRES-\d+$"),
        "fuds": re.compile(r"^FUDS-[A-Za-z0-9._-]+$"),
        "brac": re.compile(r"^BRAC-[a-z0-9-]+$"),
    }
    bad, examples, checked = 0, [], 0
    for sid, program in c.id_program.items():
        checked += 1
        pat = patterns.get(program)
        if pat and not pat.match(sid):
            bad += 1
            if len(examples) < 200:
                examples.append(f"{program}:{sid}")
    yield Finding(
        "id-namespace", "struct", verdict(bad), checked, bad,
        "ids match their program's documented namespace", examples,
    )


@check("program-consistent", "struct")
def c_program_consistent(c: Corpus):
    bad, examples, checked = 0, [], 0
    for fname in ENRICHMENT_FILES:
        for rec in c.sites.get(fname, []):
            sid, prog = rec.get("id"), rec.get("program")
            if sid not in c.id_program or prog is None:
                continue
            checked += 1
            if prog != c.id_program[sid]:
                bad += 1
                if len(examples) < 200:
                    examples.append(f"{fname}:{sid}:{prog}!={c.id_program[sid]}")
    yield Finding(
        "program-consistent", "struct", verdict(bad), checked, bad,
        "enrichment `program` agrees with the program file that owns the id", examples,
    )


@check("join-orphans", "struct")
def c_join_orphans(c: Corpus):
    bad, examples, checked = 0, [], 0
    per_file = {}
    for fname in ENRICHMENT_FILES:
        recs = c.sites.get(fname, [])
        orphans = [r.get("id") for r in recs if r.get("id") not in c.universe]
        checked += len(recs)
        bad += len(orphans)
        if orphans:
            per_file[fname] = len(orphans)
            for o in orphans[:5]:
                if len(examples) < 200:
                    examples.append(f"{fname}:{o}")
    yield Finding(
        "join-orphans", "struct", verdict(bad), checked, bad,
        "every enrichment id resolves to a record in a program file",
        examples, {"per_file": per_file},
    )


@check("coverage", "struct")
def c_coverage(c: Corpus):
    total = len(c.universe)
    cov = {}
    for fname in ENRICHMENT_FILES:
        ids = {r.get("id") for r in c.sites.get(fname, [])}
        cov[fname] = round(100.0 * len(ids & set(c.universe)) / total, 1)
    yield Finding(
        "coverage", "struct", "INFO", total, 0,
        "enrichment coverage of the site universe (%)", [], {"coverage_pct": cov},
    )


@check("sites-mirror", "struct")
def c_sites_mirror(c: Corpus):
    """docs/data/sites.json must be byte-equivalent to superfund-npl.json."""
    a = (DATA / "sites.json").read_bytes()
    b = (DATA / "superfund-npl.json").read_bytes()
    bad = 0 if a == b else 1
    yield Finding(
        "sites-mirror", "struct", verdict(bad), 1, bad,
        "sites.json is an exact mirror of superfund-npl.json",
        [] if not bad else [f"sites={len(a)}B superfund-npl={len(b)}B"],
    )


@check("value-domains", "struct")
def c_value_domains(c: Corpus):
    bad, examples, checked = 0, [], 0
    counters: dict[str, Counter] = defaultdict(Counter)
    for sid, rec in c.merged.items():
        checked += 1
        st = rec.get("state")
        if st is not None and st not in ALL_STATE_CODES:
            bad += 1
            counters["state"][st] += 1
            if len(examples) < 200:
                examples.append(f"{sid}:state={st!r}")
        code = rec.get("npl_status_code")
        if code is not None and code not in NPL_STATUS_CODES:
            bad += 1
            counters["npl_status_code"][code] += 1
            if len(examples) < 200:
                examples.append(f"{sid}:npl={code!r}")
        prog = rec.get("program")
        if prog not in PROGRAMS:
            bad += 1
            counters["program"][prog] += 1
        for fld in ("nri_risk_rating", "nri_wildfire_rating", "nri_drought_rating",
                    "nri_heatwave_rating"):
            val = rec.get(fld)
            if val is not None and val not in NRI_RATINGS:
                bad += 1
                counters[fld][val] += 1
                if len(examples) < 200:
                    examples.append(f"{sid}:{fld}={val!r}")
        ect = rec.get("energy_community_type")
        if ect is not None and ect not in ENERGY_COMMUNITY_TYPES:
            bad += 1
            counters["energy_community_type"][ect] += 1
        iso = rec.get("iso_rto")
        if iso is not None and iso not in ISO_RTOS:
            bad += 1
            counters["iso_rto"][iso] += 1
            if len(examples) < 200:
                examples.append(f"{sid}:iso={iso!r}")
    yield Finding(
        "value-domains", "struct", verdict(bad), checked, bad,
        "categorical fields hold only documented values", examples,
        {"offending_values": {k: dict(v.most_common(10)) for k, v in counters.items()}},
    )


@check("numeric-ranges", "struct")
def c_numeric_ranges(c: Corpus):
    this_year = date.today().year
    rules: dict[str, tuple[float, float]] = {
        # Ceiling is deliberately loose: WWII FUDS "maneuver areas" are
        # legitimately enormous (Northwest Maneuver Area 8.0M acres, Tennessee
        # 4.3M) because they were training REGIONS, not parcels. Anything
        # under Alaska's land area is at least conceivable; the real
        # size check is `acreage-vs-state-area` below, which asks whether a
        # site is bigger than the state it sits in.
        "acreage": (0.0001, 400_000_000),
        "parcel_acreage": (0.0001, 400_000_000),
        "transmission_kv": (1, 1200),
        "substation_kv": (1, 1200),
        "power_plant_mw": (0.01, 25_000),
        "retired_plant_mw": (0.01, 25_000),
        "planned_retirement_mw": (0.01, 25_000),
        "nri_risk_score": (0, 100),
        "grant_total_usd": (0, 500_000_000),
        "grant_count": (0, 500),
        "region": (1, 10),
        "retired_plant_year": (1900, this_year),
        "planned_retirement_year": (this_year - 2, this_year + 40),
    }
    for fld in DISTANCE_FIELDS:
        rules[fld] = (0.0, MAX_DISTANCE_MI)
    for fld, cap in RADIUS_CAPPED_FIELDS.items():
        rules[fld] = (0.0, cap)

    # Scan every file's OWN records, not the merged view — a bad value must
    # be attributed to the file that emitted it, even when the fill-if-empty
    # join means users never see it.
    bad, examples, checked = 0, [], 0
    per_field: Counter = Counter()
    for fname in list(PROGRAM_FILES.values()) + ENRICHMENT_FILES:
        for rec in c.sites.get(fname, []):
            sid = rec.get("id")
            for fld, (lo, hi) in rules.items():
                val = rec.get(fld)
                if val is None:
                    continue
                checked += 1
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    bad += 1
                    per_field[f"{fname}:{fld}"] += 1
                    continue
                if math.isnan(val) or val < lo or val > hi:
                    bad += 1
                    per_field[f"{fname}:{fld}"] += 1
                    if len(examples) < 200:
                        examples.append(f"{fname}:{sid}:{fld}={val}")
    yield Finding(
        "numeric-ranges", "struct", verdict(bad), checked, bad,
        "numeric fields fall inside their physically/contractually valid range",
        examples, {"per_field": dict(per_field)},
    )


@check("dates", "struct")
def c_dates(c: Corpus):
    bad, examples, checked = 0, [], 0
    today = date.today().isoformat()
    iso = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for sid, rec in c.merged.items():
        for fld in ("cleanup_complete_date",):
            val = rec.get(fld)
            if val is None:
                continue
            checked += 1
            if not iso.match(str(val)) or str(val) > today:
                bad += 1
                if len(examples) < 200:
                    examples.append(f"{sid}:{fld}={val}")
        enf = rec.get("enforcement") or {}
        for fld in ("last_violation_date", "last_inspection_date",
                    "last_formal_action_date"):
            val = enf.get(fld)
            if not val:
                continue
            checked += 1
            if not iso.match(str(val)) or str(val) > today:
                bad += 1
                if len(examples) < 200:
                    examples.append(f"{sid}:enforcement.{fld}={val}")
        for doc in rec.get("documents") or []:
            val = doc.get("date")
            if not val:
                continue
            checked += 1
            if not iso.match(str(val)) or str(val) > today or str(val) < "1970-01-01":
                bad += 1
                if len(examples) < 200:
                    examples.append(f"{sid}:doc={val}")
        lu = rec.get("last_updated")
        if lu is not None:
            checked += 1
            # Epoch ms; anything outside 1990..now+1y is corrupt.
            if not (631_152_000_000 < float(lu) < 1_900_000_000_000):
                bad += 1
                if len(examples) < 200:
                    examples.append(f"{sid}:last_updated={lu}")
    yield Finding(
        "dates", "struct", verdict(bad), checked, bad,
        "dates are ISO-formatted and not in the future", examples,
    )


@check("urls", "struct")
def c_urls(c: Corpus):
    bad, examples, checked = 0, [], 0
    ok = re.compile(r"^https://[a-z0-9.-]+\.[a-z]{2,}(/|$)", re.I)
    hosts: Counter = Counter()
    for sid, rec in c.merged.items():
        for fld in ("profile_url",):
            val = rec.get(fld)
            if not val:
                continue
            checked += 1
            if not ok.match(val):
                bad += 1
                if len(examples) < 200:
                    examples.append(f"{sid}:{fld}={val[:60]}")
            else:
                hosts[val.split("/")[2]] += 1
        for doc in rec.get("documents") or []:
            val = doc.get("url")
            if not val:
                continue
            checked += 1
            if not ok.match(val):
                bad += 1
                if len(examples) < 200:
                    examples.append(f"{sid}:doc={val[:60]}")
            else:
                hosts[val.split("/")[2]] += 1
    yield Finding(
        "urls", "struct", verdict(bad), checked, bad,
        "profile and document URLs are well-formed https", examples,
        {"hosts": dict(hosts.most_common(10))},
    )


# --------------------------------------------------------------------------
# GEO
# --------------------------------------------------------------------------


@check("coord-present", "geo")
def c_coord_present(c: Corpus):
    per_program: Counter = Counter()
    total: Counter = Counter()
    examples = []
    for sid, rec in c.universe.items():
        prog = rec.get("program")
        total[prog] += 1
        if rec.get("lat") is None or rec.get("lon") is None:
            per_program[prog] += 1
            if len(examples) < 200:
                examples.append(sid)
    bad = sum(per_program.values())
    yield Finding(
        "coord-present", "geo", verdict(bad), sum(total.values()), bad,
        "every site record carries lat and lon", examples,
        {"missing_by_program": dict(per_program), "total_by_program": dict(total)},
    )


@check("coord-range", "geo")
def c_coord_range(c: Corpus):
    bad, examples, checked = 0, [], 0
    reasons: Counter = Counter()
    for sid, rec in c.universe.items():
        lat, lon = rec.get("lat"), rec.get("lon")
        if lat is None or lon is None:
            continue
        checked += 1
        why = None
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            why = "out-of-range"
        elif lat == 0 and lon == 0:
            why = "null-island"
        elif abs(lat) < 1e-9 or abs(lon) < 1e-9:
            why = "zero-component"
        elif -125.5 <= lat <= -66.5 and 24 <= lon <= 49.5:
            why = "lat/lon-swapped"
        if why:
            bad += 1
            reasons[why] += 1
            if len(examples) < 200:
                examples.append(f"{sid}:{why}:{lat},{lon}")
    yield Finding(
        "coord-range", "geo", verdict(bad), checked, bad,
        "coordinates are in range, non-null-island, and not lat/lon swapped",
        examples, {"reasons": dict(reasons)},
    )


@check("coord-in-region", "geo")
def c_coord_in_region(c: Corpus):
    """Coordinates must land in CONUS or in the box of a US territory."""
    bad, examples, checked = 0, [], 0
    by_state: Counter = Counter()
    for sid, rec in c.universe.items():
        lat, lon = rec.get("lat"), rec.get("lon")
        if lat is None or lon is None:
            continue
        checked += 1
        inside = any(
            lo_lat <= lat <= hi_lat and lo_lon <= lon <= hi_lon
            for (lo_lat, lo_lon, hi_lat, hi_lon) in REGION_BOXES.values()
        )
        if not inside:
            bad += 1
            by_state[rec.get("state")] += 1
            if len(examples) < 200:
                examples.append(f"{sid}:{rec.get('state')}:{lat},{lon}")
    yield Finding(
        "coord-in-region", "geo", verdict(bad), checked, bad,
        "coordinates land inside CONUS or a US territory bounding box",
        examples, {"by_state": dict(by_state.most_common(15))},
    )


@check("point-in-state", "geo")
def c_point_in_state(c: Corpus):
    """Does the site's geometry agree with its own `state` field?

    This is the strongest offline test for a wrong coordinate: the source
    ships state as an attribute and lat/lon as geometry, populated by
    independent paths. Disagreement means one of the two is wrong.

    Raw containment over-reports, because a site legitimately on a state
    line lands microscopically over it and the us-states.json polygons are
    generalized. So every mismatch is also measured: how far is the point
    from the claimed state's own boundary? Under `BORDER_TOLERANCE_MI` the
    disagreement is cartographic noise; beyond it, the record is wrong.
    """
    BORDER_TOLERANCE_MI = 1.0
    idx = c.states
    rings_by_state = _state_rings()

    bad, examples, checked = 0, [], 0
    pairs: Counter = Counter()
    unresolved = 0
    borderline = 0
    offenders: list[dict] = []

    for sid, rec in c.universe.items():
        lat, lon = rec.get("lat"), rec.get("lon")
        claimed = rec.get("state")
        if lat is None or lon is None or claimed not in STATE_NAME_TO_CODE.values():
            continue
        name = idx.containing(lat, lon)
        if name is None:
            unresolved += 1
            continue
        checked += 1
        actual = STATE_NAME_TO_CODE.get(str(name))
        if not actual or actual == claimed:
            continue
        # How deep into the wrong state is it?
        depth = _distance_to_state_mi(lat, lon, claimed, rings_by_state)
        if depth is not None and depth <= BORDER_TOLERANCE_MI:
            borderline += 1
            continue
        bad += 1
        pairs[f"{claimed}->{actual}"] += 1
        offenders.append({
            "id": sid, "claimed": claimed, "actual": actual,
            "lat": lat, "lon": lon,
            "mi_from_claimed_state": None if depth is None else round(depth, 1),
            "name": (rec.get("name") or "")[:48],
        })
    offenders.sort(key=lambda o: -(o["mi_from_claimed_state"] or 0))
    examples = [
        f"{o['id']}:{o['claimed']}!={o['actual']}:{o['mi_from_claimed_state']}mi-out"
        for o in offenders[:6]
    ]
    yield Finding(
        "point-in-state", "geo", verdict(bad), checked, bad,
        f"lat/lon sits inside its own state's polygon (>{BORDER_TOLERANCE_MI} mi "
        f"outside = error; {borderline} borderline cases excused)",
        examples,
        {"mismatch_pairs": dict(pairs.most_common(25)),
         "borderline_within_tolerance": borderline,
         "unresolved_outside_all_polygons": unresolved,
         "offenders": offenders[:400]},
    )


_STATE_RINGS: Optional[dict[str, list[list[list[float]]]]] = None


def _state_rings() -> dict[str, list[list[list[float]]]]:
    """state code -> list of exterior rings, for point-to-boundary distance."""
    global _STATE_RINGS
    if _STATE_RINGS is None:
        out: dict[str, list] = defaultdict(list)
        geo = json.loads((DATA / "us-states.json").read_text())
        for feat in geo["features"]:
            code = STATE_NAME_TO_CODE.get(feat["properties"].get("name"))
            if not code:
                continue
            geom = feat["geometry"]
            polys = ([geom["coordinates"]] if geom["type"] == "Polygon"
                     else geom["coordinates"])
            for rings in polys:
                out[code].append(rings[0])
        _STATE_RINGS = dict(out)
    return _STATE_RINGS


def _distance_to_state_mi(
    lat: float, lon: float, code: str, rings_by_state: dict
) -> Optional[float]:
    """Great-circle-ish distance from (lat, lon) to the claimed state's border."""
    rings = rings_by_state.get(code)
    if not rings:
        return None
    coslat = math.cos(math.radians(lat))
    best = float("inf")
    for ring in rings:
        # Cheap bbox reject: a ring whose bbox is already far can't win.
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        dx = max(min(lons) - lon, lon - max(lons), 0.0) * coslat
        dy = max(min(lats) - lat, lat - max(lats), 0.0)
        if math.hypot(dx, dy) * 69.0 > best:
            continue
        prev = ring[0]
        for cur in ring[1:]:
            d = _point_seg_deg(lon, lat, prev[0], prev[1], cur[0], cur[1], coslat)
            if d < best:
                best = d
            prev = cur
    return None if best == float("inf") else best * 69.0


def _point_seg_deg(px, py, ax, ay, bx, by, coslat) -> float:
    """Point-to-segment distance in degree-equivalents (lon scaled by cos lat)."""
    apx, apy = (px - ax) * coslat, py - ay
    abx, aby = (bx - ax) * coslat, by - ay
    denom = abx * abx + aby * aby
    t = 0.0 if denom == 0 else max(0.0, min(1.0, (apx * abx + apy * aby) / denom))
    return math.hypot(apx - t * abx, apy - t * aby)


@check("point-in-county", "geo")
def c_point_in_county(c: Corpus):
    idx = c.counties
    bad, examples, checked = 0, [], 0
    pairs: Counter = Counter()
    for sid, rec in c.universe.items():
        lat, lon = rec.get("lat"), rec.get("lon")
        claimed = rec.get("county")
        state = rec.get("state")
        if lat is None or lon is None or not claimed or _is_sentinel(claimed):
            continue
        actual = idx.lookup(lat, lon, expected_state=state)
        if actual is None:
            continue
        checked += 1
        if _norm_county(actual) != _norm_county(claimed):
            bad += 1
            pairs[f"{state}:{_norm_county(claimed)}->{_norm_county(actual)}"] += 1
            if len(examples) < 300:
                examples.append(f"{sid}:{state}:{claimed}!={actual}")
    yield Finding(
        "point-in-county", "geo", verdict(bad, warn_only=True), checked, bad,
        "lat/lon falls inside the polygon of the record's own county",
        examples, {"mismatch_pairs": dict(pairs.most_common(25))},
    )


SENTINELS = {"-- not defined --", "_null_", "not defined", "none", "n/a", "na",
             "unknown", "no city", "null", ""}


def _is_sentinel(val: Any) -> bool:
    return str(val).strip().lower() in SENTINELS


def _norm_county(name: str) -> str:
    n = str(name).strip().lower()
    n = re.sub(r"\b(county|parish|borough|census area|city and borough|municipality|"
               r"municipio|city)\b", "", n)
    n = re.sub(r"[^a-z0-9]+", "", n)
    return n


@check("coord-duplicates", "geo")
def c_coord_duplicates(c: Corpus):
    """Many sites stacked on one coordinate = geocoder centroid fallback."""
    buckets: dict[tuple[float, float], list[str]] = defaultdict(list)
    for sid, rec in c.universe.items():
        lat, lon = rec.get("lat"), rec.get("lon")
        if lat is None or lon is None:
            continue
        buckets[(round(lat, 6), round(lon, 6))].append(sid)
    clusters = {k: v for k, v in buckets.items() if len(v) >= 3}
    stacked = sum(len(v) for v in clusters.values())
    worst = sorted(clusters.items(), key=lambda kv: -len(kv[1]))[:12]
    examples = [f"{len(v)}@{k[0]},{k[1]}:{v[0]}" for k, v in worst]
    yield Finding(
        "coord-duplicates", "geo", verdict(stacked, warn_only=True),
        len(buckets), stacked,
        "sites sharing an identical coordinate with >=2 others (centroid fallback)",
        examples,
        {"cluster_count": len(clusters),
         "largest": [{"coord": list(k), "n": len(v), "sample": v[:5]} for k, v in worst]},
    )


@check("coord-precision", "geo")
def c_coord_precision(c: Corpus):
    coarse, examples, checked = 0, [], 0
    by_program: Counter = Counter()
    for sid, rec in c.universe.items():
        lat, lon = rec.get("lat"), rec.get("lon")
        if lat is None or lon is None:
            continue
        checked += 1
        dp = max(_decimals(lat), _decimals(lon))
        if dp <= 2:  # ~1.1 km resolution or worse
            coarse += 1
            by_program[rec.get("program")] += 1
            if len(examples) < 200:
                examples.append(f"{sid}:{lat},{lon}")
    yield Finding(
        "coord-precision", "geo", verdict(coarse, warn_only=True), checked, coarse,
        "coordinates carry >2 decimal places (<~1.1 km positional resolution)",
        examples, {"by_program": dict(by_program)},
    )


@check("coord-placeholder", "geo")
def c_coord_placeholder(c: Corpus):
    """Coordinates that are obviously typed-in rather than surveyed.

    Whole or half degrees, or a lat/lon whose fractional parts are equal,
    are the signature of a placeholder rather than a measurement.
    """
    bad, examples, checked = 0, [], 0
    kinds: Counter = Counter()
    for sid, rec in c.universe.items():
        lat, lon = rec.get("lat"), rec.get("lon")
        if lat is None or lon is None:
            continue
        checked += 1
        why = None
        if float(lat).is_integer() and float(lon).is_integer():
            why = "whole-degree"
        elif abs(lat * 2 - round(lat * 2)) < 1e-9 and abs(lon * 2 - round(lon * 2)) < 1e-9:
            why = "half-degree"
        elif abs(abs(lat) - abs(lon)) < 1e-9:
            why = "lat==|lon|"
        if why:
            bad += 1
            kinds[why] += 1
            if len(examples) < 200:
                examples.append(f"{sid}:{rec.get('state')}:{lat},{lon}")
    yield Finding(
        "coord-placeholder", "geo", verdict(bad), checked, bad,
        "no coordinate sits on a whole/half degree or mirrors its own components",
        examples, {"kinds": dict(kinds)},
    )


@check("text-sentinels", "geo")
def c_text_sentinels(c: Corpus):
    """Source placeholder strings must be nulled at the connector, not shipped."""
    bad, examples, checked = 0, [], 0
    per_field: Counter = Counter()
    for sid, rec in c.universe.items():
        for fld in ("city", "county", "address", "state", "name", "current_owner"):
            val = rec.get(fld)
            if val is None:
                continue
            checked += 1
            if _is_sentinel(val):
                bad += 1
                per_field[f"{fld}={str(val).strip()}"] += 1
                if len(examples) < 200:
                    examples.append(f"{sid}:{fld}={val!r}")
    yield Finding(
        "text-sentinels", "geo", verdict(bad, warn_only=True), checked, bad,
        "no record ships a source sentinel string in place of a null",
        examples, {"per_field": dict(per_field.most_common(15))},
    )


def _decimals(v: float) -> int:
    s = repr(float(v))
    if "e" in s or "E" in s:
        return 10
    return len(s.split(".")[1].rstrip("0")) if "." in s else 0


# --------------------------------------------------------------------------
# INFRA
# --------------------------------------------------------------------------


@check("infra-lipschitz", "infra")
def c_infra_lipschitz(c: Corpus):
    """Nearest-feature distance is 1-Lipschitz in position.

    For sites A and B: |d(A) - d(B)| <= dist(A, B). Both operands come from
    our own files, so a violation is a self-contained proof of a defect —
    a mis-indexed segment, a stale join, or a wrong coordinate on one of the
    two sites. Tolerance absorbs the 0.1 mi output rounding on both values
    plus the connector's local-equirectangular projection error.
    """
    pts: list[tuple[str, float, float, dict]] = []
    for sid, rec in c.merged.items():
        lat, lon = rec.get("lat"), rec.get("lon")
        if lat is None or lon is None:
            continue
        vals = {f: rec.get(f) for f in DISTANCE_FIELDS if rec.get(f) is not None}
        if vals:
            pts.append((sid, lat, lon, vals))

    cell = 0.03  # ~2 mi latitude
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, (_, lat, lon, _) in enumerate(pts):
        grid[(int(lat // cell), int(lon // cell))].append(i)

    tol = 0.25  # 0.1+0.1 rounding, 0.05 projection slack
    max_pairs_per_site = 40
    violations: list[dict] = []
    per_field: Counter = Counter()
    pairs_checked = 0

    for i, (sid_a, lat_a, lon_a, va) in enumerate(pts):
        cy, cx = int(lat_a // cell), int(lon_a // cell)
        neighbours: list[int] = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                neighbours.extend(grid.get((cy + dy, cx + dx), ()))
        budget = max_pairs_per_site
        for j in neighbours:
            if j <= i:
                continue
            if budget <= 0:
                break
            sid_b, lat_b, lon_b, vb = pts[j]
            sep = haversine_mi(lat_a, lon_a, lat_b, lon_b)
            if sep > 2.0:
                continue
            budget -= 1
            pairs_checked += 1
            for fld, a_val in va.items():
                b_val = vb.get(fld)
                if b_val is None:
                    continue
                # A value pinned at the 100 mi cap is censored, not measured.
                if a_val >= MAX_DISTANCE_MI or b_val >= MAX_DISTANCE_MI:
                    continue
                excess = abs(a_val - b_val) - sep - tol
                if excess > 0:
                    per_field[fld] += 1
                    if len(violations) < 400:
                        violations.append({
                            "field": fld, "a": sid_a, "b": sid_b,
                            "a_val": a_val, "b_val": b_val,
                            "separation_mi": round(sep, 3),
                            "excess_mi": round(excess, 3),
                        })
    bad = sum(per_field.values())
    violations.sort(key=lambda v: -v["excess_mi"])
    examples = [
        f"{v['field']} {v['a']}={v['a_val']} vs {v['b']}={v['b_val']} "
        f"sep={v['separation_mi']} excess={v['excess_mi']}"
        for v in violations[:6]
    ]
    yield Finding(
        "infra-lipschitz", "infra", verdict(bad), pairs_checked, bad,
        "|d(A)-d(B)| <= dist(A,B) holds for every nearest-X distance field",
        examples, {"per_field": dict(per_field), "worst": violations[:60]},
    )


@check("infra-identical-coords", "infra")
def c_infra_identical_coords(c: Corpus):
    """Two records at the same coordinate must get identical distances."""
    buckets: dict[tuple[float, float], list[str]] = defaultdict(list)
    for sid, rec in c.merged.items():
        lat, lon = rec.get("lat"), rec.get("lon")
        if lat is None or lon is None:
            continue
        buckets[(round(lat, 6), round(lon, 6))].append(sid)
    bad, examples, checked = 0, [], 0
    per_field: Counter = Counter()
    for coord, ids in buckets.items():
        if len(ids) < 2:
            continue
        for fld in DISTANCE_FIELDS:
            vals = {c.merged[i].get(fld) for i in ids}
            vals.discard(None)
            if len(vals) <= 1:
                continue
            checked += 1
            spread = max(vals) - min(vals)
            if spread > 0.15:
                bad += 1
                per_field[fld] += 1
                if len(examples) < 200:
                    examples.append(f"{fld}@{coord[0]},{coord[1]}:{sorted(vals)[:3]}")
    yield Finding(
        "infra-identical-coords", "infra", verdict(bad), checked, bad,
        "co-located records receive identical nearest-feature distances",
        examples, {"per_field": dict(per_field)},
    )


@check("infra-substation-vs-line", "infra")
def c_infra_sub_vs_line(c: Corpus):
    """A substation sits on the transmission network it switches.

    So transmission_mi should not materially exceed substation_mi. A large
    positive gap means the transmission index missed a line the substation
    index proves is there.
    """
    bad, examples, checked = 0, [], 0
    gaps: list[tuple[float, str]] = []
    by_state: Counter = Counter()
    over_10 = over_25 = 0
    for sid, rec in c.merged.items():
        t, s = rec.get("transmission_mi"), rec.get("substation_mi")
        if t is None or s is None:
            continue
        if t >= MAX_DISTANCE_MI or s >= MAX_DISTANCE_MI:
            continue
        checked += 1
        gap = t - s
        if gap > 2.0:
            bad += 1
            by_state[rec.get("state")] += 1
            over_10 += gap > 10
            over_25 += gap > 25
            gaps.append((gap, f"{sid}:t={t},s={s}"))
    gaps.sort(reverse=True)
    examples = [g[1] for g in gaps[:6]]
    yield Finding(
        "infra-substation-vs-line", "infra", verdict(bad, warn_only=True),
        checked, bad,
        "transmission_mi exceeds substation_mi by >2 mi — HIFLD line coverage "
        "is sparser than OSM substations. COMPENSATED in scoring since "
        "2026-08-09 (dc-score.js _effectiveGridAccess); this stays visible as "
        "a measure of the source gap, not an unhandled defect",
        examples,
        {"by_state": dict(by_state.most_common(15)),
         "gap_over_10mi": over_10, "gap_over_25mi": over_25,
         "worst": [g[1] for g in gaps[:60]]},
    )


@check("infra-tombstones", "infra")
def c_infra_tombstones(c: Corpus):
    """Records with no distance fields at all should be out-of-CONUS."""
    recs = c.sites.get("infra-proximity.json", [])
    tomb = [r["id"] for r in recs
            if not any(r.get(f) is not None for f in DISTANCE_FIELDS)]
    conus = REGION_BOXES["conus"]
    surprising = []
    for sid in tomb:
        rec = c.universe.get(sid)
        if not rec:
            continue
        lat, lon = rec.get("lat"), rec.get("lon")
        if lat is None or lon is None:
            continue
        if conus[0] <= lat <= conus[2] and conus[1] <= lon <= conus[3]:
            surprising.append(f"{sid}:{rec.get('state')}:{lat},{lon}")
    yield Finding(
        "infra-tombstones", "infra", verdict(len(surprising), warn_only=True),
        len(tomb), len(surprising),
        "distance-free tombstones are all outside CONUS (no source coverage)",
        surprising[:8], {"tombstone_total": len(tomb),
                         "in_conus": surprising[:100]},
    )


@check("planned-retire-recompute", "infra")
def c_planned_retire_recompute(c: Corpus):
    """Exactly recompute planned_retirement_* from the local overlay."""
    plants = c.sites.get("planned-retirements.json", [])
    if not plants:
        yield Finding("planned-retire-recompute", "infra", "WARN", 0, 1,
                      "planned-retirements.json missing")
        return
    bad, examples, checked = 0, [], 0
    field_bad: Counter = Counter()
    for rec in c.sites.get("planned-retirements-proximity.json", []):
        site = c.universe.get(rec["id"])
        if not site or site.get("lat") is None:
            continue
        checked += 1
        best = min(
            plants,
            key=lambda p: haversine_mi(site["lat"], site["lon"], p["lat"], p["lon"]),
        )
        d = haversine_mi(site["lat"], site["lon"], best["lat"], best["lon"])
        claimed = rec.get("planned_retirement_mi")
        problems = []
        if claimed is None or abs(claimed - d) > 0.15:
            problems.append(f"mi {claimed}!={round(d, 2)}")
            field_bad["planned_retirement_mi"] += 1
        if rec.get("planned_retirement_name") != best["name"]:
            problems.append(f"name {rec.get('planned_retirement_name')}!={best['name']}")
            field_bad["planned_retirement_name"] += 1
        if rec.get("planned_retirement_mw") is not None and \
                abs(rec["planned_retirement_mw"] - best["mw"]) > 0.6:
            problems.append(f"mw {rec['planned_retirement_mw']}!={best['mw']}")
            field_bad["planned_retirement_mw"] += 1
        if rec.get("planned_retirement_year") != best.get("last_retirement_year"):
            problems.append(
                f"year {rec.get('planned_retirement_year')}!={best.get('last_retirement_year')}")
            field_bad["planned_retirement_year"] += 1
        if problems:
            bad += 1
            if len(examples) < 200:
                examples.append(f"{rec['id']}:{';'.join(problems)}")
    yield Finding(
        "planned-retire-recompute", "infra", verdict(bad), checked, bad,
        "planned_retirement_* reproduced exactly from planned-retirements.json",
        examples, {"per_field": dict(field_bad)},
    )


@check("nuclear-proximity-recompute", "infra")
def c_nuclear_recompute(c: Corpus):
    """Recompute nuclear-brownfield-proximity distances from site coords."""
    recs = c.sites.get("nuclear-brownfield-proximity.json", [])
    radius = c.raw.get("nuclear-brownfield-proximity.json", {}).get("radius_mi", 50)
    bad, examples, checked = 0, [], 0
    for rec in recs:
        nlat, nlon = rec.get("lat"), rec.get("lon")
        if nlat is None:
            continue
        for nb in rec.get("nearby_brownfields") or []:
            site = c.universe.get(nb.get("id"))
            checked += 1
            if not site or site.get("lat") is None:
                bad += 1
                if len(examples) < 200:
                    examples.append(f"{rec['nuclear_site_id']}:unknown-id={nb.get('id')}")
                continue
            d = haversine_mi(nlat, nlon, site["lat"], site["lon"])
            claimed = nb.get("mi", nb.get("distance_mi"))
            if claimed is None or abs(float(claimed) - d) > 0.2 or d > radius + 0.5:
                bad += 1
                if len(examples) < 200:
                    examples.append(
                        f"{rec['nuclear_site_id']}->{nb.get('id')}:{claimed}!={round(d, 2)}")
    yield Finding(
        "nuclear-proximity-recompute", "infra", verdict(bad), checked, bad,
        "nuclear→brownfield distances reproduce from the sites' own coordinates",
        examples,
    )


@check("retired-industrial-join", "infra")
def c_retired_industrial_join(c: Corpus):
    """Recompute the retired-industrial → tracked-corpus 1 mi join."""
    bad, examples, checked = 0, [], 0
    for rec in c.sites.get("retired-industrial.json", []):
        tid = rec.get("tracked_site_id")
        if not tid:
            continue
        checked += 1
        site = c.universe.get(tid)
        if not site or site.get("lat") is None:
            bad += 1
            if len(examples) < 200:
                examples.append(f"{rec['id']}:unknown tracked id {tid}")
            continue
        d = haversine_mi(rec["lat"], rec["lon"], site["lat"], site["lon"])
        claimed = rec.get("tracked_site_mi")
        if claimed is None or abs(float(claimed) - d) > 0.1 or d > 1.05:
            bad += 1
            if len(examples) < 200:
                examples.append(f"{rec['id']}:{claimed}!={round(d, 3)}")
        if rec.get("tracked_site_program") and \
                rec["tracked_site_program"] != site.get("program"):
            bad += 1
            if len(examples) < 200:
                examples.append(f"{rec['id']}:program mismatch")
    yield Finding(
        "retired-industrial-join", "infra", verdict(bad), checked, bad,
        "retired-industrial tracked-site join distances reproduce exactly", examples,
    )


@check("infra-state-outliers", "infra")
def c_infra_state_outliers(c: Corpus):
    """Flag distances far outside their state's own distribution.

    Not a proof of error, but a wrong coordinate usually lands a site in
    empty terrain and produces a distance nothing else in that state shows.
    """
    by_state: dict[tuple[str, str], list[tuple[float, str]]] = defaultdict(list)
    for sid, rec in c.merged.items():
        st = rec.get("state")
        if st not in STATES:
            continue
        for fld in ("transmission_mi", "highway_mi"):
            val = rec.get(fld)
            if val is not None and val < MAX_DISTANCE_MI:
                by_state[(st, fld)].append((val, sid))
    outliers: list[str] = []
    total = 0
    for (st, fld), vals in by_state.items():
        if len(vals) < 30:
            continue
        vals.sort()
        p50 = vals[len(vals) // 2][0]
        p99 = vals[int(len(vals) * 0.99)][0]
        threshold = max(p99 * 3, p50 * 20, 15.0)
        for v, sid in vals:
            if v > threshold:
                total += 1
                if len(outliers) < 200:
                    outliers.append(f"{fld} {sid} {st}={v} (p50={p50},p99={p99})")
    yield Finding(
        "infra-state-outliers", "infra", "INFO", sum(len(v) for v in by_state.values()),
        total, "distances >3x the state's p99 — candidate bad coordinates",
        outliers[:6], {"outliers": outliers[:150]},
    )


# --------------------------------------------------------------------------
# DERIVED
# --------------------------------------------------------------------------


@check("acreage-vs-state-area", "geo")
def c_acreage_vs_state(c: Corpus):
    """No site can be larger than the state that contains it.

    A far better size test than an absolute ceiling: FUDS maneuver areas
    legitimately reach 8M acres, so any fixed cap either lets real garbage
    through or rejects real data. The state's own land area is the physical
    bound, and it scales correctly from Rhode Island to Alaska.
    """
    bad, examples, checked = 0, [], 0
    for sid, rec in c.merged.items():
        ac = rec.get("acreage")
        st = rec.get("state")
        limit = STATE_LAND_ACRES.get(st)
        if ac is None or limit is None:
            continue
        checked += 1
        if ac > limit:
            bad += 1
            if len(examples) < 200:
                examples.append(
                    f"{sid}:{st}:{ac:,.0f}ac > state's {limit:,.0f}ac"
                )
    yield Finding(
        "acreage-vs-state-area", "geo", verdict(bad), checked, bad,
        "no site's acreage exceeds the land area of its own state", examples,
    )


# Land area in acres (US Census 2020 land area, sq mi x 640).
STATE_LAND_ACRES = {
    "AK": 365_481_600, "TX": 167_624_960, "CA": 99_813_760, "MT": 93_271_040,
    "NM": 77_766_400, "AZ": 72_688_000, "NV": 70_264_320, "CO": 66_485_760,
    "WY": 62_147_200, "OR": 61_598_720, "UT": 52_696_960, "MN": 50_955_520,
    "ID": 52_933_120, "KS": 52_510_720, "NE": 49_031_680, "SD": 48_881_920,
    "ND": 44_452_480, "OK": 44_087_680, "MO": 44_248_320, "WA": 42_694_400,
    "GA": 37_295_360, "MI": 36_492_160, "IA": 35_860_480, "IL": 35_580_160,
    "WI": 34_761_600, "FL": 34_721_280, "AR": 33_599_360, "AL": 32_476_800,
    "NC": 31_180_800, "NY": 30_680_960, "MS": 30_222_720, "PA": 28_804_480,
    "LA": 28_867_840, "TN": 26_367_360, "OH": 26_209_920, "VA": 25_496_320,
    "KY": 25_512_320, "IN": 23_158_400, "ME": 19_847_680, "SC": 19_390_080,
    "WV": 15_410_560, "MD": 6_319_360, "VT": 5_936_640, "NH": 5_768_960,
    "MA": 5_034_880, "NJ": 4_748_160, "HI": 4_112_640, "CT": 3_100_160,
    "DE": 1_250_560, "RI": 677_120, "DC": 39_040,
    "PR": 2_174_720, "GU": 133_760, "VI": 86_400, "MP": 116_480,
    "AS": 49_920,
}


@check("dc-candidate-recompute", "derived")
def c_dc_candidate(c: Corpus):
    """Re-derive EPA RE-Powering `data_center_reuse_candidate`.

    Rule (connectors/epa_redev.py:is_dc_candidate): NearElectL starts with
    "Yes" AND acreage >= 50 AND InWaterServiceArea starts with "Yes".
    """
    bad, examples, checked = 0, [], 0
    for rec in c.sites.get("epa-redev.json", []):
        flag = rec.get("data_center_reuse_candidate")
        if flag is None:
            continue
        checked += 1
        elec = str(rec.get("near_electric_transmission") or "")
        water = str(rec.get("near_water_supply") or "")
        # Read the RE-Powering record's OWN acreage — that is what
        # epa_redev.is_dc_candidate() uses. Falling back to the NPL value here
        # would make the check disagree with the code it exists to verify.
        ac = rec.get("acreage")
        expected = bool(
            elec.lower().startswith("yes")
            and water.lower().startswith("yes")
            and ac is not None and ac >= 50
        )
        if expected != bool(flag):
            bad += 1
            if len(examples) < 200:
                examples.append(f"{rec['id']}:flag={flag} elec={elec[:12]} "
                                f"water={water[:12]} ac={ac}")
    yield Finding(
        "dc-candidate-recompute", "derived", verdict(bad), checked, bad,
        "data_center_reuse_candidate matches the documented EPA criteria", examples,
    )


@check("redev-coord-agreement", "derived")
def c_redev_coords(c: Corpus):
    """epa-redev ships its own lat/lon for Superfund sites — an independent
    EPA layer. Disagreement with superfund-npl means one layer is wrong."""
    bad, examples, checked = 0, [], 0
    dists: list[tuple[float, str]] = []
    for rec in c.sites.get("epa-redev.json", []):
        site = c.universe.get(rec["id"])
        if not site or site.get("lat") is None or rec.get("lat") is None:
            continue
        checked += 1
        d = haversine_mi(site["lat"], site["lon"], rec["lat"], rec["lon"])
        dists.append((d, rec["id"]))
        if d > 5.0:
            bad += 1
            if len(examples) < 200:
                examples.append(f"{rec['id']}:{round(d, 1)}mi apart")
    dists.sort(reverse=True)
    p = {}
    if dists:
        n = len(dists)
        p = {"p50": round(dists[n // 2][0], 3),
             "p95": round(dists[n // 20][0], 3),
             "max": round(dists[0][0], 2)}
    yield Finding(
        "redev-coord-agreement", "derived", verdict(bad, warn_only=True),
        checked, bad,
        "EPA RE-Powering and NPL layers place the same site within 5 mi",
        examples, {"separation_mi": p, "worst": [f"{i}:{round(d, 2)}"
                                                 for d, i in dists[:40]]},
    )


@check("redev-acreage-agreement", "derived")
def c_redev_acreage(c: Corpus):
    bad, examples, checked = 0, [], 0
    for rec in c.sites.get("epa-redev.json", []):
        site = c.universe.get(rec["id"])
        a, b = rec.get("acreage"), (site or {}).get("acreage")
        if a is None or b is None or b == 0:
            continue
        checked += 1
        ratio = a / b
        if ratio > 5 or ratio < 0.2:
            bad += 1
            if len(examples) < 200:
                examples.append(f"{rec['id']}:redev={a} npl={b}")
    yield Finding(
        "redev-acreage-agreement", "derived", verdict(bad, warn_only=True),
        checked, bad,
        "RE-Powering and NPL acreage agree within a 5x factor", examples,
    )


@check("ai-summary-consistency", "derived")
def c_ai_summary(c: Corpus):
    """The static summary restates acreage / place / status — a stale summary
    is a silent lie in the most user-visible surface."""
    bad, examples, checked = 0, [], 0
    reasons: Counter = Counter()
    acre_re = re.compile(r"([\d,]+(?:\.\d+)?)-acre")
    for rec in c.sites.get("ai-summary.json", []):
        text = rec.get("summary")
        site = c.merged.get(rec["id"])
        if not text or not site:
            continue
        checked += 1
        problems = []
        m = acre_re.search(text)
        if m:
            stated = float(m.group(1).replace(",", ""))
            actual = site.get("acreage")
            if actual is None:
                problems.append("acreage-stated-but-null")
            elif abs(stated - round(actual)) > max(1.0, actual * 0.02):
                problems.append(f"acreage {stated}!={actual}")
        elif site.get("acreage") is not None and "acre" not in text:
            problems.append("acreage-missing-from-summary")
        st = site.get("state")
        if st and f", {st}" not in text and st not in text:
            problems.append(f"state {st} absent")
        if not text.rstrip().endswith("AI-generated summary from federal records."):
            problems.append("missing-attribution")
        if problems:
            bad += 1
            for p in problems:
                reasons[p.split()[0]] += 1
            if len(examples) < 200:
                examples.append(f"{rec['id']}:{';'.join(problems)}")
    yield Finding(
        "ai-summary-consistency", "derived", verdict(bad, warn_only=True),
        checked, bad,
        "static summaries restate the record's own acreage/state and carry attribution",
        examples, {"reasons": dict(reasons)},
    )


@check("oz-ira-consistency", "derived")
def c_oz_ira(c: Corpus):
    bad, examples, checked = 0, [], 0
    for sid, rec in c.merged.items():
        checked += 1
        if rec.get("oz_rural") is True and rec.get("in_opportunity_zone") is not True:
            bad += 1
            if len(examples) < 200:
                examples.append(f"{sid}:rural-but-not-oz")
        if rec.get("oz_tract_geoid") and rec.get("in_opportunity_zone") is not True:
            bad += 1
            if len(examples) < 200:
                examples.append(f"{sid}:geoid-but-not-oz")
        geoid = rec.get("oz_tract_geoid")
        if geoid and not re.fullmatch(r"\d{11}", str(geoid)):
            bad += 1
            if len(examples) < 200:
                examples.append(f"{sid}:bad-geoid={geoid}")
        ect = rec.get("energy_community_type")
        if ect and rec.get("in_energy_community") is not True:
            bad += 1
            if len(examples) < 200:
                examples.append(f"{sid}:ec-type-but-not-ec")
    yield Finding(
        "oz-ira-consistency", "derived", verdict(bad), checked, bad,
        "Opportunity-Zone and IRA sub-fields agree with their boolean rollups",
        examples,
    )


@check("oz-geoid-vs-county", "derived")
def c_oz_geoid_state(c: Corpus):
    """The OZ tract GEOID embeds a state FIPS — it must match the site's state."""
    fips = _state_fips()
    bad, examples, checked = 0, [], 0
    pairs: Counter = Counter()
    for sid, rec in c.merged.items():
        geoid = rec.get("oz_tract_geoid")
        st = rec.get("state")
        if not geoid or not st or len(str(geoid)) != 11:
            continue
        checked += 1
        want = fips.get(st)
        got = str(geoid)[:2]
        if want and got != want:
            bad += 1
            pairs[f"{st}({want})->{got}"] += 1
            if len(examples) < 200:
                examples.append(f"{sid}:{st}:{geoid}")
    yield Finding(
        "oz-geoid-vs-county", "derived", verdict(bad), checked, bad,
        "OZ tract GEOID state prefix matches the record's state", examples,
        {"pairs": dict(pairs.most_common(20))},
    )


def _state_fips() -> dict[str, str]:
    return {
        "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
        "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
        "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
        "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
        "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
        "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
        "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
        "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
        "WV": "54", "WI": "55", "WY": "56", "PR": "72", "VI": "78", "GU": "66",
        "MP": "69", "AS": "60",
    }


@check("enrichment-freshness", "derived")
def c_freshness(c: Corpus):
    ages = {}
    today = datetime.now().date()
    stale = []
    for fname, payload in c.raw.items():
        if not isinstance(payload, dict):
            continue
        gen = payload.get("generated_at")
        if not gen:
            continue
        try:
            d = datetime.fromisoformat(str(gen).replace("Z", "+00:00")).date()
        except ValueError:
            stale.append(f"{fname}:unparseable={gen}")
            continue
        age = (today - d).days
        ages[fname] = age
        if age > 365:
            stale.append(f"{fname}:{age}d")
        if age < 0:
            stale.append(f"{fname}:future={gen}")
    yield Finding(
        "enrichment-freshness", "derived", verdict(len(stale), warn_only=True),
        len(ages), len(stale), "no data file is >1 year stale or dated in the future",
        stale[:8], {"age_days": dict(sorted(ages.items(), key=lambda kv: -kv[1]))},
    )


# Overlay files with a live Pydantic contract in schema.py. A schema class
# that nothing validates against is documentation pretending to be a guard —
# this check is what makes the classes load-bearing (spec 04/08 lesson).
OVERLAY_SCHEMA_FILES = {
    "coal-conversions.json": ("CoalConversionAsset", "assets"),
    "coal-conversions-proximity.json": ("CoalConversionProximityRecord", "matches"),
    "federal-clean-energy.json": ("FederalCleanEnergySite", "sites"),
    "hanford-e2e.json": ("HanfordParcel", "parcels"),
}

# Curated overlays whose every row must carry the provenance pair
# (source_url-ish citation + verified_at audit stamp) — the
# STATE_DC_INCENTIVES discipline applied to overlay data files.
CURATED_PROVENANCE_FILES = {
    "coal-conversions.json": ("assets", "source_url", "verified_at"),
    "federal-clean-energy.json": ("sites", "solicitation_url", "verified_at"),
    "hanford-e2e.json": ("parcels", "source_url", "verified_at"),
}


@check("overlay-pydantic-schema", "struct")
def c_overlay_schema(c: Corpus):
    """Validate curated overlay files against their schema.py classes."""
    try:
        import schema as schema_mod
    except Exception as exc:  # pragma: no cover
        yield Finding("overlay-pydantic-schema", "struct", "WARN", 0, 1,
                      f"pydantic import failed: {exc}")
        return
    bad, examples, checked = 0, [], 0
    for fname, (cls_name, key) in OVERLAY_SCHEMA_FILES.items():
        payload = c.raw.get(fname)
        cls = getattr(schema_mod, cls_name, None)
        if payload is None or cls is None:
            bad += 1
            examples.append(f"{fname}: missing file or schema class {cls_name}")
            continue
        for rec in payload.get(key, []) or []:
            checked += 1
            try:
                cls.model_validate(rec)
            except Exception as exc:
                bad += 1
                if len(examples) < 200:
                    msg = str(exc).splitlines()[1] if "\n" in str(exc) else str(exc)
                    examples.append(f"{fname}:{rec.get('plant_name') or rec.get('site_id') or rec.get('id')}:{msg[:70]}")
    yield Finding(
        "overlay-pydantic-schema", "struct", verdict(bad), checked, bad,
        "coal/federal overlay records validate against their schema.py classes (extra=forbid)",
        examples,
    )


@check("curated-provenance", "derived")
def c_curated_provenance(c: Corpus):
    """Every curated overlay row carries a resolvable-looking citation and an
    audit stamp; stale stamps (>200 days) surface as a WARN so the quarterly
    re-audit cadence is visible in CI, not just in CLAUDE.md."""
    bad, stale, examples, stale_ex, checked = 0, 0, [], [], 0
    today = datetime.now().date()
    for fname, (key, url_field, date_field) in CURATED_PROVENANCE_FILES.items():
        payload = c.raw.get(fname)
        if payload is None:
            continue
        for rec in payload.get(key, []) or []:
            checked += 1
            label = rec.get("plant_name") or rec.get("site_id") or rec.get("id")
            url = rec.get(url_field)
            stamp = rec.get(date_field)
            if not (isinstance(url, str) and url.startswith("https://")):
                bad += 1
                if len(examples) < 50:
                    examples.append(f"{fname}:{label}:missing {url_field}")
            if not (isinstance(stamp, str) and len(stamp) == 10):
                bad += 1
                if len(examples) < 50:
                    examples.append(f"{fname}:{label}:missing {date_field}")
                continue
            try:
                d = datetime.fromisoformat(stamp).date()
            except ValueError:
                bad += 1
                if len(examples) < 50:
                    examples.append(f"{fname}:{label}:unparseable {date_field}={stamp}")
                continue
            if d > today:
                # A future audit stamp is invalid, not fresh — it would
                # suppress the staleness WARN until that date plus 200 days
                # (same rule as enrichment-freshness's future check).
                bad += 1
                if len(examples) < 50:
                    examples.append(f"{fname}:{label}:future {date_field}={stamp}")
                continue
            if (today - d).days > 200:
                stale += 1
                if len(stale_ex) < 50:
                    stale_ex.append(f"{fname}:{label}:{stamp}")
    yield Finding(
        "curated-provenance", "derived", verdict(bad), checked, bad,
        "every curated coal/federal overlay row carries source_url + verified_at",
        examples,
    )
    yield Finding(
        "curated-provenance-freshness", "derived", verdict(stale, warn_only=True),
        checked, stale,
        "curated overlay audit stamps are <200 days old (quarterly re-audit cadence)",
        stale_ex,
    )


@check("coal-catalog-coherence", "derived")
def c_coal_catalog_coherence(c: Corpus):
    """Internal coherence of the coal conversion catalog + proximity join:
    status/year agreement, DERIVED queue eligibility (an operating plant's
    POI is not transferable), switchyard kV in a real voltage class, the
    modeled valuation reproducing its own formula, and join distances
    reproducing against the catalog coordinates."""
    import math

    payload = c.raw.get("coal-conversions.json")
    prox = c.raw.get("coal-conversions-proximity.json")
    if not payload:
        yield Finding("coal-catalog-coherence", "derived", "WARN", 0, 1,
                      "coal-conversions.json missing")
        return
    KV_CLASSES = {69.0, 115.0, 138.0, 161.0, 230.0, 345.0, 500.0, 765.0}

    def formula(mw: float, water: bool, rail: bool, dist: float) -> float:
        base = mw * 180_000.0 + (25_000_000.0 if water else 0.0) \
            + (12_000_000.0 if rail else 0.0) + 8_000_000.0
        return round(base * math.exp(-0.25 * dist), 2)

    bad, examples, checked = 0, [], 0
    assets = payload.get("assets", []) or []
    by_name = {a.get("plant_name"): a for a in assets}
    for a in assets:
        checked += 1
        name = a.get("plant_name")
        problems = []
        if a.get("status") == "retired" and not a.get("retired_year"):
            problems.append("retired without retired_year")
        if a.get("status") == "planned_retirement" and not a.get("planned_retirement_year"):
            problems.append("planned_retirement without year")
        if a.get("status") == "operating" and (
            a.get("retired_year") or a.get("planned_retirement_year")
        ):
            problems.append("operating with a retirement year")
        if bool(a.get("queue_transfer_eligible")) != (
            a.get("status") in ("retired", "planned_retirement")
            and not a.get("poi_occupied", False)
        ):
            problems.append("queue_transfer_eligible not derived from status/poi_occupied")
        if float(a.get("switchyard_kv", -1)) not in KV_CLASSES:
            problems.append(f"kv {a.get('switchyard_kv')} not a voltage class")
        expect = formula(a.get("nameplate_coal_mw", 0.0), a.get("has_water_intake", False),
                         a.get("has_rail", False), 0.0)
        if abs(expect - float(a.get("est_stranded_asset_value_usd", -1))) > 1.0:
            problems.append("valuation does not reproduce formula")
        if problems:
            bad += 1
            if len(examples) < 50:
                examples.append(f"{name}: {'; '.join(problems)}")

    join_checked = 0
    if prox:
        merged = c.merged
        for rec in prox.get("matches", []) or []:
            join_checked += 1
            checked += 1
            site = merged.get(rec.get("id"))
            plant = by_name.get(rec.get("coal_conversion_plant_name"))
            if site is None or plant is None or site.get("lat") is None:
                bad += 1
                if len(examples) < 50:
                    examples.append(f"{rec.get('id')}: unknown site or plant in join")
                continue
            d = haversine_mi(site["lat"], site["lon"],
                             plant["latitude"], plant["longitude"])
            claimed = rec.get("coal_conversion_plant_mi")
            if claimed is None or abs(float(claimed) - d) > 0.15 or d > 10.5:
                bad += 1
                if len(examples) < 50:
                    examples.append(f"{rec.get('id')}:{claimed}!={round(d, 2)}")
            # None-safe, not truthiness — a legitimate 0.0-mi distance must
            # not fall through to the 99 sentinel.
            ft_mi = 99.0 if claimed is None else float(claimed)
            want_ft = (ft_mi <= 1.5) and bool(plant.get("queue_transfer_eligible"))
            if bool(rec.get("coal_conversion_queue_fasttrack")) != want_ft:
                bad += 1
                if len(examples) < 50:
                    examples.append(f"{rec.get('id')}: fasttrack flag not derived")
    yield Finding(
        "coal-catalog-coherence", "derived", verdict(bad), checked, bad,
        "coal catalog rows internally coherent; proximity join reproduces distances + derived flags",
        examples, {"assets": len(assets), "join_rows": join_checked},
    )


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", default=None,
                    help="Run only these families or check ids.")
    ap.add_argument("--json", type=Path, default=None,
                    help="Write full findings (with offending ids) here.")
    ap.add_argument("--list", action="store_true", help="List checks and exit.")
    ap.add_argument("--fail-on", default="FAIL", choices=["FAIL", "WARN", "NEVER"],
                    help="Exit non-zero at this severity or worse.")
    args = ap.parse_args()

    if args.list:
        for cid, fam, fn in CHECKS:
            print(f"{fam:7} {cid:32} {(fn.__doc__ or '').strip().splitlines()[0][:70]}")
        return 0

    selected = [(cid, fam, fn) for cid, fam, fn in CHECKS
                if not args.only or cid in args.only or fam in args.only]

    print("loading corpus…", file=sys.stderr)
    corpus = Corpus()
    print(f"universe: {len(corpus.universe):,} sites across "
          f"{len(PROGRAM_FILES)} programs; {len(corpus.raw)} files\n", file=sys.stderr)

    findings: list[Finding] = []
    current_family = None
    for cid, fam, fn in selected:
        if fam != current_family:
            print(f"\n── {fam.upper()} " + "─" * (66 - len(fam)))
            current_family = fam
        try:
            for f in fn(corpus):
                findings.append(f)
                print(f.line(), flush=True)
        except Exception as exc:  # a broken check must not hide the others
            f = Finding(cid, fam, "FAIL", 0, 1, f"check raised: {type(exc).__name__}: {exc}")
            findings.append(f)
            print(f.line(), flush=True)

    counts = Counter(f.level for f in findings)
    print("\n" + "=" * 78)
    print(f"{counts['PASS']} pass · {counts['WARN']} warn · {counts['FAIL']} fail · "
          f"{counts['INFO']} info   ({len(findings)} checks)")

    if args.json:
        args.json.write_text(json.dumps(
            {"universe": len(corpus.universe),
             "findings": [f.to_dict() for f in findings]}, indent=1))
        print(f"full detail → {args.json}")

    if args.fail_on == "NEVER":
        return 0
    if counts["FAIL"]:
        return 1
    if args.fail_on == "WARN" and counts["WARN"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
