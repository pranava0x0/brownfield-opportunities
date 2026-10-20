# Site review, 2026-10-18

What the site does, what was wrong, what changed. Raw agent reports are in this folder
(A-D data-source audits, F-I adversarial method reviews, S Sonnet synthesis, E history
mining, U UAT measurements).

## What the site is for

An atlas of ~46,800 federally tracked contaminated or former-military sites (EPA
Superfund, EPA ACRES brownfields, USACE FUDS, DOD BRAC), joined to grid, road, rail,
water, flood and land data, to find sites worth investigating for data centers, power
generation, nuclear reactors and heavy industry. Curated tabs cover coal plants, DOE
cleanup sites, retired heavy industry and the nuclear pipeline.

## What was wrong (before)

- **No answers.** Since 2026-09-12 the default tab listed 46,759 sites alphabetically
  with "Unknown / Not assessed" in most cells. The Data Center / Generation /
  Manufacturing buttons changed nothing (`assessSite` ignored them). Nuclear,
  Microreactor, Maritime and Nickel lists were alphabetical too.
- **No stated method.** No tab said how sites were judged; caveats repeated on 8 surfaces.
- **11 tabs, several duplicates.** Maritime and Nickel were the same evidence table as
  Explore over a different subset; Microreactors mixed a catalog with another such list.
- **Heavy load.** 69 MB of JSON parsed before the first answer.
- **Data defects.** County/zone lookups ignored multipart polygons (FEMA risk missing for
  10,131 sites, every Delaware Superfund site); 297 "acreages" were counties, regions,
  rivers or plumes; 8 curated nuclear/coal rows and 2 DOE ratings were stale or wrong;
  the coal tab covered 18 hand-picked of 244 EIA coal retirements and showed a dollar
  "stranded value" with no government basis.

## Interactions to key information

| Task | Before | After |
|---|---|---|
| Shortlist for a data center | 4+ clicks, still 18,946 alphabetical rows | 0: default tab, ranked, method on top |
| Shortlist for solar / port industry / nickel | not possible | 1 click |
| Which military base for an AP1000 / SMR / microreactor | 2 clicks + 4 screens, no order | 1-2 clicks, ranked |
| Best coal plant to reuse | 1 click, 18 plants by size | 1 click, 244 plants ranked |
| How a site was judged | not stated anywhere | method card above every list; full table in Data & methods |
| Facts on one site | 3 + 1-4 screens; checks absent | 3; checks first, unknowns in one line |
| DOE parcel answer on a phone | first row at 1,246 px | 864 px |

Startup JSON 68.9 MB → 34.7 MB decoded; no horizontal scroll on any tab at 375 px.

## Methods now

Every ranking is a few pass/fail checks in `docs/screens.js`, each with a cited
threshold tagged agency (EPA RE-Powering, FEMA, NRC, Army, EIA) or ours. Rank = checks
met, then fewest unknowns, then one named tie-breaker. Missing data never passes.
`node scripts/screen.js explain <site-id>` prints the same result from the shell.
Line and river checks use the distance to the nearest line or gage that meets the threshold, not the
value of the nearest one (fixed 2026-10-19 after code review; counts below are after the fix).

| Screen | Checks | Sites meeting all (2026-10-19) |
|---|---|---|
| Data center | line ≥115 kV ≤5 mi, ≥100 ac, outside SFHA, road ≤10 mi | 1,194 |
| Solar farm (EPA RE-Powering) | ≥35 ac, ≥69 kV line ≤10 mi, road ≤10 mi, outside SFHA | 1,771 |
| Port industry | principal port ≤10 mi, ≥100 ac, ≥115 kV ≤5 mi, outside SFHA | 150 |
| Nickel refinery | ≥300 ac, rail ≤1 mi, ≥115 kV ≤5 mi, river ≥100 cfs ≤10 mi, port or feedstock | 43 |
| Large reactor (14 bases) | no 25k city ≤10 mi (10 CFR 100.3), PGA ≤0.30 g (AP1000 DCD), supply river ≥100× withdrawal (Vogtle EIS), ≥230 kV ≤5 mi, ≥500 ac | 2 meet 4 of 5 |
| SMR | same, scaled to 300 MW | Fort Drum 5/5 |
| Microreactor | Army Janus selection (Aug 2026), line ≤5 mi | 5 |
| Civilian nuclear (68) | permit or license in force, existing reactor site, population center | Palisades, TMI |
| Coal plants (244, EIA-860M) | all coal retired, no other unit ≥50 MW running, ≥230 kV ≤2 mi | 115 |
| Retired industry (658, GHGRP) | EPA-accepted reason, plant not mine, cleanup record ≤1 mi | 185 |

## Data sources (verdicts from the audits)

Valid or valid with caveats: EPA NPL (exact match to live, 1,908), USACE FUDS (exact id
match; 1,301 coordinate-less properties dropped), BRAC, EPA RE-Powering, EIA-860M
(newest month pinned), HIFLD transmission/gas/plants, TIGER roads/rail, USGS gages, HUD
Opportunity Zones, DOE/NETL energy communities, BTS ports, GHGRP.
Stale: EPA ACRES (frozen Aug-2021 layer), ISO/RTO (source now token-walled).
Invalid as used: ECHO site matching (shared registry ids, mismatched facility names),
ACRES "cleanup status" (it is grant status), climate zone (third-party host),
census-workforce (no output without a key). Follow-ups are in backlog.md §2 #15-23.

## Scripts added (deterministic replacements for repeated agent work)

`screen.js`, `check_acreage_artifacts.py`, `build_coal_plants.py`,
`build_population_centers.py`, `build_infra_core.py`, `research_queue.py`,
`routine_ctl.py`, `project_status.py`, `env.sh`, `check_upstream_freshness.py --markdown`,
and `routine/daily-site-research.md` (the routine prompt rewritten around them).
History mining found ~half of all commits came from the daily routine, with 109 inline
backlog edits, 68 clock checks and 33 comment fetches across 22 runs; those are now
script calls.
