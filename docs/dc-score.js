// Composite DC suitability score (0–100).
//
// A weighted sum of the per-site signals already on disk from the
// infra-proximity + epa-redev enrichment connectors. Higher = better
// candidate for data-center or energy-generation development. Returns
// null when transmission distance is missing (the load-bearing signal —
// a site you can't power isn't a DC candidate at any size).
//
// Component caps (total 100):
//   - Transmission distance: 20
//   - Voltage (kV):          20
//   - Acreage:               25
//   - Gas pipeline:          15
//   - Logistics (highway+rail): 10
//   - Readiness (DC candidate / cleanup / active reuse): 10
//
// Bucket thresholds align with the existing DC_TIERS ladder where possible
// (≥138 / 230 / 500 kV, ≥25 / 100 / 500 ac, transmission ≤1 mi) so the
// numeric score and the tier pill never disagree about ordering.

const DC_SCORE_WEIGHTS = Object.freeze({
  transmission_distance: 20,
  voltage:               20,
  acreage:               25,
  gas_pipeline:          15,
  logistics:             10,
  readiness:             10,
});

const DC_SCORE_TOOLTIP =
  "DC suitability score (0–100). Weighted sum: transmission distance (20), " +
  "voltage (20), acreage (25), gas pipeline (15), highway + rail logistics (10), " +
  "readiness — EPA DC candidate flag, NPL cleanup status, active reuse (10). " +
  "Higher = better candidate. Sites without transmission data score N/A.";

function _scoreTransmissionDistance(mi) {
  if (mi == null) return 0;
  if (mi <= 0.05) return 20;       // adjacent / on-site
  if (mi >= 2)    return 0;        // too far
  // Linear falloff between 0.05 and 2 mi.
  return Math.round((1 - mi / 2) * 20);
}

function _scoreVoltage(kv) {
  if (kv == null) return 0;
  if (kv >= 500) return 20;
  if (kv >= 230) return 16;
  if (kv >= 138) return 12;
  if (kv >= 69)  return 8;
  return 4;
}

function _scoreAcreage(acres) {
  if (acres == null) return 0;
  if (acres >= 500) return 25;
  if (acres >= 100) return 20;
  if (acres >= 25)  return 14;
  if (acres >= 5)   return 7;
  return 2;
}

function _scoreGasPipeline(mi) {
  if (mi == null) return 0;
  if (mi <= 0.05) return 15;
  if (mi <= 1)    return 12;
  if (mi <= 5)    return 8;
  if (mi <= 15)   return 4;
  return 0;
}

function _scoreLogistics(highwayMi, railMi) {
  let s = 0;
  if (highwayMi != null) {
    if (highwayMi <= 1)       s += 5;
    else if (highwayMi <= 5)  s += 3;
    else if (highwayMi <= 15) s += 1;
  }
  if (railMi != null) {
    if (railMi <= 1)       s += 5;
    else if (railMi <= 5)  s += 3;
    else if (railMi <= 15) s += 1;
  }
  return Math.min(s, 10);
}

function _scoreReadiness(site) {
  let s = 0;
  if (site.data_center_reuse_candidate === true) s += 5;
  if (site.npl_status_code === "D") s += 3;       // cleanup complete
  else if (site.npl_status_code === "F") s += 1;  // on Final NPL
  if (typeof site.in_reuse === "string" && /^yes/i.test(site.in_reuse)) s += 2;
  return Math.min(s, 10);
}

function computeDcCompositeScore(site) {
  if (!site) return null;
  if (site.transmission_mi == null) return null;
  const total =
      _scoreTransmissionDistance(site.transmission_mi)
    + _scoreVoltage(site.transmission_kv)
    + _scoreAcreage(site.acreage)
    + _scoreGasPipeline(site.gas_pipeline_mi)
    + _scoreLogistics(site.highway_mi, site.rail_mi)
    + _scoreReadiness(site);
  return Math.max(0, Math.min(100, total));
}

function computeDcScoreBreakdown(site) {
  if (!site) return null;
  if (site.transmission_mi == null) return null;
  return {
    transmission_distance: _scoreTransmissionDistance(site.transmission_mi),
    voltage:               _scoreVoltage(site.transmission_kv),
    acreage:               _scoreAcreage(site.acreage),
    gas_pipeline:          _scoreGasPipeline(site.gas_pipeline_mi),
    logistics:             _scoreLogistics(site.highway_mi, site.rail_mi),
    readiness:             _scoreReadiness(site),
  };
}

window.computeDcCompositeScore = computeDcCompositeScore;
window.computeDcScoreBreakdown = computeDcScoreBreakdown;
window.DC_SCORE_WEIGHTS = DC_SCORE_WEIGHTS;
window.DC_SCORE_TOOLTIP = DC_SCORE_TOOLTIP;
