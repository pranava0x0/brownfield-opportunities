// Maritime siting — two 0-100 lenses over the whole brownfield corpus, for
// sites near a coastal or Great Lakes port: floating/offshore nuclear, and
// coastal on-site generation / data centers. Same pure/deterministic
// contract as dc-score.js / ap1000-score.js / microreactor-score.js.
//
// Grounding (WebSearch pass, 2026-08-27 — see data-source-research.md §33
// for the port/shipyard data-source probes; findings below are about
// siting CRITERIA, not data sources):
//   * Every serious floating-reactor program uses an EXISTING large-vessel
//     or offshore-module shipyard rather than a purpose-built nuclear site.
//     Akademik Lomonosov's hull was laid at Sevmash (Russia's submarine
//     yard) and outfitted at Baltic Shipyard — https://en.wikipedia.org/
//     wiki/Akademik_Lomonosov. The 1970s Offshore Power Systems study (the
//     closest full US engineering rubric) specified a dedicated shipyard
//     with a 900-ton gantry crane doing assembly-line construction before
//     ocean tow — https://whatisnuclear.com/offshore-nuclear-plants.html.
//     ThorCon and Core Power both design explicitly for shipyard
//     fabrication + barge/tow delivery — https://world-nuclear-news.org/
//     articles/core-power-plans-mass-production-of-floating-nuclear-power-plants.
//     This is why shipyard proximity carries the largest single weight on
//     the floating-nuclear lens.
//   * The Offshore Power Systems design sited 2.8 mi offshore behind a
//     breakwater viable to 70 ft water depth, and was engineered for a
//     100-year storm with hurricane resilience as a FIRST-ORDER design
//     driver, not an afterthought (same source). This project has no
//     bathymetry layer, so water depth is unassessed — like AP1000/
//     microreactor's undocumented seismic gap, this is disclosed rather
//     than guessed at. Hurricane exposure IS assessed, via the nearest
//     port's FEMA-NRI annual hurricane frequency (port_hurricane_freq).
//   * Two named 2026 US pilots validate the port-proximity thesis directly:
//     Bluecore Energy leased a berth at Port of Long Beach for a prototype
//     reactor module (https://www.workboat.com/bluecore-energy-developing-
//     nuclear-power-barge-at-port-of-long-beach), and Core Power + Port of
//     Corpus Christi signed an Aug 2026 feasibility MOC (https://www.world-
//     nuclear-news.org/articles/second-us-port-to-explore-nuclear-maritime-
//     technologies) — Corpus Christi Bay is also home to Kiewit Offshore
//     Services, this dataset's top heavy_module shipyard.
//   * For coastal generation/data centers, heavy equipment (large power
//     transformers, SMR modules) DOES move by barge/ship when it exceeds
//     truck/rail limits (https://www.omegamorgan.com/case-studies/
//     logistics/507000-pound-transformer-to-barge-move/; NuScale ships its
//     ~700-ton modules "by truck, rail, or barge" —
//     https://www.nuscalepower.com/products/nuscale-power-module), but
//     industry commentary treats it as a SECONDARY delivery-feasibility
//     factor, not a primary siting driver on par with grid access
//     (https://omnilogistics.com/data-center-logistics-2026/). That's why
//     the coastal-generation lens weights transmission well above port
//     access, the inverse of the floating-nuclear lens's priority order.
//
// Naming: every internal helper/constant below carries a `_maritime` /
// `MARITIME_` prefix, even ones with an otherwise-unique name. Plain
// top-level `function`/bare-`const` declarations in a classic (non-module)
// <script> become properties of `window`, and dc-score.js already defines
// bare names like `_scoreSubstation` / `_scoreGasPipeline` / `_floodPenalty`
// — loading this file after dc-score.js silently overwrote those and broke
// the DC/Generation/Manufacturing lenses (caught in browser verification,
// 2026-08-27). Same lesson microreactor-score.js's `_micro`/`MICRO_` prefix
// already encodes; this file just didn't follow it on the first pass.

