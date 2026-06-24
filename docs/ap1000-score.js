// AP1000 nuclear-reactor siting suitability — a single 0–100 lens over the
// 14 curated military installations in docs/data/ap1000-sites.json.
//
// Scope follows the user's priority order: developable acreage first, cooling
// water second, electrical infrastructure third (transmission + substation),
// then construction workforce and fiber. Water remains heavily weighted because
// a Westinghouse AP1000 (1,117 MWe net, ~3,400 MWth) rejects ~2,300 MWth and,
// on a closed-cycle cooling tower, needs ~30–40 MGD makeup withdrawal /
// ~15–20 MGD consumptive — a binding physical constraint for a thermal reactor.
//
// NOT in the score (deliberately, to honor the five-factor scope): seismic and
// flood. Both are genuinely deal-affecting for a nuclear build — Edwards,
// Fort Campbell, JBLM and Fort Wainwright all carry real flags — so the data
// file ships seismic_flag / flood_flag and the UI surfaces them as prominent
// context, just not folded into the number.
//
// Pure / deterministic, same contract as dc-score.js: a reader can reconstruct
// exactly why a base ranks where it does.

// Piecewise-linear interpolation through ascending [x, frac] anchors; clamps
// outside the range. (Same helper shape as dc-score.js — the anchors ARE the
// documented intent.)
function _ap1000Interp(x, pts) {
  if (x == null) return 0;
  if (x <= pts[0][0]) return pts[0][1];
  const last = pts[pts.length - 1];
  if (x >= last[0]) return last[1];
  for (let i = 1; i < pts.length; i++) {
    if (x <= pts[i][0]) {
      const x0 = pts[i - 1][0], y0 = pts[i - 1][1];
      const x1 = pts[i][0], y1 = pts[i][1];
      return y0 + ((x - x0) / (x1 - x0)) * (y1 - y0);
    }
  }
  return last[1];
}

// Positive caps sum to exactly 100.
const AP1000_WEIGHTS = Object.freeze({
  acreage:      30,   // hundreds-to-thousands of contiguous acres
  water:        27,   // on-site/nearby cooling source and water infrastructure
  transmission: 14,   // export ~1,117 MW: HV line, close
  substation:   10,   // actual point of interconnection / switchyard proxy
  workforce:    13,   // skilled construction labor within ~1 hr
  fiber:         6,   // controls/comms — useful, but least differentiating here
});

const AP1000_SCORE_TOOLTIP =
  "AP1000 siting suitability (0–100). Weighted in priority order: " +
  "developable acreage (30), cooling water (27), electrical infrastructure " +
  "(24 total: transmission distance+voltage 14 + substation distance+voltage " +
  "10), construction workforce within ~1 hr (13), and fiber (6). Seismic " +
  "and flood are shown as flags but NOT scored. " +
  "Water/acreage/workforce/fiber are analyst-researched (no federal GIS layer " +
  "exists); transmission/substation are computed from the project's infra-" +
  "proximity spatial index.";

// Cooling-water adequacy → fraction. The rating already folds in source type
// and reach (e.g. Fort Campbell is "marginal" precisely because its abundant
// river is 12+ mi away and downhill), so this is a direct map.
const _AP1000_WATER_FRAC = { abundant: 1.0, adequate: 0.62, marginal: 0.33, poor: 0.12 };

function _ap1000ScoreWater(site, cap) {
  const f = _AP1000_WATER_FRAC[(site.water_adequacy || "").toLowerCase()];
  return f == null ? 0 : Math.round(f * cap);
}

// Fiber connectivity → fraction.
const _AP1000_FIBER_FRAC = { excellent: 1.0, good: 0.75, moderate: 0.5, limited: 0.25 };

function _ap1000ScoreFiber(site, cap) {
  const f = _AP1000_FIBER_FRAC[(site.fiber || "").toLowerCase()];
  return f == null ? 0 : Math.round(f * cap);
}

