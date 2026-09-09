// Nickel refining — two 0-100 siting lenses over the whole brownfield corpus.
// Same pure/deterministic contract as dc-score.js / ap1000-score.js /
// microreactor-score.js / maritime-score.js.
//
// Grounding: research/nickel-refining-siting-2026-09.md (process routes,
// power, water, reagents, permitting) and
// research/nickel-supply-chain-geography-2026-09.md (where the feedstock,
// offtake and acid actually are). The load-bearing findings:
//
//   * ONLY TWO ROUTES ARE SCREENABLE against a US brownfield: a
//     hydrometallurgical refinery on imported MHP/MSP or matte, and a
//     black-mass battery-recycling plant making nickel sulfate. They are the
//     same chemical building block with different feed. A sulfide SMELTER is
//     deliberately NOT scored: none operates in the US, EPA never wrote a
//     nickel-smelting NESHAP subpart so a proposal would face a case-by-case
//     MACT determination, and the load is a continuous 80-120 MW furnace that
//     pairs with a captive mine and captive generation, not a grid-tied
//     brownfield. RKEF and HPAL are out for the same class of reason —
//     Indonesia built 10.4 GW of OFF-GRID captive coal for RKEF alone.
//
//   * THE TWO LIVE US PROJECTS PUBLISHED OPPOSITE SITING LOGIC, and that is
//     why there are two lenses rather than one:
//       - Electra narrowed to the southeastern US on DEEP-WATER PORT access
//         for globally sourced MHP/MSP plus proximity to the battery
//         corridor and "workforce availability in established chemical
//         processing and manufacturing regions" — https://www.globenewswire.com/
//         news-release/2026/06/08/3307955/0/en/electra-advances-engineering-
//         study-for-battery-grade-nickel-refinery-in-the-united-states.html
//       - Westwin built in LANDLOCKED Lawton, Oklahoma, on a 480-acre tract
//         inside a RAIL industrial park, because its feed is domestic ore and
//         recycled batteries — https://lawtonedc.com/news/article/
//         westwin-elements-breaks-ground-on-americas-only-critical-
//         mineralspilot-plant
//     Averaging those into one score would describe neither. The import lens
//     has no feedstock term (the feedstock arrives by ship); the domestic
//     lens has no port term (Lawton is 400 miles from salt water).
//
//   * BROWNFIELD SITING IS BEING USED AS PERMITTING ACCELERATION. Talon moved
//     its processing plant off the Minnesota mine to a former Westmoreland
//     coal mine at Beulah, North Dakota explicitly to narrow the mine's
//     environmental review — https://me.smenet.org/talon-plans-433-million-
//     processing-facility-in-north-dakota/
//
// Naming: every internal helper and constant carries a `_nickel` / `NICKEL_`
// prefix. Plain top-level declarations in a classic (non-module) <script>
// become properties of `window`, and dc-score.js already owns bare names like
// `_scoreSubstation` and `_floodPenalty`; loading a later file that redefines
// them silently broke the DC lens once already (2026-08-27). No exceptions
// for names that look unique.

// ---------------------------------------------------------------------------
// Weights. Each table MUST sum to 100 — a new component takes points from an
// existing one, it does not append. Guarded by
// test_nickel_weight_tables_each_sum_to_100.
//
// Land is NOT in either table. A refinery needs roughly 300-500 acres (Vale's
// Long Harbour is ~370 including residue ponds; Westwin's tract is 480), but
// 5,000 acres is worth no more than 500 — it is a threshold, not a ranked
// factor. Same discipline as the AP1000 tab's 500-acre gate and the
// microreactor tab's 5-acre one. See nickelAcreageStatus().
//
// Sulfuric acid distance is also deliberately unscored. Large hydromet plants
// normally burn sulfur on site and make their own acid — the acid plant
// doubles as the SO2 control device and recovers process steam — so distance
// to merchant acid is a cost input, not a siting determinant. `nickel_acid_mi`
// is joined onto every record and available to any surface that wants it, but
// nothing renders it today — see backlog.md.
const NICKEL_WEIGHTS_IMPORT = {
  port: 24,        // Electra's own first-named criterion
  water: 24,       // process + cooling makeup; the binding constraint
  transmission: 12,
  voltage: 6,
  substation: 10,
  rail: 12,        // reagents in, product out, merchant acid if not self-made
  demand: 12,      // the battery/stainless corridor
};

const NICKEL_WEIGHTS_DOMESTIC = {
  rail: 25,        // Westwin's own criterion — a rail industrial park
  feedstock: 23,   // domestic concentrate, tailings, or black mass
  water: 24,
  transmission: 12,
  voltage: 6,
  substation: 10,
};

