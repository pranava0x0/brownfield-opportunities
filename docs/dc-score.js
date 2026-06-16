// Site suitability scoring — two complementary lenses, both 0–100.
//
// Every signal here is already on disk from the infra-proximity +
// epa-redev + opportunity-zone + iso-rto enrichment connectors. The
// scorers are pure / deterministic so a buyer can reason about why a
// site ranks where it does — no ML, no hidden state.
//
//   computeDcCompositeScore(site)   — siting a data-center LOAD.
//   computeGenerationScore(site)    — siting NEW power GENERATION.
//
// The two lenses share machinery (transmission, voltage, substation,
// gas, acreage, flood penalty) but weight it differently, because what
// makes a parcel good for a 200 MW compute load is not what makes it
// good for a 200 MW solar/gas/storage build:
//
//   • A data center wants to be NEAR existing power it can buy —
//     transmission, a substation to interconnect, and ideally an
//     existing plant for a PPA / behind-the-meter deal. Footprint
//     matters but tops out around hyperscale (~500 ac).
//   • New generation wants LAND first (solar is ~5–8 ac/MW), a way to
//     EXPORT what it makes (transmission + substation to interconnect),
//     gas feedstock for thermal builds, and an organized market
//     (ISO/RTO) to clear the interconnection queue and sell into.
//     Co-location with an ACTIVE plant is irrelevant — you ARE the
//     plant — and a site already "in reuse" is a liability, not a plus,
//     because the land is occupied. A RETIRED plant is the opposite:
//     reusing its interconnection position is the canonical repowering
//     play (coal-to-solar / coal-to-storage / coal-to-gas), so the
//     generation lens carries a grid_reuse component fed by the
//     EIA-860M retired_plant_* fields.
//
// Continuous signals (distances, acreage, MW) score on piecewise-linear
// curves via _interp() rather than hard steps — a 99-acre parcel should
// not score 5 points below a 100-acre one. Voltage stays class-stepped
// because real lines come in discrete standard classes (69/138/230/500).
//
// Both lenses gate on transmission distance: a site with no grid within
// the connector's 100-mi window can neither be powered (DC) nor
// interconnect its output (generation), so the score is null, not 0 —
// "we can't assess this" is different from "this is bad."
//
// Both apply a Special-Flood-Hazard-Area penalty: a site inside FEMA's
// 1%-annual-chance floodplain (in_sfha === true) effectively can't be
// permitted as critical infrastructure without expensive elevation /
// flood-proofing. It's a strong negative but mitigable, so it subtracts
// rather than zeroing the score. in_sfha === null (unmapped / not yet
// backfilled) is NOT penalized — absence of evidence isn't evidence.

// ---------------------------------------------------------------------------
// Shared component scorers. Each returns points on a 0..cap scale; the
// per-lens weight tables below pick the cap.
// ---------------------------------------------------------------------------

// Piecewise-linear interpolation through ascending [x, frac] anchors.
// Clamps outside the anchor range. The anchors ARE the documented
// design intent; interpolation just removes the arbitrary cliffs
// between them.
function _interp(x, pts) {
  if (x <= pts[0][0]) return pts[0][1];
  const last = pts[pts.length - 1];
  if (x >= last[0]) return last[1];
  for (let i = 1; i < pts.length; i++) {
    if (x <= pts[i][0]) {
      const x0 = pts[i - 1][0], y0 = pts[i - 1][1];
      const x1 = pts[i][0],     y1 = pts[i][1];
      return y0 + ((x - x0) / (x1 - x0)) * (y1 - y0);
    }
  }
  return last[1];
}

// Distance to the nearest transmission line, linear falloff 0.05→2 mi.
// The load-bearing signal for both lenses — adjacent is full marks,
// ≥2 mi is zero. (DC-lens shape: a compute load effectively has to sit
// AT the grid; it can't amortize a long private line.)
function _scoreTransmissionDistance(mi, cap) {
  if (mi == null) return 0;
  if (mi <= 0.05) return cap;     // adjacent / on-site
  if (mi >= 2)    return 0;       // too far to matter
  return Math.round((1 - mi / 2) * cap);
}

