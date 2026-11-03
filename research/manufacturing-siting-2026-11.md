# Manufacturing siting: robots, gas turbines, transformers, critical minerals (2026-11)

Four siting screens added to the atlas on 2026-11-02, with a catalog of named US plants and the site needs those plants show. Everything below the generated marker is written by `python3 scripts/manufacturing_catalog.py memo` from `docs/data/manufacturing-facilities.json` and `docs/screens.js`, so the memo cannot disagree with the site.

## How the rows were checked

1. Claude Haiku 5.5 researchers searched the web and opened each page they cite (brief: `data/validation/manufacturing/RESEARCH_BRIEF.md`).
2. Claude Sonnet 5.5 verifiers re-opened every page and graded each row supported, unsupported, contradicted or unverifiable, correcting fields from the page (`VERIFIER_BRIEF.md`).
3. Code re-fetched every page and looked for the quote (`scripts/manufacturing_catalog.py adjudicate`, the same rule as the local-records pipeline).
4. Claude Opus 5.5 decided the disputes (`data/validation/manufacturing/opus.json`, reasons recorded).

A row ships only if a second model read it. Plants are mapped at their town's 2024 Census Gazetteer point, not at the plant, so distances are good to a few miles.

## What the screens cannot see

- **Workforce.** No labor-force layer covers the corpus (the county labor-force connector needs a Census key nobody has registered). The "plant of this kind nearby" check is a proxy for suppliers and trained workers, not a measure of them.
- **Buildings.** Several plants reused large existing buildings (Eaton converted an 861,000 sq ft building in Jonesville SC). The atlas has land area for about a fifth of sites and no building inventory.
- **Heavy haul.** Large power transformers and gas-turbine casings weigh hundreds of tons. Rail within a mile is the check; bridge ratings, clearances, Schnabel-car routes and barge docks are not assessed.
- **Test power and gas.** Transformer test bays and turbine test stands need high-capacity power and gas service. Line and pipeline distances show what is nearby, not available capacity.
- **Federal awards change.** DOE and DoD awards are listed as the page states them; several 2022-2024 awards were later renegotiated or cancelled. Each row links its source and date.

<!-- generated below -->


## Robotics

Robot and physical-AI assembly plants are light-industrial buildings near engineers and suppliers. No agency threshold exists; ours come from built plants.

**Checks**

- Land ≥20 acres (`acreage ≥ 20`, ours). Built robot plants run 70,000 to 800,000 sq ft of floor; 20 acres fits the middle of that range with parking and yard.
- Primary road within 5 mi (`highway_mi ≤ 5`, ours).
- Outside flood zone (`in_sfha = false`, agency).
- Robot or AI-hardware plant within 100 mi (`mfg_robotics_mi ≤ 100`, ours). Distance to a Census place point for the nearest operating, building or announced plant of this kind: a proxy for suppliers and trained workers nearby. Plant points are good to a few miles.

**What built plants show** (quotes are verbatim from the linked page)

