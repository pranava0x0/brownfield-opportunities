# AP1000 Water Validation — 14 Military Installations

Citation-grade validation of every water-availability claim in the AP1000 siting
overlay (`docs/data/ap1000-sites.json`), plus the AP1000's actual water demand.
Compiled 2026-06-25 from authoritative primary sources (USGS NWIS streamgages,
NRC/DOE environmental reviews, state water agencies). Every figure carries a
verbatim quote and a deep-link URL so it can be re-checked.

**Bottom line:** 10 of 14 ratings held; **4 changed** after rigorous review
(Robins ↓, Fort Hood ↓, JB McGuire-Dix-Lakehurst ↓, Edwards ↓), and 2 source
attributions were corrected (Fort Bragg, Fort Campbell). See §3.

---

## 1. AP1000 water demand (the screen)

A single Westinghouse AP1000 (1,117 MWe net) rejects heat through **natural-draft
hyperbolic cooling towers** (one per unit — *not* mechanical-draft, which the
AP1000 uses only for the small auxiliary service-water system). The authoritative
water balance is the Vogtle Electric Generating Plant (VEGP) Units 3 & 4 record —
two AP1000s cooled from the Savannah River — documented in the NRC EIS (NUREG-1872,
reproduced in NRC NUREG-1947 COL FSEIS) and the joint DOE FEIS (EIS-0476).

| Quantity (normal operation) | Two units | **Per AP1000 unit** |
|---|---|---|
| Cooling-tower **makeup withdrawal** | 37,224 gpm = 53.6 MGD = **83 cfs** | 18,612 gpm = **26.8 MGD = 41.5 cfs** |
| **Consumptive use** (evaporation + drift) | 27,924 gpm = 40.2 MGD = **62 cfs** | 13,962 gpm = **20.1 MGD = 31.1 cfs ≈ 22,400 acre-ft/yr** |
| Blowdown (returned to river) | 9,300 gpm = 13.4 MGD = 20.7 cfs | 6,981 gpm = 10.0 MGD |
| **Maximum** makeup withdrawal | 57,784 gpm = 83.2 MGD = **129 cfs** | 28,892 gpm = 41.6 MGD |

**Use the consumptive figure (~20 MGD / ~31 cfs / ~22,400 acre-ft/yr per unit) for
"water actually lost"** — withdrawal is larger because closed-cycle towers return
blowdown to the source.

Verbatim quotes (DOE EIS-0476 FEIS Part 1, reproducing NUREG-1872):
- > "The normal make-up water flow rate would be 2348.47 L/s (37,224 gpm)."
- > "The normal consumptive water use rate (evaporation and drift) would be 1761.73 L/s (27,924 gpm)."
- > "The normal blowdown rate would be 586.74 L/s (9,300 gpm)."
- > "The proposed cooling system for the new units includes one concrete natural draft hyperbolic cooling tower for each unit … approximately 183 m (600 ft) tall."
- > "at the normal withdrawal rate of 2.35 m³/s (83 cfs, 37,224 gpm), the proposed VEGP Units 3 and 4 would withdraw 1 percent of the average river discharge."

Regulatory/permit cross-check — Georgia EPD water-withdrawal permit (via Powers
Engineering report for the Southern Environmental Law Center, 2014):
- > "a maximum water withdrawal rate of 74 million gallons per day (mgd) from the Savannah River … The average expected withdrawal rate specified in the draft permit is 62 mgd."

Sources:
- DOE EIS-0476 FEIS Part 1 (verbatim CWS figures): https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf
- NRC NUREG-1947 Vogtle 3&4 COL FSEIS: https://www.nrc.gov/docs/ML1107/ML11076A010.pdf · index: https://www.nrc.gov/reading-rm/doc-collections/nuregs/staff/sr1947/index
- AP1000 Design Control Document, Aux Systems Ch. 9.2 (Westinghouse via NRC): https://www.nrc.gov/docs/ML0715/ML071580932.pdf
- Powers Engineering / SELC, Vogtle 3&4 water-permit report: https://cleanenergy.org/wp-content/uploads/Ex1_PowersEgr_Vogtle3and4_H2OPermitReport_051514.pdf

