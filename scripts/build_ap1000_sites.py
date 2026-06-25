#!/usr/bin/env python3
"""Build docs/data/ap1000-sites.json — a curated AP1000 reactor-siting overlay.

This is a hand-curated analysis overlay (like reference-campuses.json /
retired-industrial.json), NOT a connector / SiteRecord set, so it stays out of
schema.py and refresh.py. It screens 14 named U.S. military installations for
siting a Westinghouse AP1000 (1,117 MWe net, ~3,400 MWth). Developable acreage
is retained as an eligibility threshold / context field, while the requested
ranking differentiates sites by cooling water; electrical infrastructure
(transmission + substation); construction workforce; and fiber.

Provenance, by field:
  • lat/lon + transmission_* + substation_* + gas/rail/highway + power_plant_*:
    REAL, joined from docs/data/infra-proximity.json (the project's own
    spatial-index computation) by `infra_source_id` — the best whole-installation
    record in the dataset, or an on-base proxy (Fort Benning uses Lawson AAF).
  • retired_plant_*: REAL, from EIA Form EIA-860M April 2026 ("Retired" sheet),
    computed by this script at build time by finding the nearest ≥100 MW
    dispatchable plant within RETIRED_PLANT_RADIUS_MI for each installation's
    lat/lon. Same source as the eia-retired-plants connector.
  • installation_acreage + developable_acreage + water_* + fiber: ANALYST-
    researched from public sources (cited in *_source / *_note). These are NOT
    federal GIS layers — the project has no water or fiber layer — so they are
    explicitly flagged as analyst assessment in the UI.
  • seismic_flag / flood_flag: informational only; NOT part of the score.
    Nuclear-relevant, so shown.

AP1000 cooling context (one unit, closed-cycle natural-draft tower; per the
Vogtle 3&4 NRC EIS / DOE EIS-0476): ~26.8 MGD withdrawal / ~20.1 MGD consumptive
(~22,400 acre-ft/yr) — a binding constraint, hence water is the highest-weighted
factor in docs/ap1000-score.js. See ap1000-water-validation.md for the
citation-grade per-site validation (USGS gauges, quotes) and the AP1000 demand
derivation.

Run:  python3 scripts/build_ap1000_sites.py
"""
import hashlib
import io
import json
import math
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "docs" / "data"
INFRA_PATH = DATA / "infra-proximity.json"
OUT_PATH = DATA / "ap1000-sites.json"

# ---- EIA-860M retired plant enrichment ------------------------------------
# Same source and column schema as connectors/eia_retired_plants.py.
# April 2026 is now in the archive; use that stable URL so the data matches
# what the eia-retired-plants connector last pulled.
EIA_860M_URL = (
    "https://www.eia.gov/electricity/data/eia860m/archive/xls/april_generator2026.xlsx"
)
_EIA_CACHE_KEY = "ap1000_eia_860m_apr2026"
_EIA_CACHE_HASH = hashlib.sha256(_EIA_CACHE_KEY.encode()).hexdigest()[:16]
_EIA_CACHE_FILENAME = f"{_EIA_CACHE_HASH}.bin"

# Search within 25 mi — wider than the connector's 5 mi so we surface context
# for "nearby but not on-site" retired plants useful for nuclear siting.
RETIRED_PLANT_RADIUS_MI = 25.0
MIN_PLANT_MW = 100.0

# Dispatchable EIA fuel codes that imply stranded grid infrastructure.
_DISPATCHABLE = frozenset({
    "BIT", "SUB", "LIG", "NG", "DFO", "RFO", "JF", "KER",
    "NUC", "PC", "RC", "SC", "WC", "SGC", "OIL",
})

# EIA-860M Retired sheet column indices (0-based); rows[3:] = data.
_COL_PLANT_ID   = 2
_COL_PLANT_NAME = 3
_COL_MW         = 13
_COL_FUEL       = 16
_COL_RET_YEAR   = 21
_COL_LAT        = 24
_COL_LON        = 25

# Generated date is fixed (not Date.now) — this is a static, hand-curated
# overlay; bump it by hand when the curated research is refreshed.
GENERATED_AT = "2026-06-24"
AP1000_SOURCE = "https://westinghousenuclear.com/new-plants/ap1000-pwr/overview/"
VOGTLE_WORKFORCE_SOURCE = "https://www.energy.gov/ne/articles/5-things-you-should-know-about-plant-vogtle"

# Army "Janus Program" microreactor shortlist (announced Nov 2025). 9 of these
# 14 are on it — a documented nuclear-readiness signal (note: Janus targets
# <=20 MWe microreactors, ~56x smaller than an AP1000; it's a permitting/intent
# signal, not a like-for-like). Source:
# https://www.army.mil/article/289074/
JANUS_SOURCE = "https://www.army.mil/article/289074/army_announces_next_steps_on_janus_program_for_next_generation_nuclear_energy"
JANUS_SITES = {
    "fort-benning-ga", "fort-bragg-nc", "fort-campbell-ky", "fort-drum-ny",
    "fort-hood-tx", "fort-wainwright-ak", "holston-aap-tn", "jblm-wa",
    "redstone-arsenal-al",
}