function _maritimeInterp(x, pts) {
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

// ---------------------------------------------------------------------------
// Effective acreage — parcel is a conservative floor, same contract as
// dc-score.js:_effectiveAcreage / microreactor-score.js.
function _maritimeEffectiveAcreage(site) {
  return site.acreage ?? site.parcel_acreage ?? null;
}

// The gate. port_mi == null means one of two things depending on whether
// the enrichment has run: beforehand, "not loaded yet"; afterwards,
// "genuinely nothing within MAX_DISTANCE_MI_PORT (75 mi)". `_portChecked`
// is stamped by ensurePortProximityLoaded() on every record it touches —
// the same "we looked" marker pattern as `_infraChecked` (see
// microreactorScorable / dc-score.js's gate).
function maritimeScorable(site) {
  if (!site) return false;
  return site._portChecked === true || site.port_mi != null;
}

// ---------------------------------------------------------------------------
// Shared sub-scores
// ---------------------------------------------------------------------------

// Port distance → fraction. Ports are sparse (108 nationwide after the
// Coastal/Great-Lakes filter), so the curve stays generous out to ~40 mi —
// a site "near the coast" in the ordinary sense, not just waterfront.
const _MARITIME_PORT_DIST_ANCHORS = [[2, 1.0], [10, 0.85], [25, 0.55], [50, 0.2], [75, 0.05]];

function _maritimePortDistFrac(mi) {
  if (mi == null) return 0;
  return _maritimeInterp(mi, _MARITIME_PORT_DIST_ANCHORS);
}

// Great Lakes ports connect to the ocean only via the St. Lawrence Seaway
// (draft-limited to "Seawaymax" vessels, ~740 ft / 78 ft beam) — real but
// narrower access than an open coastal port. Scored as a discount, not a
// disqualifier: Fincantieri Marinette Marine (a large_hull shipyard in
// this dataset) is itself a Great Lakes yard.
function _maritimePortTypeFrac(portType) {
  if (portType === "Coastal") return 1.0;
  if (portType === "Great Lakes") return 0.75;
  return 0.5; // present but type unrecognized — don't zero out on a schema surprise
}

function _maritimeScorePortAccess(site, cap) {
  const dist = _maritimePortDistFrac(site.port_mi);
  const type = _maritimePortTypeFrac(site.port_type);
  return Math.round(dist * type * cap);
}

// Shipyard distance → fraction. Steeper than port distance — final assembly
// and launch logistics for a barge-scale module favor genuine proximity,
// not "somewhere in the region" (Offshore Power Systems' assembly-line
// model builds AT the yard and tows to site).
const _MARITIME_YARD_DIST_ANCHORS = [[5, 1.0], [25, 0.7], [60, 0.4], [100, 0.15], [150, 0.03]];

// Capability multiplier. heavy_module (offshore platform/topsides
// fabrication — Kiewit Offshore Services, Gulf Island Fabrication) is the
// capability actually analogous to floating-reactor module assembly;
// large_hull (naval/commercial new construction) is a plausible but less
// direct fit; naval_repair (drydock/overhaul only, no new-construction
// fabrication) is the weakest fit but not irrelevant — a repair yard still
// has heavy-lift infrastructure and skilled trades.
const _MARITIME_YARD_CAPABILITY_FRAC = Object.freeze({
  heavy_module: 1.0,
  large_hull: 0.7,
  naval_repair: 0.4,
});

function _maritimeScoreShipyard(site, cap) {
  if (site.shipyard_mi == null) return 0;
  const dist = _maritimeInterp(site.shipyard_mi, _MARITIME_YARD_DIST_ANCHORS);
  const capFrac = _MARITIME_YARD_CAPABILITY_FRAC[site.shipyard_capability] ?? 0.5;
  return Math.round(dist * capFrac * cap);
}

// Transmission-distance curve — same 2-mi-cliff shape dc-score.js uses for
// its DC lens (a compute/generation load cares about near-term
// interconnection, not a 10-mi gen-tie).
const _MARITIME_TRANS_DIST_ANCHORS = [[0.25, 1.0], [1, 0.85], [2, 0.6], [5, 0.3], [10, 0.1]];

function _maritimeGridAccessMi(site) {
  // Same substation-substitution logic as dc-score.js:_effectiveGridAccess
  // — HIFLD's public transmission layer is patchy on sub-transmission, so a
  // materially closer substation stands in for a missing line.
  const line = site.transmission_mi;
  const sub = site.substation_mi;
  if (line == null) return sub;
  if (sub != null && line - sub > 2) return sub;
  return line;
}

function _maritimeScoreTransmission(site, cap) {
  const mi = _maritimeGridAccessMi(site);
  if (mi == null) return 0;
  return Math.round(_maritimeInterp(mi, _MARITIME_TRANS_DIST_ANCHORS) * cap);
}

function _maritimeScoreSubstation(site, cap) {
  if (site.substation_mi == null) return 0;
  const frac = _maritimeInterp(site.substation_mi, [[1, 1.0], [5, 0.6], [15, 0.2]]);
  const kv = site.substation_kv;
  const kvFrac = kv == null ? 1.0 : kv < 69 ? 0.5 : kv < 115 ? 0.75 : 1.0;
  return Math.round(frac * kvFrac * cap);
}

function _maritimeScoreGasPipeline(site, cap) {
  if (site.gas_pipeline_mi == null) return 0;
  return Math.round(_maritimeInterp(site.gas_pipeline_mi, [[1, 1.0], [5, 0.6], [15, 0.2]]) * cap);
}

// Acreage — a broad ramp, not a threshold. A floating-nuclear support yard
// or a coastal generation plant both scale with available land, unlike the
// AP1000/microreactor threshold screens for a fixed reactor footprint.
const _MARITIME_ACREAGE_ANCHORS = [[5, 0.15], [25, 0.4], [100, 0.7], [500, 1.0]];

function _maritimeScoreAcreage(site, cap) {
  const ac = _maritimeEffectiveAcreage(site);
  if (ac == null) return Math.round(0.3 * cap); // unknown, not zero — most ACRES brownfields ship no acreage
  return Math.round(_maritimeInterp(ac, _MARITIME_ACREAGE_ANCHORS) * cap);
}

// Readiness — capped sum of independent sub-signals, same bundle shape as
// microreactor-score.js's _MICRO_READINESS_POINTS.
function _maritimeReadinessCleanupComplete(site) {
  if (site.npl_status_code === "D") return true;
  if (typeof site.rau_status === "string" && /^Meets the Measure/i.test(site.rau_status)) return true;
  if (typeof site.cleanup_status === "string" && /complete/i.test(site.cleanup_status)) return true;
  return false;
}

function _maritimeScoreReadiness(site, cap) {
  const points = {
    cleanup_complete: _maritimeReadinessCleanupComplete(site) ? 0.35 : 0,
    owner_known: site.current_owner ? 0.2 : 0,
    in_reuse: /^yes/i.test(site.in_reuse || "") ? 0.2 : 0,
    energy_community: site.in_energy_community === true ? 0.15 : 0,
    opportunity_zone: site.in_opportunity_zone === true ? 0.1 : 0,
  };
  const frac = Math.min(1.0, Object.values(points).reduce((a, b) => a + b, 0));
  return Math.round(frac * cap);
}

// ---------------------------------------------------------------------------
// Subtractive terms
// ---------------------------------------------------------------------------

// SFHA flood — same subtractive-term shape as every other lens in this app.
const MARITIME_FLOOD_SFHA_PENALTY = 15;

function _maritimeFloodPenalty(site) {
  return site.in_sfha === true ? MARITIME_FLOOD_SFHA_PENALTY : 0;
}

// Hurricane exposure at the nearest port. Thresholds calibrated to the
// observed distribution across the 108 Coastal/Great-Lakes principal ports
// (2026-08-27: median 0.111 annual events, p90 0.333, max 0.576 at
// Galveston, TX) — NOT arbitrary round numbers. Charged harder on the
// floating-nuclear lens (a permanently moored offshore facility) than the
// coastal-generation lens (an onshore plant/DC a port merely delivers to).
const _MARITIME_HURRICANE_ANCHORS = [[0.0, 0], [0.15, 0], [0.35, 1.0], [0.6, 1.0]];

function _maritimeHurricaneFrac(site) {
  if (site.port_hurricane_freq == null) return 0;
  return _maritimeInterp(site.port_hurricane_freq, _MARITIME_HURRICANE_ANCHORS);
}

const MARITIME_HURRICANE_PENALTY_OFFSHORE = 12;
const MARITIME_HURRICANE_PENALTY_COASTAL = 6;

// ---------------------------------------------------------------------------
// Lens 1 — Floating / offshore nuclear
// ---------------------------------------------------------------------------
// Positive caps sum to exactly 100. Shipyard proximity dominates because
// every real precedent (Lomonosov, Offshore Power Systems, ThorCon, Core
// Power) builds AT a shipyard and tows to site — see the header citations.
const OFFSHORE_NUCLEAR_WEIGHTS = Object.freeze({
  shipyard:     32,
  port_access:  20,
  transmission: 20,
  readiness:    18,
  acreage:      10,
});

function computeFloatingNuclearBreakdown(site) {
  if (!maritimeScorable(site)) return null;
  const W = OFFSHORE_NUCLEAR_WEIGHTS;
  return {
    shipyard:     _maritimeScoreShipyard(site, W.shipyard),
    port_access:  _maritimeScorePortAccess(site, W.port_access),
    transmission: _maritimeScoreTransmission(site, W.transmission),
    readiness:    _maritimeScoreReadiness(site, W.readiness),
    acreage:      _maritimeScoreAcreage(site, W.acreage),
  };
}

function computeFloatingNuclearScore(site) {
  const bd = computeFloatingNuclearBreakdown(site);
  if (bd == null) return null;
  const positive = Object.values(bd).reduce((a, b) => a + b, 0);
  const total = positive - _maritimeFloodPenalty(site)
    - Math.round(_maritimeHurricaneFrac(site) * MARITIME_HURRICANE_PENALTY_OFFSHORE);
  return Math.max(0, Math.min(100, total));
}

// ---------------------------------------------------------------------------
// Lens 2 — Coastal on-site generation / data centers
// ---------------------------------------------------------------------------
// Transmission dominates, matching every other generation/DC lens in this
// app; port access is a SECONDARY heavy-equipment-delivery bonus per the
// industry-logistics citations above, not a primary driver. No shipyard
// component — a data center or gas/generation plant has no assembly-yard
// dependency.
const COASTAL_GENERATION_WEIGHTS = Object.freeze({
  transmission: 24,
  readiness:    20,
  acreage:      18,
  substation:   14,
  port_access:  14,
  gas_pipeline: 10,
});

function computeCoastalGenerationBreakdown(site) {
  if (!maritimeScorable(site)) return null;
  const W = COASTAL_GENERATION_WEIGHTS;
  return {
    transmission: _maritimeScoreTransmission(site, W.transmission),
    readiness:    _maritimeScoreReadiness(site, W.readiness),
    acreage:      _maritimeScoreAcreage(site, W.acreage),
    substation:   _maritimeScoreSubstation(site, W.substation),
    port_access:  _maritimeScorePortAccess(site, W.port_access),
    gas_pipeline: _maritimeScoreGasPipeline(site, W.gas_pipeline),
  };
}

function computeCoastalGenerationScore(site) {
  const bd = computeCoastalGenerationBreakdown(site);
  if (bd == null) return null;
  const positive = Object.values(bd).reduce((a, b) => a + b, 0);
  const total = positive - _maritimeFloodPenalty(site)
    - Math.round(_maritimeHurricaneFrac(site) * MARITIME_HURRICANE_PENALTY_COASTAL);
  return Math.max(0, Math.min(100, total));
}

// ---------------------------------------------------------------------------
const MARITIME_SCORE_TOOLTIP_OFFSHORE =
  "Floating/offshore nuclear siting suitability (0-100). Weighted on shipyard " +
  "proximity + heavy-module capability (32 — every built or proposed floating " +
  "reactor program assembles at an existing large-vessel/offshore-module " +
  "shipyard and tows to site), port access (20), grid interconnection (20), " +
  "readiness (18), and acreage (10). SFHA flood and the nearest port's FEMA-NRI " +
  "hurricane frequency both subtract. Water depth is NOT assessed — this " +
  "project has no bathymetry layer.";

const MARITIME_SCORE_TOOLTIP_COASTAL =
  "Coastal on-site generation / data-center siting suitability (0-100). " +
  "Weighted on grid interconnection (24), readiness (20), acreage (18), " +
  "substation proximity (14), port access as a secondary heavy-equipment-" +
  "delivery signal (14), and gas pipeline proximity (10). SFHA flood and " +
  "hurricane frequency both subtract, at half the floating-nuclear lens's rate.";

// Grouped for breakdown chips. Keys MUST match the breakdown object exactly
// or chips silently render 0 (the _DC_SUIT_GROUPS / _MICRO_SUIT_GROUPS drift
// risk documented in dc-score.js / microreactor-score.js).
const OFFSHORE_NUCLEAR_SUIT_GROUPS = Object.freeze([
  { title: "Assembly & access", keys: ["shipyard", "port_access"] },
  { title: "Grid & land", keys: ["transmission", "acreage"] },
  { title: "Readiness", keys: ["readiness"] },
]);

const COASTAL_GENERATION_SUIT_GROUPS = Object.freeze([
  { title: "Grid", keys: ["transmission", "substation"] },
  { title: "Delivery & fuel", keys: ["port_access", "gas_pipeline"] },
  { title: "Land & readiness", keys: ["acreage", "readiness"] },
]);

// ---------------------------------------------------------------------------
window.computeFloatingNuclearScore = computeFloatingNuclearScore;
window.computeFloatingNuclearBreakdown = computeFloatingNuclearBreakdown;
window.computeCoastalGenerationScore = computeCoastalGenerationScore;
window.computeCoastalGenerationBreakdown = computeCoastalGenerationBreakdown;
window.maritimeScorable = maritimeScorable;
window.OFFSHORE_NUCLEAR_WEIGHTS = OFFSHORE_NUCLEAR_WEIGHTS;
window.COASTAL_GENERATION_WEIGHTS = COASTAL_GENERATION_WEIGHTS;
window.MARITIME_FLOOD_SFHA_PENALTY = MARITIME_FLOOD_SFHA_PENALTY;
window.MARITIME_HURRICANE_PENALTY_OFFSHORE = MARITIME_HURRICANE_PENALTY_OFFSHORE;
window.MARITIME_HURRICANE_PENALTY_COASTAL = MARITIME_HURRICANE_PENALTY_COASTAL;
window.MARITIME_SCORE_TOOLTIP_OFFSHORE = MARITIME_SCORE_TOOLTIP_OFFSHORE;
window.MARITIME_SCORE_TOOLTIP_COASTAL = MARITIME_SCORE_TOOLTIP_COASTAL;
window.OFFSHORE_NUCLEAR_SUIT_GROUPS = OFFSHORE_NUCLEAR_SUIT_GROUPS;
window.COASTAL_GENERATION_SUIT_GROUPS = COASTAL_GENERATION_SUIT_GROUPS;
