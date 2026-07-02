# Manufacturing reuse opportunities for brownfields — sector expansion (2026-07-02)

The dashboard's two scoring lenses cover **data-center loads** and **new power
generation**. This analysis expands the reuse thesis to *manufacturing*
sectors that plausibly site on brownfields, with the siting factors each one
actually weighs — several of which (workforce, logistics proximity) the
dashboard already measures or could measure cheaply. Companion data work
landed with this doc: the **planned-retirements overlay**
(`docs/data/planned-retirements.json`) — 90 operating plants ≥100 MW /
~75.6 GW with announced retirement dates, the forward-looking generation
counterpart to `eia-retired-plants` / `retired-industrial`.

## Why manufacturing is the next reuse wave

- EPA's Jan 2026 guidance ([EPA-540-S-26-001](https://www.epa.gov/system/files/documents/2026-01/guidance-on-the-redevelopment-of-superfund-and-brownfield-sites-as-ai-data-centers.pdf))
  formalized Superfund/brownfield reuse for AI data centers; industry press
  ([IA Magazine, Feb 2026](https://www.iamagazine.com/2026/02/02/are-brownfield-sites-set-to-drive-a-building-boom-in-2026/))
  expects the ~450k-site brownfield inventory to absorb uses "well beyond
  data centers" in 2026.
- Brownfields carry exactly what heavy manufacturing needs and greenfields
  lack: existing grid interconnection, heavy-industrial zoning, rail spurs,
  water rights, and (often) a legacy industrial workforce within commuting
  range ([ESS News, Apr 2026](https://www.ess-news.com/2026/04/13/making-the-case-for-brownfield-battery-builds/)).

## Sector taxonomy — site requirements vs. dashboard signals

| Sector | Power | Water | Acreage | Rail/highway | Workforce | Notes / evidence |
|---|---|---|---|---|---|---|
| **Battery cell / gigafactory** | 50–300 MW | Moderate | 100–500 ac | Rail helpful (materials in, packs out) | 1,500–3,000 semi-skilled; legacy mfg workforce is a fit (Viridi Buffalo GreenForce model) | Brownfield colocation cuts timeline via existing grid ([ESS News](https://www.ess-news.com/2026/04/13/making-the-case-for-brownfield-battery-builds/), [IndustryWeek Buffalo](https://www.industryweek.com/technology-and-iiot/video/55315374/battery-manufacturer-bets-big-on-brownfield-site-in-buffalo-new-york)) |
| **BESS (grid storage) install** | Interconnect IS the product | Minimal | 5–50 ac | No | Small O&M crew | Best inside "load pockets"; retired-plant / retired-industrial sites are ideal — our grid-inheritance signal directly applies |
| **EAF / green steel** | 150–400 MW | High (cooling) | 300–1,000 ac | Rail essential (scrap in, coil out) | 1,000+; strongly favors legacy steel towns | Brownfield revamps run months-to-years vs greenfield ([3DS/DELMIA](https://blog.3ds.com/brands/delmia/greenfield-steel-plant-vs-brownfield-steel-plant-whats-the-difference/)); our `rail_mi` + `transmission_kv` + retired-steel-mill overlay entries are the screen |
| **Hydrogen electrolysis / e-fuels / ammonia** | 100 MW–1 GW+ | High (feedstock!) | 50–300 ac | Pipeline or port/rail for offtake | Modest (100–300) | Customers are chemicals/fertilizer/steel/e-fuels; port- or pipeline-proximate brownfields anchor export plays ([Springer](https://link.springer.com/chapter/10.1007/978-3-031-55206-9_17), [BDD 2026 outlook](https://www.bddelectrode.com/blog/2026-outlook-for-water-electrolysis-hydrogen-projects/)); our `gas_pipeline_mi` is a proxy for pipeline corridors |
| **Semiconductor fab** | 50–100 MW (ultra-reliable) | Very high + ultra-pure | 500–1,200 ac | Highway; air-freight proximity | 2,000–5,000 highly skilled + university pipeline | Least brownfield-tolerant (vibration, contamination risk to cleanrooms); realistic only on *lightly*-impacted large sites near metro workforce ([Manufacturing Dive 2026](https://www.manufacturingdive.com/news/major-factory-construction-projects-to-watch-in-2026/809448/)) |
| **Defense industrial (munitions, shipyard-adjacent, drones)** | Modest | Low–moderate | 100–5,000 ac (buffer!) | Rail + highway | Clearance-eligible workforce near existing installations | FUDS/BRAC records are literally former defense land — buffer distances and heavy-industrial zoning survive; the AP1000 military tab already models the workforce side |
| **Electrolyzer / cleantech component mfg** | 10–50 MW | Low | 20–100 ac | Highway | Skilled trades; IIJA-funded ([DOE](https://www.energy.gov/eere/fuelcells/bipartisan-infrastructure-law-clean-hydrogen-electrolysis-manufacturing-and-0)) | Fits mid-size ACRES brownfields that fail every DC screen (no 100+ ac, no 138 kV) |

## What this implies for the dashboard

1. **The signals already on disk cover most of the screen.** Power
   (`transmission_mi/kv`, `substation_mi/kv`), water-adjacent proxies (flood
   zone, NRI drought), logistics (`rail_mi`, `highway_mi`,
   `gas_pipeline_mi`), incentives (OZ, IRA energy community), and land
   (`acreage`). What manufacturing adds that DC/generation don't weigh:
   **rail becomes primary** (steel, batteries, ammonia), **workforce becomes
   scored** (semi/battery/steel), and mid-size sites (20–300 ac) become
   *valuable* instead of screened out.
2. **Workforce is the missing data layer.** Census LEHD/LODES (WAC files,
   free bulk CSV) gives manufacturing-sector employment within a commute
   radius of any lat/lon — one pre-indexed pass, same pure-Python spatial
   pattern as `connectors/spatial.py`. This is the single highest-value new
   connector for a manufacturing lens (backlog item added).
3. **A third scoring lens ("Manufacturing fit") is cheap once workforce
   exists** — reweight existing components: rail 20, transmission 15,
   acreage 15 (peaking at 100–500 ac, not monotonic), workforce 20, water/
   climate 10, gas 10, readiness/incentives 10. Sums to 100 per the
   weight-table contract in `dc-score.js`.
4. **Generation-side counterpart landed now:** the planned-retirements
   overlay surfaces the ~90 dated interconnect hand-offs (Cumberland 2.6 GW
   2026, Monroe 3.3 GW 2028, Rockport 2.6 GW 2028 …) that DOE's
   [coal-to-nuclear studies](https://www.energy.gov/ne/articles/doe-report-finds-hundreds-retiring-coal-plant-sites-could-convert-nuclear)
   identify as hosting 128–174 GW of nuclear repowering potential across 145
   coal sites.

## Sources

- [EPA guidance on Superfund/brownfield redevelopment as AI data centers (Jan 2026)](https://www.epa.gov/system/files/documents/2026-01/guidance-on-the-redevelopment-of-superfund-and-brownfield-sites-as-ai-data-centers.pdf)
- [ESS News — Making the case for brownfield battery builds (Apr 2026)](https://www.ess-news.com/2026/04/13/making-the-case-for-brownfield-battery-builds/)
- [IndustryWeek — Battery manufacturer bets big on brownfield site in Buffalo](https://www.industryweek.com/technology-and-iiot/video/55315374/battery-manufacturer-bets-big-on-brownfield-site-in-buffalo-new-york)
- [Dassault/DELMIA — Greenfield vs brownfield steel plants](https://blog.3ds.com/brands/delmia/greenfield-steel-plant-vs-brownfield-steel-plant-whats-the-difference/)
- [Springer — Redevelopment of industrial brownfields through green hydrogen](https://link.springer.com/chapter/10.1007/978-3-031-55206-9_17)
- [DOE — IIJA hydrogen electrolysis manufacturing awards](https://www.energy.gov/eere/fuelcells/bipartisan-infrastructure-law-clean-hydrogen-electrolysis-manufacturing-and-0)
- [Manufacturing Dive — Major factory construction projects to watch in 2026](https://www.manufacturingdive.com/news/major-factory-construction-projects-to-watch-in-2026/809448/)
- [IA Magazine — Are brownfield sites set to drive a building boom in 2026?](https://www.iamagazine.com/2026/02/02/are-brownfield-sites-set-to-drive-a-building-boom-in-2026/)
- [DOE — Coal-to-nuclear transitions (145 sites, 128–174 GW)](https://www.energy.gov/ne/articles/doe-report-finds-hundreds-retiring-coal-plant-sites-could-convert-nuclear)
- [Utility Dive — 269 GWe potential at nuclear + coal sites](https://www.utilitydive.com/news/us-nuclear-coal-power-sites-could-host-up-to-269-gwe-of-new-nuclear-capaci/727066/)
- [EIA-860M Preliminary Monthly Electric Generator Inventory](https://www.eia.gov/electricity/data/eia860m/)
