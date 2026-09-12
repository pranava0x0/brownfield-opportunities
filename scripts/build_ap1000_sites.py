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
  • retired_plant_*: REAL, from the pinned EIA Form EIA-860M workbook ("Retired" sheet),
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
import datetime as dt
import io
import json
import math
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from connectors.eia860m_source import EIA_860M_URL, EIA_WORKBOOK_MONTH, EIA_CACHE_FILENAME

DATA = ROOT / "docs" / "data"
INFRA_PATH = DATA / "infra-proximity.json"
OUT_PATH = DATA / "ap1000-sites.json"

# ---- EIA-860M retired plant enrichment ------------------------------------
# One pinned source vintage/cache identity shared with retired/planned producers.
_EIA_CACHE_FILENAME = EIA_CACHE_FILENAME

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

# Separate build freshness from the date the analyst-curated claims were last
# verified. Rebuilding must not leave `generated_at` pinned to an older file.
ANALYSIS_VERIFIED_AT = "2026-07-02"
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
        "water_distance_mi": 0, "water_adequacy": "unknown",
        "water_note": "Woods Reservoir was constructed for AEDC cooling. The cited historical article does not establish current annual demand or spare capacity. Historical use does not establish available reactor supply. Current firm yield, competing demands, intake capacity and a project allocation are unassessed.",
        "water_source_url": "https://www.arnold.af.mil/News/Article-Display/Article/3163926/woods-reservoir-completed-70-years-ago-this-month/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
        "seismic_flag": "moderate", "flood_flag": "low",
        "siting_note": "Moderate seismic (regional New Madrid / East TN influence). Historical test-facility cooling infrastructure is documented; capacity for a new project is unassessed. Not a Janus site.",
        "nuclear_notes": "No documented DoD/DOE reactor-program interest, but uniquely large on-site power and cooling infrastructure.",
    },
    {
        "id": "davis-monthan-afb-az", "name": "Davis-Monthan AFB", "branch": "Air Force",
        "state": "AZ", "infra_source_id": "FUDS-J09AZ1023",
        "installation_acreage": 10763, "developable_acreage": 2500,
        "developable_basis": "Heavily built airfield + ~2,600-ac AMARG 'boneyard' consume most of the footprint; remaining open land is constrained. No EUL land record found.",
        "acreage_source": "https://en.wikipedia.org/wiki/309th_Aerospace_Maintenance_and_Regeneration_Group",
        "water_source": "Tucson AMA aquifer / CAP (Colorado River) delivery",
        "water_distance_mi": 7, "water_adequacy": "unknown",
        "water_note": "Tucson groundwater and CAP imports are potential source contexts. The retained source discusses historical Colorado River shortage conditions; it is not a current project allocation or a site supply study. Present entitlement, firm yield and cooling design remain unassessed.",
        "water_source_url": "https://www.cap-az.com/water/water-supply/colorado-river-operations-2/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
        "seismic_flag": "low", "flood_flag": "low",
        "siting_note": "Historical water constraints warrant a current supply study; cooling design and project feasibility remain unassessed.",
        "nuclear_notes": "Not on the Janus shortlist or any AF reactor pilot.",
    },
    {
        "id": "edwards-afb-ca", "name": "Edwards AFB", "branch": "Air Force",
        "state": "CA", "infra_source_id": "CA1570024504",
        "installation_acreage": 301000, "developable_acreage": 100000,
        "developable_basis": "~301,000 ac is largely undeveloped / semi-improved test-range and dry-lake land; vast contiguous open parcels away from the lakebeds and flight lines. Land is the least-constrained resource.",
        "acreage_source": "https://en.wikipedia.org/wiki/Edwards_Air_Force_Base",
        "water_source": "Antelope Valley groundwater basin / AVEK (State Water Project)",
        "water_distance_mi": 0, "water_adequacy": "unknown",
        "water_note": "USGS documents historical Antelope Valley groundwater depletion and subsidence. These are material source constraints; they do not establish the feasibility of a specific cooling design. Imported supply, entitlement and project-scale reliability remain unassessed.",
        "water_source_url": "https://ca.water.usgs.gov/projects/antelope-valley/antelope-valley-land-subsidence.html",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
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
        "water_distance_mi": 0.5, "water_adequacy": "unknown",
        # Retained USGS observation is an annual mean, never 7Q10/low flow.
        "water_drought_year_mean_cfs": 854.1,
        "water_drought_year": 2012,
        "water_statistic": "annual_mean",
        "water_statistic_source_url": "https://waterservices.usgs.gov/nwis/stat/?format=rdb&sites=02213000&statReportType=annual&statTypeCd=mean&parameterCd=00060",
        "water_note": "Ocmulgee River is mapped along the installation. Upstream Macon gage 02213000 reports a 2012 ANNUAL MEAN of 854.1 cfs; this is not a daily minimum, 7Q10 or firm supply. A 42 cfs withdrawal is approximately 4.9% of that annual mean, which does not establish a permissible withdrawal or drought margin. Site intake, low-flow reliability and allocation remain unassessed.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-02213700/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
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
        "water_distance_mi": 0.5, "water_adequacy": "unknown",
        "water_note": "Chattahoochee River gage 02341460 provides regional streamflow context. No site-specific low-flow assessment, spare intake capacity or allocation for a new reactor is retained.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-02341460/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
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
        "water_distance_mi": 10, "water_adequacy": "unknown",
        "water_note": "The retained supply research identifies Fayetteville PWC and the Cape Fear River, rather than the Little River. The approximately 10-mile distance is an analyst estimate, not a surveyed intake route. New project service capacity, low-flow reliability and allocation remain unassessed.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-02102500/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
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
        "water_distance_mi": 13, "water_adequacy": "unknown",
        "water_note": "The retained research identifies on-post groundwater and the Cumberland River as possible source contexts. The river distance and lift are analyst estimates, not an engineered conveyance route. Groundwater sustainable yield and a new surface supply allocation remain unassessed.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-03431500/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
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
        "water_distance_mi": 0.5, "water_adequacy": "unknown",
        "water_note": "Black River gage 04260500 provides regional flow context. Nearby Lake Ontario is a separate potential source, not unlimited or allocated backup supply. Intake routing, low-flow reliability and applicable allocation remain unassessed.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-04260500/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
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
        "water_distance_mi": 8, "water_adequacy": "unknown",
        "water_note": "The retained source reports Belton Lake yield of 100,257 acre-feet per year. An AP1000 reference consumptive demand of approximately 22,400 acre-feet/year is about 22% of that reported system yield. This comparison excludes existing commitments and does not establish spare yield, a supply contract or project feasibility.",
        "water_source_url": "https://wcid1.org/about-us/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
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
        "water_distance_mi": 0, "water_adequacy": "unknown",
        "water_note": "Chena River gage 15514000 provides regional streamflow context. The Tanana is a different potential source requiring a confirmed intake and route; winter ice and seasonal flow require separate assessment. Project water availability and entitlement remain unassessed.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-15514000/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
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
        "water_distance_mi": 1, "water_adequacy": "unknown",
        "water_note": "Nisqually River gage 12089500 provides regional context; groundwater and Puget Sound are distinct potential supplies with different treatment and regulatory requirements. No current project allocation or low-flow reliability study is retained.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-12089500/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
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
        "water_distance_mi": 0, "water_adequacy": "unknown",
        "water_note": "The Kirkwood-Cohansey aquifer is a potential groundwater source context. Aquifer storage and statewide pumping totals do not establish sustainable yield at a project wellfield. Source identity, project demand, environmental constraints and allocation require assessment.",
        "water_source_url": "https://pinelandsalliance.org/water-supply-aquifer/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
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
        "water_distance_mi": 0, "water_adequacy": "unknown",
        "water_note": "South Fork Holston gage 03487500 provides regional flow context. Regulated flows and existing industrial use do not establish spare supply or a new project allocation. Site intake capacity and low-flow reliability remain unassessed.",
        "water_source_url": "https://waterservices.usgs.gov/nwis/site/?format=rdb&sites=03487500&siteOutput=expanded",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
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
        "water_distance_mi": 0, "water_adequacy": "unknown",
        "water_note": "Tennessee River / Wheeler Reservoir and gage 03575500 provide source context. A large mean river flow does not establish unlimited supply, spare intake capacity or a new allocation. Project reliability and entitlement remain unassessed.",
        "water_source_url": "https://waterdata.usgs.gov/monitoring-location/03575500/",
        "fiber": "unknown",
        "fiber_note": "No site-specific carrier, service, capacity or route evidence retained. Fiber availability is unassessed.",
        "seismic_flag": "moderate", "flood_flag": "moderate",
        "siting_note": "Southern terminus of the Eastern-Tennessee Seismic Zone — moderate design factor; Tennessee River/Wheeler floodplain on the southern boundary. TVA region + huge co-located mission demand.",
        "nuclear_notes": "Army Janus shortlist (Nov 2025). TVA region (Clinch River BWRX-300 + 6 GW SMR program).",
    },
]

