// Microreactor siting suitability — a 0–100 lens over the whole 46,759-site
// corpus, for a 1–20 MWe factory-built power block.
//
// This lens deliberately INVERTS the grid logic every other lens in this app
// uses. A data center, a utility-scale generator and a factory all want to be
// near a high-voltage line. A microreactor's entire commercial case is the
// opposite: it exists to serve a load the grid serves badly or not at all.
// Fort Wainwright is the canonical row — the one Army Janus installation whose
// displaced alternative is coal and oil at Alaskan prices.
//
// Grounding for the weights, carried from two sibling research projects:
//   * EVERY U.S. microreactor to reach criticality has done so under a DOE
//     authorization on federal land — Antares Mark-0, Valar Ward 250,
//     Deployable Unity, Aalo CTR and Oklo Groves, all in 2026 — not under an
//     NRC operating licence. Project Pele is a DoD build; ANPI pairs vendors
//     to Air Force bases; Janus is nine Army installations. Federal land is
//     the licensing fast lane, and it is the single largest differentiator
//     between a 2028 and a 2035 in-service date.
//   * The fleet is truck- and container-delivered. A Kaleidos unit is 70
//     tonnes in one shipping container; an eVinci is a transportable
//     factory-built unit on a site "as small as two acres". Road access is a
//     physical precondition, not a convenience.
//
// Pure / deterministic, same contract as dc-score.js and ap1000-score.js: a
// reader can reconstruct exactly why a site ranks where it does.

