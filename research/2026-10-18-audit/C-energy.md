# Audit C: energy, port, nickel overlays (as of 2026-10-18)

Read-only. Links checked with `-A brownfield-audit/1.0`, 1.5 s pacing. Calculations reproduced from the August 2026 EIA workbook, which I downloaded and read with the repo venv in `-I` mode. Scratch files are under `scratchpad/audit/work/`.

Link status: about 88 distinct citation URLs across the scoped datasets. All resolve (200) except 3 × 403 bot-blocks (bts.gov/ntad, maritime.dot.gov/data-reports, datacenterdynamics) and 1 × 503 on the EIA index (transient; the index returned content earlier).

Overall: no 200-day staleness in the scoped files (oldest verified_at is 2026-06-08, reference-campuses). Vintage is fine. Errors are in row-level claims, not in the pipelines.

---

## 1. EIA-860M: `eia-retired-plants.json`, `planned-retirements.json`, `planned-retirements-proximity.json`
- Primary: EIA-860M (government). Pin is **August 2026**. Live check: `/xls/august_generator2026.xlsx` returns 200 XLSX (13.96 MB). `/xls/` and `/archive/xls/` for Sep, Oct and Dec 2026 return 503, so August is the newest real month. Pin is current.
- **Doc contradicts the live site:** CLAUDE.md says `/xls/` is dead and `/archive/xls/` is the only working path. Today it is the reverse: `/archive/xls/august...` returns 503, and the code's `/xls/` path works. The code is correct. The CLAUDE.md guidance is stale.
- Reproduced exactly from the August workbook: planned retirements **94 plants, 77,402 MW**, same names as shipped (builder rules applied verbatim).
- `planned-retirements-proximity`: brute-force recompute gives 675 of 677 shipped records within 5 mi. The 2 extras sit at 4.97–5.00 mi (metric boundary).
- `eia-retired-plants`: the connector's own `PointIndex` (run against the August cache) indexes **469 plants**, matching the project note. 1,500 of 1,500 random shipped distances reproduce within 0.15 mi. My own brute-force reimplementation disagreed; that was my grouping error, not the data.
- **Semantics:** `Planned Retirement Year` is a utility filing and is reversible. Campbell (Consumers, 2026) is held open under DOE §202(c) orders renewed every ~90 days since May 2025 (latest Order 202-26-39, in effect to 2026-11-14; first order vacated by the D.C. Circuit 2026-09-11, later renewals still in force per reporting). Craig Unit 1 (2026 in the workbook) is also under a 202(c) order (GEM confirms). The overlay shows these as planned retirements with no caveat.
- Stale orphan: `data/cache/f5fc6a369570d33f.bin` is an **April 2026** workbook under a pre-URL cache key. Current code reads `917bfa9f6bb729b9.bin` (August, correct). The orphan is unused but misleading.
- Frontend: planned-retirement popup already has a "dates can slip" caveat. Good.
- **Verdict: VALID-WITH-CAVEAT.** Fix: annotate rows under active 202(c) orders (or in status); delete the orphan cache; correct the CLAUDE.md archive-path note.

## 2. `retired-industrial.json` (EPA GHGRP "stopped reporting", 658 sites)
- Primary: EPA GHGRP via Envirofacts (government). Generated 2026-07-02; `ghgrp_latest_year` = 2023. Whether that is the newest GHGRP year needs a check against the current release. Not confirmed here.
- Sampled 4 facilities against Envirofacts reporting history: Flint Hills North Pole (refinery closed 2014 per public record, last reports 2023) and Flint Hills Resources Alaska (both stopped-reporting 2018–2023): consistent with closure. **Hecla Greens Creek** (silver/zinc mine, Alaska): **operating in 2025** (8.72 M oz Ag; Hecla 2026 guidance), yet listed as a closure candidate after its last report in 2018. Olam West Coast (2013): unresolved.
- "Stopped reporting" means the facility stopped filing GHGRP reports. It does not mean closed. The popup says this honestly ("could be closed, idled, or below threshold"). The "Retired Sites" framing and the popup phrase "A former large-load facility" overclaim for operating facilities. The 125 Mining rows include operating mines.
- **Verdict: VALID-WITH-CAVEAT.** Fix: add an operating-status check (state permits or EIA/MSHA) or label the row "reporting stopped — operating status unknown"; drop mining or restrict it to closed mines; reword "former large-load facility"; confirm `ghgrp_latest_year` against the newest release.