# ISO/RTO grid operator per installation. 1,117 MW interconnection context
# matters enormously: PJM (7-yr queue) vs TVA (bilateral, faster) vs ERCOT
# (no federal jurisdiction) vs isolated ASEA (Railbelt) are radically different.
# Source: EIA ISO/RTO overview + each BA's published tariff / interconnection guide.
_EIA_ISO_RTO_SOURCE = "https://www.eia.gov/electricity/wholesale/"
GRID_OPERATOR = {
    "arnold-afb-tn": {
        "rto": "TVA",
        "note": (
            "Tennessee Valley Authority — vertically integrated, no competitive queue. "
            "Interconnection via bilateral agreement. TVA's Clinch River BWRX-300 project "
            "makes it the most nuclear-receptive large utility in the US."
        ),
        "source": "https://www.tva.com/energy/our-power-system/transmission/request-for-transmission-service",
    },
    "davis-monthan-afb-az": {
        "rto": "Non-RTO/WECC (Tucson Electric Power)",
        "note": (
            "Tucson Electric Power (TEP) balancing authority — WECC region, no ISO/RTO queue. "
            "Vertically integrated IOU; large interconnections require bilateral negotiations. "
            "No organized capacity market."
        ),
        "source": "https://www.tucsonelectric.com/energy/transmission",
    },
    "edwards-afb-ca": {
        "rto": "CAISO (Southern California Edison)",
        "note": (
            "California ISO balancing authority (SCE distribution territory). "
            "CAISO interconnection queue exceeds 300 GW; post-FERC Order 2023 reforms "
            "target 5-year median timelines, but 1,117 MW nuclear would be a novel "
            "CAISO category with multi-year study periods."
        ),
        "source": "https://www.caiso.com/generation/Pages/InterconnectionProcesses/default.aspx",
    },
    "robins-afb-ga": {
        "rto": "Non-RTO/SERC (Georgia Power / Southern Company)",
        "note": (
            "Southern Company (Georgia Power) service territory — SERC region, no ISO/RTO queue. "
            "Southern Company has direct AP1000 experience (Vogtle 3 & 4) in this territory. "
            "Bilateral agreements; typically faster than PJM/NYISO for large nuclear."
        ),
        "source": "https://www.southerncompany.com/transmission",
    },
    "fort-benning-ga": {
        "rto": "Non-RTO/SERC (Georgia Power / Southern Company)",
        "note": (
            "Same Georgia Power / Southern Company territory as Robins AFB — "
            "SERC region, bilateral interconnection. Southern Company's Vogtle AP1000 "
            "experience makes this the most nuclear-familiar BA of the 14."
        ),
        "source": "https://www.southerncompany.com/transmission",
    },
    "fort-bragg-nc": {
        "rto": "Non-RTO/SERC (Duke Energy Carolinas)",
        "note": (
            "Duke Energy Carolinas service territory — SERC region, no ISO/RTO queue. "
            "Duke is vertically integrated in the Carolinas; bilateral interconnect. "
            "Duke has SMR interest in the Carolinas but no active AP1000 program."
        ),
        "source": "https://www.dukeenergy.com/home/products/electric-transmission",
    },
    "fort-campbell-ky": {
        "rto": "TVA",
        "note": (
            "Fort Campbell straddles the TN/KY border (cantonment primarily Clarksville, TN); "
            "served by Tennessee Valley Authority. Same bilateral-agreement interconnection "
            "path as Arnold AFB and Holston AAP — no organized capacity queue."
        ),
        "source": "https://www.tva.com/energy/our-power-system/transmission/request-for-transmission-service",
    },
    "fort-drum-ny": {
        "rto": "NYISO (National Grid / Zone C)",
        "note": (
            "New York ISO, Zone C (Central NY / National Grid territory). "
            "NYISO has a structured interconnection queue; NY's Climate Leadership and "
            "Community Protection Act creates demand for carbon-free baseload. "
            "Queue timelines typically 3-5 years for large projects."
        ),
        "source": "https://www.nyiso.com/generation-interconnection",
    },
    "fort-hood-tx": {
        "rto": "ERCOT",
        "note": (
            "Electric Reliability Council of Texas — self-contained, no FERC jurisdiction. "
            "ERCOT's interconnection queue (~350 GW pending) has moved faster than PJM "
            "historically. Texas's deregulated market offers competitive PPA pricing."
        ),
        "source": "https://www.ercot.com/mktrules/guides/interconnection",
    },
    "fort-wainwright-ak": {
        "rto": "ASEA Railbelt (GVEA — no RTO)",
        "note": (
            "Golden Valley Electric Association (GVEA) on the Railbelt grid — a ~400-mi "
            "isolated AC system. No ISO/RTO; project-by-project bilateral. "
            "An AP1000's 1,117 MW dwarfs the Railbelt's ~700 MW peak load — "
            "would require behind-the-fence configuration."
        ),
        "source": "https://www.gvea.com/about/our-grid",
    },
    "jblm-wa": {
        "rto": "Non-RTO/WECC (Puget Sound Energy / BPA)",
        "note": (
            "Puget Sound Energy (PSE) retail territory, Bonneville Power Administration (BPA) "
            "transmission grid. WECC without ISO/RTO — BPA manages bulk transmission. "
            "BPA's Columbia River hydro provides abundant balancing reserves. "
            "Bilateral process with BPA typically 3-4 years for large projects."
        ),
        "source": "https://www.bpa.gov/energy-and-services/transmission/generator-interconnection",
    },
    "jbmdl-nj": {
        "rto": "PJM (PSE&G / JCP&L)",
        "note": (
            "PJM Interconnection — largest RTO in the US (13 states + DC). "
            "Queue exceeds 1,200 GW; median timelines now approaching 7 years post-reform. "
            "A 1,117 MW AP1000 would enter the most congested interconnection queue in "
            "North America. NJ's ZEC program could reduce revenue risk."
        ),
        "source": "https://www.pjm.com/planning/interconnection-agreements",
    },
    "holston-aap-tn": {
        "rto": "TVA",
        "note": (
            "Tennessee Valley Authority — same bilateral path as Arnold AFB and Fort Campbell. "
            "Holston sits in TVA's East Tennessee territory adjacent to the Clinch River "
            "BWRX-300 site, making TVA the most institutionally prepared BA on this list "
            "for licensing and interconnecting new nuclear generation."
        ),
        "source": "https://www.tva.com/energy/our-power-system/transmission/request-for-transmission-service",
    },
    "redstone-arsenal-al": {
        "rto": "TVA",
        "note": (
            "Tennessee Valley Authority — Wheeler Reservoir on-site is a TVA-managed "
            "impoundment, reinforcing the operational relationship. "
            "NASA Marshall / Space Command mission tenants provide a high-value load "
            "anchor for a potential PPP structure with TVA."
        ),
        "source": "https://www.tva.com/energy/our-power-system/transmission/request-for-transmission-service",
    },
}


