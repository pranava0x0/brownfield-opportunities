# UAT record — Brownfield Opportunities

Created: 2026-09-12. Last run: 2026-09-12. Category UI, rebuilt artifacts and mobile national Map fit verified.

## Runtime

Static HTML/CSS/JavaScript in `docs/`; Leaflet canvas map; Python Playwright e2e suite. Tests start their own loopback server through `tests/e2e/conftest.py`. No dependency installation needed for this session. Use 375×812, 768×1024, 1280×900 and 1440×900 viewports.

## Critical flows

1. Open the default route. Explore should show named sites and separate evidence categories after required data settles. Explicit `#map` remains Map.
2. Read grid/fiber/water findings, then open a site. The drawer supplies sources, geometry basis and unresolved capacity/entitlement questions. No composite score or numbered suitability rank.
3. Search for a real site, select a state and clear the filters. Shared-corpus tabs honor the same state; zero matches stay empty, including Microreactors.
4. Switch through Nuclear Siting, Microreactors, Maritime and Nickel. Curated populations are labeled separately. New data appears on demand; failure states cannot say no match or absent infrastructure.
5. At mobile width, primary evidence is visible without whole-page horizontal scrolling. Open/close detail, filter UI and map legend. Keyboard focus remains visible; Escape closes the detail.
6. Open Map. Site markers eventually finish loading; a detail deep link targets the correct record. Map readiness is separate from list/core evidence readiness.
7. Export results. Exported evidence terminology and unknowns agree with the UI; no legacy numeric suitability columns or hidden numeric ordering.
8. Visit several tabs, return to Explore and filter again. Track retained DOM growth and long tasks; initial DOM limits alone are insufficient.
9. Search `107 Brattleboro Road`. Water must show the Lower Green River network reach and fiber must show MassBroadband 123 regional context. The drawer must keep intake, rights, parcel service, capacity and route diversity unresolved.
10. Open DOE Sites → Portsmouth → Site infrastructure. Power must name X-530, X-515 and Don Marquis as asset-scoped evidence and must not claim spare capacity or transferable rights.

## Measured baseline

See `research/ux-uat-2026-09-12.md` for full scope, method, observations and limitations. Baseline screenshots and machine-readable measurements are in `/tmp/brownfield-uat-2026-09-12/` (transient, excluded from production).

| Area | Last tested | Observation before revision |
|---|---|---|
| Map landing, all widths | 2026-09-12 | No whole-page overflow or page errors; mobile legend obscures much of map |
| Rankings, all widths | 2026-09-12 | Mobile score outside initial horizontal viewport |
| Nuclear Siting, all widths | 2026-09-12 | Long mobile introduction pushes first-site insight below fold |
| Microreactors, all widths | 2026-09-12 | Shared-corpus ranking mixes unsuitable inference with precise totals |
| Nickel, all widths | 2026-09-12 | Distinct port/rail eligibility; supply-chain dataset loads on tab |
| About, all widths | 2026-09-12 | Visited in multi-tab session; content retained after navigation |
| Default category Explore | 2026-09-12 | Four widths: five categories visible; no landing overflow; 1,519 initial DOM |
| New exports / drawer confidence | 2026-09-12 | Explicit unknowns, independent confidence, no numeric suitability columns |

## Timing and data caveats

- The legacy `__APP_READY__` could fire from program hydration before all enrichment completed. Await the revised core-ready contract, and each optional surface's own ready state.
- Local server is uncompressed; raw bytes are not production transfer bytes. Calculated gzip totals are estimates.
- LCP records fast header text, not ready site evidence. Record useful-row and interaction readiness separately.
- Chromium `performance.memory` is approximate and does not establish a memory leak.
- Do not use fixed sleep to declare data ready. Wait for data state or a visible evidence result; include an explicit failure assertion.
- Map markers are canvas-rendered. Use exposed Leaflet/site hooks for deterministic selection; do not count marker DOM icons as site population.
- Older project UAT skill references obsolete refresh IDs and historical known-state values. Current source and runtime take precedence.

## Latest verification

Final rebuilt-artifact run: 24 initial requests, 68.91 MB decoded resources, 1,519 initial DOM elements, no unhandled errors across seven views at all four widths. Calculated gzip remains about 6.40 MB; source metadata growth offsets much of the deferred-data transfer saving. Full results and caveats are in the research report.

Targeted final regression run: `python3 -m pytest tests/e2e/test_microreactor.py::test_alaska_commitments_are_remapped_into_the_inset tests/e2e/test_nickel_tab.py::test_the_nickel_tab_retries_a_failed_port_load tests/e2e/test_candidates_view.py::test_planned_retirement_join_covers_all_programs tests/e2e/test_evidence_exploration.py -q --browser chromium --maxfail=3` — **14 passed in 28.72 s**.

The inherited minimum Map zoom was corrected after visual UAT found the western states cropped on phones. Two regression cases passed in 9.47 s; four-width screenshot retests contain the entire atlas bounds without overflow or errors. Broader performance limits remain the large core payload and 13,815 retained DOM elements after seven views. This is lab UAT, not field Core Web Vitals certification or a human participant study.


Final implementation gate: **261 browser tests passed** (`python3 -m pytest tests/e2e -q -n 2`, 443.29 s); **828 unit tests passed**. No skipped tests. Follow-up regressions cover first-open parcel map targets, explicit loading/error/empty states, a lazy-program deep link, unique category CSV headers, and compilation dates that advance only when deferred artifacts load.