// Generation-lens transmission distance — longer reach than the DC
// curve. Utility-scale projects routinely build gen-tie lines of
// several miles (~$1–2M/mi against a nine-figure build), so the value
// decays gently to zero at 10 mi instead of cliffing at 2.
function _scoreTransmissionDistanceGen(mi, cap) {
  if (mi == null) return 0;
  return Math.round(_interp(mi, [[0.05, 1.0], [2, 0.55], [10, 0]]) * cap);
}

// Nominal kV of the nearest line. Higher class = more transfer capacity
// (to import for a DC, or export for generation).
function _scoreVoltage(kv, cap) {
  if (kv == null) return 0;
  let frac;
  if (kv >= 500)      frac = 1.0;   // EHV — mega-campus / large gen export
  else if (kv >= 230) frac = 0.8;   // hyperscale-grade
  else if (kv >= 138) frac = 0.6;   // colo-grade
  else if (kv >= 69)  frac = 0.4;   // sub-transmission
  else                frac = 0.2;   // distribution-class
  return Math.round(frac * cap);
}

// Distance to the nearest substation — the actual point of
// interconnection. A 500 kV line 0.3 mi away is worthless without a
// substation close enough to tap, which is why this is a distinct
// component from transmission distance.
//
// The OSM `power=substation` source includes thousands of small
// distribution substations that can't serve (or export) bulk power, so
// when the voltage tag PROVES distribution class the distance score is
// discounted. A null kv is NOT discounted — ~27% of records lack the
// tag, and absence of evidence isn't evidence (same principle as the
// flood / climate null handling).
function _scoreSubstation(mi, kv, cap) {
  if (mi == null) return 0;
  const dist = _interp(mi, [[0.5, 1.0], [2, 0.75], [5, 0.5], [10, 0.25], [15, 0]]);
  let quality = 1.0;
  if (kv != null) {
    if (kv < 69)       quality = 0.5;   // distribution-class — not a bulk POI
    else if (kv < 115) quality = 0.75;  // sub-transmission — limited headroom
  }
  return Math.round(dist * quality * cap);
}

// Capacity fraction shared by every plant pathway. The MW of the plant
// bounds what the interconnection position is worth: a 100 MW POI can't
// host a hyperscale campus (300+ MW), while ≥1 GW covers any single
// build. Interpolated so 2,151 MW ≠ 100 MW (they previously both earned
// full credit).
function _mwFrac(mw) {
  return _interp(mw, [[100, 0.5], [500, 0.85], [1000, 1.0]]);
}

// Recency multiplier for a RETIRED plant's interconnection value. FERC
// interconnection service lapses after permanent retirement and the
// freed transmission headroom gets reabsorbed by the queue over time —
// the Homer City (retired 2023) pattern works because the switchyard,
// ROW, and network upgrades are still in place. A 2002 retirement
// keeps the corridor but has almost certainly lost the queue position.
// Absolute-year buckets keep the score deterministic; re-baseline them
// on the annual audit pass (same rhythm as STATE_DC_INCENTIVES).
function _retirementRecency(year) {
  if (year == null)  return 1.0;   // unknown — don't punish
  if (year >= 2018)  return 1.0;   // fresh — interconnect typically intact
  if (year >= 2008)  return 0.75;  // infrastructure persists, capacity contested
  return 0.5;                      // corridor only — agreement long gone
}

