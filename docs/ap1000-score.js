// AP1000 nuclear-reactor siting suitability — a single 0–100 lens over the
// 14 curated military installations in docs/data/ap1000-sites.json.
//
// Scope follows the user's current priority order: developable acreage is an
// eligibility threshold first, then the ranking differentiates by cooling
// water, electrical infrastructure (transmission + substation), construction
// workforce, and fiber. Water remains heavily weighted because a Westinghouse
// AP1000 (1,117 MWe net, ~3,400 MWth) rejects ~2,300 MWth and, on a
// closed-cycle natural-draft cooling tower, needs ~26.8 MGD makeup withdrawal /
// ~20.1 MGD consumptive (per unit; Vogtle 3&4 NRC EIS) — a binding physical
// constraint for a thermal reactor. See ap1000-water-validation.md.
//
// NOT in the score: acreage beyond the threshold, seismic, and flood. The
// geohazards are genuinely deal-affecting for a nuclear build — Edwards, Fort
// Campbell, JBLM and Fort Wainwright all carry real flags — so the data file
// ships seismic_flag / flood_flag and the UI surfaces them as prominent
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

const AP1000_MIN_DEVELOPABLE_ACRES = 500;

// ---------------------------------------------------------------------------
// Reactor classes. AP1000 / APR1400 are LARGE Gen III+ PWRs — a different
// CATEGORY from SMRs (AP300-class) and microreactors (Janus-class), not
// points on one continuum: the certified large designs are wet-cooled with a
// fixed design basis, while SMR/micro designs shrink water demand 3–300× and
// several are air-coolable, which changes which sites are viable at all (a
// desert base that is `severe` water for an AP1000 can host an air-cooled
// microreactor — exactly the Army Janus premise at 9 of these 14 sites).
// Consumptive cfs scales from the Vogtle 3&4 record (31.1 cfs per 1,117 MWe
// unit — ap1000-water-validation.md §1) by nameplate; APR1400 uses linear
// MWe scaling (comparable thermal efficiency) pending a US APR1400 EIS.
// Each class carries its own citations: `spec_source` (nameplate/design) and
// `water_source` (basis of the consumptive figure). AP1000 water is the
// as-built Vogtle 3&4 environmental record; APR1400 and AP300 are linear
// per-MWe scalings of that record (stated in the note — no US EIS exists yet
// for either); the microreactor figure reflects air-cooled designs per the
// Army Janus program materials.
const REACTOR_CLASSES = Object.freeze({
  ap1000: Object.freeze({
    label: "AP1000", group: "Large PWR", mwe: 1117,
    consumptive_cfs: 31.1, withdrawal_cfs: 41.5,
    min_acres: 500, volt_profile: "large", dry_cooling_viable: false,
    spec_source: "https://westinghousenuclear.com/new-plants/ap1000-pwr/overview/",
    water_source: "https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf",
    water_basis: "Vogtle 3&4 FEIS as-built record: 26.8 MGD withdrawal / 20.1 MGD (31.1 cfs) consumptive per unit, natural-draft towers",
  }),
  apr1400: Object.freeze({
    label: "APR1400", group: "Large PWR", mwe: 1400,
    consumptive_cfs: 39.0, withdrawal_cfs: 52.0,
    min_acres: 500, volt_profile: "large", dry_cooling_viable: false,
    spec_source: "https://www.nrc.gov/reactors/new-reactors/large-lwr/design-cert/apr1400.html",
    water_source: "https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf",
    water_basis: "Linear per-MWe scaling of the Vogtle 3&4 record (31.1 cfs × 1400/1117) — no US APR1400 EIS exists; comparable thermal efficiency",
  }),
  ap300: Object.freeze({
    label: "AP300-class SMR", group: "SMR", mwe: 330,
    consumptive_cfs: 9.2, withdrawal_cfs: 12.3,
    min_acres: 100, volt_profile: "smr", dry_cooling_viable: true,
    spec_source: "https://westinghousenuclear.com/new-plants/ap300-smr/",
    water_source: "https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf",
    water_basis: "Linear per-MWe scaling of the Vogtle 3&4 record (31.1 cfs × 330/1117); AP300 reuses AP1000 passive-plant technology and supports hybrid/dry cooling",
  }),
  micro: Object.freeze({
    label: "Microreactor (Janus-class)", group: "Microreactor", mwe: 10,
    consumptive_cfs: 0, withdrawal_cfs: 0,   // typically air-cooled
    min_acres: 20, volt_profile: "micro", dry_cooling_viable: true,
    spec_source: "https://www.army.mil/article/289074/army_announces_next_steps_on_janus_program_for_next_generation_nuclear_energy",
    water_source: "https://www.army.mil/article/289074/army_announces_next_steps_on_janus_program_for_next_generation_nuclear_energy",
    water_basis: "Janus-class microreactors (≤20 MWe) are air-cooled designs — no cooling-water makeup requirement",
  }),
});