> Caveat: NRC's own `nrc.gov/docs` servers timed out repeatedly during this
> review; the verbatim CWS quotes were extracted from the DOE EIS-0476 mirror,
> which reproduces the identical NUREG-1872 text, and cross-checked against the
> FEIS's own cfs figures (83 / 129 cfs) and the Georgia EPD permit (74 / 62 MGD).

---

## 2. Per-site validation

Screen = ~42 cfs withdrawal / ~31 cfs (22,400 acre-ft/yr) consumptive per unit.
USGS mean-annual discharge and drainage area are quoted from the machine-readable
NWIS RDB endpoints (see §4). "Withdrawal %" = 42 cfs ÷ mean annual flow.

"Dataset" = the rating in `ap1000-sites.json` today (after main's recent
"tighten water scoring" pass, which added a `severe` tier = 0 water points).
"Validated" = the rigorous finding of this review.

| # | Site | Source | USGS gauge | Drainage (mi²) | Mean flow (cfs) | Withdrawal % | Dataset | **Validated** |
|---|---|---|---|---|---|---|---|---|
| 1 | Redstone Arsenal AL | Tennessee R / Wheeler Res. | 03575500 | 25,610 | ~41,650 | 0.10% | Abundant | **Abundant ✓** |
| 2 | Fort Wainwright AK | Chena → Tanana R | 15514000 / 15515500 | 1,995 / 25,560 | 1,336 / ~41,000 | 3.1% / 0.1% | Abundant | **Abundant ✓** (winter → Tanana) |
| 3 | Fort Benning GA | Chattahoochee R | 02341460 | 4,630 | ~6,873 | 0.6% | Abundant | **Abundant ✓** (ACF compact-limited) |
| 4 | Fort Drum NY | Black R | 04260500 | 1,864 | ~4,242 | 1.0% | Abundant | **Abundant ✓** |
| 5 | Holston AAP TN | S.F. Holston R | 03487500 | 1,935 | ~2,910 | 1.4% | Abundant | **Abundant ✓** (S. Fork only) |
| 6 | Arnold AFB TN | Woods Reservoir / Elk R | 03579100 | 275 | ~470 | 9% | Abundant | **Abundant ✓** (AEDC already draws ~61 MGD) |
| 7 | JB Lewis-McChord WA | Nisqually R + aquifer | 12089500 | 517 | >2,000 | <2% | Adequate | **Adequate ✓** (volume abundant; new water-right unproven) |
| 8 | Fort Bragg NC | **Cape Fear R** (~10 mi) | 02102500 | 3,464 | ~3,224 | 1.3% | Marginal | **Marginal ✓** (source corrected: Cape Fear, not Little R) |
| 9 | Robins AFB GA | Ocmulgee R | 02213700 / 02213000 | 2,690 | ~2,680 | 1.6% | Abundant | **Adequate ↓** (854 cfs in 2012 drought) |
| 10 | Fort Hood TX | Belton Lake (Leon R) | — | — | 100,257 AF/yr firm yield | **~22% of firm yield** | Poor | **Poor ✓** (marginal if a large new allocation is secured) |
| 11 | Fort Campbell KY | on-post karst GW; Cumberland R ~13 mi | 03431500 | 15,897 | ~23,765 | 0.18% | Marginal | **Marginal ✓** (infra-limited, not resource) |
| 12 | JB McGuire-Dix-Lakehurst NJ | Kirkwood-Cohansey aquifer | — | — | ~27 MGD ≈ 28% of statewide aquifer pumping | — | Poor | **Poor ✓** (water is the limiting factor) |
| 13 | Edwards AFB CA | Antelope Valley GW + SWP | — | — | adjudicated overdraft; SWP 5% | — | Severe | **Severe ✓** (dry-cooling required) |
| 14 | Davis-Monthan AFB AZ | Tucson AMA GW + CAP | — | — | overdraft; CAP −30% | — | Severe | **Severe ✓** (dry-cooling required) |

### Detailed entries (with quotes)