// 0..1 fraction of inheritance value from an EIA-860M confirmed-retired
// plant. ≤1 mi means the site effectively IS (or abuts) the plant
// property — full credit. 1–3 mi is "next to a freed-up grid node":
// the local headroom argument still holds but the POI itself isn't
// acquirable, so half credit. Non-dispatchable (solar/wind/geothermal)
// retirements don't leave behind a firm interconnect and score 0.
function _retiredPlantFrac(site) {
  const mi = site.retired_plant_mi, mw = site.retired_plant_mw;
  if (mi == null || mi > 3 || mw == null || mw < 100) return 0;
  const fuel = (site.retired_plant_fuel || "").toLowerCase();
  // Non-dispatchable: EIA codes SUN/WND/GEO/LFG/MSW or HIFLD text solar/wind/geothermal
  if (/^(sun|wnd|geo|lfg|msw|obs|wds|ab|blq|slw|tdf)$/.test(fuel)
      || /solar|wind|geothermal/i.test(fuel)) return 0;
  let frac = _mwFrac(mw) * _retirementRecency(site.retired_plant_year);
  if (mi > 1) frac *= 0.5;
  return frac;
}

// "Grid Inherit" signal — DC lens. A retired coal/gas plant nearby may
// carry an inheritable FERC interconnection position, bypassing PJM's
// 5–7-year queue (the Homer City / Widows Creek pattern). All pathways
// scale by _mwFrac — capacity bounds what the position is worth.
//
// 1. EIA-860M confirmed-retired plant (preferred): ≥100 MW dispatchable,
//    ≤1 mi full / 1–3 mi half, × retirement recency.
// 2. HIFLD active coal/gas ≥500 MW ≤1 mi — behind-the-meter / direct PPA
//    (the Conesville / Widows Creek pattern with an operating plant).
// 3. Operating nuclear ≥500 MW within 5 mi → 45%. The AWS/Talen
//    Susquehanna deal ($650M, 2023) confirms nuclear proximity as a DC
//    signal: 24/7 carbon-free baseload, stable voltage, PPA pathway even
//    when behind-the-fence direct connect is blocked (FERC 2024). Radius
//    is wider because nuclear connects high in the transmission
//    hierarchy; capped at 45% because the interconnect is NOT stranded.
// 4. Active coal/gas ≥500 MW 1–5 mi → 30% — the same PPA-neighborhood
//    logic as nuclear but weaker: hyperscalers' carbon-free-energy
//    targets price thermal PPAs below nuclear ones.
function _scoreGridInheritance(site, cap) {
  const retired = _retiredPlantFrac(site);
  if (retired > 0) return Math.round(cap * retired);

  const mi = site.power_plant_mi, mw = site.power_plant_mw;
  if (mi == null || mw == null || mw < 500) return 0;
  const fuel = site.power_plant_fuel || "";
  if (mi <= 1 && /coal|natural gas/i.test(fuel)) {
    return Math.round(cap * _mwFrac(mw));
  }
  if (mi <= 5 && /nuclear/i.test(fuel)) {
    return Math.round(cap * 0.45 * _mwFrac(mw));
  }
  if (mi <= 5 && /coal|natural gas/i.test(fuel)) {
    return Math.round(cap * 0.3 * _mwFrac(mw));
  }
  return 0;
}

// "Grid reuse" signal — generation lens. Repowering a RETIRED plant's
// interconnection position (coal-to-solar / coal-to-storage / coal-to-
// gas) is the canonical way a new-generation build skips the queue —
// distinct from active-plant co-location, which is worthless when you
// ARE the plant, and so intentionally not credited here.
function _scoreGridReuse(site, cap) {
  return Math.round(cap * _retiredPlantFrac(site));
}

// Distance to the nearest natural-gas pipeline. Enables behind-the-meter
// gas turbines (DC bridge power) or gas-fired generation feedstock.
// A lateral past ~30 mi isn't economic for either use, so the tail
// tapers to zero there instead of cliffing at 15.
function _scoreGasPipeline(mi, cap) {
  if (mi == null) return 0;
  return Math.round(_interp(mi, [[0.05, 1.0], [1, 0.8], [5, 0.55], [15, 0.27], [30, 0]]) * cap);
}