// Water-rights obtainability multiplier — availability ≠ obtainability. A
// site in a fully-appropriated western basin (Tucson AMA, adjudicated
// Antelope Valley) cannot acquire a new ~22,400 acre-ft/yr consumptive right
// at any reasonable price; a compact-/watermaster-gated basin (ACF, DRBC
// docket, Brazos watermaster) adds a real but passable gate. Multiplicative
// on the water component because rights without water and water without
// rights are both worthless. Missing (unassessed) → 1.0: absence of
// evidence isn't evidence. Micro class ignores the multiplier — an
// air-cooled unit needs no new consumptive right.
const AP1000_WATER_RIGHTS_MULT = Object.freeze({
  obtainable: 1.0,
  contested: 0.6,
  fully_appropriated: 0.2,
});

function _ap1000RightsMult(site) {
  const m = AP1000_WATER_RIGHTS_MULT[(site.water_rights_class || "").toLowerCase()];
  return m == null ? 1.0 : m;
}

// Positive caps sum to exactly 100. Acreage is deliberately not a point score:
// every current installation clears the minimum land screen, so acreage stays
// visible/cited as a threshold instead of ranking 300k-acre ranges above
// better-water/grid sites.
const AP1000_WEIGHTS = Object.freeze({
  water:        40,   // on-site/nearby cooling source and water infrastructure
  transmission: 22,   // export ~1,117 MW: HV line, close
  substation:   16,   // actual point of interconnection / switchyard proxy
  workforce:    15,   // skilled construction labor within ~1 hr
  fiber:         7,   // controls/comms — useful, but least differentiating here
});

const AP1000_SCORE_TOOLTIP =
  "AP1000 siting suitability (0–100). Acreage is a threshold screen: current " +
  "sites must clear 500 developable acres, but acreage is not ranked beyond " +
  "that. Weighted factors are cooling water (40), electrical infrastructure " +
  "(38 total: transmission distance+voltage 22 + substation distance+voltage " +
  "16), construction workforce within ~1 hr (15), and fiber (7). Seismic and " +
  "flood are shown as flags but NOT scored. Water/acreage/workforce/fiber are " +
  "analyst-researched (no federal GIS layer exists); transmission/substation " +
  "are computed from the project's infra-proximity spatial index.";

// Cooling-water adequacy → fraction, per class GROUP. The large-PWR table is
// the original calibration (the analyst rating already folds in source type
// and reach — Fort Campbell is "marginal" precisely because its abundant
// river is 12+ mi away and downhill). SMRs soften every bucket because the
// demand is ~3.4× smaller and hybrid/dry cooling is design-viable; the
// microreactor table barely differentiates because an air-cooled unit needs
// essentially no cooling makeup.
const _AP1000_WATER_FRAC_BY_GROUP = Object.freeze({
  "Large PWR":    { abundant: 1.0, adequate: 0.62, marginal: 0.33, poor: 0.12, severe: 0.0 },
  "SMR":          { abundant: 1.0, adequate: 0.85, marginal: 0.6,  poor: 0.35, severe: 0.1 },
  "Microreactor": { abundant: 1.0, adequate: 1.0,  marginal: 0.9,  poor: 0.75, severe: 0.6 },
});
const _AP1000_WATER_FRAC = _AP1000_WATER_FRAC_BY_GROUP["Large PWR"]; // legacy alias

// Low-flow margin tiers (documented low flow ÷ class consumptive demand).
// Anchor sanity check: NRC accepted Vogtle at ~1% of AVERAGE Savannah
// discharge, so a ≥30× margin against a DROUGHT/7Q10 flow is comfortably
// inside precedent. Interpolated so a 9.9× margin isn't cliffed below a 10×.
const _AP1000_MARGIN_ANCHORS = [[1, 0.2], [3, 0.5], [10, 0.8], [30, 1.0]];