# Construction-workforce availability within ~1 hour. An AP1000 build peaks at
# several thousand construction workers over ~5-7 years (Vogtle 3&4 peaked near
# 9,000), so a sizable skilled-labor pool within commuting range materially
# de-risks cost/schedule; a remote site must import and camp labor. Ratings:
# strong (metro >=500k within ~1 hr) / good (~250-500k) / moderate (small local
# towns, larger metro near the 1-hr edge) / limited (rural/isolated, <~150k).
# Metro figures are standard Census MSA populations; source URLs given where a
# specific drive-time / MSA figure was checked.
WORKFORCE = {
    "arnold-afb-tn": {"rating": "moderate", "metro": "Tullahoma/Manchester local (~90k); Huntsville ~1h20m",
        "note": "Immediate towns (Tullahoma, Manchester, Shelbyville, Winchester) are small; Huntsville's ~500k metro is 59 mi / ~1h20m and Nashville ~1.5 hr — both just beyond the 1-hour pool.",
        "source": "https://www.travelmath.com/driving-time/from/Tullahoma,+TN/to/Huntsville,+AL"},
    "davis-monthan-afb-az": {"rating": "strong", "metro": "Tucson metro (~1.04M), on-site",
        "note": "Tucson MSA ~1.04M surrounds the base — a deep construction/industrial labor pool on-site."},
    "edwards-afb-ca": {"rating": "good", "metro": "Antelope Valley / Lancaster-Palmdale (~0.5M), ~45 min",
        "note": "Lancaster + Palmdale ~0.5M within ~45 min; Greater LA is beyond 1 hr but the Antelope Valley trades pool is solid."},
    "robins-afb-ga": {"rating": "good", "metro": "Warner Robins + Macon metro (~410k), ~30 min",
        "note": "Macon-Warner Robins combined ~410k within ~30 min."},
    "fort-benning-ga": {"rating": "good", "metro": "Columbus GA metro (~330k), adjacent",
        "note": "Columbus GA MSA ~330k adjacent to the cantonment."},
    "fort-bragg-nc": {"rating": "good", "metro": "Fayetteville metro (~525k), adjacent",
        "note": "Fayetteville MSA ~525k adjacent; Raleigh is ~1+ hr beyond."},
    "fort-campbell-ky": {"rating": "strong", "metro": "Clarksville (~180k) + Nashville metro (~2M) ~1 hr",
        "note": "Clarksville ~180k on the doorstep, and the ~2M Nashville metro is ~50 min — a deep pool."},
    "fort-drum-ny": {"rating": "limited", "metro": "Watertown-Fort Drum MSA (~116k), rural",
        "note": "Rural North Country; Watertown-Fort Drum MSA ~116k (incl. soldiers). Syracuse is ~70 mi / >1 hr — a megaproject would import and camp most labor.",
        "source": "https://www.citypopulation.de/en/usa/metro/48060__watertown_fort_drum/"},
    "fort-hood-tx": {"rating": "strong", "metro": "Killeen-Temple metro (~470k); Waco/Austin ~1 hr",
        "note": "Killeen-Temple-Fort Hood MSA ~470k on-site; Waco ~1 hr and Austin ~1-1.5 hr add depth."},
    "fort-wainwright-ak": {"rating": "limited", "metro": "Fairbanks North Star Borough (~95k), isolated",
        "note": "Fairbanks ~95k is the only labor pool for hundreds of miles; an AP1000 build would import nearly all skilled trades at high cost — a major schedule/cost risk."},
    "jblm-wa": {"rating": "strong", "metro": "Tacoma + Seattle metro (~4M) within ~1 hr",
        "note": "Tacoma adjacent and the ~4M Seattle-Tacoma metro within ~1 hr — one of the deepest pools of the 14."},
    "jbmdl-nj": {"rating": "strong", "metro": "Philadelphia metro (~6.2M) + Trenton within ~1 hr",
        "note": "Philadelphia MSA ~6.2M + Trenton within ~1 hr; NYC ~1.25 hr — abundant skilled trades."},
    "holston-aap-tn": {"rating": "good", "metro": "Tri-Cities TN/VA (~510k) within ~1 hr",
        "note": "Tri-Cities (Kingsport-Bristol + Johnson City) ~510k within ~1 hr."},
    "redstone-arsenal-al": {"rating": "strong", "metro": "Huntsville metro (~500k+), on-site",
        "note": "Huntsville MSA ~500k+ on-site with an unusually deep aerospace/engineering and skilled-trades base."},
}

# The 5 non-Janus installations are the bases named in the Air Force's Request
# for Lease Proposal (RFLP No. AFCEC-26-R-0002, "AI Data Center Development"),
# which in Oct 2025 offered ~3,100 ac of underutilized land across these five
# bases for private >100 MW / >$500M data-center development (offers due
# 2025-11-14, awards ~Jan 2026; pursuant to EOs 14179 & 14318). The Government
# sought first right of refusal on any co-located power generation — an on-base
# generation hook even though the solicitation targets data centers, not
# reactors. The parcels below are the RFLP's underutilized-land offering and are
# surfaced as provenance; they're distinct from (and smaller than) each base's
# broader reactor-siteable land, so they do NOT replace `developable_acreage`
# (which stays on a consistent total-developable basis across all 14 sites).
# Sources: official SAM.gov opportunity plus Edwards AFB public Q&A.
AF_RFLP_SOURCE = "https://sam.gov/workspace/contract/opp/e74af0fe0e03406e80488d7f5c538baa/view"
AF_RFLP_ARTICLE_SOURCE = "https://www.edwards.af.mil/News/Display/Article/4354128/have-questions-about-the-solicitation-for-ai-data-centers-we-got-answers/"
AF_LEASE = {
    "arnold-afb-tn":        {"acres": 274,  "detail": "Two parcels — 122 ac + 152 ac"},
    "davis-monthan-afb-az": {"acres": 300,  "detail": "One 300-ac parcel"},
    "edwards-afb-ca":       {"acres": 2100, "detail": "Seven parcels, 100–560 ac each (>2,100 ac total) — the largest of the five offerings"},
    "jbmdl-nj":             {"acres": 193,  "detail": "Two parcels — 73 ac + 120 ac"},
    "robins-afb-ga":        {"acres": 265,  "detail": "Three parcels, 30–135 ac each"},
}