## 3. `coal-conversions.json` (18 curated) and `coal-conversions-proximity.json` (140 sites ≤10 mi)
- Upstream: Global Energy Monitor wiki (NGO compilation, not a government primary). All 18 URLs resolve. verified_at 2026-08-23 / 2026-09-25 (≤56 days). Proximity file is derived; not separately sampled.
- Sampled 6 GEM pages and 1 federal record:
  - **Conesville** supported (GEM units 136+148+161.5+841.5+443.9+443.9 = 2,174.8 MW; units retired 2019–2020). Matches the row.
  - **Widows Creek** supported (last unit retired 2015; Google plan for 2016 construction).
  - **Cumberland** supported (TVA Feb 2026 decision to run past 2028).
  - **Craig** supported with a caveat (Units 2–3 2028 planned; Unit 1 2026 is under a §202(c) order; row notes this).
  - **Naughton — contradicted/outdated:** GEM says Units 1–2 stopped burning coal 2025-12-31 and convert to gas in 2026. The row says `planned_retirement`, no year, `queue_transfer_eligible: true` (derived from status). A gas-converting plant likely still occupies its POI.
  - **Belews Creek — partially contradicted:** row year 2036; GEM table shows Units 1–2 retire 2040 (planned); GEM text says 2036. Row note says Duke proposed 2040. Year field conflicts with note.
  - **Homer City 1,884 MW — not supported by cited page:** GEM units 1–3 sum to 2,012 MW (660/660/692), and the reference-campuses row says 2,000 MW. Unit 4 was not found on the page. Check against EIA-860.
- **Valuation semantics:** `est_stranded_asset_value_usd` = `calculate_stranded_asset_valuation(..., distance_mi=0.0)`, so the documented exp(−0.25·mi) decay is always 1. The value is also computed for operating and converted plants (Cumberland, Colstrip, Martin Lake, Montour). app.js labels the column **"Stranded Value"** (table header) even though the popup says "Modeled value" — the table header overclaims.
- **Verdict: VALID-WITH-CAVEAT.** Fix: fix Naughton status and POI flag; reconcile Belews year with the 2040 proposal; re-source Homer City MW from EIA-860; restrict the stranded-value column to retired/planned rows and rename it "Modeled replacement value"; delete the dead decay term or implement it.

## 4. `coal-nepa.json` (18 NEPA screens)
- Plant set matches `coal-conversions.json` exactly (18/18 names). Generated 2026-08-24, before the 2026-09-25 coal rebuild. Attributes may differ; not re-screened. Screening counts are context only, not score inputs.
- **Verdict: VALID-WITH-CAVEAT** (re-run after the coal rebuild). No sampling of screen values done.

## 5. `federal-clean-energy.json` (10 DOE rows)
- Primary: DOE/EM/OCED (government). All cited URLs resolve. verified_at 2026-08-23 / 2026-08-24.
- Sampled 3 of 10 (Mineral Basin and Lewis Ridge not checked):
  - **SRS** — DOE selection page confirms SRS as one of four selections; the **Amentum** partner claim is not on the cited page (unsupported by its citation).
  - **Paducah** — the cited page is the 2025 solicitation. The **Jul-2026 award**, Brookfield, NextEra 2 GW gas and 1.8 GW claims are not on it (unsupported by its citation).
  - **Portsmouth** — groundbreaking 2026-03-20 and "10 GW" new generation supported. The "10 GW DC + ~9.2 GW gas, $33.3B" split is not on the cited page.
- **`available_acreage` is misleading:** it holds full reservation sizes (SRS 198,000 ac; INL 570,000 ac with 44,000 offered; NNSS 860,000 ac). The builder docstring discloses this, but the field name and any "available acreage" label overstate.
- **Verdict: VALID-WITH-CAVEAT.** Fix: add the award/partner sources; rename the field or label it "reservation acreage".

## 6. `reference-campuses.json` (10 hand-curated, no builder)
- Sources resolve except datacenterdynamics (403). 8 rows last refreshed 2026-06-08 (132 days, under 200).
- **Google Widows Creek — status contradicted by its citation:** row says "operational". The cited Google blog post says "we'll be building on the grounds of the Widows Creek coal power plant" (a planned-build announcement, ~2015 per the "14th site" wording). Nothing cited supports operational status.
- **Conesville — MW contradicted:** row says "2,005 MW". GEM unit sum is 2,174.8 MW, which matches our own coal row. The 2,005 figure has no source on the row.
- **Homer City — MW inconsistent:** row says "2,000 MW"; coal row says 1,884; GEM units 1–3 sum to 2,012.
- Other rows (Project Marvel, Cheswick, QTS, Microsoft, Meta, NorthPoint, AWS, Homer City status) not sampled.
- **Verdict: INVALID** (status and MW fields on at least 3 of 10 rows). Fix: re-source Widows Creek status and Conesville/Homer City MW; add a verified_at per field, not per row.