- land: Agility Robotics' humanoid robot factory is a 70,000 square foot building in Salem, Oregon — "Initial construction of Agility’s 70,000 square foot robot factory began last year, and it is set to open later this year." ([source](https://agilityrobotics.com/content/opening-robofab-worlds-first-factory-for-humanoid-robots))
- land: Waymo and Magna's Mesa, Arizona vehicle integration plant is a 239,000 square foot facility — "the recently built 239,000-square-foot facility" ([source](https://www.azfamily.com/2025/05/06/waymo-plans-expand-car-fleet-through-new-mesa-factory))
- land: Anduril's planned hyperscale autonomous-systems factory campus sits on 500 acres near Rickenbacker International Airport — "located on 500 acres near Rickenbacker International Airport south of Columbus" ([source](https://industryweek.com/leadership/news/55261459/anduril-industries-to-build-5-million-square-foot-manufacturing-facility-in-ohio))
- land: Yaskawa's Franklin, Wisconsin campus is planned to reach more than 800,000 square feet of manufacturing, packaging, and training space over three to eight years — "eventually encompassing more than 800,000 square feet of advanced manufacturing, packaging, and training space." ([source](https://foodindustryexecutive.com/2025/08/yaskawa-america-announces-new-robotics-manufacturing-expansion-in-franklin-wisconsin/))
- land: Yaskawa bought a former Transpak Corp. building in Franklin, Wisconsin in 2023 and still occupies it, so the robot campus builds on a reused building — "In 2023, Yaskawa America purchased the former Transpak Corp. building in Franklin, which the manufacturer currently occupies." ([source](https://biztimes.com/yaskawa-america-to-invest-180-million-to-relocate-headquarters-to-franklin/))
- workforce: Agility expects RoboFab to employ more than 500 workers in Salem at full capacity — "At full capacity, RoboFab will employ more than 500 workers in Salem" ([source](https://agilityrobotics.com/content/opening-robofab-worlds-first-factory-for-humanoid-robots))
- workforce: Yaskawa's Wisconsin robotics expansion is expected to create more than 700 new jobs — "will create more than 700 new jobs" ([source](https://www.plantservices.com/industry-news/news/55298080/yaskawa-america-invests-180m-to-expand-robotics-manufacturing-facility-in-wisconsin))
- other: Wisconsin authorized up to $18 million in performance-based Enterprise Zone tax credits for the Yaskawa campus — "authorizing up to $18 million in performance-based Enterprise Zone tax credits" ([source](https://www.plantservices.com/industry-news/news/55298080/yaskawa-america-invests-180m-to-expand-robotics-manufacturing-facility-in-wisconsin))
- land: FANUC plans a new robot production plant of 840,000 sq ft on property it will acquire — "to acquire property and construct a new 840,000 sq. ft. facility" ([source](https://www.fanucamerica.com/news-resources/fanuc-america-press-releases/2026/03/24/fanuc-america-invests-90-million-robot-manufacturing-expansion))
- land: Amazon Robotics' Westborough mobile drive unit plant is a 350,000 sq ft facility — "The 350,000-square-foot facility" ([source](https://www.areadevelopment.com/newsitems/10-29-2021/amazon-westborough-massachusetts.shtml))
- land: Wistron bought two existing sites in Fort Worth for its AI supercomputer plants — "Wistron purchased two sites for the factories in June and July" ([source](https://www.hillwood.com/newsroom/news-articles/nvidia-partner-wistron-confirms-fort-worth-supercomputer-plants-750-million-plus-investment/))
- land: Saronic's $300 million Franklin, Louisiana shipyard expansion adds more than 300,000 sq ft of production space — "which will add more than 300,000 square feet of new production capacity" ([source](https://www.navalnews.com/naval-news/2025/12/saronic-expands-its-louisiana-shipyard-with-300-million-investment-to-accelerate-autonomous-ship-production/))
- workforce: Saronic's Franklin, Louisiana shipyard expansion adds 1,500 skilled jobs — "adding 1,500 skilled jobs" ([source](https://www.navalnews.com/naval-news/2025/12/saronic-expands-its-louisiana-shipyard-with-300-million-investment-to-accelerate-autonomous-ship-production/))
- workforce: Universal Robots' Wixom cobot hub is expected to create over 200 jobs — "creating over 200 jobs over the coming years." ([source](https://www.universal-robots.com/news-and-media/news-center/new-us-operations-hub-to-open-in-2026/))
- port: Saronic's Port Alpha in Brownsville, Texas is designed to build vessels up to 850 ft, on an initial 835 acres at the Port of Brownsville with waterfront access — "Port Alpha will encompass a shipyard and manufacturing facility capable of producing vessels up to 850-ft." ([source](https://www.navalnews.com/?p=89127))

**Plants**

| Plant | Place | Status | Investment | Federal award | Source |
|---|---|---|---|---|---|
| Magna Mesa upfitting facility for Waymo autonomous vehicles | Mesa, AZ | operating |  |  | [link](https://www.azfamily.com/2025/05/06/waymo-plans-expand-car-fleet-through-new-mesa-factory) |
| Boston Dynamics Robotics Metaplant Application Center, Savannah | Savannah, GA | operating |  |  | [link](https://manufacturingdive.com/news/boston-dynamics-begins-robotics-testing-hyundai-atlas-humanoid/831000) |
| Saronic Franklin shipyard expansion (Gulf Craft, Franklin) | Franklin, LA | expansion | $300M |  | [link](https://www.navalnews.com/naval-news/2025/12/saronic-expands-its-louisiana-shipyard-with-300-million-investment-to-accelerate-autonomous-ship-production/) |
| Amazon Robotics mobile drive unit plant, Westborough | Westborough, MA | operating |  |  | [link](https://www.areadevelopment.com/newsitems/10-29-2021/amazon-westborough-massachusetts.shtml) |
| Universal Robots US Operations Hub, Wixom | Wixom, MI | announced |  |  | [link](https://www.universal-robots.com/news-and-media/news-center/new-us-operations-hub-to-open-in-2026/) |
| Agility Robotics RoboFab humanoid robot factory | Salem, OR | under construction |  |  | [link](https://agilityrobotics.com/content/opening-robofab-worlds-first-factory-for-humanoid-robots) |
| Foxconn Houston AI server factory (NVIDIA systems; robots planned on lines) | Houston, TX | operating |  |  | [link](https://techinformed.com/foxconn-to-use-humanoid-robots-at-houston-ai-server-plant/) |
| Saronic Port Alpha shipyard, Brownsville | Brownsville, TX | announced | $3.00B |  | [link](https://www.navalnews.com/?p=89127) |
| Yaskawa America Franklin robotics campus expansion | Franklin, WI | announced | $180M |  | [link](https://www.plantservices.com/industry-news/news/55298080/yaskawa-america-invests-180m-to-expand-robotics-manufacturing-facility-in-wisconsin) |

## Gas turbines

Turbine casings and rotors leave by rail, heavy-haul trailer or barge, and the plants that make them are large campuses. Test-stand gas supply is not assessed.

**Checks**

- Land ≥50 acres (`acreage ≥ 50`, ours). Caterpillar's Lafayette engine campus is 1.6 million sq ft, about 37 acres of floor.
- Rail within 1 mi (`rail_mi ≤ 1`, ours).
- Line ≥115 kV within 5 mi (`transmission_115kv_mi ≤ 5`, ours).
- Outside flood zone (`in_sfha = false`, agency).

**What built plants show** (quotes are verbatim from the linked page)

- port: Large gas turbines are delivered by barge into an inland port and unloaded by heavy-lift crane — "The gas turbine arrives at the Port of Catoosa from Savannah by barge." ([source](https://www.barnhartcrane.com/projects/turbine-transport/))
- heavy haul: Steam turbines are moved by heavy-lift crane, then by self-propelled modular trailer to a laydown area, then loaded onto rail cars — "hauled to the laydown area on a Goldhofer trailer." ([source](https://www.barnhartcrane.com/projects/turbine-transport/))
- rail: A large engine plant expansion budgeted on-site rail infrastructure alongside new machinery — "would go toward new machinery equipment, as well as on-site rail infrastructure." ([source](https://www.insideindianabusiness.com/articles/caterpillar-planning-725m-expansion-in-lafayette))
- land: Existing heavy-engine plant campus of 1.6 million sq ft was expanded by a 300,000 sq ft addition rather than a greenfield build — "build and equip a 300,000-square-foot addition to the 1.6 million-square-foot facility" ([source](https://www.insideindianabusiness.com/articles/caterpillar-planning-725m-expansion-in-lafayette))
- workforce: A turbine factory expansion adds skilled production jobs to the local workforce — "The expansion will add 220 jobs to Mitsubishi's local workforce." ([source](https://www.ajc.com/news/2026/10/georgia-power-turbine-plant-mitsubishi/))
- land: A closed heavy-equipment plant was reused to restart gas turbine manufacturing instead of building new — "officially took over the former Caterpillar Work Tools facility in Wamego." ([source](https://ecodevo.com/one-year-of-solar-turbines-in-wamego-from-transition-to-global-energy-production/))

**Plants**

| Plant | Place | Status | Investment | Federal award | Source |
|---|---|---|---|---|---|
| GE Vernova Chamblee steam turbine repair and life extension | Chamblee, GA | expansion | $2M |  | [link](https://www.gevernova.com/company/investing-in-manufacturing) |
| Mitsubishi Power Savannah Machinery Works expansion | Savannah, GA | expansion | $490M |  | [link](https://www.ajc.com/news/2026/10/georgia-power-turbine-plant-mitsubishi/) |
| Caterpillar Lafayette Large Engine Center expansion | Lafayette, IN | expansion | $725M |  | [link](https://www.insideindianabusiness.com/articles/caterpillar-planning-725m-expansion-in-lafayette) |
| Solar Turbines Wamego gas turbine plant | Wamego, KS | operating |  |  | [link](https://ecodevo.com/one-year-of-solar-turbines-in-wamego-from-transition-to-global-energy-production/) |
| GE Vernova Bangor gas power capacity growth | Bangor, ME | expansion | $20M |  | [link](https://www.gevernova.com/company/investing-in-manufacturing) |
| Howmet Aerospace Whitehall casting plant expansion | Whitehall, MI | expansion |  |  | [link](https://www.industrialinfo.com/news/article/howmet-adds-capacity-as-gas-turbine-demand-skyrockets--364394) |
| Siemens Energy Charlotte gas turbine manufacturing restart | Charlotte, NC | announced |  |  | [link](https://charlotteregion.com/news/siemens-energy-to-add-500-jobs-in-nc-including-charlotte-site/) |
| Siemens Energy Winston-Salem gas turbine parts plant | Winston-Salem, NC | operating |  |  | [link](https://charlotteregion.com/news/siemens-energy-to-add-500-jobs-in-nc-including-charlotte-site/) |
| GE Vernova Parsippany gas power capacity growth | Parsippany, NJ | expansion | $25M |  | [link](https://www.gevernova.com/company/investing-in-manufacturing) |
| GE Vernova Schenectady gas power manufacturing | Schenectady, NY | expansion | $90M |  | [link](https://www.gevernova.com/company/investing-in-manufacturing) |
| GE Vernova Greenville gas turbine factory expansion | Greenville, SC | expansion | $160M |  | [link](https://www.gevernova.com/news/press-releases/ge-vernova-announces-more-160-million-investment-greenville-facility) |
| Howmet Aerospace Wichita Falls superalloy foundry expansion | Wichita Falls, TX | expansion |  |  | [link](https://www.industrialinfo.com/news/article/howmet-adds-capacity-as-gas-turbine-demand-skyrockets--364394) |
| GE Vernova Richmond gas turbine component repair and life extension | Richmond, VA | expansion | $17M |  | [link](https://www.gevernova.com/company/investing-in-manufacturing) |

## Transformers

Large power transformers weigh hundreds of tons and leave by rail; extra-high-voltage plants test units at up to 765 kV, so a 230 kV or higher line nearby is our proxy for test power.

**Checks**

- Land ≥40 acres (`acreage ≥ 40`, ours). Eaton's Jonesville transformer plant reuses an 861,000 sq ft building (about 20 acres of floor).
- Rail within 1 mi (`rail_mi ≤ 1`, ours).
- Line ≥230 kV within 5 mi (`transmission_230kv_mi ≤ 5`, ours).
- Outside flood zone (`in_sfha = false`, agency).

**What built plants show** (quotes are verbatim from the linked page)

- heavy haul: Large power transformers weighing about 208.8 tons (460,300 lb) each were discharged from a ship directly onto rail cars and moved by rail — "each 460,300 Lbs (abt 208,8 tons)" ([source](https://www.ajot.com/news/heavy-transformers-travel-through-usa))
- rail: Heavy transformers were delivered by rail to a siding about 20 miles short of the final site, with the last leg by road — "transported by rail to a rail siding 20 miles from the final destination" ([source](https://www.ajot.com/news/heavy-transformers-travel-through-usa))
- port: Heavy transformers arrived by ocean at a deep-water port before rail transport inland — "from the Port of Houston to North Liberty, Indiana" ([source](https://www.ajot.com/news/heavy-transformers-travel-through-usa))
- land: A new-build medium power transformer plant addition occupied a facility of about 144,000 sq ft adjacent to an existing plant — "a new 144,000 square foot facility adjacent to its existing plant" ([source](https://www.prolec.energy/news/prolec-ge-invests-an-additional-140-million-in-the-u-s-to-support-north-american-electric-grid-goals/))
- reuse: Eaton converted an existing 861,000 sq ft building into a three-phase transformer factory instead of building new — "The investment will include the acquisition and retrofit of an existing 861,000-square-foot facility" ([source](https://www.areadevelopment.com/newsItems/2-15-2025/eaton-jonesville-south-carolina.shtml))
- workforce: A transformer plant expansion of this scale adds about 330 production, maintenance, and engineering jobs — "will require the addition of more than 330 full-time production, maintenance, supervisory and engineering positions" ([source](https://www.prolec.energy/news/prolec-ge-invests-an-additional-140-million-in-the-u-s-to-support-north-american-electric-grid-goals/))
- other: Extra-high-voltage transformer plants add in-house 765 kV manufacturing and testing capability, which implies a dedicated test bay (test-bay power not stated) — "add manufacturing and testing capabilities for 765-kilovolt-class transformers" ([source](https://www.tdworld.com/substations/news/55362928/hd-hyundai-electric-expands-us-manufacturing-with-new-alabama-facility))
- land: Virginia Transformer's planned power transformer plant in Muscle Shoals, Alabama will be built on about 90 acres — "The plant will be built on about 90 acres within the Shoals Research Airpark." ([source](https://governor.alabama.gov/newsroom/2026/05/governor-ivey-announces-virginia-transformer-plant-will-bring-1100-jobs-to-northwest-alabama/))
- rail: The Virginia Transformer Alabama plant is served by a dedicated Norfolk Southern rail spur for shipping and supply chain needs — "The site's dedicated Norfolk Southern rail spur will guarantee Virginia Transformer's shipping and supply chain needs are met" ([source](https://governor.alabama.gov/newsroom/2026/05/governor-ivey-announces-virginia-transformer-plant-will-bring-1100-jobs-to-northwest-alabama/))
- rail: Hitachi Energy's South Boston, Virginia large transformer plant ships completed units by rail from the rear of the facility, so oversized equipment moves directly onto the rail network — "Completed units will ship by rail from the rear of the facility" ([source](https://www.enr.com/articles/63252-hitachi-breaks-ground-on-457m-va-large-power-transformer-plant-expansion))
- other: Hitachi Energy's South Boston transformer plant needs tall assembly bays and a 375-ton overhead crane (assembly bays over 120 ft; building height about 130 ft) — "assembly bays taller than 120 ft and an overall building height of about 130 ft to accommodate a 375-ton overhead crane" ([source](https://www.enr.com/articles/63252-hitachi-breaks-ground-on-457m-va-large-power-transformer-plant-expansion))
- other: Virginia Transformer's planned Muscle Shoals power transformer plant is a 600,000-square-foot building — "600,000-square-foot, state-of-the-art power transformer plant" ([source](https://governor.alabama.gov/newsroom/2026/05/governor-ivey-announces-virginia-transformer-plant-will-bring-1100-jobs-to-northwest-alabama/))
- workforce: Hitachi Energy's South Boston project came with county support: 10 acres committed for workforce housing and waived permit and utility connection fees — "The county also committed 10 acres for workforce housing and waived permit and utility connection fees." ([source](https://www.enr.com/articles/63252-hitachi-breaks-ground-on-457m-va-large-power-transformer-plant-expansion))

**Plants**

| Plant | Place | Status | Investment | Federal award | Source |
|---|---|---|---|---|---|
| HD Hyundai Electric Montgomery second U.S. transformer plant | Montgomery, AL | under construction | $200M |  | [link](https://www.tdworld.com/substations/news/55362928/hd-hyundai-electric-expands-us-manufacturing-with-new-alabama-facility) |
| Virginia Transformer Muscle Shoals power transformer plant (Shoals Research Airpark) | Muscle Shoals, AL | announced |  |  | [link](https://governor.alabama.gov/newsroom/2026/05/governor-ivey-announces-virginia-transformer-plant-will-bring-1100-jobs-to-northwest-alabama/) |
| Virginia Transformer Rincon, Georgia large power transformer expansion | Rincon, GA | under construction |  |  | [link](https://www.vatransformer.com/virginia-transformer-breaks-ground-on-georgia-transformer-expansion-in-rincon/) |
| Prolec GE Shreveport (Caddo Parish) transformer plant expansion | Shreveport, LA | expansion | $28M |  | [link](https://www.opportunitylouisiana.gov/news/prolec-ge-shreveport-facility-expansion-to-create-153-new-jobs) |
| WEG Transformers Washington, Missouri Specialty Transformer plant expansion | Washington, MO | expansion | $77M |  | [link](https://ded.mo.gov/press-room/weg-expand-washington-investing-77-million-and-creating-50-new-jobs) |
| Howard Industries Ellisville Technology Facility expansion (Jones County) | Ellisville, MS | expansion |  |  | [link](https://www.howard.com/INFO/news/2025/06/26/howard-industries-invests-over-230-million-to-expand-operations-across-mississippi.cfm) |
| Howard Industries Quitman Amorphous Facility expansion (Clarke County) | Quitman, MS | expansion |  |  | [link](https://www.howard.com/INFO/news/2025/06/26/howard-industries-invests-over-230-million-to-expand-operations-across-mississippi.cfm) |
| Pennsylvania Transformer Technology Raeford, North Carolina expansion | Raeford, NC | announced | $102M |  | [link](https://governor.nc.gov/news/press-releases/2025/02/17/governor-stein-announces-102-million-expansion-domestic-transformer-manufacturer-raeford) |
| Prolec GE Goldsboro transformer plant expansion | Goldsboro, NC | expansion | $140M |  | [link](https://www.prolec.energy/news/prolec-ge-invests-an-additional-140-million-in-the-u-s-to-support-north-american-electric-grid-goals/) |
| Siemens Energy large power transformer factory, Charlotte | Charlotte, NC | announced | $150M |  | [link](https://www.manufacturingdive.com/news/siemens-energy-large-power-transformer-facility-charlotte-north-carolina/708676/) |
| Cleveland-Cliffs Butler Works electrification project (induction reheat furnaces) | Lyndora, PA | expansion |  | DOE $75M | [link](https://www.wpxi.com/news/local/cleveland-cliffs-170m-butler-works-project-survives-federal-review-track-2028/XB6CCAI7ERHLFNBAF23OJJRVAE/) |
| Eaton Jonesville three-phase transformer factory | Jonesville, SC | announced | $340M |  | [link](https://www.areadevelopment.com/newsItems/2-15-2025/eaton-jonesville-south-carolina.shtml) |
| ERMCO Dyersburg transformer campus expansion | Dyersburg, TN | expansion | $70M |  | [link](https://www.ermco-eci.com/ermco-nine-millionth-transformer/) |
| Hitachi Energy Alamo transformer bushings (HVDC) expansion | Alamo, TN | expansion | $97M |  | [link](https://www.tn.gov/ecd/news/2025/8/20/hitachi-energy-to-expand-manufacturing-operations-in-crockett-county.html) |
| Hyosung HICO Memphis 765 kV transformer factory | Memphis, TN | announced | $157M |  | [link](https://www.actionnews5.com/2025/11/12/hyosung-hico-expands-again-bringing-240-new-jobs-memphis) |
| Hammond Power Solutions Fort Worth transformer facility (leased) | Fort Worth, TX | announced | $36M |  | [link](https://www.tdworld.com/utility-business/news/55407296/texas-bound-hammond-power-solutions-to-boost-us-footprint-with-new-fort-worth-facility-amid-rising-data-center-demand) |
| LS Electric Bastrop campus (technical center) | Bastrop, TX | operating |  |  | [link](https://www.bastropedc.org/media-center/news/p/item/62401/ls-electric-celebrates-grand-opening-of-bastrop-campus) |
| Hitachi Energy Bland transformer production and warehouse expansion | Bland, VA | expansion | $22M |  | [link](https://www.areadevelopment.com/newsItems/4-28-2025/hitachi-energy-bland-virginia.shtml) |
| Hitachi Energy South Boston large power transformer facility expansion | South Boston, VA | under construction | $457M |  | [link](https://www.wdbj7.com/2026/06/29/more-than-800-new-jobs-expected-with-building-south-boston-transformer-production-facility/) |
| JST Power Equipment Wytheville transformer plant | Wytheville, VA | operating |  |  | [link](https://transformer-technology.com/jst-power-equipment-opens-new-transformer-manufacturing-facility-in-virginia/) |
| SPX Transformer Solutions Waukesha plant expansion | Waukesha, WI | operating | $70M |  | [link](https://www.americanmachinist.com/shop-operations/article/21897645/spx-increases-large-transformer-manufacturing) |

## Critical minerals

Refining and separation plants need land for process and tailings areas, high power, process water, and rail for reagents and product.

**Checks**

- Land ≥100 acres (`acreage ≥ 100`, ours). Albemarle's Kings Mountain lithium site is 1,200 acres; a magnet plant (e-VAC Sumter) took 85.
- Rail within 1 mi (`rail_mi ≤ 1`, ours).
- Line ≥115 kV within 5 mi (`transmission_115kv_mi ≤ 5`, ours).
- Gaged river ≥100 cfs within 10 mi (`water_100cfs_gage_mi ≤ 10`, ours). Distance to a USGS gage on a river of that size, not a water right. No qualifying gage nearby is unknown, never a fail.
- Outside flood zone (`in_sfha = false`, agency).

**What built plants show** (quotes are verbatim from the linked page)

- land: MP Materials began building a 200,000 sq ft rare earth metal and magnet plant in Fort Worth in April 2022 — "began building the 200,000-SF plant" ([source](https://dallasinnovates.com/in-u-s-milestone-mp-materials-begins-producing-rare-earth-magnets-at-fort-worth-facility/))
- land: Novonix converted an existing former GE nuclear turbine manufacturing building in Chattanooga into its synthetic graphite plant (a retrofit rather than a greenfield build) — "a former GE nuclear turbine manufacturing facility" ([source](https://www.power-eng.com/energy-storage/batteries/in-win-for-battery-supply-chain-u-s-s-first-anode-plant-opens-in-tennessee/))
- other: Unresolved wastewater disposal permit issues were the main stated obstacle to Lynas's Texas rare earth processing plant, and the company warned that water treatment challenges could raise costs — "unresolved wastewater disposal permit issues" ([source](https://news.metal.com/newscontent/103646309-lynas-texas-rare-earth-plant-plan-stalled-over-wastewater-permit-issues))
- workforce: U.S. Antimony's $15 million Thompson Falls expansion is expected to add roughly 25 jobs in Sanders County — "add roughly 25 jobs to Sanders County" ([source](https://www.dailymontanan.com/?p=33119))
- power: The state announcement said Benson, NC met Vulcan Elements' need for scale, power, transportation systems and workforce; the page gives no megawatt figure — "Benson accommodated Vulcan's need for scale, power, transportation systems and workforce." ([source](https://researchtriangle.org/news/vulcan-elements-selects-johnston-county-for-1000-job-magnet-factory/))
- other: DOE's battery materials processing and manufacturing funding opportunity (DE-FOA-0003099) includes a Community Benefits Plan, and Amendment 000004 updated its page limit — "The purpose of this amendment is to update the page limit for the Community Benefits Plan." ([source](https://netl.doe.gov/node/13087))
- other: Cirba Solutions (Sept 2024) was selected to enter award negotiation with DOE for up to $200 million, so the funding was not final at selection — "selected to enter into award negotiation with the U.S. Department of Energy for up to $200 million" ([source](https://www.cirbasolutions.com/cirba-solutions-selected-for-200-million-award-negotiations-for-critical-materials-refining/))
- other: In October 2025 DOE cancelled more than $700 million in manufacturing and battery grants, saying the projects had missed milestones and were not economically viable — "These projects had missed milestones" ([source](https://www.utilitydive.com/news/department-energy-project-grants-cancelled-battery-manufacturing-trump/803347/))

**Plants**

| Plant | Place | Status | Investment | Federal award | Source |
|---|---|---|---|---|---|
| Princeton NuEnergy Commerce, Georgia facility | Commerce, GA | announced | $110M | DOE $50M | [link](https://wastedive.com/news/battery-recycling-500m-grant-funding-princeton-nuenergy-nth-cycle/828698) |
| Syrah Vidalia active anode material plant | Vidalia, LA | operating |  | DOE $220M | [link](https://www.mining-technology.com/news/syrah-begins-producing-active-anode) |
| ICL Specialty Products battery plant (St. Louis) | St. Louis, MO | cancelled |  | DOE $197M | [link](https://www.utilitydive.com/news/department-energy-project-grants-cancelled-battery-manufacturing-trump/803347/) |
| U.S. Antimony smelter, Thompson Falls (Sanders County) | Thompson Falls, MT | expansion | $15M |  | [link](https://www.dailymontanan.com/?p=33119) |
| Albemarle Kings Mountain lithium conversion facility and former mine | Kings Mountain, NC | operating |  | DOE $150M | [link](https://www.albemarle.com/us/en/news/kings-mountain-all-elements-lithium-ecosystem) |
| Vulcan Elements magnet plant, Benson (Johnston County) | Benson, NC | announced | $1.00B |  | [link](https://researchtriangle.org/news/vulcan-elements-selects-johnston-county-for-1000-job-magnet-factory/) |
| Blue Whale Materials Bartlesville lithium-ion battery recycling facility expansion | Bartlesville, OK | expansion |  | DOE $55M | [link](https://www.okcommerce.gov/blue-whale-materials-awarded-55-million-doe-grant-to-expand-bartlesville-ok-lithium-ion-battery-recycling-facility/) |
| Stardust Power lithium refinery, Southside Industrial Park | Muskogee, OK | under construction | $1.20B |  | [link](https://www.northernminer.com/news/stardust-power-breaks-ground-on-us1-2b-lithium-refinery-in-oklahoma/1003875050) |
| USA Rare Earth magnet and metal plant, Stillwater | Stillwater, OK | announced | $100M |  | [link](https://www.okcommerce.gov/governor-stitt-department-of-commerce-secure-first-domestic-rare-earth-metal-and-magnet-manufacturing-facility/) |
| Cirba Solutions lithium-ion processing facility (Columbia, SC) | Columbia, SC | announced |  | DOE $200M | [link](https://www.cirbasolutions.com/cirba-solutions-selected-for-200-million-award-negotiations-for-critical-materials-refining/) |
| e-VAC Magnetics magnet factory, Pocotaligo Industrial Park (Sumter County) | Sumter, SC | announced | $500M |  | [link](https://www.areadevelopment.com/newsItems/12-15-2023/e-vac-magnetics-sumter-south-carolina.shtml) |
| Novonix Riverside synthetic graphite plant, Chattanooga | Chattanooga, TN | operating | $20M | DOE $100M | [link](https://www.power-eng.com/energy-storage/batteries/in-win-for-battery-supply-chain-u-s-s-first-anode-plant-opens-in-tennessee/) |
| MP Materials Independence facility, Fort Worth | Fort Worth, TX | operating |  | IRS and U.S. Treasury Department $58M | [link](https://dallasinnovates.com/in-u-s-milestone-mp-materials-begins-producing-rare-earth-magnets-at-fort-worth-facility/) |
| Tesla lithium refinery, Robstown | Robstown, TX | operating |  |  | [link](https://www.industrialinfo.com/iirenergy/industry-news/article/tesla-starts-up-us-first-large-scale-lithium-refinery-in-texas--337356) |