# USGS ASCE 7-22 seismic hazard — prefetched from the USGS Design Maps API
# (earthquake.usgs.gov/ws/designmaps/asce7-22.json) at Risk Category IV /
# Site Class C. Values are stable reference data; re-fetch only if coordinates
# change. AP1000 SSE threshold = 0.30g PGA — sites above need site-specific
# seismic analysis. Three of 14 sites exceed it: JBLM (2×), Fort Wainwright,
# Fort Campbell (marginally). Edwards AFB also above at 0.45g.
USGS_SEISMIC = {
    # pgam = design PGA (g), ss = MCE_R 0.2s spectral accel (g), sdc = Seismic Design Category
    "arnold-afb-tn":        {"pgam": 0.18, "ss": 0.39, "sdc": "C"},
    "davis-monthan-afb-az": {"pgam": 0.13, "ss": 0.28, "sdc": "C"},
    "edwards-afb-ca":       {"pgam": 0.45, "ss": 1.00, "sdc": "D"},
    "robins-afb-ga":        {"pgam": 0.11, "ss": 0.23, "sdc": "C"},
    "fort-benning-ga":      {"pgam": 0.07, "ss": 0.17, "sdc": "C"},
    "fort-bragg-nc":        {"pgam": 0.10, "ss": 0.23, "sdc": "C"},
    "fort-campbell-ky":     {"pgam": 0.37, "ss": 0.79, "sdc": "D"},
    "fort-drum-ny":         {"pgam": 0.12, "ss": 0.23, "sdc": "A"},
    "fort-hood-tx":         {"pgam": 0.03, "ss": 0.07, "sdc": "A"},
    "fort-wainwright-ak":   {"pgam": 0.46, "ss": 1.05, "sdc": "D"},
    "jblm-wa":              {"pgam": 0.59, "ss": 1.50, "sdc": "D"},
    "jbmdl-nj":             {"pgam": 0.12, "ss": 0.20, "sdc": "A"},
    "holston-aap-tn":       {"pgam": 0.20, "ss": 0.34, "sdc": "C"},
    "redstone-arsenal-al":  {"pgam": 0.18, "ss": 0.38, "sdc": "C"},
}

