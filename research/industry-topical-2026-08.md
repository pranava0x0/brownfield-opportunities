# What the industry is talking about — August 2026 sweep

**Date:** 2026-08-23 · **Method:** Pranava's x.com bookmarks (read via Chrome, Aug 14–23 window),
targeted web verification against UtilityDive, E&E-adjacent trade press, FERC/DOE/ERCOT/TVA primary
sources, and the current episode lists of Volts, Open Circuit (Latitude Media), and the Energy Gang.
**Purpose:** ground the `docs/specs/` backlog (2026-08-23 roadmap) and the coal-repowering PR in what
buyers, regulators, and the energy-twitter discourse actually care about *right now* — and correct
the spec/PR claims that the sweep proved wrong.

Every claim below carries its source. Items marked **⚠ corrects PR/spec** contradict something
currently in the repo and were fixed in the same branch as this document.

---

## T1 — Speed-to-power has shifted from queue reform to bring-your-own-power

The dominant siting question is no longer "where is the queue shortest" but "can the site
self-supply while it waits."

- **~56 GW of on-site (behind-the-meter) generation was planned by US data-center developers as of
  early 2026 — 30% of all planned DC builds.** Texas leads (20.6 GW), then New Mexico (9.2),
  Pennsylvania (7.5), Utah (6.0). Gas dominates; solar+BESS co-location is the fast follower.
  Source: [pv-magazine 2026-08-06](https://www.pv-magazine.com/2026/08/06/) via Christian Breyer;
  bookmarked with Xiao Wang's caveat that the "56 GW solar+storage" framing is mostly BTM gas.
- **xAI ("SpaceXAI") Memphis/Southaven** runs the marquee BTM story: "world's largest grid-connected
  battery pack" claim (Aug 21 post) *plus* TVA approving +100 MW of grid supply — explicitly traded
  against 100 MW of on-site gas generators (Fred Stafford, Aug 21).
- **Wood Mackenzie (Energy Gang) pegs the US data-center demand pipeline at 183–220 GW**, framing
  reliability, affordability, permitting, and supply chains as the four constraint axes.
  [Energy Gang](https://www.woodmac.com/podcasts/energy-gang/)
- **Flexibility is the cheap unlock the models ignore**: Volts' "For data centers, a little
  flexibility goes a long way" and the Mar-2026 episode with Camus/Astrid Atkinson + Jesse Jenkins
  ("power parks": flexible interconnection, battery-backed). Matches the LBNL "76 GW could connect
  today at 0.25% curtailment" finding already in `backlog.md`.
  [volts.wtf](https://www.volts.wtf/p/for-data-centers-a-little-flexibility)

**Implication for us:** the Generation lens and the coal engine are pointed the right way, but the
dashboard says nothing about *self-supply feasibility* (gas proximity is scored for delivery, not
for BTM plant siting) or *flexibility*. At minimum the Rankings explainer should say firm-load is
assumed. Spec 04/09 updated accordingly.

## T2 — The federal framework: FERC's large-load docket is the clock everyone watches

Timeline now anchoring every queue conversation (and the user's own FERC Show Cause microsite):

1. **Oct 2025** — Energy Secretary invokes DOE Organization Act §403 to force a FERC rulemaking on
   large-load (>20 MW) interconnection.
2. **Dec 2025** — FERC orders PJM to write explicit co-location rules for large loads at generators
   (the Talen/Susquehanna aftermath; a win for nuclear/gas owners).
   [Baker Botts summary](https://www.bakerbotts.com/thought-leadership/publications/2025/december/ferc-issues-order-providing-guidance-for-co-locating-power-plants-with-data-centers-within-pjm)
3. **Jun 2026** — FERC issues **§206 show-cause orders to all six RTOs/ISOs** to justify or reform
   large-load integration rules; five named issues incl. study process for "electrically proximate"
   and co-located loads, cost-shift prevention, alternative transmission tech.
   [McGuireWoods](https://www.mcguirewoods.com/client-resources/alerts/2026/6/ferc-issues-section-206-show-cause-orders-directing-all-six-rtos-isos-to-justify-or-reform-large-load-integration-rules/) ·
   [FERC](https://www.ferc.gov/news-events/news/ferc-act-large-load-interconnection-docket-june-2026)
4. **By Jun 2026 (rolling)** — FERC commits to act on the large-load docket; RTO compliance filings
   land through H2 2026.

**Queue-skip mechanics, correctly named** (⚠ corrects PR/spec — the PR's "PJM Section 49 / MISO
Attachment X / ERCOT Batch Zero" framing conflated three different things):

- **PJM**: *Surplus Interconnection Service* (FERC Order 845) and the *generator Replacement
  process* reuse an existing POI; the *Reliability Resource Initiative* (Dec 2024) and the
  *Expedited Interconnection Track* (EIT — **FERC-approved 2026-06-09, accepting requests**; ≥500 MW
  capacity resources, state-sponsored, ≤10/yr, sunsets end-2027) expedite new generation serving
  large loads.
  [RenewableEnergyWorld](https://www.renewableenergyworld.com/power-grid/pjm-proposes-an-expedited-interconnection-track-for-generators-to-supply-large-load-additions/) ·
  [UtilityDive (FERC approval)](https://www.utilitydive.com/news/ferc-pjm-fast-track-expedited-interconnection-eit/822479/)
- **MISO**: Generator Replacement + surplus study process share an existing POI; *ERAS* (Expedited
  Resource Addition Study, 2025) fast-tracks resource-adequacy projects.
  [K&L Gates](https://www.klgates.com/Regional-Grid-Operators-Attempt-to-Tackle-Resource-Adequacy-by-Fast-Tracking-Generator-Interconnection-6-6-2025)
- **ERCOT**: "**Batch Zero**" is REAL but it is a **large-load interconnection study batch** (first
  batch of the PUCT-approved Batch Study framework; technical submissions due 2026-07-10,
  classifications due 2026-08-07 — **but ERCOT paused Batch Zero** under the Governor's large-load
  verification directive, so no classifications issued as of late Aug 2026), with PCLR (Provisional
  Controllable Load Resource) and WLPUN (Withdrawal-Limited Private Use Network) designations —
  **not** a generator queue-transfer rule. TX **SB6 (2025)** is the co-location/interconnection
  statute. [Baker Botts](https://www.bakerbotts.com/thought-leadership/publications/2026/august/texas-large-load-interconnection-update---ercot-batch-zero-pause-and-verification-process)
  [ERCOT](https://www.ercot.com/files/docs/2026/06/18/ERCOT-Trending-Topic-New-Batch-Connection-Process-for-Large-Electricity-Users.pdf) ·
  [EPE](https://epeconsulting.com/epe-intelligence/news/ercot-introduces-a-new-batch-study-framework-for-large-load-interconnections)

## T3 — Ratepayer politics: DC-specific tariffs are now the mainstream instrument

- **TVA approved a dedicated data-center rate class on 2026-08-20** (board meeting in Memphis):
  ~+10% average for DC customers phased over 3 years from Oct 1 2026, an upfront
  capacity-commitment charge, and an extra charge for loads >5 MW. Households explicitly shielded.
  Same meeting: xAI/SpaceXAI approved as a **directly-served TVA customer** (leaving MLGW).
  [Action News 5](https://www.actionnews5.com/2026/08/20/tva-approves-10-rate-spike-data-centers-protect-household-rate-payers/) ·
  [Chattanooga TFP](https://www.timesfreepress.com/news/2026/aug/20/tva-to-charge-data-centers-more-for-power-under/)
- **The state bill mix flipped**: tax-incentive bills fell from 58% of all state DC bills (2024) to
  **14.9% (2026)** while electricity-rate/ratepayer-protection bills climbed 5% → **11.7%**.
  [MultiState](https://www.multistate.us/insider/2026/2/20/state-data-center-legislation-in-2026-tackles-energy-and-tax-issues) ·
  [ArentFox Schiff](https://www.afslaw.com/perspectives/alerts/state-regulation-data-centers-2026-shifting-landscape)
- **NY passed the first statewide measure** — the *Responsible Data Center Development Act*,
  legislature 2026-06-04 (on top of EO 62's DEC-permit pause already in `STATE_DC_REGULATION`).
- **Indiana**: HB 1210 enacted (1% revenue-sharing folded in from HB 1333); Indianapolis
  City-County Council passed a non-binding pause resolution to May 2027. Latitude Media covers the
  $5B DC backlash + bill spikes there.
- **Jigar Shah's framing** (bookmarked, Aug 22): "the mechanics of doubling the electricity rates is
  not hard. But it doesn't actually change the way the system operates" — i.e., tariffs are
  politically necessary but not sufficient; Open Circuit's recent arc ("The new reality for data
  centers: no easy answers", "A reckoning for the electro-bros") is all affordability.
- Joe Weisenthal's "RAIny Day Fund" (Aug 21) — a 401(k)-like savings vehicle to fund AI/grid
  buildout — shows the financing/affordability debate has reached macro-commentary.

**Implication:** `STATE_DC_REGULATION` correctly excludes cost-causation tariffs from the penalty,
but the *quarterly re-audit* now needs a tariff-tracking sibling: TVA joins TX SB6 / OR POWER Act /
OK HB2992 / OH AEP in the excluded-by-design list, and NY's RDCDA must be reflected in the next
audit. Spec 09 updated.

## T4 — The land-use backlash gives brownfields a marketing tailwind

- Rep. Tom Tiffany (WI, Aug 20, bookmarked): a data-center plan "would destroy AT LEAST 100,000
  acres of Wisconsin land… you get a data center AND thousands of acres of solar panels in your
  backyard" — farmland preservation is now an anti-DC (and anti-renewables) rallying point.
- Volts' "Making sense of the data center backlash" (Jul 2026, w/ Energy Empire) tallies
  moratorium activity across **38 states**; "Doing data centers the not-dumb way" and the Aug-5
  episode (state legislatures writing DC rules faster than they can verify demand forecasts) carry
  the same theme. [volts.wtf](https://www.volts.wtf/p/making-sense-of-the-data-center-backlash)
- Framing beats siting: Matt Slotnick's viral "call them computer farms" (Aug 21) is a joke with a
  real point — land-use identity determines local politics.

**Implication:** "already-disturbed land, no farmland taken" is this dashboard's single strongest
positioning line and it appears nowhere in the UI copy. Hero/About copy + Spec 01 (dossier's
community context inventory) updated to say it.

## T5 — Coal fleet: retirements are *slipping*, and conversions are the marquee deals

Two opposing currents, both load-bearing for the coal engine:

**(a) Retirement dates are now policy-contingent.** DOE has issued **43+ §202(c) emergency orders
since May 2025** (J.H. Campbell renewed through Aug 2026; Eddystone 3&4; Centralia; Schahfer…),
states are suing, and ordered plants run at low capacity factors.
[POWER log](https://www.powermag.com/doe-has-issued-more-than-40-section-202c-emergency-orders-since-may-2025-heres-an-updated-log/) ·
[UtilityDive](https://www.utilitydive.com/news/doe-coal-fired-emergency-campbell-lawsuit/820459/)
⚠ corrects PR/spec: any `planned_retirement_year` in our coal catalog is a *claim with a date and a
source*, not a fact — rows now carry `verified_at` + `source_url`, and the engine copy warns dates
can slip **in both directions** (early retirement < 202(c) extension < DC-driven life extension).

**(b) The conversions that actually closed, for the catalog:**
- **Homer City (PA)**: 4.5 GW gas / $10B "Homer City Energy Campus", 7 GE Vernova 7HA.02 turbines,
  first deliveries 2026, ops target 2027, **3,200+ acre** campus, EQT gas-supply agreement-in-
  principle (Jul 2025). ⚠ corrects spec: this is Homer City Redevelopment + Kiewit — **not Amazon**.
  [UtilityDive](https://www.utilitydive.com/news/homer-city-gas-fired-power-station-data-center-firstenergy/744332/) ·
  [Homer City Redevelopment](https://www.homercityredevelopment.com/project-overview)
- **Colstrip (MT)**: ⚠ corrects PR — NOT retiring 2030. NorthWestern Energy became **55% majority
  owner of Units 3&4 on 2026-01-01** (Avista + Puget exits at $0); development agreements with
  Sabey, Atlas Power, and Quantica for **150 MW of DC load in late 2027 growing to ~1,500 MW by
  2030**. Colstrip is the *life-extension-for-data-centers* pattern.
  [NorthWestern 8-K](https://www.sec.gov/Archives/edgar/data/0001993004/000199300426000031/ex991pressreleaseq12026.htm) ·
  [Daily Montanan](https://dailymontanan.com/2023/01/17/northwestern-energy-acquires-avista-energy-share-of-colstrip-effective-2026/)
- **Montour (PA)**: ⚠ corrects PR — gas conversion **completed Aug 2023** (dual-fuel), coal
  retirement required by end-2025. It is an operating gas plant, not a retired hulk.
  [GEM wiki](https://www.gem.wiki/Montour_Steam_Station)
- **Kemmerer/Naughton (WY)**: ⚠ corrects PR — the town is **Kemmerer** (not "Kemper"). TerraPower's
  Natrium **Kemmerer Unit 1 received its NRC construction permit 2026-03-04** (first commercial
  non-LWR approval in 40+ years; safety review finished ahead of schedule and 11% under budget) and
  **construction began 2026-04-23**, completion target 2030 — the only operating coal-to-nuclear
  conversion project in the world.
  [POWER](https://www.powermag.com/terrapowers-kemmerer-1-enters-construction-timeline-of-the-natrium-projects-road-to-first-power/) ·
  [NPR](https://www.npr.org/2026/05/02/nx-s1-5798892/wyoming-celebrates-nuclear-renaissance-as-feds-approve-license-for-a-new-reactor)
- **Clinch River (TN)**: TVA's BWRX-300 construction permit — NRC staff recommendation Jun 2026,
  mandatory hearing 2026-08-13; first US BWRX-300 CPA.
  [ANS](https://www.ans.org/news/2026-07-01/article-8174/clinch-river-construction-permit-recommendation-follows-safety-evaluation/)
- Marquee rows the catalog should eventually gain (from EIA-860M derivation, not hand-typing):
  Brandon Shores (MD, retired 2025), Coal Creek (ND, hosting Applied Digital), Intermountain (UT,
  hydrogen-capable CCGT repower + HVDC to LA), San Juan (NM, retired 2022), Sherco (MN, solar
  repowering + nearby hyperscale load).

## T6 — Federal land is the fastest-moving siting theater

- **DOE AI-data-center sites** (per the Jul 2025 selection + 2026 awards): the four flagship sites
  are **INL, Oak Ridge (ETTP), Paducah, and Savannah River**; Portsmouth got a parallel announcement
  in Mar 2026. **Paducah selected Brookfield Asset Management (Jul 2026)** with **NextEra building
  2 GW of new gas + transmission upgrades + up to 2.6 GW of BESS for a 1.8-GW AI/HPC campus**;
  **SRS selected Amentum** to negotiate the lease for an AI DC + on-site power.
  [DOE](https://www.energy.gov/articles/doe-announces-site-selection-ai-data-center-and-energy-infrastructure-development-federal) ·
  [ANS Jul 2026](https://www.ans.org/news/2026-07-31/article-8261/privatesector-data-center-plans-advance-for-paducah-and-savannah-river-sites/)
  ⚠ corrects PR: federal-clean-energy.json's Paducah/SRS/Portsmouth stages + partners updated.
- **NEPA speed is now a competitive variable**: Heatmap scoop (Jae Holzman, Aug 21, bookmarked) —
  the administration claims it will finish the **entire federal environmental review for the
  biggest US gas project — the OpenAI–Nvidia data center in Ohio — in seven months**. Whatever the
  merits, precedent pace matters to Spec 01's NEPA-precedent engine.
- **CEML (mine lands)**: **Lewis Ridge is Rye Development's pumped-storage** project — **266 MW per
  the FERC Final License Application** (filed 2025; earlier draft filings said 287 MW), EIS NOI in
  the Federal Register 2026-05-12 — ⚠ corrects PR, which had it as "287 MW solar / EDF Renewables".
  **Mineral Basin** is Swift Current's 402 MW solar on ~2,700 ac of Clearfield County PA mine land —
  confirmed, not cancelled. Also from the domain-review pass: **Portsmouth broke ground 2026-03-20**
  on the SoftBank/SB Energy PORTS Technology Campus (10 GW DC + ~9.2 GW gas, $33.3B), **Hanford
  selected Hecate Energy** (up to 1 GW solar+storage, realty negotiations), and **TVA's board voted
  2026-02-11 to keep Cumberland and Kingston running past their scheduled retirements** — the
  clearest single datapoint that announced coal retirement dates are policy-contingent.
  [Federal Register NOI](https://www.federalregister.gov/documents/2026/05/12/2026-09425/lewis-ridge-pumped-storage-llc-notice-of-intent-to-prepare-an-environmental-impact-statement-for-the) ·
  [RenewableEnergyWorld](https://www.renewableenergyworld.com/energy-business/policy-and-regulation/475-million-award-for-energy-on-mine-lands-includes-lewis-ridge-coal-to-pumped-storage/)

## T7 — Microreactors & tooling odds-and-ends from the bookmark pile

- **Aalo Atomics** (Matt Loszak) is actively posting nuclear-history threads — Aalo's Pod/XMR at
  INL is already in our fleet file; the vendor-content cadence supports the demand-ladder spec.
- **Kyle Walker's Texas parcel work** (Aug 21–22, bookmarked): mapped **14.3M Texas parcel records
  (13.5M unique shapes, owner info) from a 7 GB geodatabase to a public interactive map**, with a
  how-to at [walker-data.com/posts/millions-of-parcels](https://walker-data.com/posts/millions-of-parcels/).
  This implies a *bulk-download* path for TX cadastral data (TxGIO stratmap land-parcels GDB) that
  bypasses the token-walled ArcGIS Query endpoint that blocked our `parcel-owner` TX row —
  worth a probe next parcel round (bulk file → local `PolygonIndex`, same as county TopoJSON).
- a16z charts (bookmarked): agentic token usage passed human-initiated tokens (Feb 2026), frontier
  firms pulling away — the demand side of the DC boom keeps compounding.
- Satya Nadella (Aug 21): first production **NVIDIA Vera Rubin** racks landing at Microsoft DCs —
  the hardware cadence that drives ≥1 GW campus power asks.

---

## What this sweep changes, spec by spec

| Spec | Change driven by this sweep |
|---|---|
| 01 Reuse dossier | Add community/rates context inventory (moratorium + tariff exposure); NEPA-pace precedents (7-month full review) as a precedent attribute; "no farmland taken" positioning line. |
| 02 Workforce | Unchanged technically; affordability politics raise the value of jobs/economic-benefit fields (they are the pro-DC counterargument in every hearing). |
| 03 OR-SAGE | Population density parameter doubles as a backlash-risk proxy — worth a sentence; otherwise unchanged. |
| 04 Coal engine | Correct queue-mechanism names (T2); status model gains `converted_gas` + life-extension; per-row `verified_at`/`source_url` mandatory; retirement-slippage caveat (202(c)); Homer City/Colstrip/Montour/Kemmerer facts fixed; auto-derive fields from cached EIA-860M as the durable path. |
| 05 Water | xAI Memphis + TVA >5 MW charge show water & power politics converging on the same metros; keep 7Q10 plan, add municipal-supply-politics note. |
| 06 RE-Powering 190k | Add a verification step: confirm the dataset is still published under the current administration before building the connector. |
| 07 Microreactor match | Aalo INL cadence supports it; unchanged scope. |
| 08 Federal portfolio | Paducah = Brookfield/NextEra (2 GW gas + 2.6 GW BESS + 1.8 GW campus); SRS = Amentum; Portsmouth Mar-2026; Lewis Ridge = 266 MW pumped storage (Rye, per the FERC FLA); per-row `verified_at`; NNSS office label fixed. |
| 09 Queue + eCFR | Anchor to the FERC timeline (§403 Oct 2025 → PJM co-location Dec 2025 → §206 show-cause Jun 2026); replace the queue matrix with verified mechanisms per RTO; add DC-tariff tracking (TVA Aug 2026) to the quarterly re-audit scope. |

## Source index

X bookmarks (accessed via Chrome, 2026-08-23): @xiaowang1984 (×3), @SpaceXAIMemphis, @kyle_e_walker
(×2), @MattLoszak, @satyanadella, @JigarShahDC, @matt_slotnick, @jaeporeon (Heatmap), @TheStalwart,
@TomTiffanyWI, @fredstaffordcs, @bgurley/@patrick_oshag.

Web: links inline above — UtilityDive (Homer City, 202(c) ×3, FERC ×2), DOE/energy.gov (AI-DC site
selection, 202(c) log, CEML), ANS Nuclear Newswire (Paducah/SRS advance, Clinch River), POWER
(Kemmerer timeline, 202(c) log), ERCOT (Batch Zero notices), McGuireWoods/White & Case/Baker Botts
(FERC orders), MultiState + ArentFox Schiff (state legislation), TVA coverage (Action News 5,
Times Free Press, WPLN), NorthWestern Energy SEC filings (Colstrip), GEM wiki (Montour), Federal
Register (Lewis Ridge NOI), volts.wtf, latitudemedia.com (Open Circuit), woodmac.com (Energy Gang),
walker-data.com (TX parcels).