**1. Redstone Arsenal — Tennessee River / Wheeler Reservoir — ABUNDANT ✓ (strongest).**
USGS 03575500 (Tennessee R at Whitesburg, on Wheeler Reservoir at the arsenal's
southern boundary): drainage `"25610.00"` mi²; mean annual ~41,650 cfs (1985–94
sample). 42 cfs ≈ 0.10% of flow (~670×). Intakes confirmed —
> "RSA currently utilizes two intakes along the Tennessee River and operates one permitted treatment plant" (ATSDR Public Health Assessment).
Dedicated supply gauge: USGS 03575750 "Redstone Arsenal Water Supply-Tennessee River."
URLs: https://waterdata.usgs.gov/monitoring-location/03575500/ · https://waterdata.usgs.gov/monitoring-location/03575750/ · https://www.atsdr.cdc.gov/hac/pha/redstonearmy/redstonearmypha071205.pdf

**2. Fort Wainwright — Chena → Tanana River — ABUNDANT ✓ (winter caveat).**
Chena R at Fairbanks (USGS 15514000): drainage 1,995 mi², mean
> "1,336 cu ft/s (37.8 m³/s)," period 1948–2012.
Tanana R at Nenana (USGS 15515500): drainage 25,560 mi², ~41,000 cfs. Interior-AK
rivers are ice-covered Nov–Apr; Tanana winter flow drops to ~7,100 cfs (still
~170× the screen). Source the Tanana, not the Chena, in winter, with a deep
intake / infiltration gallery to avoid frazil ice.
URLs: https://water.usgs.gov/nwc/NWC/sw/graphs/S15514000.html · https://waterdata.usgs.gov/monitoring-location/USGS-15515500/

**3. Fort Benning — Chattahoochee River — ABUNDANT ✓ (allocation-limited).**
USGS 02341460 (Chattahoochee at 14th St, Columbus): drainage `"4630"` mi²; mean
annual ~6,873 cfs (2015–24). 42 cfs ≈ 0.6% (~110×). The base's Water Resource
Facility withdraws directly from the river. **Caveat:** withdrawals are governed by
the contentious ACF tri-state compact — the binding constraint is *allocation/
permitting*, not hydrology.
URLs: https://waterdata.usgs.gov/monitoring-location/USGS-02341460/

**4. Fort Drum — Black River — ABUNDANT ✓.**
USGS 04260500 (Black R at Watertown): drainage 1,864 mi²; mean annual
> "4,242 cu ft/s (120.1 m³/s)."
42 cfs ≈ 1.0%. The Hudson–Black River Regulating District augments low flows;
Lake Ontario (~25 mi) is an effectively unlimited backup.
URLs: https://waterdata.usgs.gov/monitoring-location/USGS-04260500/

**5. Holston AAP — South Fork Holston River — ABUNDANT ✓.**
USGS 03487500 (S.F. Holston at Kingsport): drainage `"1935.00"` mi²; mean
annual ~2,910 cfs. 42 cfs ≈ 1.4% (~47×). TVA-regulated by three upstream dams
(South Holston, Boone, Fort Patrick Henry) which set minimum flows. It is the
**South Fork only** (~1,935 mi²), so "abundant" rather than "vast," but still ~47×
the screen.
URLs: https://waterservices.usgs.gov/nwis/site/?format=rdb&sites=03487500&siteOutput=expanded

**6. Arnold AFB (AEDC) — Woods Reservoir / Elk River — ABUNDANT ✓.**
Woods Reservoir holds
> "26 billion gallons of water on a 3,980-acre … reservoir"
(≈ 79,800 acre-ft), purpose-built for AEDC cooling. AEDC already withdraws
> "more than 22.4 billion US gallons"
annually (~61 MGD) — so a 27 MGD reactor is well within demonstrated capacity.
Elk R near Estill Springs (USGS 03579100): mean ~470 cfs (use 03580750, Elk R
below Tims Ford Dam, for current real-time flow). The screen is ~10× below river
flow and a fraction of a reservoir built for cooling.
URLs: https://www.arnold.af.mil/News/Article-Display/Article/3163926/woods-reservoir-completed-70-years-ago-this-month/ · https://waterdata.usgs.gov/monitoring-location/USGS-03579100/