// Piecewise-linear interpolation through ascending [x, frac] anchors; clamps
// outside the range. Same helper shape as dc-score.js / ap1000-score.js — the
// anchors ARE the documented intent, so changing one is a scoring change.
function _microInterp(x, pts) {
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

// Land is a THRESHOLD, not a ranked factor — the same discipline
// ap1000-score.js applies at 500 acres. Beyond the screen, more land does not
// make a better microreactor site: Westinghouse publishes 5 MWe on two acres,
// so a 40,000-acre range has no advantage over a 12-acre parcel. The screen
// sits above the largest published vendor footprint (2 ac) to leave room for
// the pad, the switchyard and a security perimeter, none of which any vendor
// in the fleet has published a figure for.
const MICRO_MIN_ACRES = 5;

// Upper edge of the microreactor product band. Above this, the fleet's
// designs stop being the right answer and an SMR is the comparison.
const MICRO_BAND_MWE = 20;

// Positive caps sum to exactly 100. Adding a component means taking points
// from an existing one — never appending. Guarded by
// test_micro_weights_sum_to_100.
const MICRO_WEIGHTS = Object.freeze({
  licensing_path: 24,  // federal land → DOE authorization pathway
  grid_isolation: 22,  // INVERTED distance-to-grid — the diesel-displacement case
  anchor_load:    18,  // an identified local load in or near the 1–20 MWe band
  deliverability: 18,  // a factory unit has to physically arrive by road or rail
  readiness:      18,  // remediated, owned, and financeable
});

// Subtractive terms, applied after the weighted sum so the weight table stays
// at 100 (same structure as dc-score.js's flood and climate penalties).
//
// Flood is charged LESS here than on the data-center lens (12 vs 18) for a
// physical reason, not a softer standard: a 2–20 acre reactor pad can be sited
// out of the mapped floodplain inside a larger parcel, which a 200-acre
// campus cannot. Null / unmapped is NOT penalised — absence of evidence is
// not evidence of safety.
const MICRO_FLOOD_SFHA_PENALTY = 12;

// Wildfire only. The data-center lens charges the MAX of wildfire and drought;
// drought is dropped here because the heat-pipe (eVinci, Antares R1) and
// helium HTGR (Kaleidos, KRONOS) designs in the fleet are air-coolable, so
// cooling-water scarcity is not the binding constraint it is for a wet-cooled
// thermal plant. Wildfire stays: it is an operability and physical-security
// threat to a small, remote, largely unattended unit.
const MICRO_WILDFIRE_PENALTY = Object.freeze({
  "very high": 8,
  "relatively high": 4,
});

// ---------------------------------------------------------------------------
// Effective acreage — the parcel is a conservative floor. A program-reported
// acreage always wins; the cadastral parcel only ever fills a null. Same
// contract as dc-score.js:_effectiveAcreage.
function _microEffectiveAcreage(site) {
  return site.acreage ?? site.parcel_acreage ?? null;
}

// Land screen. Returns true / false / null — null means "unknown", which is
// NOT the same as "too small". 100% of EPA ACRES brownfields ship no acreage
// (the source FeatureServer has no acreage column at all) and ~66% of FUDS
// properties have no digitized boundary, so a null-means-fail rule would
// silently delete most of the corpus from this lens.
function microreactorMeetsAcreageThreshold(site) {
  const ac = _microEffectiveAcreage(site);
  if (ac == null) return null;
  return ac >= MICRO_MIN_ACRES;
}

// ---------------------------------------------------------------------------
// 1. Licensing path (24)
//
// Federal land carries a DOE / DoD authorization pathway that has, so far,
// been the ONLY route a U.S. microreactor has actually taken to criticality.
// A private brownfield goes through NRC construction-permit and operating
// licence review instead — the KRONOS MMR at the University of Illinois is
// the fleet's one docketed example and is still in review.
//
// BRAC over FUDS: a closed base is federally held land being actively
// dispositioned, so both the authorization pathway AND site control are on
// the table. A FUDS property is formerly-used — many have already transferred
// to private or state hands, so the federal pathway is likelier but not
// guaranteed.
const _MICRO_LICENSING_FRAC = Object.freeze({
  brac: 1.0,
  fuds: 0.85,
  superfund_federal: 0.9,
  superfund: 0.35,
  brownfield: 0.3,
});

function _microLicensingKey(site) {
  if (site.program === "brac") return "brac";
  if (site.program === "fuds") return "fuds";
  if (site.program === "superfund") {
    // EPA's federal-facility flag: "Y" = the site is on a federal facility
    // (DoD, DOE, VA, …), which puts it on the same authorization footing as
    // an active installation. Everything else is the NRC path.
    return site.federal_facility_code === "Y" ? "superfund_federal" : "superfund";
  }
  return "brownfield";
}

function _microScoreLicensing(site, cap) {
  const frac = _MICRO_LICENSING_FRAC[_microLicensingKey(site)];
  return Math.round((frac == null ? 0 : frac) * cap);
}

// ---------------------------------------------------------------------------
// 2. Grid isolation (22) — INVERTED
//
// Far from transmission scores HIGH. A site 0.3 mi from a 500 kV line has a
// cheap grid alternative and no reason to buy a first-of-a-kind reactor; a
// site 40 miles out is running diesel.
//
// A NULL distance is the strongest signal in the dataset, not a missing
// value. Every one of the 46,759 sites appears in infra-proximity.json — the
// connector emits a tombstone `{id, program}` when no feature is in range —
// so a null distance means nothing of that kind is within 100 miles. With
// BOTH the line and the substation null, the site is genuinely off-grid
// (almost all of it interior Alaska and the Pacific territories). See
// CLAUDE.md, "Infra-proximity emits tombstone records".
//
// Because that reading depends on the enrichment having actually run, the
// score GATES on it: see computeMicroreactorScore.
const _MICRO_ISOLATION_ANCHORS = [[0.25, 0.05], [1, 0.15], [3, 0.35], [10, 0.7], [25, 0.95], [50, 1.0]];

// Distance to the nearest grid access point of ANY kind — the MINIMUM of the
// line and the substation, not a blend of the two.
//
// This is not a tuning choice, it is the only defensible reading of the data.
// A substation cannot exist without being connected to the network, so a
// substation one mile away is positive proof of grid service no matter what
// the transmission layer says. And the transmission layer says wrong things
// here: HIFLD's public feed carries bulk lines well but is patchy on
// sub-transmission (69 / 46 / 34.5 kV), so 6,222 sites — 13.5% of the corpus —
// report a substation materially CLOSER than their "nearest" line. dc-score.js
// documents the same gap and handles it in the opposite direction, in
// _effectiveGridAccess().
//
// A 60/40 blend of the two distances was the first cut here, and it broke the
// ranking outright: eight of the top twelve sites were FUDS properties around
// Sault Ste Marie, Michigan, credited with 41–44 miles of isolation while
// sitting a mile from a substation and four miles from a 29 MW power plant.
// Manufactured isolation is worse than no isolation term at all — it puts
// grid-served sites at the top of a ranking whose entire premise is that the
// grid is absent.
function _microGridAccessMi(site) {
  const line = site.transmission_mi;
  const sub = site.substation_mi;
  if (line == null && sub == null) return null;   // nothing of either kind within 100 mi
  if (line == null) return sub;
  if (sub == null) return line;
  return Math.min(line, sub);
}

function _microIsolationFrac(mi) {
  if (mi == null) return 1.0;                     // off-grid: nothing within 100 mi
  return _microInterp(mi, _MICRO_ISOLATION_ANCHORS);
}

function _microScoreGridIsolation(site, cap) {
  return Math.round(_microIsolationFrac(_microGridAccessMi(site)) * cap);
}

// ---------------------------------------------------------------------------
// 3. Anchor load (18)
//
// Isolation alone is worthless — an empty tundra scores maximum isolation and
// has nobody to sell to. This component is the counterweight: is there an
// identified local load, and is it the KIND of load a 1–20 MWe block
// displaces?
//
// The nearest power plant is the proxy. A small petroleum-fired plant ten
// miles away is a community running gensets — a like-for-like replacement at
// the highest displaced fuel cost in the country. A 2 GW combined-cycle plant
// next door means the grid is strong and a 1 MWe unit adds nothing.
const _MICRO_ANCHOR_DIST_ANCHORS = [[1, 1.0], [5, 0.8], [10, 0.5], [25, 0.2], [50, 0]];

// Nameplate of the nearest plant → how well it maps onto the product band.
function _microAnchorScaleFrac(mw) {
  if (mw == null) return 0.5;                     // plant located, size unknown
  if (mw <= MICRO_BAND_MWE) return 1.0;           // inside the product band
  if (mw <= 50) return 0.85;
  if (mw <= 100) return 0.6;
  if (mw <= 500) return 0.3;
  return 0.12;                                    // utility-scale: strong grid
}

// Displaced fuel cost — and, more importantly, whether the nearest plant is
// evidence of a LOAD at all.
//
// This is the discriminator, so it carries the largest share of the blend.
// Dispatchable generation is built where demand is: a small petroleum-fired
// plant is a community running gensets, the most expensive power in the
// country and the exact thing a microreactor replaces. Non-dispatchable
// generation is the opposite — solar and wind farms are sited on cheap rural
// land precisely BECAUSE nothing is there. Solar is the nearest plant for
// 14,722 of the 46,759 sites in this corpus, the single most common answer,
// so treating it as an anchor would have handed a third of the corpus a load
// signal that does not exist.
function _microAnchorFuelFrac(fuel) {
  if (!fuel) return 0.4;
  const f = String(fuel).toLowerCase();
  if (/petroleum|oil|diesel/.test(f)) return 1.0;
  if (/coal/.test(f)) return 0.85;
  if (/natural gas/.test(f)) return 0.7;
  if (/biomass|landfill|waste/.test(f)) return 0.55;  // dispatchable, often behind-the-meter industrial
  if (/hydro/.test(f)) return 0.35;                   // dispatchable but cheap and already clean
  if (/nuclear/.test(f)) return 0.2;                  // the load is already served, cleanly
  if (/solar|wind|batter|storage|geothermal/.test(f)) return 0.05;  // not a load signal
  return 0.4;
}

// No plant within 100 mi. A load may still exist — a mine, a village — but we
// have no evidence of one, so this is a floor rather than a zero. It is
// deliberately low: "isolated with nothing to serve" is the characteristic
// failure mode at the top of an isolation-weighted ranking.
const _MICRO_ANCHOR_FLOOR = 0.15;

// Fuel MULTIPLIES rather than averages in, and the reason is not tuning.
// Distance and size answer "is there a plant of about the right size nearby";
// fuel answers the prior question of whether that plant is evidence of a
// displaceable load AT ALL. Averaging let a 3.5 MW solar farm 2.5 miles away
// score 11 of 18 on the strength of its distance and size, which is exactly
// the signal solar does not carry — a solar farm sits on cheap rural land
// BECAUSE nothing is there. As a multiplier, a non-dispatchable neighbour
// collapses to the same floor as having found nothing, which is the honest
// answer: it never scores WORSE than finding nothing, and never better.
function _microScoreAnchorLoad(site, cap) {
  if (site.power_plant_mi == null) return Math.round(_MICRO_ANCHOR_FLOOR * cap);
  const dist = _microInterp(site.power_plant_mi, _MICRO_ANCHOR_DIST_ANCHORS);
  const scale = _microAnchorScaleFrac(site.power_plant_mw);
  const fuel = _microAnchorFuelFrac(site.power_plant_fuel);
  const frac = Math.max(_MICRO_ANCHOR_FLOOR, fuel * (0.6 * dist + 0.4 * scale));
  return Math.round(frac * cap);
}

// ---------------------------------------------------------------------------
// 4. Deliverability (18)
//
// The whole fleet is factory-built and shipped whole: one shipping container
// (Kaleidos, 70 t), a truck-delivered unit (Antares R1), a transportable
// module (eVinci, Project Pele). If a 70-tonne package cannot reach the site,
// nothing else about the site matters.
//
// This is also the deliberate BRAKE on the isolation premium. Without it an
// isolation-weighted ranking runs away to places no reactor can be delivered
// to. A null highway distance means Census TIGER has no primary road — no
// Interstate, US or major state route — within 100 miles, so it scores zero
// rather than being treated as unknown.
//
// Deliberately a near-flat ADEQUACY gate, not a proximity reward. A site 0.4
// miles from an Interstate and one 12 miles from it are equally deliverable —
// a low-boy trailer covers the last twelve miles without anyone noticing. Only
// where access genuinely fails does the curve fall away.
//
// The first cut used a steep proximity curve ([[1, 1.0], [5, 0.8], [15, 0.5],
// …]) and it quietly became a proxy for "urban", handing 18 points to
// well-connected suburban sites and cancelling out the isolation premium this
// whole lens exists to express. Rewarding closeness to a highway on a lens
// whose thesis is remoteness is scoring against yourself.
//
// Truck is the primary mode for every design in the fleet, so highway carries
// 70% against rail's 30%.
function _microScoreDeliverability(site, cap) {
  const road = site.highway_mi == null ? 0
    : _microInterp(site.highway_mi, [[15, 1.0], [40, 0.6], [80, 0.2]]);
  const rail = site.rail_mi == null ? 0
    : _microInterp(site.rail_mi, [[15, 1.0], [40, 0.5], [80, 0.1]]);
  return Math.round((0.7 * road + 0.3 * rail) * cap);
}

// ---------------------------------------------------------------------------
// 5. Readiness (18) — capped sum of independent sub-signals
//
// Unlike the generation lens, active reuse counts POSITIVE here. A reactor
// pad is a couple of acres inside a larger property, so an occupied site is
// not a liability — it is a site with a host, an existing electrical service,
// and quite possibly the load itself.
//
// The IRA energy-community bonus is weighted above the Opportunity Zone one
// because it is a direct +10 percentage-point adder on the clean-electricity
// investment credit for which new nuclear qualifies, whereas an OZ is a
// capital-gains deferral for the equity stack.
const _MICRO_READINESS_POINTS = Object.freeze({
  cleanup_complete: 6,
  energy_community: 4,
  in_reuse: 3,
  owner_known: 3,
  opportunity_zone: 2,
});

// Cleanup complete = deleted from the NPL, or EPA's Sitewide Ready for
// Anticipated Use measure met, or an ACRES cleanup marked complete. The
// retracted SWRAU variants are NOT a ready signal.
function _microCleanupComplete(site) {
  if (site.npl_status_code === "D") return true;
  if (typeof site.rau_status === "string" && /^Meets the Measure/i.test(site.rau_status)) return true;
  if (typeof site.cleanup_status === "string" && /complete/i.test(site.cleanup_status)) return true;
  return false;
}

function _microReadinessParts(site) {
  const P = _MICRO_READINESS_POINTS;
  return {
    cleanup_complete: _microCleanupComplete(site) ? P.cleanup_complete : 0,
    energy_community: site.in_energy_community === true ? P.energy_community : 0,
    in_reuse: /^yes/i.test(site.in_reuse || "") ? P.in_reuse : 0,
    owner_known: site.current_owner ? P.owner_known : 0,
    opportunity_zone: site.in_opportunity_zone === true ? P.opportunity_zone : 0,
  };
}

function _microScoreReadiness(site, cap) {
  const parts = _microReadinessParts(site);
  const total = Object.values(parts).reduce((a, b) => a + b, 0);
  return Math.min(cap, total);
}

// ---------------------------------------------------------------------------
// Subtractive terms
function _microFloodPenalty(site) {
  return site.in_sfha === true ? MICRO_FLOOD_SFHA_PENALTY : 0;
}

function _microWildfirePenalty(site) {
  const r = (site.nri_wildfire_rating || "").toLowerCase();
  return MICRO_WILDFIRE_PENALTY[r] || 0;
}

// ---------------------------------------------------------------------------
// The gate.
//
// `transmission_mi == null` carries opposite meanings before and after the
// infra-proximity enrichment lands: beforehand it means "not loaded yet",
// afterwards it means "genuinely off-grid". Scoring the first as the second
// would hand every site in the corpus a perfect isolation score during the
// second or two between first paint and the lazy load resolving.
//
// `_infraChecked` is stamped by ensureInfraLoaded() on every record the join
// touches, so it is the exact "we looked" marker. A site that already carries
// a distance needs no marker — the value itself is the evidence.
function microreactorScorable(site) {
  if (!site) return false;
  return site._infraChecked === true || site.transmission_mi != null;
}

function computeMicroreactorBreakdown(site) {
  if (!microreactorScorable(site)) return null;
  const W = MICRO_WEIGHTS;
  return {
    licensing_path: _microScoreLicensing(site, W.licensing_path),
    grid_isolation: _microScoreGridIsolation(site, W.grid_isolation),
    anchor_load: _microScoreAnchorLoad(site, W.anchor_load),
    deliverability: _microScoreDeliverability(site, W.deliverability),
    readiness: _microScoreReadiness(site, W.readiness),
  };
}

function computeMicroreactorScore(site) {
  const bd = computeMicroreactorBreakdown(site);
  if (bd == null) return null;
  const positive = Object.values(bd).reduce((a, b) => a + b, 0);
  const total = positive - _microFloodPenalty(site) - _microWildfirePenalty(site);
  return Math.max(0, Math.min(100, total));
}

// True when the site has no transmission line within the connector's 100-mile
// search radius — the hard islanded case. Only designs with a published
// no-grid-required claim (Antares R1; BWXT's expeditionary Project Pele) can
// serve one, so the UI surfaces it as a vendor filter, not just a score input.
function microreactorIsOffGrid(site) {
  return microreactorScorable(site) && _microGridAccessMi(site) == null;
}

const MICRO_SCORE_TOOLTIP =
  "Microreactor siting suitability (0–100) for a 1–20 MWe factory-built power " +
  "block. This lens INVERTS the grid signal: distance from transmission scores " +
  "HIGH, because a microreactor's case is displacing diesel where the grid is " +
  "weak or absent. Weighted factors are federal-land licensing pathway (24), " +
  "grid isolation (22), anchor load — an identified local load in or near the " +
  "1–20 MWe band (18), deliverability by road and rail (18), and site readiness " +
  "(18). SFHA flood subtracts 12 and Very High / Relatively High wildfire " +
  "subtracts 8 / 4. Land is a " + MICRO_MIN_ACRES + "-acre threshold screen, not " +
  "a ranked factor. Seismic is not scored — this project has no seismic layer " +
  "over the corpus.";

// Grouped for the breakdown chips. Keys MUST match the breakdown object
// exactly or the chips silently render 0 — the same drift risk documented for
// _DC_SUIT_GROUPS in dc-score.js.
const _MICRO_SUIT_GROUPS = Object.freeze([
  { title: "Pathway", keys: ["licensing_path", "readiness"] },
  { title: "The case", keys: ["grid_isolation", "anchor_load"] },
  { title: "Logistics", keys: ["deliverability"] },
]);

// ---------------------------------------------------------------------------
window.computeMicroreactorScore = computeMicroreactorScore;
window.computeMicroreactorBreakdown = computeMicroreactorBreakdown;
window.microreactorScorable = microreactorScorable;
window.microreactorIsOffGrid = microreactorIsOffGrid;
window.microreactorGridAccessMi = _microGridAccessMi;
window.microreactorMeetsAcreageThreshold = microreactorMeetsAcreageThreshold;
window.MICRO_WEIGHTS = MICRO_WEIGHTS;
window.MICRO_MIN_ACRES = MICRO_MIN_ACRES;
window.MICRO_BAND_MWE = MICRO_BAND_MWE;
window.MICRO_FLOOD_SFHA_PENALTY = MICRO_FLOOD_SFHA_PENALTY;
window.MICRO_WILDFIRE_PENALTY = MICRO_WILDFIRE_PENALTY;
window.MICRO_SCORE_TOOLTIP = MICRO_SCORE_TOOLTIP;
window._MICRO_SUIT_GROUPS = _MICRO_SUIT_GROUPS;