function _ap1000ScoreWater(site, cap, cls) {
  const c = cls || REACTOR_CLASSES.ap1000;
  const rights = c.group === "Microreactor" ? 1.0 : _ap1000RightsMult(site);
  // Air-cooled class: water is not a binding constraint; score the residual
  // service-water need off the softened adequacy table only.
  let frac;
  if (site.water_low_flow_cfs != null && c.consumptive_cfs > 0) {
    // Computed margin from a DOCUMENTED low/drought flow (preferred over the
    // adequacy bucket when available — means overstate reliability ~3×; the
    // 2012 Ocmulgee drought at Robins is the canonical example).
    frac = site.water_low_flow_cfs <= 0 ? 0
      : _ap1000Interp(site.water_low_flow_cfs / c.consumptive_cfs, _AP1000_MARGIN_ANCHORS);
  } else {
    frac = _AP1000_WATER_FRAC_BY_GROUP[c.group][(site.water_adequacy || "").toLowerCase()];
  }
  return frac == null ? 0 : Math.round(frac * rights * cap);
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

function ap1000MeetsAcreageThreshold(site, classKey) {
  const c = REACTOR_CLASSES[classKey] || REACTOR_CLASSES.ap1000;
  return (site?.developable_acreage ?? 0) >= c.min_acres;
}

// Nominal-kV → fraction of capacity value, per class voltage profile.
// Exporting ~1,117–1,400 MW really wants ≥230 kV (115/138 kV implies major
// network upgrades); a 330 MWe SMR is comfortably served by 138–230 kV; a
// microreactor connects at distribution level, so line class barely matters.
function _ap1000VoltFrac(kv, profile) {
  if (kv == null) return 0;
  if (profile === "micro") return kv >= 69 ? 1.0 : 0.8;
  if (profile === "smr") {
    if (kv >= 230) return 1.0;
    if (kv >= 138) return 0.85;
    if (kv >= 115) return 0.7;
    if (kv >= 69)  return 0.45;
    return 0.2;
  }
  // "large" — the original AP1000 calibration
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
function _ap1000ScoreTransmission(site, cap, cls) {
  if (site.transmission_mi == null) return 0;
  const dist = _ap1000Interp(site.transmission_mi,
    [[0.1, 1.0], [1, 0.8], [2, 0.6], [5, 0.35], [10, 0.12], [20, 0]]);
  const volt = _ap1000VoltFrac(site.transmission_kv, (cls || REACTOR_CLASSES.ap1000).volt_profile);
  return Math.round((0.6 * dist + 0.4 * volt) * cap);
}

// Substation = distance blended with voltage, ~55/45. Voltage matters a lot
// here: a 1,117 MW interconnection needs a bulk (≥230 kV) substation/
// switchyard — a distribution-class (≤69 kV) substation can't serve and
// implies a brand-new switchyard build, so it's heavily discounted.
function _ap1000ScoreSubstation(site, cap, cls) {
  if (site.substation_mi == null) return 0;
  const dist = _ap1000Interp(site.substation_mi,
    [[0.5, 1.0], [2, 0.75], [5, 0.45], [10, 0.2], [15, 0]]);
  const volt = _ap1000VoltFrac(site.substation_kv, (cls || REACTOR_CLASSES.ap1000).volt_profile);
  return Math.round((0.55 * dist + 0.45 * volt) * cap);
}

// classKey defaults to "ap1000" so every pre-class caller (and the locked
// e2e expectations) keeps its exact behavior.
function computeAp1000Breakdown(site, classKey) {
  if (!site) return null;
  const W = AP1000_WEIGHTS;
  const cls = REACTOR_CLASSES[classKey] || REACTOR_CLASSES.ap1000;
  return {
    water:        _ap1000ScoreWater(site, W.water, cls),
    transmission: _ap1000ScoreTransmission(site, W.transmission, cls),
    substation:   _ap1000ScoreSubstation(site, W.substation, cls),
    workforce:    _ap1000ScoreWorkforce(site, W.workforce),
    fiber:        _ap1000ScoreFiber(site, W.fiber),
  };
}

function computeAp1000Score(site, classKey) {
  const bd = computeAp1000Breakdown(site, classKey);
  if (bd == null) return null;
  const total = Object.values(bd).reduce((a, b) => a + b, 0);
  return Math.max(0, Math.min(100, total));
}

// ---------------------------------------------------------------------------
window.computeAp1000Score = computeAp1000Score;
window.computeAp1000Breakdown = computeAp1000Breakdown;
window.AP1000_WEIGHTS = AP1000_WEIGHTS;
window.AP1000_MIN_DEVELOPABLE_ACRES = AP1000_MIN_DEVELOPABLE_ACRES;
window.ap1000MeetsAcreageThreshold = ap1000MeetsAcreageThreshold;
window.AP1000_SCORE_TOOLTIP = AP1000_SCORE_TOOLTIP;
window.REACTOR_CLASSES = REACTOR_CLASSES;
window.AP1000_WATER_RIGHTS_MULT = AP1000_WATER_RIGHTS_MULT;