// Subtractive, so the weight tables still sum to 100 — same structure as
// dc-score.js's flood and climate terms.
const NICKEL_FLOOD_SFHA_PENALTY = 18;
const NICKEL_DROUGHT_PENALTY = { "Very High": 10, "Relatively High": 5 };

// Land thresholds, in acres. Validated 2026-09-09 against published site
// footprints (research/nickel-refining-siting-2026-09.md §Land):
//
//   Vale Long Harbour, from its EIS — the strongest evidence here, because
//     the same document sizes TWO residue-handling designs for the same
//     50 kt Ni/yr plant:
//       ponded residue:    65 ha plant + 85 ha pipeline/ponds = 150 ha = 371 ac
//       dry (sub-aerial):  65 ha plant + 40 ha gypsum stack   = 105 ha = 259 ac
//     https://www.gov.nl.ca/eccc/files/env-assessment-projects-y2008-1243-04-eis-amend-executive-summary.pdf
//     (project record: https://www.gov.nl.ca/eccc/projects/project-1243/)
//   Westwin Elements, Lawton OK — 480-acre tract at a 68 kt/yr nameplate
//     → 7.06 ac/kt, against Long Harbour's ponded 7.4 ac/kt. Two independent
//     facilities within 5% of each other on acres-per-kt.
//     https://www.okcommerce.gov/westwin-elements-breaks-ground-on-americas-only-critical-minerals-pilot-plant/
//
// 300 acres therefore sits BETWEEN the same plant's two published designs —
// above the 259-acre dry-stack variant and below the 371-acre ponded one.
// That is a far better justification than a round number, and it means the
// threshold does not silently assume a residue pond.
//
// A BLACK-MASS RECYCLING plant is a different size of thing entirely, and a
// single flat threshold misscreened it by roughly 3x. Confirmed pure
// recycling-to-sulfate sites: Cirba Solutions Lancaster OH 36.8 ac
// (DOE/EA-2213), Li-Cycle Rochester Hub 41–65 ac. The larger "recycling"
// campuses often quoted (Ascend Apex 1 at 140 ac, Cirba SC at 206 ac,
// Redwood's 900+ ac) are integrated precursor/CAM plants, not recycling
// alone — do not use them to justify raising this number.
//
// Caveat worth keeping: this rests on two confirmed refinery footprints and
// a handful of recycler ones. It is a screening floor, not an engineering
// requirement, and a refinery that dry-stacks or trucks residue off-site
// could plausibly fit nearer Long Harbour's plant-only 161 acres.
const NICKEL_MIN_ACRES = 300;            // hydromet refinery on imported feed
const NICKEL_MIN_ACRES_RECYCLING = 100;  // black-mass recycling to nickel sulfate

