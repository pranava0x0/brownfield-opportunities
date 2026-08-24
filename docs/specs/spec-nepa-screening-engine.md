# Spec 10: Reusable NEPA Screening Engine (`nepa_screening.py`) & Screen-Any-Catalog Roadmap

**Status:** v1 shipped 2026-08-24 — shared module extracted from the Janus builder; three production consumers (Janus, Hanford E2E, coal repowering)
**Priority:** High (Impact: 5/5, Size: 2/5 remaining, Completeness: 5/5)
**Target Version:** v1.15.x
**Lead Component:** `scripts/nepa_screening.py`, `scripts/build_janus_nepa.py`, `scripts/build_hanford_e2e.py`, `scripts/build_coal_nepa.py`

---

## 1. Executive Summary & Value Proposition

Every curated site list this platform ships (Janus installations, coal
repowering assets, Hanford parcels, nuclear pipeline sites, federal
clean-energy reservations, reference campuses) faces the same question the
scoring lenses structurally cannot answer: **what does the environmental and
permitting record around this point look like?** PNNL's `nepa-mcp` answers it
per point — but as of 2026-08-21 the only consumer was a Janus-specific
script with all machinery inlined.

v1 extracts the engine: one audited module owning the IPv4 pin, the
1.5 s/host throttle (monkeypatched into `requests.Session.request` so
nepa-mcp's own fan-out obeys the repo's ethics floor), bounded upstream
timeouts, disk caching with explicit-unavailable records, ten response
normalizers written against live-captured 0.1.1 shapes, the source-matrix
loop with per-site failure isolation, and Map Composer package collection.
A new screening product is now a ~200-line curation file, proven three times
in one day. Full tool census: [research/nepa-mcp-capability-census-2026-08.md](../../research/nepa-mcp-capability-census-2026-08.md).

## 2. Contracts the engine enforces (do not weaken)

1. **nepa-mcp is never a project dependency.** Python ≥3.12 + shapely/pyproj
   stay out of `requirements.txt`; every `import nepa_mcp` lives inside a
   function body so pytest (3.9) unit-tests the pure logic
   (`tests/test_nepa_screening.py`, fake-loader injection).
2. **Unavailable is never a no-hit.** Failures cache as
   `{"status": "unavailable"}` and render as "Unavailable" — a deliberate
   trade: a transient blip stays cached until a `--no-cache` rerun, which
   beats hammering a struggling federal host on every rebuild.
3. **Version pinned, fail-loud.** `verify_nepa_mcp_version()` refuses any
   release other than 0.1.1; the normalizers are shape-coupled and an
   upgrade must re-run the capability census first.
4. **One process at a time.** The throttle is per-process; two concurrent
   builders halve the effective per-host floor. Sequence them.
5. **Callers own cache naming** (`cache_path_fn`) because Janus shipped a
   legacy quirk (`--padus-0p1mi`) that must keep resolving.

## 3. Roadmap

| Phase | Deliverable | Notes |
|---|---|---|
| **R1** | `build_nepa_screens.py --catalog <file> --id-field --name-field --lat-field --lon-field` generic CLI | Screens ANY catalog JSON without a new script. The three existing builders stay (they own curation the generic CLI can't), but one-off questions ("screen the nuclear-civilian 29") stop needing code. |
| **R2** | Screen the remaining curated catalogs: `nuclear-civilian-sites.json` (29 promising-tier), `federal-clean-energy.json` (10), `reference-campuses.json` (10) | Each is a drawer/popup "Permitting screen" section reusing the coal chip renderer. Budget: ~50 sites × 7 sources ≈ 40 min once, cached forever. |
| **R3** | **Top-of-ranking screening ritual**: after each scoring change, screen the top 10 of each lens and log deltas to `issues.md` | The S1 scenario from the integration spec, made a habit. Never a corpus field — 46,749 sites would silently lack it. |
| **R4** | Screening-vs-corpus cross-checks in `validate_against_sources.py` | `fema_nfhl.get_flood_zones` vs stored `flood_zone`/`in_sfha` on a sample (S4 scenario); WARN vs FAIL per the `UPSTREAM_QUALITY_CHECKS` split; must model `Corpus.merged` fill-if-empty semantics. |
| **R5** | Credential unlocks: `CENSUS_API_KEY` → Spec 02 validation path; `EPA_AQS_*` → Spec 12 nonattainment gate | Both free. Keys live in env only (never committed); absence stays visible as unavailable. |

## 4. Verification

- `tests/test_nepa_screening.py` — 11 unit tests: normalizers against
  live-captured shapes, cache round-trips, per-site failure isolation,
  missing-server isolation, map-package summarizing.
- Each consumer keeps its own contract tests (`test_janus_nepa.py`,
  `test_hanford_e2e.py`) so a module refactor cannot silently change an
  artifact's shape.
- Engine changes require re-running one warm-cache builder end-to-end
  (cheap) before merge.