// DC acreage curve — footprint matters but saturates at the hyperscale
// threshold (~500 ac); a 50,000-acre parcel is no better than a 500-acre
// one for a single campus.
function _scoreAcreageDc(acres, cap) {
  if (acres == null) return 0;
  return Math.round(_interp(acres, [[0, 0], [5, 0.25], [25, 0.55], [100, 0.8], [500, 1.0]]) * cap);
}

// Generation acreage curve — land is the dominant constraint and bigger
// is genuinely better (utility-scale solar/wind scales with acreage), so
// the curve keeps climbing past where the DC curve flattens.
function _scoreAcreageGen(acres, cap) {
  if (acres == null) return 0;
  return Math.round(_interp(acres,
    [[0, 0], [5, 0.08], [25, 0.22], [100, 0.45], [250, 0.65], [500, 0.85], [1000, 1.0]]) * cap);
}

// Highway + rail proximity (DC-only) — construction logistics, equipment
// delivery. Minor relative to power, capped low.
function _scoreLogistics(highwayMi, railMi, cap) {
  let s = 0;
  const each = cap / 2;
  for (const mi of [highwayMi, railMi]) {
    if (mi == null) continue;
    if (mi <= 1)       s += each;
    else if (mi <= 5)  s += each * 0.6;
    else if (mi <= 15) s += each * 0.2;
  }
  return Math.min(Math.round(s), cap);
}

const _ORGANIZED_RTOS = new Set([
  "PJM", "MISO", "ERCOT", "CAISO", "SPP", "NYISO", "ISO-NE",
]);

// ISO/RTO membership (generation-only) — an organized market means a
// defined interconnection queue and a place to sell the output. A
// bilateral / non-RTO region (or any unrecognized value) is workable
// but harder, so it scores half.
function _scoreIsoRto(iso, cap) {
  if (iso == null) return 0;
  return _ORGANIZED_RTOS.has(iso) ? cap : Math.round(cap * 0.5);
}

// SFHA flood penalty — subtracted from both lenses. Only when explicitly
// inside the 1%-annual-chance floodplain; unmapped (null) is not charged.
function _floodPenalty(site) {
  return site.in_sfha === true ? FLOOD_SFHA_PENALTY : 0;
}

const FLOOD_SFHA_PENALTY = 18;

// FEMA NRI climate penalty — subtracted from both lenses. Driven by the two
// operationally-deal-affecting hazards: wildfire (insurability / continuity)
// and drought (cooling-water availability). Takes the MAX severity across the
// two so a Very-High in either charges the full penalty; null/unrated is not
// charged (absence of evidence ≠ low risk). Heat wave is displayed but not
// penalized — it raises cooling cost but rarely blocks a project.
const CLIMATE_PENALTY_VERY_HIGH = 10;
const CLIMATE_PENALTY_REL_HIGH = 5;

function _climatePenalty(site) {
  let worst = 0;
  for (const r of [site.nri_wildfire_rating, site.nri_drought_rating]) {
    if (r === "Very High") worst = Math.max(worst, CLIMATE_PENALTY_VERY_HIGH);
    else if (r === "Relatively High") worst = Math.max(worst, CLIMATE_PENALTY_REL_HIGH);
  }
  return worst;
}

// ---------------------------------------------------------------------------
// Lens 1 — data-center LOAD suitability. Positive caps sum to 100; the
// flood penalty pushes below that and the result is clamped to [0,100].
// ---------------------------------------------------------------------------

const DC_SCORE_WEIGHTS = Object.freeze({
  transmission_distance: 16,
  voltage:               14,
  substation:            12,
  grid_inheritance:       8,  // large coal/gas ≥500 MW ≤1 mi (was generic power_plant)
  acreage:               20,
  gas_pipeline:          10,
  logistics:              6,
  readiness:             14,
});

const DC_SCORE_TOOLTIP =
  "Data-center suitability (0–100). Weighted sum of power access — " +
  "transmission distance (16), voltage (14), substation (12), grid " +
  "inheritance (8: retired or large coal/gas/nuclear plant nearby, " +
  "scaled by MW and retirement recency) — plus acreage (20), gas " +
  "pipeline (10), highway+rail logistics (6), and readiness (14: EPA " +
  "DC flag, cleanup status, reuse, Opportunity Zone). A Special Flood " +
  "Hazard Area subtracts 18. Sites without transmission data score N/A.";

