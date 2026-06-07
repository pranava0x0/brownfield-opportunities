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
//     Co-location with an existing plant is irrelevant — you ARE the
//     plant — and a site already "in reuse" is a liability, not a plus,
//     because the land is occupied.
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

// Distance to the nearest transmission line, linear falloff 0.05→2 mi.
// The load-bearing signal for both lenses — adjacent is full marks,
// ≥2 mi is zero.
function _scoreTransmissionDistance(mi, cap) {
  if (mi == null) return 0;
  if (mi <= 0.05) return cap;     // adjacent / on-site
  if (mi >= 2)    return 0;       // too far to matter
  return Math.round((1 - mi / 2) * cap);
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
function _scoreSubstation(mi, cap) {
  if (mi == null) return 0;
  let frac;
  if (mi <= 0.5)     frac = 1.0;
  else if (mi <= 2)  frac = 0.75;
  else if (mi <= 5)  frac = 0.5;
  else if (mi <= 10) frac = 0.25;
  else               frac = 0;
  return Math.round(frac * cap);
}

// "Grid Inherit" signal — DC-only. A retired coal/gas plant ≥500 MW within
// 1 mi may carry an inheritable FERC interconnection agreement, bypassing
// PJM's 5–7-year queue (the Homer City / Widows Creek pattern). Only large
// dispatchable capacity qualifies; generic proximity is intentionally not
// rewarded here since the strategic value is the queue bypass, not just
// having a plant nearby.
function _scoreGridInheritance(site, cap) {
  if (site.power_plant_mi == null || site.power_plant_mi > 1) return 0;
  if (site.power_plant_mw == null || site.power_plant_mw < 500) return 0;
  if (site.power_plant_fuel == null) return 0;
  if (!/coal|natural gas/i.test(site.power_plant_fuel)) return 0;
  return cap;
}

// Distance to the nearest natural-gas pipeline. Enables behind-the-meter
// gas turbines (DC bridge power) or gas-fired generation feedstock.
function _scoreGasPipeline(mi, cap) {
  if (mi == null) return 0;
  if (mi <= 0.05) return cap;
  if (mi <= 1)    return Math.round(cap * 0.8);
  if (mi <= 5)    return Math.round(cap * 0.55);
  if (mi <= 15)   return Math.round(cap * 0.27);
  return 0;
}

// DC acreage curve — footprint matters but saturates at the hyperscale
// threshold (~500 ac); a 50,000-acre parcel is no better than a 500-acre
// one for a single campus.
function _scoreAcreageDc(acres, cap) {
  if (acres == null) return 0;
  if (acres >= 500) return cap;
  if (acres >= 100) return Math.round(cap * 0.8);
  if (acres >= 25)  return Math.round(cap * 0.55);
  if (acres >= 5)   return Math.round(cap * 0.25);
  return Math.round(cap * 0.05);
}

// Generation acreage curve — land is the dominant constraint and bigger
// is genuinely better (utility-scale solar/wind scales with acreage), so
// the curve keeps climbing past where the DC curve flattens.
function _scoreAcreageGen(acres, cap) {
  if (acres == null) return 0;
  if (acres >= 1000) return cap;
  if (acres >= 500)  return Math.round(cap * 0.85);
  if (acres >= 250)  return Math.round(cap * 0.65);
  if (acres >= 100)  return Math.round(cap * 0.45);
  if (acres >= 25)   return Math.round(cap * 0.22);
  if (acres >= 5)    return Math.round(cap * 0.08);
  return 0;
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
// bilateral / non-RTO region is workable but harder, so it scores half.
function _scoreIsoRto(iso, cap) {
  if (iso == null) return 0;
  if (_ORGANIZED_RTOS.has(iso)) return cap;
  if (iso === "non-RTO")        return Math.round(cap * 0.5);
  return Math.round(cap * 0.5);  // any other lower-48 value
}

// SFHA flood penalty — subtracted from both lenses. Only when explicitly
// inside the 1%-annual-chance floodplain; unmapped (null) is not charged.
function _floodPenalty(site) {
  return site.in_sfha === true ? FLOOD_SFHA_PENALTY : 0;
}

const FLOOD_SFHA_PENALTY = 18;

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
  "inheritance (8: coal/gas ≥500 MW within 1 mi) — plus acreage (20), " +
  "gas pipeline (10), highway+rail logistics (6), and readiness (14: EPA " +
  "DC flag, cleanup status, reuse, Opportunity Zone). A Special Flood " +
  "Hazard Area subtracts 18. Sites without transmission data score N/A.";

// readiness for a data-center load: signals that the parcel is ready to
// transact and develop. Cap 14 (sub-signals can sum to 15; OZ is the
// financial sweetener that gets absorbed by the cap on a fully-ready site).
function _scoreReadinessDc(site) {
  let s = 0;
  if (site.data_center_reuse_candidate === true) s += 5;
  if (site.npl_status_code === "D") s += 3;       // cleanup complete
  else if (site.npl_status_code === "F") s += 1;  // on Final NPL
  if (typeof site.in_reuse === "string" && /^yes/i.test(site.in_reuse)) s += 2;
  if (site.in_opportunity_zone === true) {
    // Rural OZ: 30% QOF basis step-up vs. 15% for standard → +7 vs +5
    s += site.oz_rural === true ? 7 : 5;
  }
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
    substation:            _scoreSubstation(site.substation_mi, W.substation),
    grid_inheritance:      _scoreGridInheritance(site, W.grid_inheritance),
    acreage:               _scoreAcreageDc(site.acreage, W.acreage),
    gas_pipeline:          _scoreGasPipeline(site.gas_pipeline_mi, W.gas_pipeline),
    logistics:             _scoreLogistics(site.highway_mi, site.rail_mi, W.logistics),
    readiness:             _scoreReadinessDc(site),
    flood_penalty:        -_floodPenalty(site),
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
  acreage:               28,   // land is the dominant constraint
  transmission_distance: 18,   // a way to export the output
  substation:            16,   // the actual interconnection point
  voltage:               12,   // export headroom
  gas_pipeline:          12,   // gas-fired feedstock
  iso_rto:                8,   // organized market = clearer queue + offtake
  readiness:              6,   // developable / clean / incentivized land
});

const GENERATION_SCORE_TOOLTIP =
  "Power-generation siting suitability (0–100). Weighted for building NEW " +
  "generation: acreage (28), transmission distance to export (18), " +
  "substation interconnection (16), voltage headroom (12), gas-pipeline " +
  "feedstock (12), ISO/RTO market (8), readiness (6). A Special Flood " +
  "Hazard Area subtracts 18. Unlike the DC score it ignores power-plant " +
  "co-location (you ARE the plant) and doesn't reward active reuse " +
  "(occupied land). Sites without transmission data score N/A.";

// readiness for a generation build: a cleaned-up, vacant, incentivized
// parcel is ideal. Deliberately does NOT credit `in_reuse` — an
// occupied site is worse for a ground-up build, not better.
function _scoreReadinessGen(site) {
  let s = 0;
  if (site.npl_status_code === "D") s += 4;       // cleanup complete → developable
  if (site.in_opportunity_zone === true) s += 2;  // financing sweetener
  return Math.min(s, GENERATION_SCORE_WEIGHTS.readiness);
}

function computeGenerationScoreBreakdown(site) {
  if (!site) return null;
  if (site.transmission_mi == null) return null;
  const W = GENERATION_SCORE_WEIGHTS;
  return {
    acreage:               _scoreAcreageGen(site.acreage, W.acreage),
    transmission_distance: _scoreTransmissionDistance(site.transmission_mi, W.transmission_distance),
    substation:            _scoreSubstation(site.substation_mi, W.substation),
    voltage:               _scoreVoltage(site.transmission_kv, W.voltage),
    gas_pipeline:          _scoreGasPipeline(site.gas_pipeline_mi, W.gas_pipeline),
    iso_rto:               _scoreIsoRto(site.iso_rto, W.iso_rto),
    readiness:             _scoreReadinessGen(site),
    flood_penalty:        -_floodPenalty(site),
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