# Curated installations. infra_source_id joins onto infra-proximity.json.
SITES = [
    {
        "id": "arnold-afb-tn", "name": "Arnold AFB (AEDC)", "branch": "Air Force",
        "state": "TN", "infra_source_id": "FUDS-G04TN0002",
        "installation_acreage": 40000, "developable_acreage": 25000,
        "developable_basis": "Overwhelmingly undeveloped forest/buffer — the built test-facility core is a few thousand acres; the rest is the ~25,000-ac AEDC Wildlife Management Area, with large contiguous parcels around Woods Reservoir. Estimate from total minus developed core.",
        "acreage_source": "https://tennesseeencyclopedia.net/entries/arnold-engineering-development-center/",
        "water_source": "Woods Reservoir (on-site, Elk River impoundment)",
        "water_distance_mi": 0, "water_adequacy": "abundant",
        "water_note": "Woods Reservoir (~26 billion gal storage, Elk River impoundment) purpose-built as AEDC cooling supply. AEDC already withdraws >22.4 billion gal/yr (~61 MGD) — well above an AP1000's ~9.8 Bgal/yr withdrawal (~26.8 MGD) / ~7.3 Bgal/yr consumptive. Elk River (USGS 03579100) mean ~470 cfs, ~10x the ~42 cfs screen.",
        "water_source_url": "https://www.arnold.af.mil/News/Article-Display/Article/3163926/woods-reservoir-completed-70-years-ago-this-month/",
        "fiber": "good",
        "fiber_note": "DISN-served major test complex on the I-24 corridor (Tullahoma/Manchester); well-connected but not metro-dense.",
        "seismic_flag": "moderate", "flood_flag": "low",
        "siting_note": "Moderate seismic (regional New Madrid / East TN influence). Already operates power + cooling infrastructure at the right scale — physically among the best-suited, though not a Janus site.",
        "nuclear_notes": "No documented DoD/DOE reactor-program interest, but uniquely large on-site power and cooling infrastructure.",
    },
    {
        "id": "davis-monthan-afb-az", "name": "Davis-Monthan AFB", "branch": "Air Force",
        "state": "AZ", "infra_source_id": "FUDS-J09AZ1023",
        "installation_acreage": 10763, "developable_acreage": 2500,
        "developable_basis": "Heavily built airfield + ~2,600-ac AMARG 'boneyard' consume most of the footprint; remaining open land is constrained. No EUL land record found.",
        "acreage_source": "https://en.wikipedia.org/wiki/309th_Aerospace_Maintenance_and_Regeneration_Group",
        "water_source": "Tucson AMA aquifer / CAP (Colorado River) delivery",
        "water_distance_mi": 7, "water_adequacy": "severe",
        "water_note": "Tucson AMA is in admitted groundwater overdraft (statutory 2025 safe-yield goal unmet, ADWR). The CAP (Colorado River) backstop was cut by 512,000 acre-ft — ~30% of CAP's normal supply — with nearly all Arizona reductions falling on CAP users. A ~30,000 acre-ft/yr consumptive demand is not sustainable; dry-cooling required.",
        "water_source_url": "https://www.cap-az.com/water/water-supply/colorado-river-operations-2/",
        "fiber": "excellent",
        "fiber_note": "DISN plus dense Tucson metro carrier fiber.",
        "seismic_flag": "low", "flood_flag": "low",
        "siting_note": "Water scarcity, not geohazards, is the binding constraint. Dry-cooling penalty would cut output and economics.",
        "nuclear_notes": "Not on the Janus shortlist or any AF reactor pilot.",
    },
    {
        "id": "edwards-afb-ca", "name": "Edwards AFB", "branch": "Air Force",
        "state": "CA", "infra_source_id": "CA1570024504",
        "installation_acreage": 301000, "developable_acreage": 100000,
        "developable_basis": "~301,000 ac is largely undeveloped / semi-improved test-range and dry-lake land; vast contiguous open parcels away from the lakebeds and flight lines. Land is the least-constrained resource.",
        "acreage_source": "https://en.wikipedia.org/wiki/Edwards_Air_Force_Base",
        "water_source": "Antelope Valley groundwater basin / AVEK (State Water Project)",
        "water_distance_mi": 0, "water_adequacy": "severe",
        "water_note": "Antelope Valley basin is in court-adjudicated overdraft: USGS documents >6 ft of basin-wide land subsidence (~4 ft at the base, 'adversely affecting the runways on the lakebed') and ~8.7M acre-ft cumulative storage depletion. The SWP import via AVEK delivered just 5% of requested supplies in 2022-23. Wet-cooling is not viable — dry-cooling required.",
        "water_source_url": "https://ca.water.usgs.gov/projects/antelope-valley/antelope-valley-land-subsidence.html",
        "fiber": "good",
        "fiber_note": "DISN + AFRL/test-range data infrastructure; Lancaster-Palmdale metro ~30+ mi.",
        "seismic_flag": "elevated", "flood_flag": "low",
        "siting_note": "Elevated seismic — Mojave, near the Garlock & San Andreas systems; a serious AP1000 design factor. Enormous land but marginal water + weak 115 kV access.",
        "nuclear_notes": "No documented reactor-program interest despite abundant remote land.",
    },
    {
        "id": "robins-afb-ga", "name": "Robins AFB", "branch": "Air Force",
        "state": "GA", "infra_source_id": "GA1570024330",
        "installation_acreage": 8722, "developable_acreage": 2000,
        "developable_basis": "Built-out depot/airfield (WR-ALC); the eastern Ocmulgee buffer holds undeveloped land but is partly flood-constrained. Usable upland parcels limited. Estimate; no EUL figure found.",
        "acreage_source": "https://en.wikipedia.org/wiki/Robins_Air_Force_Base",
        "water_source": "Ocmulgee River (forms the eastern boundary)",
        "water_distance_mi": 0.5, "water_adequacy": "adequate",
        "water_note": "Ocmulgee on the eastern boundary (USGS 02213700, drainage 2,690 sq mi); mean annual ~2,680 cfs (via upstream Macon gauge 02213000) comfortably covers a ~42 cfs AP1000 withdrawal. Downgraded from abundant: the smallest of the big-river sites, it fell to 854 cfs in the 2012 drought (withdrawal ~7.3% of that), so a non-interruptible nuclear load is drought-exposed.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-02213700/",
        "fiber": "excellent",
        "fiber_note": "DISN + WR-ALC is a major IT/depot hub; Macon metro carrier fiber nearby.",
        "seismic_flag": "low", "flood_flag": "moderate",
        "siting_note": "Low seismic (stable GA coastal plain) — favorable. The Ocmulgee floodplain along the eastern boundary is the cooling asset but also the flood vector; site on upland.",
        "nuclear_notes": "No documented interest at Robins (though GA hosts the Vogtle AP1000s).",
    },
    {
        "id": "fort-benning-ga", "name": "Fort Benning (Fort Moore)", "branch": "Army",
        "state": "GA", "infra_source_id": "FUDS-I04GA0394",
        "infra_proxy_note": "Transmission/substation from Lawson Army Airfield (on-base), ~2.9 mi from the cantonment centroid.",
        "installation_acreage": 182000, "developable_acreage": 40000,
        "developable_basis": "Vast majority is training/range/maneuver land; only a modest cantonment is built out. Estimate from total minus core; no published EUL figure.",
        "acreage_source": "https://home.army.mil/benning/About",
        "water_source": "Chattahoochee River",
        "water_distance_mi": 0.5, "water_adequacy": "abundant",
        "water_note": "The base's own Water Resource Facility withdraws directly from the Chattahoochee (base flow ~900 cfs; range 780-13,800 cfs at Columbus) — comfortably covers AP1000 withdrawal.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-02341460/",
        "fiber": "good",
        "fiber_note": "Columbus GA metro carrier fiber + DISN; large established post adjacent to a mid-size metro.",
        "seismic_flag": "low", "flood_flag": "low",
        "siting_note": "Low seismicity; riverine flood confined to the Chattahoochee floodplain — site on an upland terrace.",
        "nuclear_notes": "Army Janus microreactor shortlist (Nov 2025).",
    },
    {
        "id": "fort-bragg-nc", "name": "Fort Bragg (Fort Liberty)", "branch": "Army",
        "state": "NC", "infra_source_id": "FUDS-I04NC0516",
        "installation_acreage": 161000, "developable_acreage": 25000,
        "developable_basis": "~142,000+ ac of training land, but explicitly described as 'every acre at a premium' — real siting competition. No EUL acreage published.",
        "acreage_source": "https://www.globalsecurity.org/military/facility/fort-bragg.htm",
        "water_source": "Cape Fear River (~10 mi, via Fayetteville PWC)",
        "water_distance_mi": 10, "water_adequacy": "marginal",
        "water_note": "Source corrected: the post is supplied from the Cape Fear River (USGS 02102500 at Lillington, mean annual 3,224 cfs, drainage 3,464 sq mi) — NOT the Little River (USGS 02103000, only 407 cfs mean / 131.5 cfs in the 2011 drought, too small for a dedicated intake). The Cape Fear easily covers ~42 cfs (1.3%) but a dedicated ~10-mi intake into an allocation-contested basin keeps this marginal, not comfortably adequate.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-02102500/",
        "fiber": "excellent",
        "fiber_note": "World's largest Army installation; dense DISN backbone, airborne/SOCOM C2 infrastructure, Fayetteville metro carriers.",
        "seismic_flag": "low", "flood_flag": "low",
        "siting_note": "Low-moderate seismic (Sandhills); well-drained sandy terrain, low flood risk. Best transmission of the 14 (230 kV adjacent).",
        "nuclear_notes": "Army Janus microreactor shortlist (Nov 2025).",
    },
    {
        "id": "fort-campbell-ky", "name": "Fort Campbell", "branch": "Army",
        "state": "KY", "infra_source_id": "FUDS-G04TN0301",
        "installation_acreage": 105000, "developable_acreage": 25000,
        "developable_basis": "Large training reservation, compact cantonment; ~20,000-35,000 ac of range/impact/maneuver land. No EUL figure found.",
        "acreage_source": "https://en.wikipedia.org/wiki/Fort_Campbell",
        "water_source": "Cumberland River (~12-15 mi S); on-post karst groundwater today",
        "water_distance_mi": 13, "water_adequacy": "marginal",
        "water_note": "Post supply is on-post karst groundwater — cannot sustain ~27 MGD. The Cumberland River (USGS 03431500 at Nashville, mean 23,765 cfs; the downstream Clarksville reach is larger) is abundant — a ~42 cfs withdrawal is ~0.18% — but it is ~12-15 mi away and ~400 ft lower, needing a pumped pipeline. The limit is infrastructure, not water.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-03431500/",
        "fiber": "good",
        "fiber_note": "Clarksville TN metro carrier fiber + DISN; 101st Airborne C2 infrastructure.",
        "seismic_flag": "elevated", "flood_flag": "low",
        "siting_note": "Within New Madrid Seismic Zone influence (~150 mi E) — elevated design basis vs. the others. Karst terrain adds foundation diligence. Water is the weakest of the Janus sites.",
        "nuclear_notes": "Army Janus microreactor shortlist (Nov 2025).",
    },
    {
        "id": "fort-drum-ny", "name": "Fort Drum", "branch": "Army",
        "state": "NY", "infra_source_id": "FUDS-C02NY0200",
        "installation_acreage": 107265, "developable_acreage": 40000,
        "developable_basis": "Large undeveloped training/range tracts. Existing behind-the-meter precedent (ReEnergy Black River 60 MW supplied up to 100% of post load) shows on-base generation siting is workable. No EUL acreage published.",
        "acreage_source": "https://en.wikipedia.org/wiki/Fort_Drum",
        "water_source": "Black River",
        "water_distance_mi": 0.5, "water_adequacy": "abundant",
        "water_note": "Black River (USGS 04260500) drains 1,864 sq mi; mean annual 4,242 cfs — a ~42 cfs AP1000 withdrawal is ~1.0%. Hudson-Black River Regulating District augments low flows; Lake Ontario ~25 mi W is an effectively unlimited backup.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-04260500/",
        "fiber": "moderate",
        "fiber_note": "Rural North Country; DISN + regional carriers present, but less metro density than Bragg/Benning.",
        "seismic_flag": "low", "flood_flag": "low",
        "siting_note": "Low seismicity; Black River floodplain localized — site on upland. Cold-climate / heavy-snow design considerations.",
        "nuclear_notes": "Army Janus shortlist (Nov 2025), AND NY legislators have specifically called for an SMR here — the strongest documented siting interest of the 14.",
    },
    {
        "id": "fort-hood-tx", "name": "Fort Hood (Fort Cavazos)", "branch": "Army",
        "state": "TX", "infra_source_id": "FUDS-K06TX0020",
        "installation_acreage": 218000, "developable_acreage": 12000,
        "developable_basis": "One of 4 Army posts in the 2026 commercial data-center EUL RFP (50-yr leases on underutilized land); peer site Fort Bliss listed 1,384 ac after culling and Fort Hood is a larger 'multi-modal' site. Already hosts a 132-ac on-post solar field.",
        "acreage_source": "https://defensescoop.com/2026/02/06/trump-military-bases-army-lease-land-data-centers/",
        "water_source": "Belton Lake (Leon River)",
        "water_distance_mi": 8, "water_adequacy": "poor",
        "water_note": "Belton Lake (Leon River; BRA-operated) firm yield is 100,257 acre-ft/yr (Bell County WCID No.1). An AP1000's ~22,400 acre-ft/yr consumptive is ~22% of that — securable but tight in a semi-arid, drought-prone, already-allocated basin (BRA is building the Belton-to-Stillhouse pipeline to rebalance supply). Existing Fort Hood water-supply storage (~12,000 acre-ft) is far short, so poor stands absent a large new regional allocation.",
        "water_source_url": "https://wcid1.org/about-us/",
        "fiber": "good",
        "fiber_note": "Regional DISN integration hub on the I-35 Austin-Waco-DFW corridor (dense long-haul/metro fiber).",
        "seismic_flag": "low", "flood_flag": "low",
        "siting_note": "Low seismicity, geotechnically easy; the binding risk is drought / water scarcity, not geohazards. ERCOT market.",
        "nuclear_notes": "Army Janus microreactor shortlist (Nov 2025).",
    },
    {
        "id": "fort-wainwright-ak", "name": "Fort Wainwright", "branch": "Army",
        "state": "AK", "infra_source_id": "AK6210022426",
        "installation_acreage": 911600, "developable_acreage": 4500,
        "developable_basis": "Cantonment land-rich (main post ~4,500 ac) with vast adjacent training land, but PERMAFROST severely limits truly buildable area — discontinuous permafrost, thermokarst, and floodplain constrain siting. Practical buildable footprint is a fraction of nominal acreage.",
        "acreage_source": "https://en.wikipedia.org/wiki/Fort_Wainwright",
        "water_source": "Chena River (on-post) -> Tanana River",
        "water_distance_mi": 0, "water_adequacy": "abundant",
        "water_note": "Post straddles the Chena (a 100-mi Tanana tributary); ample surface water + high-yield alluvial aquifer. Water quantity is not the constraint — permafrost and seismic engineering are.",
        "water_source_url": "https://en.wikipedia.org/wiki/Fort_Wainwright",
        "fiber": "limited",
        "fiber_note": "Interior-Alaska terrestrial long-haul is thin; served via the Fairbanks metro and a small number of fiber routes — no dense carrier mesh.",
        "seismic_flag": "high", "flood_flag": "moderate",
        "siting_note": "Highest-geohazard site: discontinuous permafrost (thaw-settlement → deep/refrigerated foundations), extreme cold, very active Interior-Alaska seismicity (Denali fault region), plus Chena/Tanana floodplain. But the islanded Railbelt grid makes the energy-resilience case among the strongest.",
        "nuclear_notes": "Army Janus shortlist (Nov 2025); islanded GVEA grid drives a strong resilience case.",
    },
    {
        "id": "jblm-wa", "name": "Joint Base Lewis-McChord", "branch": "Army/Air Force",
        "state": "WA", "infra_source_id": "WA7210090067",
        "installation_acreage": 90000, "developable_acreage": 8000,
        "developable_basis": "~80,000 ac of ranges, but constrained by rare prairie/oak ecosystems, wetlands, and a Real Property Master Plan / Joint Land Use review. Realistically several thousand acres of non-sensitive land; no published AP1000-parcel figure.",
        "acreage_source": "https://installations.militaryonesource.mil/in-depth-overview/joint-base-lewis-mcchord",
        "water_source": "Nisqually River + glacial-outwash aquifer (Puget Sound ~12 mi N)",
        "water_distance_mi": 1, "water_adequacy": "adequate",
        "water_note": "JBLM runs a city-scale groundwater system on the high-yield Vashon glacial-outwash aquifer; the Nisqually River (USGS 12089500) borders the south at >2,000 cfs mean (~42 cfs ≈ <2%) and Puget Sound is ~12 mi N. Volume is abundant, but a new ~27 MGD surface-water right is unproven and several base wells exceed PFAS limits — so adequate, not abundant.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-12089500/",
        "fiber": "excellent",
        "fiber_note": "Seattle-Tacoma I-5 metro corridor, dense carrier + long-haul fiber; new JBLM Information Systems Facility (2024).",
        "seismic_flag": "high", "flood_flag": "low",
        "siting_note": "Cascadia subduction-zone risk — ~37% chance of M7.1+ in 50 yr; M9 megathrust ground motions + localized liquefaction (saturated outwash) are the dominant nuclear-foundation challenge.",
        "nuclear_notes": "Army Janus microreactor shortlist (Nov 2025).",
    },
    {
        "id": "jbmdl-nj", "name": "JB McGuire-Dix-Lakehurst", "branch": "Joint",
        "state": "NJ", "infra_source_id": "NJ0570024018",
        "installation_acreage": 42000, "developable_acreage": 4000,
        "developable_basis": "Substantial undeveloped land (former Fort Dix ranges, Pinelands buffer) but heavily constrained by Pinelands National Reserve regulation + PFAS groundwater plumes. Realistically a few thousand acres of non-sensitive land.",
        "acreage_source": "https://en.wikipedia.org/wiki/Joint_Base_McGuire%E2%80%93Dix%E2%80%93Lakehurst",
        "water_source": "Kirkwood-Cohansey aquifer (on-site)",
        "water_distance_mi": 0, "water_adequacy": "poor",
        "water_note": "No large adjacent river; the unconfined Kirkwood-Cohansey aquifer is voluminous in storage but yield-limited and Pinelands-capped. An AP1000's ~27 MGD ≈ 9.9 Bgal/yr is ~28% of the aquifer's entire statewide annual pumping (~35 Bgal/yr across ~3,000 wells), concentrated at one point and tightly coupled to Pinelands wetlands/streams. Two on-base supply wells tested 264,300 ppt PFOS/PFOA. Poor absent an external surface-water supply.",
        "water_source_url": "https://pinelandsalliance.org/water-supply-aquifer/",
        "fiber": "excellent",
        "fiber_note": "Central NJ between the Philadelphia and NYC metros — the densest fiber corridor in the US.",
        "seismic_flag": "low", "flood_flag": "low",
        "siting_note": "Low seismicity, flat coastal-plain terrain. Constraints are Pinelands environmental regulation + PFAS, not geohazards. The one site NOT on the Janus shortlist.",
        "nuclear_notes": "Not on the Janus shortlist; no documented current SMR/microreactor study found.",
    },
    {
        "id": "holston-aap-tn", "name": "Holston Army Ammunition Plant", "branch": "Army",
        "state": "TN", "infra_source_id": "FUDS-G04TN0212",
        "installation_acreage": 6024, "developable_acreage": 2500,
        "developable_basis": "Plant B (~5,900 ac, Hawkins County) is largely undeveloped and hosts a state-certified industrial site ('Technology Park II'). But much buffer land carries RDX/HMX legacy contamination with land-use controls — 'available' != 'unencumbered.'",
        "acreage_source": "https://tnecd.com/certifiedsite/technology-park-ii-at-holston-army-ammunition-plant/",
        "water_source": "Holston River (South Fork)",
        "water_distance_mi": 0, "water_adequacy": "abundant",
        "water_note": "Plant sits directly on the South Fork Holston (USGS 03487500, drainage 1,935 sq mi, mean annual ~2,910 cfs; ~42 cfs withdrawal ≈ 1.4%) and already withdraws river water for RDX/HMX manufacturing. TVA-regulated minimum flows via three upstream dams. South Fork only, so abundant rather than vast.",
        "water_source_url": "https://waterservices.usgs.gov/nwis/site/?format=rdb&sites=03487500&siteOutput=expanded",
        "fiber": "moderate",
        "fiber_note": "Ordnance site in the Kingsport (Tri-Cities) metro with regional carrier presence, but not a major IT/telecom hub.",
        "seismic_flag": "moderate", "flood_flag": "moderate",
        "siting_note": "Northern Eastern-Tennessee Seismic Zone (USGS models M7.5 possible) — a real but moderate design-basis factor; plus direct Holston River floodplain exposure. TVA region (active SMR utility).",
        "nuclear_notes": "Army Janus shortlist (Nov 2025). TVA is the most aggressive SMR utility in the US (Clinch River BWRX-300).",
    },
    {
        "id": "redstone-arsenal-al", "name": "Redstone Arsenal", "branch": "Army",
        "state": "AL", "infra_source_id": "AL7210020742",
        "installation_acreage": 38000, "developable_acreage": 4000,
        "developable_basis": "Active EUL/real-estate program; Redstone Gateway EUL = 468 ac with ~214 still undeveloped, and the arsenal is mostly open/wooded test & buffer land with large tracts beyond Gateway. Estimate well above the documented 214 ac.",
        "acreage_source": "https://www.army.mil/article/34408/redstone_plans_to_lease_land_for_growth",
        "water_source": "Tennessee River / Wheeler Reservoir (southern boundary)",
        "water_distance_mi": 0, "water_adequacy": "abundant",
        "water_note": "Redstone operates two intakes on the Tennessee River (USGS 03575500 at Whitesburg, drainage 25,610 sq mi, mean annual ~41,650 cfs; ~42 cfs withdrawal ≈ 0.10%, the strongest of the 14). Wheeler Reservoir is a large TVA mainstem impoundment — effectively unlimited.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/03575500/",
        "fiber": "excellent",
        "fiber_note": "Major DoD/IT hub — FBI's 2nd-largest HQ, NASA Marshall, Space Command, MDA; adjacent Cummings Research Park + DC BLOX Tier III data center + carrier-dense metro fiber.",
        "seismic_flag": "moderate", "flood_flag": "moderate",
        "siting_note": "Southern terminus of the Eastern-Tennessee Seismic Zone — moderate design factor; Tennessee River/Wheeler floodplain on the southern boundary. TVA region + huge co-located mission demand.",
        "nuclear_notes": "Army Janus shortlist (Nov 2025). TVA region (Clinch River BWRX-300 + 6 GW SMR program).",
    },
]