# AP1000 NRC-licensed seismic design basis (SSE = Safe Shutdown Earthquake).
# Sites with pgam > this need site-specific probabilistic seismic hazard
# analysis; the AP1000's certified design can accommodate up to 0.3g.
AP1000_SSE_THRESHOLD_G = 0.30

# Regulatory source contacts retained from July 2026 research. General basin
# rules do not establish project entitlement, so all allocation classes remain
# unknown pending a documented project-specific permit or supply contract.
WATER_RIGHTS = {
    "arnold-afb-tn": {
        "regime": "riparian (regulated)", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://www.tva.com/environment/shoreline-construction-permits",
    },
    "davis-monthan-afb-az": {
        "regime": "prior appropriation + AZ groundwater code", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://www.azwater.gov/ama/tucson-ama",
    },
    "edwards-afb-ca": {
        "regime": "hybrid (CA) — adjudicated basin", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://www.avek.org/adjudication",
    },
    "robins-afb-ga": {
        "regime": "regulated riparian (GA permit)", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://epd.georgia.gov/watershed-protection-branch/water-withdrawal-permits",
    },
    "fort-benning-ga": {
        "regime": "regulated riparian (GA permit)", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://www.supremecourt.gov/opinions/20pdf/142orig_1qm2.pdf",
    },
    "fort-bragg-nc": {
        "regime": "regulated riparian (NC)", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://www.deq.nc.gov/about/divisions/water-resources/water-planning/water-supply-planning",
    },
    "fort-campbell-ky": {
        "regime": "riparian (regulated, KY/TN)", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://eec.ky.gov/Environmental-Protection/Water/Pages/default.aspx",
    },
    "fort-drum-ny": {
        "regime": "regulated riparian (NY DEC permit)", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://dec.ny.gov/environmental-protection/water/water-withdrawals",
    },
    "fort-hood-tx": {
        "regime": "hybrid (TX) — appropriated surface water", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://www.brazos.org/About-Us/Water-Supply",
    },
    "fort-wainwright-ak": {
        "regime": "prior appropriation (AK)", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://dnr.alaska.gov/mlw/water/wrfact/",
    },
    "jblm-wa": {
        "regime": "prior appropriation (WA)", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://ecology.wa.gov/water-shorelines/water-supply/protecting-stream-flows",
    },
    "jbmdl-nj": {
        "regime": "regulated riparian (NJDEP allocation)", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://www.nj.gov/drbc/programs/project/",
    },
    "holston-aap-tn": {
        "regime": "riparian (regulated, TN)", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://www.tva.com/environment/shoreline-construction-permits",
    },
    "redstone-arsenal-al": {
        "regime": "riparian (AL — registration only)", "cls": "unknown",
        "note": "Agency/source link identifies a regulatory contact or historical context. No project-specific withdrawal entitlement, supply contract, allocation or approval outcome has been verified.",
        "source": "https://adeca.alabama.gov/water/",
    },
}