// readiness for a data-center load: signals that the parcel is ready to
// transact and develop. Cap 14 (sub-signals can sum well above it; the
// financial sweeteners — OZ, IRA energy community — get absorbed by the cap
// on a fully-ready site but lift mid-tier sites).
function _scoreReadinessDc(site) {
  let s = 0;
  if (site.data_center_reuse_candidate === true) s += 5;
  if (site.npl_status_code === "D") s += 3;       // cleanup complete
  else if (site.npl_status_code === "F") s += 1;  // on Final NPL
  if (typeof site.in_reuse === "string" && /^yes/i.test(site.in_reuse)) s += 2;
  // EPA SWRAU "all land ready for anticipated use" — the strongest public
  // per-site land-availability signal. Only the affirmative determinations
  // count (not "Does Not Meet" / "(Retracted)").
  if (typeof site.rau_status === "string" && /^Meets the Measure/i.test(site.rau_status)) s += 3;
  if (site.in_opportunity_zone === true) {
    // Rural OZ: 30% QOF basis step-up vs. 15% for standard → +7 vs +5
    s += site.oz_rural === true ? 7 : 5;
  }
  // IRA energy community: +10pp ITC/PTC bonus on a paired behind-the-meter
  // clean-energy build. A meaningful IRR lever that stacks with OZ.
  if (site.in_energy_community === true) s += 3;
  // EO 14318 "federal fast lane": superfund/brownfield ≥100 ac, grid ≤2 mi,
  // outside SFHA → NEPA categorical exclusion + fast-track Section 404.
  if ((site.program === "superfund" || site.program === "brownfield")
      && site.acreage != null && site.acreage >= 100
      && site.transmission_mi != null && site.transmission_mi <= 2
      && site.in_sfha !== true) {
    s += 3;
  }
  return Math.min(s, DC_SCORE_WEIGHTS.readiness);
}

function computeDcScoreBreakdown(site) {
  if (!site) return null;
  if (site.transmission_mi == null) return null;
  const W = DC_SCORE_WEIGHTS;
  return {
    transmission_distance: _scoreTransmissionDistance(site.transmission_mi, W.transmission_distance),
    voltage:               _scoreVoltage(site.transmission_kv, W.voltage),
    substation:            _scoreSubstation(site.substation_mi, site.substation_kv, W.substation),
    grid_inheritance:      _scoreGridInheritance(site, W.grid_inheritance),
    acreage:               _scoreAcreageDc(site.acreage, W.acreage),
    gas_pipeline:          _scoreGasPipeline(site.gas_pipeline_mi, W.gas_pipeline),
    logistics:             _scoreLogistics(site.highway_mi, site.rail_mi, W.logistics),
    readiness:             _scoreReadinessDc(site),
    flood_penalty:        -_floodPenalty(site),
    climate_penalty:      -_climatePenalty(site),
  };
}

function computeDcCompositeScore(site) {
  const bd = computeDcScoreBreakdown(site);
  if (bd == null) return null;
  const total = Object.values(bd).reduce((a, b) => a + b, 0);
  return Math.max(0, Math.min(100, total));
}

// ---------------------------------------------------------------------------
// Lens 2 — new-GENERATION suitability. Positive caps sum to 100; flood
// penalty subtracts; clamped to [0,100].
// ---------------------------------------------------------------------------

const GENERATION_SCORE_WEIGHTS = Object.freeze({
  acreage:               24,   // land is the dominant constraint
  transmission_distance: 18,   // a way to export the output (gen-tie reach to 10 mi)
  substation:            14,   // the actual interconnection point
  voltage:               12,   // export headroom
  gas_pipeline:          10,   // gas-fired feedstock
  grid_reuse:             8,   // retired-plant interconnection repowering
  iso_rto:                8,   // organized market = clearer queue + offtake
  readiness:              6,   // developable / clean / incentivized land
});

