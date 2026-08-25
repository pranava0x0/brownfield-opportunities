# Spec 13d: Proximate-Infra Data Audit + Efficient Future Refresh

**Status:** Audit RUN 2026-08-24 (live results below); the freshness gate
(`scripts/check_upstream_freshness.py`, 3 unit tests) shipped the same
session. Remaining deliverables (delta pulls, refresh.yml gating) ready.
**Scope:** every proximate-infrastructure signal the Nuclear Siting,
Microreactors, Coal, and DOE Sites tabs render — T&D, gas, water, rail,
road, fiber, substations, power plants, flood — plus the curated infra
rows the DOE dossiers added.

## Target users

- **Pranava as maintainer**: "which of my 30+ data files actually needs a
  re-pull, and which multi-hour connector runs can I skip this month?"
- **The dashboard reader** (every persona): implicitly — they consume the
  as-of dates the evidence panel and `window.__sourceDates` already show,
  and deserve pulls that track upstream reality.

## Jobs to be done

1. "Is anything I'm rendering stale against its source?" — answered in
   ~60 s by the new script instead of a hand audit.
2. "What's the cheapest refresh that closes the gap?" — the verdict table
   maps 1:1 onto connector invocations.
3. "Which datasets CAN'T tell me they changed?" — named out loud
   (UNKNOWN is a finding, never treated as current).

## Live audit results (2026-08-24)

| Source | Ours | Upstream last edit | Verdict |
|---|---|---|---|
| superfund-npl | 2026-05-12 | **2026-08-22** | **STALE** — edited two days before this audit |
| dod-fuds (layer 1) | 2026-05-12 | **2026-08-20** | **STALE** |
| epa-redev | 2026-06-16 | **2026-07-24** | **STALE** |
| EIA-860M workbook | parses **April 2026** | **May 2026 published** | **STALE** (workbook-month comparison — see below) |
| epa-acres | 2026-05-12 | 2021-08-31 | current (source frozen since 2021) |
| dod-brac | 2026-05-12 | 2021-06-10 | current (frozen) |
| transmission (HIFLD) | 2026-07-27 | 2023-09-05 | current — **and upstream is itself 2023-vintage**: the sub-transmission gap `_effectiveGridAccess` corrects is not going away |
| gas pipelines / power plants (HIFLD) | 2026-07-27 | 2025-07-01 | current |
| opportunity zones (HUD) | 2026-05-17 | 2026-02-24 | current |
| IRA coal-closure / MSA (NETL) | 2026-06-08 | 2025-07 | current — note these are the **2024 vintage layers**; watch for a 2025/2026 vintage service appearing as NEW layers, which lastEditDate will NOT catch |
| FEMA NRI counties | 2026-06-08 | 2025-12-16 | current |
| TIGER highways/rail, OSM substations, FEMA NFHL | 2026-07-27 | — | UNKNOWN (no edit signal exposed; see cadence rules) |

**Actions from this audit** (supervised, per the producer-refresh
guardrail — do NOT run unattended):
1. `python3 refresh.py --source superfund-npl --source dod-fuds --source epa-redev`
   then the enrichment chain (`--missing-only` where supported).
2. Bump `EIA_860M_URL` April→May 2026 in `connectors/eia_retired_plants.py`
   AND `scripts/build_planned_retirements.py` (the paired-URL rule), re-run
   both + `planned-retirements-proximity`.
3. UNKNOWN-cadence rules, made explicit here: TIGER = re-pull on the
   annual TIGER release (~Dec); OSM substations = semi-annual or when a
   siting decision hinges on one; NFHL = per-site cache is already
   incremental by design.

## The comparison bug worth remembering

The script's first run marked EIA-860M "current" because it compared our
file's `generated_at` (a June re-run) against the workbook month — but a
June re-run of the April workbook is still April DATA.
`our_eia_workbook_month()` now reads the month out of `EIA_860M_URL`
itself. General rule: **freshness compares the upstream artifact we
CONSUMED, never the date we last ran the code** (regression-tested).

## Efficient future pulls (the build plan)

1. **Shipped — the gate**: `check_upstream_freshness.py` (~60 s, one
   metadata request per layer, 1.5 s/host, IPv4-pinned, exit 1 on any
   STALE). Registry pattern: add a row per new source; `kind: "none"`
   rows must carry an explanatory note (unit-tested).
2. **Wire into CI** (next): a weekly `freshness` job runs the script and
   opens/updates a single tracking issue listing STALE sources — the
   cron never auto-runs producers (the empty-payload guard from the
   backlog stays a precondition for any auto-refresh).
3. **Delta pulls where the API supports it** (later): ArcGIS layers with
   `supportsQueryWithHistoricMoment` or an `EditDate` field can pull
   only changed features; EPA ACRES/FUDS layers are full-replace by
   design (producer semantics — `--missing-only` stays meaningless
   there). Scope honestly: transmission/gas/power-plant layers are the
   wins (big geometries, rare edits).
4. **Screening caches are already the efficient path** for nepa-mcp
   surfaces (per-parcel per-source files; error records deliberately
   cached — clear them to force retry, see the CLAUDE.md playbook).
5. **nepa-mcp tie-in** (spec 13c): propose a `freshness` affordance on
   every server so screens can carry upstream as-of dates the way our
   evidence panel does; until then, this script's ArcGIS pattern covers
   the layers nepa-mcp fronts for us.
6. **Open datasets that could become MCP layers** (user question):
   USGS NWIS streamflow (RDB — trivial), ISO queue CSVs, DOE NEPA
   reading-room listings, EPA EJScreen, USGS seismic design values —
   each is listed with its server proposal in spec 13c; the criterion is
   "point/ROI query answers a siting question" (bulk joins stay
   connectors).

## Readability / simple English

The script's output is one table, one verdict word per row, and one
closing sentence; every UNKNOWN carries a plain-English reason. No
jargon: "upstream last edit", not "editingInfo.dataLastEditDate", in
anything user-facing.

## Guards

- 3 unit tests (registry coverage incl. every infra layer; verdict
  logic incl. UNKNOWN-never-current and error→UNKNOWN; the
  workbook-month rule).
- The script never mutates data — it is a gate, not a refresher; the
  producer-refresh supervision guardrail stands.