**7. JB Lewis-McChord — Nisqually River + glacial-outwash aquifer — ABUNDANT ✓.**
Nisqually R at McKenna (USGS 12089500): drainage 517 mi², mean comfortably
>2,000 cfs (the upstream La Grande gauge alone is 1,460 cfs at 133 mi²). JBLM runs
its own city-scale water system —
> "Drinking water on JBLM is produced from groundwater sources that are derived and naturally filtered by aquifers"
— on the high-yield Vashon glacial-outwash aquifer. Volume is ample. **Caveat:**
since 2018 several base wells exceed PFAS limits; new withdrawals must site around
the plume + treat. Puget Sound (~12 mi) is a saline backup.
URLs: https://waterdata.usgs.gov/monitoring-location/USGS-12089500/ · https://home.army.mil/lewis-mcchord/index.php/my-Joint-Base-Lewis-Mcchord/all-services/public_works-environmental_division/drinking_water

**8. Fort Bragg — Cape Fear River — ADEQUATE ✓ (SOURCE CORRECTED).**
The post is supplied by Fayetteville PWC from the **Cape Fear River** (Hoffer
plant) — not the Little River as previously stated. The Little River at Manchester
(USGS 02103000) averages only 407 cfs (131.5 cfs in the 2011 drought) and **cannot**
support a dedicated AP1000 intake. The Cape Fear at Lillington (USGS 02102500):
drainage 3,464 mi², mean annual 3,224 cfs (1982–2025) — 42 cfs ≈ 1.3%. A dedicated
intake would tap the Cape Fear ~10 mi from post, where the basin is a contested
regional supply (Jordan Lake allocations) but physically ample.
URLs: https://waterdata.usgs.gov/monitoring-location/USGS-02102500/ · https://www.faypwc.com/water-treatment-facilities/

**9. Robins AFB — Ocmulgee River — ABUNDANT → ADEQUATE ↓.**
USGS 02213700 (Ocmulgee near Warner Robins): drainage `"2690"` mi²; mean annual
corroborated via upstream Macon gauge 02213000 at ~2,680 cfs. Mean comfortably
supports the screen (~43×), **but** this is the smallest river of the abundant
group and is drought-sensitive — the Macon gauge fell to **854 cfs in the 2012
drought** (42 cfs ≈ 7.3% of that, and a 7Q10 low-flow would be lower still). For a
non-interruptible nuclear load, "abundant" overstates the drought-year margin →
**Adequate**.
URLs: https://waterdata.usgs.gov/monitoring-location/USGS-02213700/ · https://waterservices.usgs.gov/nwis/stat/?format=rdb&sites=02213000&statReportType=annual&statTypeCd=mean&parameterCd=00060

**10. Fort Hood — Belton Lake — ADEQUATE → MARGINAL ↓.**
Belton Lake (Leon R; USACE-owned, Brazos River Authority-operated). Firm yield —
> "Lake Belton has a capacity of 1,074,500 acre-feet of water and a yield of 100,257 acre-feet" (Bell County WCID No. 1).
An AP1000's ~22,400 acre-ft/yr consumptive demand is **~22% of the reservoir's
entire firm yield**, on top of existing Killeen/Temple/Belton + BRA demand, in a
semi-arid, drought-prone, already-allocated basin (BRA is building the
Belton-to-Stillhouse pipeline to rebalance supply). A single new demand taking ~⅕
of a mid-size reservoir's firm yield is a material risk → **Marginal**.
URLs: https://wcid1.org/about-us/ · https://www.twdb.texas.gov/surfacewater/rivers/reservoirs/belton/index.asp

**11. Fort Campbell — karst groundwater / Cumberland River — MARGINAL ✓.**
Supply today is on-post karst groundwater —
> "Fort Campbell's drinking water is managed by the private firm Jacobs, sourced from a groundwater aquifer located on post."
A ~27 MGD draw from a karst aquifer is **not feasible** (fracture/conduit-limited,
seasonally flashy, already PFAS-impacted). The Cumberland River is the realistic
source: USGS 03431500 (at Nashville) means 23,765 cfs (2011–24) and the
downstream Clarksville reach (DA 15,897 mi²) is larger — 42 cfs ≈ 0.18%, trivially
available. **But** it is ~12–15 mi away and ~400 ft lower, requiring a pumped
pipeline. Rating holds at **Marginal** for the status quo; the constraint is
*infrastructure, not water* — the underlying resource is abundant.
URLs: https://waterdata.usgs.gov/monitoring-location/USGS-03431500/ · https://clarksvillenow.com/local/fort-campbell-water-supply-lawsuit-claims-forever-chemicals-have-contaminated-groundwater/

