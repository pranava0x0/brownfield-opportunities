# DOE Sites dossier curation — provenance log (2026-08-24)

Five independent primary-source research passes (numbered-claims format
with verbatim quotes; the 2026-08-23 retro's echo-back-every-row
discipline) fed the SRS / Portsmouth / Paducah / WIPP dossiers
(`scripts/build_doe_sites_e2e.py`) and Hanford's infrastructure rows
(`scripts/build_hanford_e2e.py::INFRASTRUCTURE`). This file records the
load-bearing findings and — most importantly for the quarterly re-audit —
what could NOT be verified. Full citations live on the data rows
themselves (`source_url` + `verified_at` per row, enforced by
`validate_data.py` and pr_gate citation liveness).

## Cross-cutting findings

- **Shipped-citation bug found**: `federal-clean-energy.json`'s Portsmouth
  row cited the Jul-2025 four-site DOE AI-DC announcement
  (`doe-announces-site-selection-…`) — fetched directly, it names
  INL/Oak Ridge/Paducah/SRS and **never mentions Portsmouth**. Fixed to
  the DOE-EM partnership article; NEPA link = CX listing
  (energy.gov/node/4855269). Its uncited "345 kV switchyards" claim was
  also corrected to the PORTS Virtual Museum's 330 kV figure.
- **Water is a ranked constraint, not a footnote**: WIPP's entire site
  allocation is **6.6 million gallons/YEAR** (Carlsbad Double Eagle line,
  2009 transfer agreement) vs ~20+ MGD for one large LWR — hence
  lwr_pwr=precluded(water) on the WIPP balance while microreactor=strong.
- **Hanford has NO natural-gas service**: the 2012 Cascade lateral
  (~29 mi, ~$35M, EIS-0467) was postponed then canceled; WTP moved to
  electric steam. The nat-gas category row states this rather than
  omitting the category.

## Per-site anchors (status as of 2026-08-24)

| Site | Committed / anchored | Stage caveat |
|---|---|---|
| SRS | Amentum selected **2026-07-20** to negotiate 1 GWe DC + ~2 GWe gen (gas → advanced nuclear) on 10 tracts / 3,103 ac; coalition DC BLOX, Milliken, Google, Nucor | Selection is explicitly NOT a final award → data_center=strong, not anchored. NNSA became site landlord 2024-10-01 (EM now tenant) |
| Portsmouth | SB Energy PORTS Technology Campus: executed 189-ac Batch-1 lease (CX-270875, 2025-11-17), groundbreaking **2026-03-20**, OpenAI ~8 GW 20-yr lease, NVIDIA $1.5B; Centrus SNM-2011 + $900M DOE contract (2026-07-01); Oklo 2×15-MWe Aurora land rights (Feb 2024) on SODI land | Gas plant (~9.2 GW) sits largely on ADJACENT PRIVATE land per FAST-41; OPSB certificate + CWA §401 pending (review deadline reported late Dec 2026) |
| Paducah | Brookfield 1.8 GW AI/HPC + NextEra ~2 GW gas + ≤2.6 GW BESS announced **2026-07-29** (~$100B, ~600 ac reported leased); General Matter 100-ac enrichment lease (Aug 2025) + ~$900M HALEU contract (Jan 2026) | KY PSC power-service approval pending; completion reported 2031 (LandGate) vs 2032 (E&E/NextEra) — unresolved, both presented |
| WIPP | NextEra selected **2024-09-17** for ≥150 MW solar + 100 MW storage on ≤1,800 ac of the ~9,000-ac C2CE offering | Realty-negotiation stage — no signed lease or construction found; ~7,200 ac uncommitted. DOE's Feb-2024 RFI names solar/wind/AND NUCLEAR eligible |

## Unverified / unresolved (re-check at the next audit)