const GENERATION_SCORE_TOOLTIP =
  "Power-generation siting suitability (0–100). Weighted for building NEW " +
  "generation: acreage (24), transmission distance to export (18), " +
  "substation interconnection (14), voltage headroom (12), gas-pipeline " +
  "feedstock (10), retired-plant grid reuse (8: the repowering play), " +
  "ISO/RTO market (8), readiness (6). A Special Flood Hazard Area " +
  "subtracts 18. Unlike the DC score it ignores ACTIVE-plant co-location " +
  "(you ARE the plant) and doesn't reward active reuse (occupied land). " +
  "Sites without transmission data score N/A.";

// readiness for a generation build: a cleaned-up, vacant, incentivized
// parcel is ideal. Deliberately does NOT credit `in_reuse` — an
// occupied site is worse for a ground-up build, not better. The IRA energy
// community bonus is especially relevant here: the +10pp ITC/PTC applies
// directly to a new clean-generation build, so it earns more than OZ.
function _scoreReadinessGen(site) {
  let s = 0;
  if (site.npl_status_code === "D") s += 4;       // cleanup complete → developable
  if (site.in_energy_community === true) s += 3;  // +10pp ITC/PTC on the build
  // EPA SWRAU "all land ready for anticipated use" — developable signal.
  if (typeof site.rau_status === "string" && /^Meets the Measure/i.test(site.rau_status)) s += 2;
  if (site.in_opportunity_zone === true) s += 2;  // financing sweetener
  return Math.min(s, GENERATION_SCORE_WEIGHTS.readiness);
}

function computeGenerationScoreBreakdown(site) {
  if (!site) return null;
  if (site.transmission_mi == null) return null;
  const W = GENERATION_SCORE_WEIGHTS;
  return {
    acreage:               _scoreAcreageGen(site.acreage, W.acreage),
    transmission_distance: _scoreTransmissionDistanceGen(site.transmission_mi, W.transmission_distance),
    substation:            _scoreSubstation(site.substation_mi, site.substation_kv, W.substation),
    voltage:               _scoreVoltage(site.transmission_kv, W.voltage),
    gas_pipeline:          _scoreGasPipeline(site.gas_pipeline_mi, W.gas_pipeline),
    grid_reuse:            _scoreGridReuse(site, W.grid_reuse),
    iso_rto:               _scoreIsoRto(site.iso_rto, W.iso_rto),
    readiness:             _scoreReadinessGen(site),
    flood_penalty:        -_floodPenalty(site),
    climate_penalty:      -_climatePenalty(site),
  };
}

function computeGenerationScore(site) {
  const bd = computeGenerationScoreBreakdown(site);
  if (bd == null) return null;
  const total = Object.values(bd).reduce((a, b) => a + b, 0);
  return Math.max(0, Math.min(100, total));
}

// ---------------------------------------------------------------------------

window.computeDcCompositeScore = computeDcCompositeScore;
window.computeDcScoreBreakdown = computeDcScoreBreakdown;
window.computeGenerationScore = computeGenerationScore;
window.computeGenerationScoreBreakdown = computeGenerationScoreBreakdown;
window.DC_SCORE_WEIGHTS = DC_SCORE_WEIGHTS;
window.DC_SCORE_TOOLTIP = DC_SCORE_TOOLTIP;
window.GENERATION_SCORE_WEIGHTS = GENERATION_SCORE_WEIGHTS;
window.GENERATION_SCORE_TOOLTIP = GENERATION_SCORE_TOOLTIP;
window.FLOOD_SFHA_PENALTY = FLOOD_SFHA_PENALTY;
window.CLIMATE_PENALTY_VERY_HIGH = CLIMATE_PENALTY_VERY_HIGH;
window.CLIMATE_PENALTY_REL_HIGH = CLIMATE_PENALTY_REL_HIGH;