## 7. `ports.json` (108 Coastal and Great Lakes ports, USDOT/BTS NTAD)
- Primary: BTS NTAD FeatureServer on services.arcgis.com. **Live: 150 features** (the stated Coastal + Great Lakes subset is 108). bts.gov page returns 403 to bots; the service is what the builder uses.
- 5 ports lack `state` (e.g., Duluth-Superior MN/WI; expected for multi-state ports).
- **Verdict: VALID.**

## 8. `port-proximity.json` (46,759 sites, derived from ports + shipyards)
- Sampled 8 port distances against brute-force haversine: all within 0.1 mi (equirectangular vs haversine).
- Tombstone convention intact.
- **Verdict: VALID.** Depends on shipyards caveats for shipyard fields (not sampled for shipyards).

## 9. `shipyards.json` (16 curated)
- Primary: none exists (MARAD publishes PDFs only). Source URL is the generic MARAD data-reports index, which returns 403 to bots and does not support per-row claims. Per-row citations are Wikipedia, company pages and clui.org.
- Sampled 1 (Gulf Island Houma, `heavy_module` claim): not verified (page regex failed). Not sampled further.
- **Verdict: VALID-WITH-CAVEAT.** Fix: replace the generic MARAD citation with per-row sources for each capability tag; treat `heavy_module` as unverified until checked.

## 10. `nickel-anchors.json` (16 curated; Census Gazetteer coordinates)
- Gazetteer zip resolves (200); coordinates not downloaded or checked.
- **Port Nickel "387-acre tract for sale or lease, listed as of 2026-07-19"** — the only cited source is an EPA 2025 reuse-determination PDF. It is compressed and could not be read, so the listing claim is **unverified** (no source in the dataset supports it). Other rows' status claims (Eagle Mine acquisition, Humboldt selected for Tamarack 2026-09-10, Talon BMPF not advancing) cite Talon press releases that resolve.
- `locality` precision on 12 rows is a deliberate choice (documented in the schema).
- **Verdict: VALID-WITH-CAVEAT.** Fix: source or remove the Port Nickel listing claim; add a source for the 2026-07-19 listing.

## 11. `nickel-anchor-proximity.json` (14 MB derived)
- Not sampled in this audit. Per CLAUDE.md, a brute-force haversine cross-check (0.050 mi max deviation) was done on 2026-09-08. I did not repeat it.
- **Verdict: VALID (not re-verified here).**

---

## Table

