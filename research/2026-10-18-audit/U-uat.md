# UAT findings (2026-10-18, local build of origin/main d4daea1)

## Per-tab measurements (desktop 1440x900)
| Tab | Words | Screens of scroll | Controls | First content |
|---|---|---|---|---|
| Explore (default) | 2,131 | 6.3 | 58 | lens buttons + 46,759 sites alphabetical; first row "'M' Mountain Slave Sta" (FUDS), most cells "Unknown / Not assessed" |
| Map | 1,009 | 1.5 | 4 | map with overlays |
| Table | 5,391 | 16.7 | 0 | sorted by acreage desc; first rows are 8M-acre FUDS maneuver areas |
| Retired Sites | 332 | 2.1 | 5 | grouped by prior use |
| Coal Reinvestment | 690 | 3.0 | 43 | KPI cards; table sorted by MW |
| Nuclear Siting | 1,337 | 4.4 | 297 | 14 installations alphabetical, water Unknown for all |
| Microreactors | 6,322 | 21.1 | 176 | fleet table, commitments, then alphabetical screen |
| DOE Sites | 1,391 | 3.7 | 163 | 5 site pills, fit matrix (the one tab that gives answers) |
| Maritime Siting | 6,475 | 16.2 | 152 | 150 rows alphabetical of 22,938 |
| Nickel Refining | 6,632 | 16.4 | 160 | 150 rows alphabetical |
| Data & methods | 694 | 2.4 | 14 | coverage table; no per-tab method summary |

Site detail panel (Hanford 100-Area): 621 words, 4.4 screens. Order: identifiers (EPA ID, region, address) -> 9 evidence cards (5 of them "Unknown / Not assessed", ~100 px each) -> owner -> 8 documents -> "Infrastructure proximity" (repeats the grid/rail/road numbers already shown above) -> ECHO. The research dossier sits further down.

Mobile (375x812): no horizontal page scroll (good). First result row top: Explore 441 px, Coal 912 px (below the fold), Nuclear 590, Micro 660, DOE 1,246 (below the fold). Tab strip scrolls horizontally with 11 tabs; most are off-screen.

Performance (local, uncompressed): 25 requests, 68.9 MB decoded JSON parsed before "ready" (3.3 s on localhost). Gzip transfer ~6.5 MB. Largest: infra-proximity.json 28 MB raw / 2.7 MB gz, water-proximity.json 11.8 MB / 0.8 MB, epa-acres.json 10.9 MB / 1.5 MB, opportunity-zone 4 MB, iso-rto 2.8 MB. Explore's first screen needs only name/state/program plus 5 short findings per site.

## Task flows (interactions = clicks + typed queries + scroll screens)
| Task | Path today | Interactions | Answered? |
|---|---|---|---|
| Shortlist sites for a data center | Explore -> lens Data Center (no effect) -> filters (one category at a time) | 4+ and still 18,946 rows alphabetical | No |
| Shortlist for power generation / factory | same; lens buttons do nothing | same | No |
| Which military base first for an AP1000? | Nuclear tab -> class button (no table change) | 2 + 4 screens | No (alphabetical, water unknown everywhere) |
| Best coal plant to repurpose | Coal tab -> scroll to table (mobile: below fold) | 1 + 1-2 screens | Partly (sorted by MW, not readiness) |
| Best DOE parcel for SMR | DOE tab -> site pill -> matrix | 2 | Yes |
| Facts on one site | search, type, pick | 3 + 1-4 screens | Yes, but key facts are mixed with 5 empty cards |
| How are sites ranked / what method? | Data & methods tab | 1 + 2 screens | No per-use method stated anywhere |
| How fresh is the data? | header "Compiled 2026-09-25" | 0 | Partly: research data from 2026-10-18 not reflected |

## Copy
Every view opens with 1-3 sentences of caveats ("does not establish", "remain unverified", "confidence describes evidence, not suitability"). The same disclaimer appears on at least 8 surfaces. Users see disclaimers before any answer.