function _nickelInterp(x, pts) {
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

function _nickelEffectiveAcreage(site) {
  return site.acreage ?? site.parcel_acreage ?? null;
}

// ---------------------------------------------------------------------------
// Grid access. Same correction dc-score.js:_effectiveGridAccess makes and for
// the same reason: HIFLD's public transmission layer is patchy on
// sub-transmission (69/46/34.5 kV), so 6,222 corpus sites report a SUBSTATION
// closer than their "nearest" line — impossible, since a substation is by
// definition connected. Where the gap exceeds the threshold the substation
// stands in as the interconnect point, distance and voltage together.
const NICKEL_GRID_COVERAGE_GAP_MI = 2;

function _nickelGridAccess(site) {
  const line = site.transmission_mi;
  const sub = site.substation_mi;
  if (line != null && sub != null && line - sub > NICKEL_GRID_COVERAGE_GAP_MI) {
    return { mi: sub, kv: site.substation_kv ?? null, viaSubstation: true };
  }
  return { mi: line, kv: site.transmission_kv ?? null, viaSubstation: false };
}

// A hydromet refinery is a large but INTERRUPTIBLE load — autoclave agitators,
// oxygen plant, SX pumps, EW rectifiers — not a smelter's frozen-furnace
// failure mode. So the curve is gentler than the DC lens's 2-mile cliff: a
// few miles of line extension is ordinary industrial capex here.
function _nickelScoreTransmission(mi, cap) {
  return cap * _nickelInterp(mi, [[0, 1], [1, 0.95], [3, 0.75], [6, 0.45], [12, 0.15], [20, 0]]);
}

// General industrial interconnection practice puts a 50-100 MW continuous
// load at 69-138 kV. No nickel-specific voltage citation was found, so the
// curve rewards 69 kV as adequate rather than demanding transmission class.
// Null kV is NOT treated as zero — ~27% of substations lack the OSM tag — but
// it is capped below a confirmed 138 kV.
function _nickelScoreVoltage(kv, cap) {
  if (kv == null) return cap * 0.4;
  if (kv >= 230) return cap;
  if (kv >= 138) return cap * 0.85;
  if (kv >= 69) return cap * 0.6;
  return cap * 0.25;
}

function _nickelScoreSubstation(mi, kv, cap) {
  let frac = _nickelInterp(mi, [[0, 1], [1, 0.9], [3, 0.65], [8, 0.3], [20, 0]]);
  // Same quality discount dc-score.js applies: OSM `power=substation` includes
  // provably distribution-class stations. Null kV is not discounted.
  if (kv != null) {
    if (kv < 69) frac *= 0.5;
    else if (kv < 115) frac *= 0.75;
  }
  return cap * frac;
}

// ---------------------------------------------------------------------------
// Water. Two things have to be true: the site is near a gaged stream, and that
// stream carries enough flow to matter.
//
// `water_flow_cfs` is a LONG-RUN ANNUAL MEAN, not a permittable low flow. A
// withdrawal permit is written against 7Q10, routinely an order of magnitude
// lower on a flashy river. So this component screens and ranks; it never
// establishes that water is available, and the UI says so.
//
// The flow anchors are set against the one demand figure this project has
// already validated from a primary source: Vogtle 3&4's ~41.5 cfs withdrawal
// per AP1000 unit (DOE EIS-0476, see ap1000-water-validation.md). A hydromet
// refinery's process and cooling makeup is smaller than a thermal reactor's,
// but the same precedent applies — Vogtle was permitted against roughly 1% of
// the Savannah's average flow. A few hundred cfs of mean flow is therefore a
// genuinely different proposition from a few tens, and 2,000+ cfs is a river
// that will not be the constraint.
function _nickelScoreWater(site, cap) {
  const mi = site.water_gage_mi;
  const cfs = site.water_flow_cfs;
  if (mi == null || cfs == null) return 0;
  // Distance to the GAGE, not to water — gages sit tens of miles apart on a
  // big river, so the taper is generous and only really punishes a site whose
  // nearest gaged stream is in the next basin.
  const near = _nickelInterp(mi, [[0, 1], [5, 0.9], [15, 0.6], [30, 0.3], [50, 0]]);
  const size = _nickelInterp(cfs, [[10, 0], [50, 0.25], [200, 0.55], [800, 0.8], [2000, 1]]);
  return cap * near * size;
}

// Rail. Like the microreactor lens's deliverability term this is an ADEQUACY
// gate, not a proximity race: a plant 0.3 mi from a line and one 2 mi from it
// are both rail-served once a spur is built. What matters is that rail exists
// at all, since bulk reagents inbound (Ambatovy imports ~9x its export
// tonnage) and product outbound both move by rail.
function _nickelScoreRail(mi, cap) {
  return cap * _nickelInterp(mi, [[0, 1], [2, 1], [5, 0.7], [10, 0.4], [25, 0.1], [50, 0]]);
}

// Port. Only the import lens uses this. `port_mi` is the BTS/USACE Principal
// Port join already built for the Maritime tab — Coastal and Great Lakes
// types, the top 150 US ports by tonnage.
function _nickelScorePort(site, cap) {
  const mi = site.port_mi;
  if (mi == null) return 0;
  return cap * _nickelInterp(mi, [[0, 1], [10, 0.9], [25, 0.7], [50, 0.35], [75, 0]]);
}

// Feedstock and demand are continental distances by design — "how far from
// the battery corridor" has a real answer at 600 miles.
function _nickelScoreFeedstock(mi, cap) {
  return cap * _nickelInterp(mi, [[0, 1], [50, 0.9], [150, 0.7], [400, 0.4], [800, 0.1], [1000, 0]]);
}

function _nickelScoreDemand(mi, cap) {
  return cap * _nickelInterp(mi, [[0, 1], [100, 0.9], [300, 0.7], [600, 0.4], [900, 0.1], [1200, 0]]);
}

// WORKFORCE IS DELIBERATELY NOT SCORED, and the reason is worth stating
// because Electra names it explicitly ("workforce availability in established
// chemical processing and manufacturing regions"). A first cut of this file
// scored it off `county_labor_force` — a field that is present on ZERO of the
// 46,759 records, because the connector that would fill it needs a
// CENSUS_API_KEY nobody has registered yet (see backlog.md).
//
// A component computed from a universally-null field is a CONSTANT. It added
// the same few points to every site, moved no ranking, and made the score
// table look as though workforce had been assessed when nothing had been. A
// term that cannot discriminate is worse than an absent one: it spends weight
// and buys a false impression of coverage.
//
// So it is disclosed as unassessed instead — the same treatment bathymetry
// gets on the Maritime tab and seismic gets on the microreactor lens. When
// county employment in NAICS 325 (chemicals) and 331 (primary metal) lands,
// this becomes a real term and the weight comes out of an existing one.

// ---------------------------------------------------------------------------
// Penalties. Both subtractive so the weight tables stay at 100.
function _nickelFloodPenalty(site) {
  // Only an affirmative SFHA mapping is charged. Null/unmapped is not
  // penalised — absence of evidence is not evidence, the same rule the flood
  // and climate terms follow everywhere else in this project.
  return site.in_sfha === true ? NICKEL_FLOOD_SFHA_PENALTY : 0;
}

// Drought ONLY — a deliberate divergence from dc-score.js:_climatePenalty,
// which charges max(wildfire, drought). A refinery's exposure is to water
// availability, and wildfire risk to a fenced industrial plant with no
// interface fuel is a different and much weaker claim. Documented divergence,
// guarded by test_nickel_wildfire_is_not_penalised.
function _nickelDroughtPenalty(site) {
  return NICKEL_DROUGHT_PENALTY[site.nri_drought_rating] ?? 0;
}

// ---------------------------------------------------------------------------
// Land threshold — TRI-STATE, and the null case is the important one.
//
// Returns true / false / null. `null` means the source ships no acreage,
// which is EVERY ACRES brownfield (EPA's FeatureServer has no acreage column
// at all) and two-thirds of FUDS. Reading null as "too small" would silently
// delete most of the corpus from the lens; reading it as "big enough" would
// invent a fact. It is reported as unknown and the UI says so.
function nickelAcreageStatus(site, minAcres = NICKEL_MIN_ACRES) {
  const ac = _nickelEffectiveAcreage(site);
  if (ac == null) return null;
  return ac >= minAcres;
}

// The score gate. `transmission_mi` null means the infra join has not run or
// found nothing — "cannot assess", which is not the same as "bad", so the
// score is null rather than 0.
//
// `_waterChecked` is the same guard the microreactor lens applies with
// `_infraChecked`: before the water join resolves, every site would look
// water-less and score zero on a 24-point component.
//
// `_nickelChecked` gates the supply-chain join for exactly the same reason,
// and it matters more now that the join is lazy: without it the import lens
// silently awards zero for its 12-point demand term and the domestic lens
// zero for its 23-point feedstock term, producing a ranking that looks
// complete and is materially understated (Codex review, this PR).
function nickelScorable(site) {
  return site
    && site.transmission_mi != null
    && site._waterChecked === true
    && site._nickelChecked === true;
}

function computeNickelImportBreakdown(site) {
  if (!nickelScorable(site)) return null;
  const w = NICKEL_WEIGHTS_IMPORT;
  const grid = _nickelGridAccess(site);
  const b = {
    port: _nickelScorePort(site, w.port),
    water: _nickelScoreWater(site, w.water),
    transmission: _nickelScoreTransmission(grid.mi, w.transmission),
    voltage: _nickelScoreVoltage(grid.kv, w.voltage),
    substation: _nickelScoreSubstation(site.substation_mi, site.substation_kv, w.substation),
    rail: _nickelScoreRail(site.rail_mi, w.rail),
    demand: _nickelScoreDemand(site.nickel_demand_mi, w.demand),
  };
  b.flood = -_nickelFloodPenalty(site);
  b.drought = -_nickelDroughtPenalty(site);
  b.flood_penalty = b.flood;
  b.climate_penalty = b.drought;
  b._viaSubstation = grid.viaSubstation;
  b.total = Math.max(0, Math.min(100, Object.keys(w)
    .reduce((sum, k) => sum + b[k], 0) + b.flood + b.drought));
  return b;
}

function computeNickelDomesticBreakdown(site) {
  if (!nickelScorable(site)) return null;
  const w = NICKEL_WEIGHTS_DOMESTIC;
  const grid = _nickelGridAccess(site);
  const b = {
    rail: _nickelScoreRail(site.rail_mi, w.rail),
    feedstock: _nickelScoreFeedstock(site.nickel_feedstock_mi, w.feedstock),
    water: _nickelScoreWater(site, w.water),
    transmission: _nickelScoreTransmission(grid.mi, w.transmission),
    voltage: _nickelScoreVoltage(grid.kv, w.voltage),
    substation: _nickelScoreSubstation(site.substation_mi, site.substation_kv, w.substation),
  };
  b.flood = -_nickelFloodPenalty(site);
  b.drought = -_nickelDroughtPenalty(site);
  b.flood_penalty = b.flood;
  b.climate_penalty = b.drought;
  b._viaSubstation = grid.viaSubstation;
  b.total = Math.max(0, Math.min(100, Object.keys(w)
    .reduce((sum, k) => sum + b[k], 0) + b.flood + b.drought));
  return b;
}

function computeNickelImportScore(site) {
  const b = computeNickelImportBreakdown(site);
  return b ? Math.round(b.total) : null;
}

function computeNickelDomesticScore(site) {
  const b = computeNickelDomesticBreakdown(site);
  return b ? Math.round(b.total) : null;
}

// Tier breaks are calibrated to THIS lens's own observed distribution, not
// copied from the DC lens's 75/50/25 — the same lesson the microreactor tab
// records, where reusing another lens's breaks painted the whole corpus one
// colour.
//
// Measured 2026-09-08 over the full corpus with the nationwide water join in
// place. Both lenses land on almost the same spread, which is itself worth
// knowing — the eligibility filter differs but the underlying infrastructure
// does not:
//
//   import   n=21,577  p25=55  p50=63  p75=71  p90=79  p99=92  max=96
//   domestic n=45,948  p25=52  p50=63  p75=73  p90=81  p99=91  max=96
//
// So: strong is roughly the top 10%, moderate the top third, marginal the top
// three quarters. An earlier 62/50/38 guess — made before the water join was
// national — would have called more than half the corpus "strong".
// RECALIBRATE when a refresh shifts the spread; the measurement is
// computeNickelImportScore over window.__sites.
const NICKEL_TIERS = [
  { key: "strong", label: "Strong", min: 80 },
  { key: "moderate", label: "Moderate", min: 68 },
  { key: "marginal", label: "Marginal", min: 55 },
  { key: "weak", label: "Weak", min: 0 },
];

function nickelTier(score) {
  if (score == null) return null;
  return NICKEL_TIERS.find((t) => score >= t.min) || NICKEL_TIERS[NICKEL_TIERS.length - 1];
}

// Chip groupings for the detail panel. Keys MUST match the breakdown object
// exactly or chips silently render zero — the UAT-007 drift lesson.
const _NICKEL_IMPORT_GROUPS = [
  { label: "Feed logistics", keys: ["port", "rail", "demand"] },
  { label: "Water", keys: ["water"] },
  { label: "Grid", keys: ["transmission", "voltage", "substation"] },
];
const _NICKEL_DOMESTIC_GROUPS = [
  { label: "Feed logistics", keys: ["rail", "feedstock"] },
  { label: "Water", keys: ["water"] },
  { label: "Grid", keys: ["transmission", "voltage", "substation"] },
];

if (typeof window !== "undefined") {
  window.computeNickelImportScore = computeNickelImportScore;
  window.computeNickelDomesticScore = computeNickelDomesticScore;
  window.computeNickelImportBreakdown = computeNickelImportBreakdown;
  window.computeNickelDomesticBreakdown = computeNickelDomesticBreakdown;
  window.nickelScorable = nickelScorable;
  window.nickelAcreageStatus = nickelAcreageStatus;
  window.nickelTier = nickelTier;
  window.NICKEL_WEIGHTS_IMPORT = NICKEL_WEIGHTS_IMPORT;
  window.NICKEL_WEIGHTS_DOMESTIC = NICKEL_WEIGHTS_DOMESTIC;
  window.NICKEL_MIN_ACRES = NICKEL_MIN_ACRES;
  window.NICKEL_MIN_ACRES_RECYCLING = NICKEL_MIN_ACRES_RECYCLING;
  window._NICKEL_IMPORT_GROUPS = _NICKEL_IMPORT_GROUPS;
  window._NICKEL_DOMESTIC_GROUPS = _NICKEL_DOMESTIC_GROUPS;
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { computeNickelImportScore, computeNickelDomesticScore,
    computeNickelImportBreakdown, computeNickelDomesticBreakdown,
    nickelScorable, nickelAcreageStatus, nickelTier,
    NICKEL_WEIGHTS_IMPORT, NICKEL_WEIGHTS_DOMESTIC, NICKEL_MIN_ACRES,
    NICKEL_MIN_ACRES_RECYCLING };
}