**SRS**: AI-lease tract boundaries and L-Area coordinates unpublished (site
point used, labeled low-precision); F/H-Area geocode is interpolated; a
"GE Vernova / BWRX-300" association surfaced only in search synthesis —
**do not publish a reactor-technology claim for SRS**; SC PSC jurisdiction
over behind-the-fence federal generation unconfirmed; Holtec SMR-160
agreement's current status unknown (treated as history); D-Area powerhouse
demolition status may have advanced past "~60%"; fiber: no public source
found (category omitted).

**Portsmouth**: total acreage is 3,777 (EIC) vs 3,714 (older) vs "more
than 3,700" (DOE) — presented as ~3,700-3,777; current rail carrier and
in-service status unconfirmed (22 mi built in the 1950s); no named gas
supplier/lateral for the 9.2 GW plant; OPSB docket number not located
(public meeting was set for 2026-08-27); campus job figures diverge 3.5×
by scope (10k/2k DOE vs 35k/2.5k FAST-41-scope) — both presented,
unreconciled; PPPO OSMS contract award could not be confirmed; parcel
coordinates approximate; Centrus/switchyard standalone acreage unpublished
(approx_acres=null renders "size not published").

**Paducah**: EPA ID KY8890008982 confirmed via aggregator + our own corpus
(present in sites.json), not a direct EPA page fetch; on-site rail mileage
unpublished; DUF6 remaining-inventory and mission-end date unconfirmed;
Shawnee-to-PGDP distance not precisely sourced; gas/water/fiber/substation
distance figures (4.3 mi line, 14-mi Texas Gas receipt point >100k dth/d,
0.33-mi 161-kV line, 621-MW substation, Quad State IX 0.1 mi) are
**LandGate-aggregator-only** — hedged in-text as indicative; KY siting
board jurisdiction over federal-land merchant generation unconfirmed;
WKWMA acreage accounting (4,495 current vs "2,781 conveyed") not
reconciled; no campus-level NEPA determination located.

**WIPP**: current fill % (42% is an Apr-2023 DOE filing — treat as lower
bound; a "40% / May-2026" reference could not be fetched); workforce
(~1,100 is Jun-2017 — plausibly higher now); Carlsbad distance is 26 mi
(wipp.energy.gov, EMNRD) vs 33 mi (DOE-EM page) — both cited; NM PRC
non-applicability to a merchant CFE lease is legal INFERENCE; no
WIPP-solar NEPA document located; LWA statute PDF could not be fetched
directly (BLM-administers vs DOE-jurisdiction reconciliation is a
reasonable reading, flagged); URENCO-to-WIPP mileage unverified; fiber:
no source (category omitted). Context: Holtec canceled the HI-STORE CISF
in **Oct 2025** despite the favorable Jun-2025 SCOTUS standing ruling —
NM's posture toward waste-adjacent siting is live context.

**Hanford infra pack**: Atlas Agro's MW figure spans sources (">300 MW" /
"~320 MW" Port director / "up to 350 MW") — dossier says "more than
300 MW"; the land-deadline extension is 2027-07-31 per two sources (one
outlet says July 2026 — weighted to 2027); a "~12-mi line off Ashe" figure
was search-synthesis-only and was NOT published; the "1,300 MW intertie"
phrase in one syndicated piece is inconsistent with every other figure —
not used; White Bluffs substation kV class unsourced; no
Hanford-corridor-specific NoaNet route figure exists.

## Agent-run economics (for the retro)

Five Sonnet agents, ~1.19M tokens total (SRS 249k, Portsmouth 234k,
Paducah 235k, WIPP 243k, Hanford-infra 237k incl. one resume + one
follow-up for exact URLs). All five were killed once by a session-limit
reset and resumed via SendMessage with context intact (the documented
survival playbook). The numbered-claims + PRE-VERIFIED-skip-list format
worked: zero redundant re-verification of the federal-clean-energy rows,
and every pack shipped a usable UNVERIFIED list — the Portsmouth pack's
citation-bug catch alone justified the run.