// Construction-workforce availability within ~1 hour → fraction. A multi-year
// build peaking at several thousand trades is far cheaper and lower-risk next
// to a real labor pool than at a remote site that must import and camp labor.
const _AP1000_WORKFORCE_FRAC = { strong: 1.0, good: 0.72, moderate: 0.45, limited: 0.18 };

function _ap1000ScoreWorkforce(site, cap) {
  const f = _AP1000_WORKFORCE_FRAC[(site.workforce || "").toLowerCase()];
  return f == null ? 0 : Math.round(f * cap);
}

// Developable acreage. A nuclear plant needs ~500+ contiguous acres (power
// block + exclusion-area boundary + buffer); every site here clears that, so
// the curve mainly rewards siting flexibility (buffer, EPZ, future units) and
// flattens past ~10k where extra land stops mattering for one plant.
function _ap1000ScoreAcreage(acres, cap) {
  return Math.round(_ap1000Interp(acres,
    [[0, 0], [300, 0.30], [500, 0.45], [1000, 0.60], [2500, 0.75],
     [10000, 0.92], [40000, 1.0]]) * cap);
}

// Nominal-kV → fraction of capacity value. Exporting ~1,117 MW really wants
// ≥230 kV; 115/138 kV implies major network upgrades, so it's discounted.
function _ap1000VoltFrac(kv) {
  if (kv == null) return 0;
  if (kv >= 500) return 1.0;
  if (kv >= 345) return 0.9;
  if (kv >= 230) return 0.8;
  if (kv >= 161) return 0.6;
  if (kv >= 138) return 0.5;
  if (kv >= 115) return 0.4;
  if (kv >= 69)  return 0.25;
  return 0.12;
}

// Transmission = distance (nuclear can build a gen-tie a few miles, but
// closer is much better) blended with line voltage, ~60/40.
function _ap1000ScoreTransmission(site, cap) {
  if (site.transmission_mi == null) return 0;
  const dist = _ap1000Interp(site.transmission_mi,
    [[0.1, 1.0], [1, 0.8], [2, 0.6], [5, 0.35], [10, 0.12], [20, 0]]);
  const volt = _ap1000VoltFrac(site.transmission_kv);
  return Math.round((0.6 * dist + 0.4 * volt) * cap);
}

// Substation = distance blended with voltage, ~55/45. Voltage matters a lot
// here: a 1,117 MW interconnection needs a bulk (≥230 kV) substation/
// switchyard — a distribution-class (≤69 kV) substation can't serve and
// implies a brand-new switchyard build, so it's heavily discounted.
function _ap1000ScoreSubstation(site, cap) {
  if (site.substation_mi == null) return 0;
  const dist = _ap1000Interp(site.substation_mi,
    [[0.5, 1.0], [2, 0.75], [5, 0.45], [10, 0.2], [15, 0]]);
  const volt = _ap1000VoltFrac(site.substation_kv);
  return Math.round((0.55 * dist + 0.45 * volt) * cap);
}

function computeAp1000Breakdown(site) {
  if (!site) return null;
  const W = AP1000_WEIGHTS;
  return {
    acreage:      _ap1000ScoreAcreage(site.developable_acreage, W.acreage),
    water:        _ap1000ScoreWater(site, W.water),
    transmission: _ap1000ScoreTransmission(site, W.transmission),
    substation:   _ap1000ScoreSubstation(site, W.substation),
    workforce:    _ap1000ScoreWorkforce(site, W.workforce),
    fiber:        _ap1000ScoreFiber(site, W.fiber),
  };
}

function computeAp1000Score(site) {
  const bd = computeAp1000Breakdown(site);
  if (bd == null) return null;
  const total = Object.values(bd).reduce((a, b) => a + b, 0);
  return Math.max(0, Math.min(100, total));
}

// ---------------------------------------------------------------------------
window.computeAp1000Score = computeAp1000Score;
window.computeAp1000Breakdown = computeAp1000Breakdown;
window.AP1000_WEIGHTS = AP1000_WEIGHTS;
window.AP1000_SCORE_TOOLTIP = AP1000_SCORE_TOOLTIP;