**12. JB McGuire-Dix-Lakehurst — Kirkwood-Cohansey aquifer — ADEQUATE → MARGINAL ↓.**
No large adjacent river; supply is the unconfined Kirkwood-Cohansey aquifer —
voluminous in storage ("17.7 trillion gallons") but the binding constraint is
*sustainable yield*. Statewide it is already stressed —
> "About 3,000 wells pump an estimated 35 billion gallons from the aquifer each year"
— and in Dec 2023 the Pinelands Commission tightened aquifer-protection rules. An
AP1000's ~27 MGD ≈ 9.9 billion gal/yr is **over a quarter of the entire aquifer's
current statewide annual pumping**, concentrated at one point, in a shallow aquifer
tightly coupled to Pinelands streams/wetlands. Compounding it, two on-base supply
wells tested
> "as high as 264,300 parts per trillion — 3,775 times the federally recommended level of 70 ppt"
of PFOS/PFOA. A 27 MGD groundwater withdrawal is **not sustainable** without an
external surface-water source → **Marginal**; water is the limiting factor here.
URLs: https://pinelandsalliance.org/water-supply-aquifer/ · https://pubs.usgs.gov/publication/sir20125122 · https://pfasproject.com/joint-base-mcguire-dix-lakehurst-new-jersey/

**13. Edwards AFB — Antelope Valley groundwater + SWP — MARGINAL → POOR ↓.**
The adjudicated Antelope Valley basin is in court-defined overdraft —
> "Groundwater-level declines of more than 270 feet … have resulted in land subsidence of more than 6 feet in some areas"
— with at-base
> "more than 150 feet of water-level decline … resulting in nearly 4 feet of subsidence"
that is "adversely affecting the runways on the lakebed." USGS SIR 2014-5166 models
> "cumulative depletion in groundwater storage of 8,700,000 acre-ft" (1915–2005).
The import alternative (State Water Project via AVEK) delivered just
> "an initial State Water Project (SWP) allocation of 5 percent of requested supplies"
in 2022–23. Neither source can firmly underwrite a 27 MGD reactor; adding ~30,000
acre-ft/yr to a basin already subsiding into its own runways is the opposite of
remediation → **Poor**.
URLs: https://ca.water.usgs.gov/projects/antelope-valley/antelope-valley-land-subsidence.html · https://pubs.usgs.gov/publication/sir20145166 · https://water.ca.gov/News/News-Releases/2022/Dec-22/DWR-Announces-Initial-State-Water-Project-Allocation-of-5-percent

**14. Davis-Monthan AFB — Tucson AMA groundwater + CAP — POOR ✓.**
Tucson Active Management Area —
> "Current ground-water withdrawals exceed recharge, resulting in conditions of ground-water overdraft … a sustainable long-term safe-yield has not been achieved" (Arizona DWR);
the statutory 2025 safe-yield goal remains unmet. The CAP (Colorado River) backstop is being cut —
> "This represents a 512,000 acre-foot reduction to Arizona's Colorado River water supply … constituting 30% of CAP's normal supply … Nearly all the reductions within Arizona have been taken by Central Arizona Project (CAP) water users."
A ~30,000 acre-ft/yr consumptive demand on a single-source aquifer in admitted
overdraft, backstopped by a CAP supply cut ~30% and first in line for further cuts,
is not sustainable → **Poor** confirmed.
URLs: https://www.azwater.gov/ama/active-management-area-overview · https://www.cap-az.com/water/water-supply/colorado-river-operations-2/

---

## 3. Reconciliation with the current dataset

