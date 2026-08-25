# Spec 13c: nepa-mcp Gap Analysis — What's Missing, What to Propose Upstream

**Status:** Analysis complete 2026-08-24 (grounded in the 19-server/46-tool
capability census, `research/nepa-mcp-capability-census-2026-08.md`, plus
four shipped screening products: Janus, Hanford, coal, and the four-site
DOE expansion). Upstream proposals are drafted here; filing them against
`pnnl/nepa-mcp` is a separate track.

## Method

Every gap below was hit while answering a REAL question this dashboard's
users asked (the user's own question types: "what fits here", "who decides",
"how fresh is this", "what's nearby that matters"). For each: what we did
instead, and whether the fix belongs upstream (a new nepa-mcp
server/tool), locally (our connectors), or nowhere (honestly disclosed).

## Tier 1 — gaps that forced local workarounds this quarter

| Gap | What we needed it for | What we did instead | Proposal |
|---|---|---|---|
| **NEPA document corpus** (EIS/EA/CX/FONSI text + metadata search) | "What did comparable actions face?" — the single most-asked precedent question | `eis_boundaries` polygons (WHERE, never WHAT); hand-found CX-034321, CX-270875 | **Upstream server: `nepa_documents`** wrapping PNNL's own NEPATEC/SearchNEPA corpus (120k+ docs) — query by geography + agency + action type, return doc metadata + links. PNNL owns both codebases; this is the highest-value marriage in the ecosystem |
| **DOE NEPA reading-room actions by site** | Hanford/Portsmouth/Paducah realty CX tracking (spec 11 H2) | Manual searches of energy.gov/nepa listings | Upstream tool `doe_nepa_actions(site, since)` scraping/API-ing the DOE CX/EA/EIS listings — or a local connector if upstream declines |
| **Substations** | Every siting lens; interconnection reality | Our own OSM Overpass connector (HIFLD's layer went private) | Upstream server `grid` tool `get_substations_in_roi` (OSM-backed, voltage-parsed) — we can contribute our parser (`_parse_osm_voltage`) |
| **Gas pipelines** | Coal repowering + the new DOE gas categories | Our HIFLD `Natural_Gas_Interstate_and_Intrastate_Pipelines_1` connector | Upstream `grid`/`energy` tool `get_gas_pipelines_in_roi` (same HIFLD layer, public) |
| **Transmission lines + kV** | All lenses | Our HIFLD transmission connector + `_effectiveGridAccess` correction | Same `grid` server; include the sub-transmission caveat in the tool docstring (13.5% of sites see a closer substation than any mapped line) |
| **Water availability/rights** (streamflow, basin adjudication, allocation) | AP1000 water validation; WIPP's 6.6M gal/yr verdict; SRS/Portsmouth intake context | USGS NWIS RDB curls + hand-curated water-rights rows (`WATER_RIGHTS`) | **Upstream server: `water`** — `get_streamflow_stats(gauge/latlon)` (NWIS RDB is trivially wrappable), `get_nearest_gauges_in_roi`. Rights/adjudication is state-fragmented — keep curated, but a `state_water_regime(state)` lookup table tool is feasible |
| **Interconnection queues** | "Speed to power" — the #1 screen | Nothing (LBNL Queued Up is annual/aggregate; per-ISO is messy) | Upstream `queues` server for the seven ISO public queue CSVs — normalize {POI, MW, fuel, status, cluster dates}. High effort, highest buyer value; propose as roadmap item |

## Tier 2 — quality-of-life gaps inside existing servers

| Gap | Evidence | Proposal |
|---|---|---|
| **IPaC latency/timeout behavior** | 40 s timeouts at Portsmouth ×5 (healed on retry); the census notes IPaC slowness | Upstream: expose IPaC's async job pattern or a lighter `species_list_only` mode; local: our 40 s cap + retry-after-cache-clear playbook is documented |
| **NFHL flakiness** | Connection aborts at SRS (healed on retry) | Upstream: internal retry-with-backoff in `fema_nfhl`; local: same playbook |
| **Multi-server per-process isolation** | The `src` namespace/sys.path collision (CLAUDE.md 2026-08-24) — `load_server_module` is one-server-per-process by design | **Upstream PR-ready fix**: in `load_server_module`, always re-front the server dir (remove-then-insert) instead of the `not in sys.path` guard; our `purge_server_src_namespace()` is the local shim and the PR's test case |
| **Geographic scoping metadata** | NOAA/EFH are West-Coast-only; nothing machine-readable says so — we hardcoded the exclusion | Upstream: a `coverage` field in the server registry (bbox or state list) so callers can auto-exclude inapplicable tools instead of rendering misleading zeros |
| **PAD-US ROI reliability** | Census: unreliable beyond point context; we run 0.1-mi buffers everywhere | Upstream bug report with our probe data |
| **USACE wetlands honesty** | District/delineation-region only — never presence/jurisdiction; every consumer must re-caveat | Upstream: put the limitation IN the response payload (we set `limitation` locally; make it canonical) |

## Tier 3 — new server ideas matched to this user's question types

The question patterns from this quarter's sessions, and the server each
implies:

1. "Who decides / which permits, in what order?" → **`permitting`
   server**: state siting-board registry (thresholds, statute, URL — our
   OPSB/KY-siting/EFSEC/SC-PSC rows generalized to 50 states), federal
   nexus checklist (`has_federal_handle(land_owner, funding, permit)` →
   NEPA-attaches verdict). Curated data, tool-shaped.
2. "How fresh is this layer?" → **`freshness` tool on every server**:
   return the upstream service's lastEditDate/publication date alongside
   results (our `check_upstream_freshness.py` proves the ArcGIS pattern;
   see spec 13d).
3. "What's the seismic picture?" → `usgs_seismic` server (design PGA /
   fault distance from USGS web services) — the microreactor lens
   currently discloses "seismic not scored"; OR-SAGE needs it too.
4. "Is this in an EJ/burdened community?" → EPA EJScreen wrapper
   (block-group indexes) — consultation-risk context for the coal
   audience; render as context, never a score.
5. "Who owns the land next door?" → out of scope for nepa-mcp (state
   cadastres are our parcel-owner connector's job); recommend AGAINST
   proposing — parcel data is licensing-fraught.

## What we deliberately do NOT propose

- Corpus-wide per-site screening tools (the ~19 h/layer flood-backfill
  trap): nepa-mcp is right to be per-point/per-ROI; bulk joins belong in
  connectors.
- A scoring/suitability tool inside nepa-mcp: judgment stays out of the
  evidence layer — the same "screening, not siting" rail we render.

## Upstream engagement plan

1. File the `load_server_module` re-front fix + test (small PR, high
   acceptance odds).
2. File the coverage-metadata issue with the NOAA/EFH case.
3. Open a discussion issue for `nepa_documents` (NEPATEC marriage) with
   this spec's question-type evidence.
4. Offer the substation/gas/water tool implementations from our
   connectors if a `grid`/`water` server lands.
