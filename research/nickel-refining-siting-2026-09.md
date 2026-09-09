# Nickel refining and smelting — siting requirements

Research pass 2026-09-08, for the Nickel Refining siting tab. Two WebSearch
passes plus a Sonnet research agent. Every figure below carries its source;
where sources disagree or a number could not be pinned down, that is stated
rather than smoothed over.

---

## 1. Only two process routes are screenable against a US brownfield

This is the single most important finding, and it narrows the whole exercise.

| Route | Feed | US brownfield fit |
|---|---|---|
| (a) Sulfide concentrate smelter (flash / electric furnace) | Domestic sulfide concentrate | **Out of scope.** No primary nickel smelter operates in the US. Needs a captive mine, a continuous 80–120 MW furnace load, and — because EPA never wrote a nickel-smelting NESHAP subpart — a case-by-case MACT determination. Pairs with a mine, not with a brownfield. |
| (b) Hydromet refinery on MHP / MSP / matte | Imported intermediate, by ship | **In scope. The primary case.** No roasting means no SO₂ source, so the permitting exposure of (a) mostly disappears. This is what Electra is pursuing. |
| (c) HPAL on laterite ore | Laterite ore at the mine | **Out of scope.** Laterite at 1–2% Ni is uneconomic to ship; HPAL is ore-proximate by construction and there is no US laterite resource at scale. Relevant only as the origin of the MHP that route (b) imports. |
| (d) RKEF / ferronickel / NPI | Laterite ore + coke | **Out of scope.** Produces stainless feedstock, not battery-grade nickel, and is a captive-generation model, not a grid-interconnection one — Indonesia built **10.4 GW of off-grid captive coal for RKEF alone** by 2023 ([Recourse](https://re-course.org/wp-content/uploads/2024/07/Recourse-Captive-coal-on-Obi-Island-2024-1.pdf)). |
| (e) Black-mass battery recycling to nickel sulfate | Domestic EOL batteries and scrap, by truck and rail | **In scope.** Chemically the same building block as (b) with recycled feed. No port dependency, smaller footprint, no roasting. |

So the tab screens for **(b) and (e)** — a hydrometallurgical plant — and says
plainly that a smelter is a different problem it does not screen for.

## 2. The two in-scope routes have opposite logistics, and that is the lens split

The two live US projects published divergent siting logic, which is what the
two scoring lenses encode:

* **Electra Battery Materials** narrowed to the southeastern US and named its
  criteria: **deep-water port** for globally sourced MHP/MSP feedstock,
  proximity to the southeastern battery-manufacturing corridor, logistics,
  and "workforce availability in established chemical processing and
  manufacturing regions"
  ([GlobeNewswire, 2026-06-08](https://www.globenewswire.com/news-release/2026/06/08/3307955/0/en/electra-advances-engineering-study-for-battery-grade-nickel-refinery-in-the-united-states.html);
  [Metal Tech News](https://www.metaltechnews.com/story/2026/06/10/tech-metals/electra-sizes-up-us-nickel-refinery/2792.html)).
  Target ~15,000 t/yr nickel sulfate and metal plus 1,000 t/yr cobalt.
* **Westwin Elements** built in landlocked Lawton, Oklahoma, on a **480-acre
  tract inside the OK SW Rail Industrial Park** — rail-fed, not port-fed,
  because its feed is domestic ore and recycled batteries. Pilot at 200 t/yr,
  targeting 34,000 t/yr by 2030
  ([Lawton EDC](https://lawtonedc.com/news/article/westwin-elements-breaks-ground-on-americas-only-critical-mineralspilot-plant);
  [S&P Global](https://www.spglobal.com/market-intelligence/en/news-insights/articles/2025/5/us-nickel-refinery-can-compete-with-chinese-operators-westwin-elements-ceo-88877906)).

A site with neither deep-water port nor rail serves neither route.

## 3. Brownfield siting is being used deliberately as permitting acceleration

Talon Metals moved its processing facility off the Minnesota mine site to
**Beulah, North Dakota — a former Westmoreland coal mine** — explicitly to
shrink the scope of environmental review at the mine, "allowing focus on
underground mining and rail operations only" ([SME Mining
Engineering](https://me.smenet.org/talon-plans-433-million-processing-facility-in-north-dakota/)).
$433M facility, 150 jobs, $114.8M DOE BIL grant. As of July 2026 Talon was
reported to be weighing the North Dakota site against a Michigan alternative
at Humboldt Mill ([KFGO,
2026-07-28](https://kfgo.com/2026/07/28/plans-for-north-dakota-nickel-processing-unclear-as-company-also-evaluates-michigan-site-2/)).

That is this dashboard's whole thesis stated by an operator, and it is why
Michigan is a live question rather than a hypothetical one.

## 4. Numbers worth screening against

**Footprint.** Vale's Long Harbour, Newfoundland — the closest real comparable
to a US matte/MHP-fed refinery — is 65 ha of hydromet plant plus 85 ha of
pipelines and residue ponds, about **370 acres**, with the plant itself roughly
1 km × 750 m ([Government of NL](https://www.gov.nl.ca/eccc/projects/project-1243/)).
Westwin's Lawton tract is 480 acres. A black-mass recycling plant alone is
smaller, but no clean benchmark was found. **Screening threshold: 300 acres
for a full refinery, with 100 acres as a floor for a recycling-only plant.**

**Power.** Hydromet is a large but interruptible load — autoclave agitators,
oxygen plant, SX pumps, EW rectifiers — not the frozen-furnace failure mode of
a smelter. General industrial interconnection practice puts a 50–100 MW
continuous load at 69–138 kV service
([FirstEnergy transmission requirements](https://www.firstenergycorp.com/content/dam/feconnect/files/wholesale/Requirements-for-Transmission-Connected-Facilities.pdf)).
No nickel-specific voltage citation was found, and **no source gave an actual
MW figure for Long Harbour or either proposed US refinery** — those will appear
in interconnection filings once made. Treated as moderate confidence.

**Water.** Quantitative demand in gpm or m³/t Ni **could not be resolved** from
public literature; the papers return leach chemistry, not water balances. What
is established is the regulatory side: nickel's human-health water-quality
criterion is **25 µg/L**, stricter than the aquatic-life criterion, so a
metals-bearing effluent stream means an individual NPDES permit and, if
surface water is used for cooling, Clean Water Act §316(b) intake
requirements. Ambatovy's design pumps ore 220 km as a slurry, which is water
demand before any process use ([gem.wiki](https://www.gem.wiki/Ambatovy_Nickel_power_station)).

**Reagents and inbound tonnage.** Sulfuric acid consumption per tonne of
nickel is the biggest numeric uncertainty in this pass: sources give
150–300 kg acid/t Ni in one synthesis and ~12 t of sulfur/t Ni in another —
a disagreement of roughly 10×, probably reflecting different scope (leach-stage
acid vs. total plant acid including neutralization). Large hydromet sites
usually build an **on-site sulfur-burning acid plant**, which doubles as the
SO₂ control device and recovers process steam
([Worley-Chemetics, ALTA 2024](https://d3e2i5nuh73s15.cloudfront.net/wp-content/uploads/2024/04/ALTA-2024-NCC-Paper-Worley-Chemetics.pdf)).
Merchant acid moves by rail tank car (50-ton and 100-ton classes,
~13,900–15,200 gal) in unit trains of 36–56 cars. Ambatovy imports **~2.5 Mt/yr
of limestone, coal, sulfur and ammonia — about 9× its finished-product export
tonnage** ([Ambatovy](https://ambatovy.com/en/operations/operations-components/)).
Inbound bulk logistics, not outbound product, sizes the transport requirement.

**Workforce.** Long Harbour runs **475 permanent positions** at 50,000 t Ni/yr
(3,200–6,000 at construction peak). Talon's Beulah plant plans 150. Talon's
Michigan operations carry a United Steelworkers neutrality agreement — these
are unionized craft-trade employers. Electra screens for regions with an
existing chemical-plant labor pool rather than planning to train from scratch.

## 5. What disqualifies a site

Weaker evidence than the technical sections — mostly inferred from what
successful projects screened *for*:

* No firm high-voltage service and no captive-generation option. Disqualifying
  for smelter-class loads; probably not for the batch-tolerant hydromet load.
* Neither deep-water port nor rail. Serves neither feed model.
* No chemical or metallurgical labor pool within commuting range.
* Mapped floodway. Any development requires a hydraulic no-rise analysis first.
* Community opposition surfacing late. A nickel refinery proposed at Richmond
  Hill, Georgia is a live contested case
  ([Bryan County News](https://www.bryancountynews.com/news/potential-nickel-refinery-in-richmond-hill-draws-support-criticism/)).

Seismic could not be tied to any documented nickel siting failure and is left
unscored.

## 6. The caveat that belongs on the tab

BHP mothballed its entire Western Australia Nickel West chain in 2024 — the
Kalgoorlie smelter after 51 years, the Kwinana refinery, and the Mt Keith and
Leinster mines — because Indonesian oversupply collapsed the nickel price, not
because of anything about the sites
([ABC](https://www.abc.net.au/news/2024-10-06/closure-of-bhp-kalgoorlie-nickel-smelter-after-51-years/104307662)).
A siting score measures whether a place could host a plant. It says nothing
about whether the plant should be built at the prevailing nickel price, and the
tab should say so.

## 7. Unresolved, for a later pass

1. Sulfuric acid per tonne of nickel — reconcile the ~10× disagreement against
   a primary mass balance.
2. Water demand in gpm or m³/t Ni — needs an actual permit application
   (Westwin's or Electra's, once public), not process literature.
3. Interconnection MW for Long Harbour, Electra, or Westwin.