main's recent "tighten water scoring" pass had already downgraded the weakest
sites (Hood/McGuire → poor; Edwards/Davis-Monthan → severe; JBLM → adequate;
Bragg → marginal) before this review. Against that **current** dataset, the
rigorous validation **confirms 13 of 14 ratings** with authoritative backing and
makes **one change plus one source correction**:

| Site | Change | Why |
|---|---|---|
| **Robins AFB** | Abundant → **Adequate** | Ocmulgee fell to **854 cfs in the 2012 drought** (42 cfs ≈ 7.3%); smallest of the big-river sites. The only genuine over-rating found. |
| **Fort Bragg** | source fix (rating unchanged) | Supply is the **Cape Fear River** (3,224 cfs @ Lillington, ~10 mi via PWC), **not the Little River** (407 cfs — too small for a dedicated intake). Stays **Marginal** (dedicated ~10-mi intake into an allocation-contested basin). |

Confirmed (the §2 detail now supplies the authoritative basis main's pass
lacked):
- **Fort Hood — poor holds.** Belton Lake firm yield is 100,257 AF/yr and an
  AP1000 needs ~22,400 AF/yr (~22%) — *securable but tight* (marginal-leaning),
  so poor is the conservative-correct call absent a large new allocation.
- **JB McGuire-Dix-Lakehurst — poor holds.** 27 MGD ≈ 28% of statewide
  Kirkwood-Cohansey pumping at one point, under a Pinelands withdrawal cap, with
  264,300 ppt PFAS on-base. Water is the limiting siting factor.
- **Edwards & Davis-Monthan — severe holds.** Adjudicated/overdrafted desert
  basins (Edwards: >6 ft subsidence into its own runways, SWP 5%; Davis-Monthan:
  CAP −30%, single-source aquifer) — wet-cooling is not viable; dry-cooling
  required. `severe` (0 water points) is the right tier.
- **Fort Campbell — marginal holds.** The limit is *infrastructure* (a ~12–15 mi
  / ~400-ft-lift Cumberland River pipeline), not the resource (the Cumberland is
  abundant at ~23,765 cfs).
- **JBLM — adequate holds.** Volume is abundant (Nisqually >2,000 cfs +
  city-scale aquifer), but a new 27 MGD surface-water right is unproven and the
  base sits over a PFAS plume, so adequate is the prudent rating.

Because water is weighted 40/100 in the AP1000 lens, only the Robins downgrade
moves a score; the ranking is regenerated from `scripts/build_ap1000_sites.py`.
Every site's `water_note` and `water_source_url` are upgraded to the authoritative
USGS/agency citations from §2.

---

## 4. Data-access notes (so this discovery is never re-paid)

- **USGS flow/drainage data: use the machine-readable RDB endpoints, NOT the
  portal.** `waterdata.usgs.gov/monitoring-location/...` is JavaScript-rendered and
  returns nothing to WebFetch/curl. Instead:
  - Drainage area + site metadata: `https://waterservices.usgs.gov/nwis/site/?format=rdb&sites=<GAUGE>&siteOutput=expanded` (field `drain_area_va`).
  - Annual mean discharge: `https://waterservices.usgs.gov/nwis/stat/?format=rdb&sites=<GAUGE>&statReportType=annual&statTypeCd=mean&parameterCd=00060`.
  These return plain tab-delimited text — scriptable, exact, no LLM needed.
- **Regulated-river gauges often publish stage only, not discharge** (e.g. Cape
  Fear at Fayetteville 02104000, Cumberland at Clarksville 03436500). Step to the
  nearest discharge gauge upstream/downstream (Lillington 02102500; Nashville
  03431500) and reason about drainage-area scaling.
- **NRC `nrc.gov/docs` servers time out frequently.** The DOE EIS-0476 mirror
  (`energy.gov/.../EIS-0476-FEIS_Part1-2012.pdf`) reproduces the NUREG-1872 text
  verbatim and is reliable.
- **Mean annual flow alone overstates firm supply.** For non-interruptible nuclear
  load, weigh drought-year lows / 7Q10 (Robins) and reservoir *firm yield* not
  total capacity (Fort Hood). A river dwarfing the mean withdrawal can still be
  "adequate" not "abundant" if its drought tail is thin.