def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def _get_eia_bytes():
    """Return EIA-860M April 2026 bytes from the connector's binary cache or
    download fresh. Returns None on failure (retired-plant data is optional)."""
    # Walk up from this script looking for the connector's binary cache.
    candidate = Path(__file__).resolve().parent
    for _ in range(8):
        bin_path = candidate / "data" / "cache" / _EIA_CACHE_FILENAME
        if bin_path.exists():
            print(f"EIA-860M: cache hit {bin_path}")
            return bin_path.read_bytes()
        candidate = candidate.parent

    # Not cached — download and store next to the connector cache if possible.
    print(f"EIA-860M: downloading {EIA_860M_URL} …")
    try:
        req = urllib.request.Request(
            EIA_860M_URL,
            headers={"User-Agent": "BrownfieldOpportunities/0.2 (research; static dashboard)"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as exc:
        print(f"EIA-860M: download failed ({exc}) — skipping retired-plant data", file=sys.stderr)
        return None

    # Try to cache where the connector would look next run.
    for base in [Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "cache",
                 DATA.parent]:
        try:
            base.mkdir(parents=True, exist_ok=True)
            (base / _EIA_CACHE_FILENAME).write_bytes(data)
            print(f"EIA-860M: cached {len(data)//1024}KB → {base / _EIA_CACHE_FILENAME}")
            break
        except OSError:
            continue

    return data


def _load_retired_plants() -> list[dict]:
    """Parse EIA-860M Retired sheet into a list of qualifying plant dicts."""
    try:
        import openpyxl  # type: ignore
    except ImportError:
        print("WARNING: openpyxl not installed — skipping retired plant data", file=sys.stderr)
        return []

    raw = _get_eia_bytes()
    if not raw:
        return []

    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
    ws = wb["Retired"]
    rows = list(ws.iter_rows(values_only=True))
    # rows[0] = banner, rows[1] = blank, rows[2] = header; data from rows[3:]
    data_rows = rows[3:]

    plants: dict[int, dict] = defaultdict(lambda: {
        "name": None, "lat": None, "lon": None,
        "total_mw": 0.0, "primary_fuel_mw": 0.0,
        "fuel": None, "ret_year": None,
    })

    for row in data_rows:
        plant_id = row[_COL_PLANT_ID]
        if not plant_id:
            continue
        try:
            plant_id = int(plant_id)
        except (TypeError, ValueError):
            continue

        p = plants[plant_id]
        if p["name"] is None and row[_COL_PLANT_NAME]:
            p["name"] = str(row[_COL_PLANT_NAME])

        try:
            mw = float(row[_COL_MW]) if row[_COL_MW] is not None else 0.0
        except (TypeError, ValueError):
            mw = 0.0
        p["total_mw"] += mw

        fuel_raw = row[_COL_FUEL]
        fuel = str(fuel_raw).strip().upper() if fuel_raw else None
        if fuel and mw >= p["primary_fuel_mw"]:
            p["fuel"] = fuel
            p["primary_fuel_mw"] = mw

        try:
            yr = int(row[_COL_RET_YEAR]) if row[_COL_RET_YEAR] is not None else None
        except (TypeError, ValueError):
            yr = None
        if yr is not None and (p["ret_year"] is None or yr > p["ret_year"]):
            p["ret_year"] = yr

        try:
            lat = float(row[_COL_LAT]) if row[_COL_LAT] is not None else None
            lon = float(row[_COL_LON]) if row[_COL_LON] is not None else None
        except (TypeError, ValueError):
            lat = lon = None
        if lat is not None and lon is not None:
            p["lat"] = lat
            p["lon"] = lon

    result = []
    for p in plants.values():
        if p["lat"] is None or p["lon"] is None:
            continue
        if p["total_mw"] < MIN_PLANT_MW:
            continue
        if (p["fuel"] or "").upper() not in _DISPATCHABLE:
            continue
        result.append(p)

    print(f"EIA-860M: {len(result)} qualifying retired plants loaded")
    return result


def _nearest_retired_plant(lat, lon, plants, radius_mi):
    """Return (distance_mi, plant) dict for closest plant within radius, or None."""
    best_d = radius_mi + 1
    best_p = None
    for p in plants:
        d = _haversine_mi(lat, lon, p["lat"], p["lon"])
        if d < best_d:
            best_d = d
            best_p = p
    if best_p is None:
        return None
    return {"dist_mi": round(best_d, 2), "plant": best_p}


def main() -> None:
    infra = json.loads(INFRA_PATH.read_text())
    infra_rows = infra.get("sites", infra) if isinstance(infra, dict) else infra
    infra_by_id = {r["id"]: r for r in infra_rows}

    # Load EIA-860M retired plants once (optional — gracefully absent).
    retired_plants = _load_retired_plants()

    out = []
    for s in SITES:
        rec = dict(s)
        rec["janus_site"] = s["id"] in JANUS_SITES
        if rec["janus_site"]:
            rec["janus_source_url"] = JANUS_SOURCE
        if s["id"] in AF_LEASE:
            lease = AF_LEASE[s["id"]]
            rec["af_rflp_site"] = True
            rec["af_rflp_acres"] = lease["acres"]
            rec["af_rflp_detail"] = lease["detail"]
            rec["af_rflp_source_url"] = AF_RFLP_SOURCE
            rec["af_rflp_article_url"] = AF_RFLP_ARTICLE_SOURCE
        w = WORKFORCE.get(s["id"])
        if not w:
            raise SystemExit(f"no WORKFORCE entry for {s['id']}")
        rec["workforce"] = w["rating"]
        rec["workforce_metro"] = w["metro"]
        rec["workforce_note"] = w["note"]
        if w.get("source"):
            rec["workforce_source_url"] = w["source"]
        # Every site belongs to exactly one source program: the Army Janus
        # microreactor shortlist or the Air Force AI-data-center RFLP.
        if rec["janus_site"] == bool(rec.get("af_rflp_site")):
            raise SystemExit(f"{s['id']} must be exactly one of Janus / AF-RFLP "
                             f"(janus={rec['janus_site']}, af_rflp={rec.get('af_rflp_site')})")
        src = infra_by_id.get(s["infra_source_id"])
        if not src:
            raise SystemExit(f"infra_source_id not found in infra-proximity.json: {s['infra_source_id']} ({s['id']})")
        # Real, project-computed infrastructure distances.
        rec["lat"] = _site_latlon(s["infra_source_id"])[0]
        rec["lon"] = _site_latlon(s["infra_source_id"])[1]
        for k in ("transmission_mi", "transmission_kv", "substation_mi",
                  "substation_kv", "gas_pipeline_mi", "rail_mi", "highway_mi",
                  "power_plant_mi", "power_plant_mw", "power_plant_fuel"):
            rec[k] = src.get(k)

        # Nearest large retired plant from EIA-860M (within RETIRED_PLANT_RADIUS_MI).
        if retired_plants:
            hit = _nearest_retired_plant(rec["lat"], rec["lon"], retired_plants,
                                         RETIRED_PLANT_RADIUS_MI)
            if hit:
                p = hit["plant"]
                rec["retired_plant_mi"]   = hit["dist_mi"]
                rec["retired_plant_mw"]   = round(p["total_mw"], 1)
                rec["retired_plant_fuel"] = p["fuel"]
                rec["retired_plant_year"] = p["ret_year"]
                rec["retired_plant_name"] = p["name"]

        out.append(rec)

    payload = {
        "generated_at": GENERATED_AT,
        "source": "Curated AP1000-siting analysis overlay (analyst-researched land/water/fiber; transmission/substation joined from infra-proximity.json)",
        "source_urls": {
            "ap1000_specs": AP1000_SOURCE,
            "vogtle_workforce_scale": VOGTLE_WORKFORCE_SOURCE,
            "army_janus": JANUS_SOURCE,
            "air_force_rflp": AF_RFLP_SOURCE,
            "air_force_rflp_public_qa": AF_RFLP_ARTICLE_SOURCE,
        },
        "ap1000_mwe": 1117,
        "count": len(out),
        "sites": out,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {len(out)} AP1000 sites -> {OUT_PATH}")


# Pull lat/lon from the matched whole-installation record (sites.json /
# dod-fuds.json) so the overlay anchors on the same coordinate the infra
# distances were computed from.
_LATLON_CACHE = {}


def _site_latlon(record_id: str):
    if not _LATLON_CACHE:
        for fname in ("sites.json", "dod-fuds.json", "dod-brac.json"):
            try:
                d = json.loads((DATA / fname).read_text())
            except FileNotFoundError:
                continue
            for r in d.get("sites", []):
                if r.get("lat") is not None and r.get("lon") is not None:
                    _LATLON_CACHE[r["id"]] = (r["lat"], r["lon"])
    if record_id not in _LATLON_CACHE:
        raise SystemExit(f"lat/lon not found for {record_id}")
    return _LATLON_CACHE[record_id]


if __name__ == "__main__":
    main()