def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def _get_eia_bytes():
    """Return pinned EIA-860M bytes from the connector's binary cache or
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

    cache_dir = ROOT / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / _EIA_CACHE_FILENAME).write_bytes(data)

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
        rec["water_evidence_confidence"] = "low"
        rec["water_supply_assessment"] = "unassessed"
        rec["water_evidence_reviewed_at"] = "2026-09-12"
        rec["fiber_evidence_confidence"] = "unknown"
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
                  "power_plant_mi", "power_plant_mw", "power_plant_fuel",
                  "transmission_asset_id", "substation_asset_id", "power_plant_asset_id",
                  "substation_role", "infra_evidence", "infra_assessed_lat", "infra_assessed_lon"):
            rec[k] = src.get(k)
        rec["infra_coordinate_basis"] = "borrowed_reference_record"
        rec["infra_confidence"] = "low"

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

        # ISO/RTO grid operator — affects 1,117 MW interconnection timeline.
        go = GRID_OPERATOR.get(s["id"])
        if not go:
            raise SystemExit(f"no GRID_OPERATOR entry for {s['id']}")
        rec["iso_rto"]            = go["rto"]
        rec["iso_rto_note"]       = go["note"]
        rec["iso_rto_source_url"] = go["source"]

        # USGS ASCE 7-22 quantitative seismic hazard (prefetched stable values).
        usgs = USGS_SEISMIC.get(s["id"])
        if not usgs:
            raise SystemExit(f"no USGS_SEISMIC entry for {s['id']}")
        rec["usgs_pgam"]              = usgs["pgam"]
        rec["usgs_ss"]                = usgs["ss"]
        rec["usgs_sdc"]               = usgs["sdc"]
        rec["usgs_exceeds_sse"]       = usgs["pgam"] > AP1000_SSE_THRESHOLD_G
        rec["usgs_api_source"]        = (
            f"https://earthquake.usgs.gov/ws/designmaps/asce7-22.json"
            f"?latitude={rec['lat']}&longitude={rec['lon']}"
            f"&riskCategory=IV&siteClass=C"
        )

        # Water rights — obtainability of a new large consumptive right.
        wr = WATER_RIGHTS.get(s["id"])
        if not wr:
            raise SystemExit(f"no WATER_RIGHTS entry for {s['id']}")
        rec["water_rights_regime"]     = wr["regime"]
        rec["water_rights_class"]      = wr["cls"]
        rec["water_rights_note"]       = wr["note"]
        rec["water_rights_source_url"] = wr["source"]

        out.append(rec)

    # Share layer provenance, but only asset metadata actually referenced by
    # these fourteen rows. Do not copy the national catalog into this overlay.
    infra_metadata = {}
    for layer, metadata in (infra.get("source_metadata") or {}).items():
        if not isinstance(metadata, dict):
            infra_metadata[layer] = metadata
            continue
        selected = dict(metadata)
        if "assets_by_id" in selected:
            referenced = {r.get(layer + "_asset_id") for r in out}
            selected["assets_by_id"] = {key: value for key, value in selected["assets_by_id"].items()
                                       if key in referenced}
        infra_metadata[layer] = selected

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "analysis_verified_at": ANALYSIS_VERIFIED_AT,
        "evidence_contract_reviewed_at": "2026-09-12",
        "source_metadata": {"infra": infra_metadata},
        "source": "Curated AP1000-siting analysis overlay (analyst-researched land/water/fiber; transmission/substation joined from infra-proximity.json)",
        "source_urls": {
            "ap1000_specs": AP1000_SOURCE,
            "vogtle_workforce_scale": VOGTLE_WORKFORCE_SOURCE,
            "army_janus": JANUS_SOURCE,
            "air_force_rflp": AF_RFLP_SOURCE,
            "air_force_rflp_public_qa": AF_RFLP_ARTICLE_SOURCE,
        },
        "retired_plant_source_month": EIA_WORKBOOK_MONTH,
        "retired_plant_source_url": EIA_860M_URL,
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
