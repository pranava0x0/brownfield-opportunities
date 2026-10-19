# Audit D: Nuclear and DOE-site curated data (as of 2026-10-18)

Read-only. No repo files edited. Method: row counts and `verified_at` ages from the JSON; sampled high-consequence claims checked against primary or trade-press sources via WebSearch/WebFetch and curl. Bot-blocked hosts (403) are inconclusive, not dead.

## Per-file findings

**ap1000-sites.json** (14 sites) + `docs/siting-context.js` REACTOR_CLASSES. Verdict: STALE.
- Ages: analysis_verified_at 2026-07-02 (108 d); water_evidence_reviewed_at 2026-09-12 (36 d). None over 200 d.
- Sampled 4: Fort Bragg USGS 02102500 is Cape Fear at Lillington (supported; my suspicion of a wrong gauge was refuted). AF solicitation total ~3,100 ac (supported; rows sum to 3,132). Arnold AFB listed as offered: contradicted (Arnold 2026-06-01 notice: no proposals). Award status for Davis-Monthan, Edwards, Robins, JBMDL: not found (outdated or unverified; selection was planned Jan 2026).
- All 14 `water_adequacy` = "unknown", `water_supply_assessment` = "unassessed", since commit c56eea2 (#36, 2026-09-12). The 40-pt water factor therefore scores null everywhere. CLAUDE.md still says 13/14 ratings were validated: doc-vs-data drift.
- REACTOR_CLASSES AP1000: 20.1 MGD = 31.1 cfs and 26.8 MGD = 41.5 cfs (unit conversions correct). Consumptive 20.1 MGD/unit is consistent with the ESP environmental report (27,924 gpm for two units). Withdrawal 26.8 MGD/unit: not found in the EIS-0476 PDF text, so unverified. Natural-draft towers: confirmed.
- Label error: "Vogtle 3&4 FEIS as-built record." The EIS (NUREG-1872, Aug 2008, adopted by DOE as EIS-0476) covers PROPOSED units. It is a design-basis projection, not as-built data.
- APR1400 (31.1 x 1400/1117 = 39.0 cfs) and AP300 (x 330/1117 = 9.2 cfs) are linear scalings. Only `water_basis` text says so; the numeric `consumptive_cfs`/`withdrawal_cfs` fields carry no estimate flag. "Comparable thermal efficiency" is unsourced. AP300 at 330 MWe vs ~300 nominal: unverified.
- Micro `water_basis` ("Army has not paired designs with installations") is OUTDATED: the 2026-08-26 award paired 5 vendors with 5 installations.
- Fix: mark Arnold as "no proposal received (2026-06-01)"; mark the four remaining AF sites as award unresolved; rewrite micro basis; relabel "as-built" to "2008 FEIS design-basis projection"; flag APR1400/AP300 numbers as derived estimates in-field; restore or re-document water ratings and fix CLAUDE.md.

**nuclear-civilian-sites.json** (68 sites). Verdict: STALE.
- Ages: no per-row verified_at (CLAUDE.md contract requires one). File generated_at 2026-09-25 (23 d).
- Sampled 6: Palisades fuel-loading pause (2026-08-30) supported, but the Oct-2026 NRC one-time amendment approval is missing. Crane EA/FONSI issued: supported, exact date unconfirmed. V.C. Summer: COLs terminated 2019 and Brookfield FID decision by 2028-03-31 supported; 40% complete unverified. Project Matador: COLA filed 2025-06-17 supported, but only 2 of 3 parts docketed (omitted). "Air-cooled" unverified. Kemmerer: CONTRADICTED (NRC issued the construction permit 2026-03-04; col_status is stale even at write time). Clinch River: OUTDATED (construction permit issued ~2026-09-29; row says ESP approved/CP recommended).
- Fix: Kemmerer col_status to "construction permit issued 2026-03-04"; Clinch River status to "construction permit issued 2026-09-29"; add per-row verified_at; caveat Matador partial docketing; source or drop "air-cooled".

**microreactor-fleet.json** (12 vendors, 32 commitments). Verdict: VALID-WITH-CAVEAT.
- Ages: no per-row verified_at; file generated_at 2026-09-25.
- Sampled 6: Janus vendor pairings match the 2026-08-26 announcement (Benning-Radiant, Bragg-Antares, Campbell-BWXT, Drum-Westinghouse, Hood-General Atomics). Cited army.mil and defensescoop return 403 (bot-block); trade press corroborates. Antares Mark-0 criticality June 2026: supported (day unverified). Valar Ward 250 06-18: month supported, day unverified. Romania NuScale FID 2026-02-12/13: supported, but funding is unresolved and first module is 2033 (caveat missing). Equinix: OVERSTATED ("purchase agreement", status "Signed"; the Equinix release says "preorder agreement for the purchase of 20"). Deployable Unity "2026-07-01": DISPUTED (DOE groups it in June).
- Fix: Equinix to "preorder agreement (2025-08-14), 20 Kaleidos units, deposits per Radiant"; Deployable date to "June/1 July 2026, disputed"; add Romania funding caveat; add per-row verified_at; vendor_id is null for BWXT and General Atomics.

**janus-nepa.json** (9 sites). Verdict: VALID-WITH-CAVEAT.
- Ages: no per-row verified_at; generated_at 2026-08-21 (58 d).
- Roster matches the 9 candidate installations in microreactor-fleet exactly (9/9). Screening outputs themselves were not claim-checked (0 curated claims sampled).
- Caveat: the run predates the 2026-08-26 selection, so it is not contradicted but is not refreshed for it. Re-run or annotate before citing.

**hanford-e2e.json** (9 parcels + 8 infra rows). Verdict: VALID-WITH-CAVEAT.
- Ages: oldest verified_at 2026-08-24 (55 d).
- Sampled 4: Cereza sale to Savion supported (closed 2026-02-18; DOE transfer 2026-02-19; 8,000 of 10,380 ac). Cascade "pre-application" supported (no filing found; sources point to 1H 2027). 1100-area Framatome 10% enrichment (July 2026) and TerraPower HALEU line (Nov 2025): unverified. 200-area WTP "mid-Oct 2025" vitrification: unverified. 100-area EPA page returns 200; content unchecked.
- Fix: attach per-claim sources to the 1100 and 200 dated claims.

**srs-e2e.json** (5 parcels). Verdict: VALID-WITH-CAVEAT (citation gap).
- Ages: 2026-08-24 (55 d).
- Sampled 2: Amentum selection 2026-07-20 supported (negotiation, not a lease; 1 GW DC + ~2 GW generation, gas bridging to nuclear). The cited NNSA page contains NO tract count, acreage (10 tracts / 3,103 ac), or coalition members (DC BLOX, Milliken, Google, Nucor). Those claims are unsupported by the cited URL. D-Area URL returns 200; content unchecked.
- Fix: source the tract/acre and coalition claims to a second page, or remove them.

**portsmouth-e2e.json** (5 parcels). Verdict: VALID-WITH-CAVEAT.
- Ages: 2026-08-24 (55 d).
- Sampled 1 (PORTS campus, multi-claim): March 2026 groundbreaking, OpenAI 20-yr lease (~8 GW IT, Aug 2026 reports), NVIDIA $1.5B and 4.25 GW initial tranche, first ~800 MW in 2028: supported. Caveat: the lease is ~8 GW, while the campus target is 10 GW; the row should say which. CX-270875 lease date and the Q1-2027 gas-plant timeline: unverified.
- Fix: reconcile 8 vs 10 GW; add a primary OpenAI/SB Energy source.

**paducah-e2e.json** (5 parcels). Verdict: VALID-WITH-CAVEAT (citation).
- Ages: 2026-08-24 (55 d).
- Sampled 2: Brookfield/NextEra award 2026-07-29 supported by trade press (~$100B; 8,000 construction and 600 permanent jobs; PSC approval pending). The cited URL is DOE's 2025-11-04 solicitation article: it does not support the July 2026 award. Reuters: ~1.2 GW compute and up to 1.8 GW to the grid, so "1.8 GW campus" is ambiguous. General Matter ($1.5B; $900M HALEU contract Jan 2026): unchecked.
- Fix: replace the source for the award with the July 2026 DOE announcement; state the 1.8 GW basis.

**wipp-e2e.json** (2 parcels). Verdict: STALE (status unsupported).
- Ages: 2026-08-24 (55 d).
- Sampled 1: NextEra selection Sept 2024 (~3 sq mi, >=150 MW solar + 100 MW storage, Xcel offtake) supported. "Still at realty-negotiation stage as of Aug 2026": no 2026 source found, so unsupported or unverifiable. The 6.6 M gal/yr allocation: unchecked.
- Fix: drop "as of Aug 2026" or confirm with DOE EM; date the claim to Sept 2024.

**Cross-file / siting-context.js:** Micro REACTOR_CLASSES basis is outdated (see ap1000 above). The AP1000 water-rating drift conflicts with CLAUDE.md.

## Summary table

| file | rows | oldest verified_at | sampled ok/total | biggest issue | fix |
|---|---|---|---|---|---|
| ap1000-sites.json (+REACTOR_CLASSES) | 14 | 2026-07-02 (analysis) | 2/4 | Arnold AFB offer withdrawn; all water ratings reset to "unknown" (40% factor inert) | Update AF RFLP status; rewrite micro basis; fix "as-built" label; flag scaled estimates; reconcile CLAUDE.md |
| nuclear-civilian-sites.json | 68 | none per row (file 2026-09-25) | 4/6 (2 outdated) | Kemmerer col_status and Clinch River status stale | Update both; add per-row verified_at |
| microreactor-fleet.json | 12 + 32 | none per row (file 2026-09-25) | 4/6 (1 overstated, 1 disputed) | Equinix called a "purchase agreement", status "Signed" | Correct Equinix wording; flag Deployable date |
| janus-nepa.json | 9 | none per row (file 2026-08-21) | 0 curated claims; roster 9/9 | Predates the 2026-08-26 selection | Re-run or annotate |
| hanford-e2e.json | 9 + 8 | 2026-08-24 | 2/4 | 1100 and 200 dated claims lack per-claim sources | Attach sources |
| srs-e2e.json | 5 | 2026-08-24 | 1/2 | Tract/acre and coalition claims absent from cited URL | Source or remove |
| portsmouth-e2e.json | 5 | 2026-08-24 | 1/1 (multi-claim) | 8 GW lease vs 10 GW campus target unreconciled | Reconcile; primary source |
| paducah-e2e.json | 5 | 2026-08-24 | 1/2 | Award cites a Nov-2025 solicitation; 1.8 GW basis ambiguous | Replace citation; clarify |
| wipp-e2e.json | 2 | 2026-08-24 | 0/1 | "Still at negotiation as of Aug 2026" unsupported | Drop or confirm |

## Contradicted and outdated claims

1. ap1000-sites.json, arnold-afb-tn (af_rflp_site, 274 ac). Claim: AF RFLP parcels offered. Current: Arnold AFB notice (2026-06-01) says no proposals for Arnold parcels. URL: https://www.arnold.af.mil/News/Article-Display/Article/4505271/notification-of-ai-data-center-no-proposal/
2. docs/siting-context.js, REACTOR_CLASSES.micro.water_basis. Claim: Army "has not paired reactor designs with installations." Current: 2026-08-26 selection paired Radiant (Benning), Antares (Bragg), BWXT (Campbell), Westinghouse (Drum), General Atomics (Hood). URL: https://www.world-nuclear-news.org/articles/us-army-selects-five-microreactor-vendors-to-power-bases
3. docs/siting-context.js, REACTOR_CLASSES.ap1000.water_basis. Claim: "Vogtle 3&4 FEIS as-built record." Current: EIS-0476 / NUREG-1872 (Aug 2008) is a licensing EIS for proposed units. URL: https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf
4. ap1000-sites.json, all 14 sites. Claim (CLAUDE.md): 13/14 water ratings validated. Current file: all "unknown" / "unassessed" since c56eea2 (2026-09-12). Doc-vs-data contradiction.
5. nuclear-civilian-sites.json, kemmerer-wy (col_status "nrc_construction_license_accepted"). Current: NRC voted 2026-03-04 to issue the construction permit (US SFR Owner LLC). URL: https://world-nuclear-news.org/articles/nrc-issues-construction-permit-for-first-natrium-plant
6. nuclear-civilian-sites.json, clinch-river-tn (status esp_approved; "recommending the CP"). Current: NRC issued the construction permit to TVA (~2026-09-29). URL: https://world-nuclear-news.org/articles/first-construction-permit-issued-for-bwrx300-smr-in-us
7. nuclear-civilian-sites.json, palisades-mi (fuel-loading pause). Outdated: NRC approved the one-time amendment and workaround (2026-10). URL: https://www.michiganpublic.org/transportation-infrastructure/2026-10-14/regulators-approve-plan-to-remove-damaged-fuel-assembly-at-palisades
8. microreactor-fleet.json, equinix-radiant (name "20-reactor purchase agreement", status "Signed"). Overstated: Equinix release (2025-08-14) says "preorder agreement for the purchase of 20." URL: https://investor.equinix.com/news-events/press-releases/detail/1079/equinix-collaborates-with-leading-alternative-energy
9. microreactor-fleet.json, deployable-unity-inl (criticality 2026-07-01). Disputed: DOE groups it in June 2026; trade press dates 1 July. URL: https://www.energy.gov/articles/us-department-energy-meets-president-trumps-goal-delivers-third-advanced-reactor
10. srs-e2e.json, srs-ai-lease-area (10 tracts, 3,103 ac, coalition names). Unsupported by cited URL. URL: https://www.energy.gov/nnsa/articles/nnsa-selects-amentum-ai-data-center-and-energy-project-savannah-river-site
11. paducah-e2e.json, paducah-ai-campus (cited source). Cited page is a 2025-11-04 solicitation, not the 2026-07-29 award. URL: https://www.energy.gov/em/articles/us-energy-department-seeks-proposals-ai-data-centers-energy-projects-paducah-site
12. wipp-e2e.json, wipp-lwa-balance ("still at realty-negotiation stage as of Aug 2026"). Unsupported: no 2026 source found. URL: https://www.energy.gov/em/em-clean-energy-land-reuse
13. ap1000-sites.json, AF RFLP sites other than Arnold. Outdated or unverified: Jan 2026 selection planned, no award found. URL: https://www.defensenews.com/air/2025/10/23/us-air-force-to-lease-base-land-for-private-ai-data-centers/

## Dead-link and citation-quality notes
- 403 bot-blocks (inconclusive): defensescoop.com 2026-08-26 article; army.mil 289074 and 293057; nrc.gov natrium.html.
- waterdata.usgs.gov monitoring-location pages return 200 but are JS shells (ap1000 water_source_url). Prefer the waterservices RDB endpoint.
- Live and unchanged: energy.gov (Hanford, SRS, Portsmouth, Paducah, WIPP, EIS PDF), epa.gov hanford-100, energy-northwest.com, investor.equinix.com.
- Not sampled: janus-nepa screening values, microreactor VENDOR specs, most hanford/srs/portsmouth/paducah/wipp infrastructure rows.