| dataset | primary source? | verdict | vintage | sampled rows ok/total | biggest issue | fix |
|---|---|---|---|---|---|---|
| eia-retired-plants.json | yes, EIA-860M (Aug 2026, newest live) | VALID-WITH-CAVEAT | 2026-08 preliminary | 1,500/1,500 distances; 469 plants | CLAUDE.md archive-path guidance is stale; orphan April cache | fix docs; delete orphan `f5fc…bin` |
| planned-retirements.json | yes, EIA-860M (Aug 2026) | VALID-WITH-CAVEAT | 2026-08 preliminary | 94/94 plants, 77,402 MW exact | Campbell and Craig 2026 retirement held open by DOE §202(c) orders; no caveat | annotate 202(c) rows |
| planned-retirements-proximity.json | derived from EIA | VALID | 2026-08 | 675/677 within 5 mi (2 boundary cases) | — | — |
| retired-industrial.json | yes, EPA GHGRP (via Envirofacts) | VALID-WITH-CAVEAT | 2026-07-02; latest year field 2023 | 2/4 consistent with closure; 1 contradicted (Greens Creek operating); 1 unresolved | "stopped reporting" read as closure; 125 mining rows include operating mines | add operating-status check; reword; confirm latest year |
| coal-conversions.json | no, GEM wiki (NGO compiler) | VALID-WITH-CAVEAT | 2026-08-23 / 09-25 | 4/6 supported, 1 contradicted (Naughton status), 1 partial (Belews year), Homer City MW unsupported | Naughton status; "Stranded Value" on operating plants | fix status; restrict/rename value; reconcile years and MW |
| coal-conversions-proximity.json | derived | VALID-WITH-CAVEAT | 2026-09-25 | not sampled | inherits coal caveats | — |
| coal-nepa.json | derived (nepa-mcp) | VALID-WITH-CAVEAT | 2026-08-24 | 18/18 plant names match | predates 09-25 coal rebuild | re-run |
| federal-clean-energy.json | yes, DOE/EM/OCED | VALID-WITH-CAVEAT | 2026-08-23/24 | 3 of 10 checked; partner/award claims not on cited pages (SRS, Paducah); Portsmouth partly | `available_acreage` = full reservation; partner claims unsupported by citation | add award sources; rename field |
| reference-campuses.json | no, press/news (hand-curated) | INVALID | 2026-06-08 to 09-25 | 3 checked: Widows Creek status contradicted; Conesville MW contradicted; Homer City MW inconsistent | status and MW fields unsupported | re-source Widows Creek; fix MW; per-field dates |
| ports.json | yes, BTS NTAD (live service, 150 features) | VALID | 2026-08-28 | source live, subset consistent | state missing on 5 multi-state ports | none |
| port-proximity.json | derived | VALID | 2026-08-28 | 8/8 distances within 0.1 mi | shipyard fields inherit shipyard caveat | — |
| shipyards.json | no; MARAD index is generic and 403s bots | VALID-WITH-CAVEAT | 2026-08-27 | 0 verified (1 attempted, inconclusive) | capability tags unsourced per row | per-row sources |
| nickel-anchors.json | partly; Census Gazetteer and press | VALID-WITH-CAVEAT | 2026-09-08 / 09-12 | 1 checked: Port Nickel listing unverified | 387-acre listing has no readable source | source or remove claim |
| nickel-anchor-proximity.json | derived | VALID (not re-verified) | 2026-09-12 | not sampled | — | — |

---

## Contradicted or unsupported curated rows (for the top list)

1. **reference-campuses / Google Widows Creek Data Center**: `status: operational`. Cited https://blog.google/inside-google/infrastructure/a-power-plant-for-internet-our-newest/ describes a planned build ("we'll be building on the grounds of the Widows Creek coal power plant"). Not operational.
2. **reference-campuses / Conesville AI Campus**: "AEP Conesville Power Plant (coal, 2,005 MW ...)". GEM https://www.gem.wiki/Conesville_Power_Plant unit table sums to 2,174.8 MW, matching our coal row.
3. **coal-conversions / Naughton Power Plant**: `planned_retirement`, no year, `queue_transfer_eligible: true`. GEM https://www.gem.wiki/Naughton_Power_Plant says Units 1–2 stopped burning coal 2025-12-31 and convert to gas in 2026.
4. **coal-conversions / Belews Creek**: `planned_retirement_year 2036`. GEM https://www.gem.wiki/Belews_Creek_Steam_Station table shows 2040 (planned) for Units 1–2, and the row's own note says Duke proposed 2040.
5. **coal-conversions / Homer City**: `nameplate_coal_mw 1884`. GEM https://www.gem.wiki/Homer_City_Generating_Station Units 1–3 sum to 2,012 MW; reference-campuses says 2,000 MW. Not supported by the cited page.
6. **federal-clean-energy / Paducah**: Jul-2026 award, Brookfield and NextEra 2 GW gas. Not on the cited DOE page (https://www.energy.gov/em/articles/us-energy-department-seeks-proposals-ai-data-centers-energy-projects-paducah-site, a 2025 solicitation).
7. **federal-clean-energy / Savannah River**: Amentum partner. Not on the cited DOE selection page.
8. **retired-industrial / Hecla Greens Creek** (facility GHGRP-1006162): flagged as stopped-reporting candidate. Mine operating in 2025 (SEC/Hecla results).

## Notes on method
- The retired-plant brute-force mismatch was my reimplementation error (469 vs 508 plants). The connector's own index was used for the 1,500-sample check.
- Caveat on the web checks: DOE 202(c) status for Campbell comes from public reporting (michiganpublic.org 2026-05-18; michigan.gov AG 2026-09-11; Earthjustice), not from a DOE page directly.
- Unverified: shipyard capability tags, Homer City unit 4, Port Nickel listing, Mineral Basin and Lewis Ridge rows, nickel-anchor-proximity values.
