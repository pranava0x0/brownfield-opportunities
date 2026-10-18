// Siting screens: a few pass/fail criteria per use, each threshold taken from
// a named public source. A site's rank is the number of criteria it passes,
// then the number it leaves unknown, then one stated tie-breaker. Missing data
// is "unknown", never a pass. No weights.
//
// Loaded by the browser (window.SiteScreens) and by node
// (scripts/screen.js explain|top) so every ranking can be traced from a shell.
(function (root) {
  "use strict";
  const VERSION = "screens-1";
  const num = v => typeof v === "number" && Number.isFinite(v);
  // A test returns true (pass), false (fail) or null (unknown).
  const atMost = (field, max) => s => num(s[field]) ? s[field] <= max : null;
  const atLeast = (field, min) => s => num(s[field]) ? s[field] >= min : null;
  const miles = v => num(v) ? (v < 0.1 ? "<0.1 mi" : `${v.toFixed(1)} mi`) : "unknown";
  const acres = v => num(v) ? `${Math.round(v).toLocaleString("en-US")} ac` : "unknown";

  // Grid access: the nearer of a mapped line or substation. A substation is
  // connected to the network by definition, so it stands in when the public
  // line layer misses sub-transmission.
  function gridMi(s) {
    const d = [s.transmission_mi, s.substation_mi].filter(num);
    return d.length ? Math.min(...d) : null;
  }
  // Reported acreage, unless scripts/check_acreage_artifacts.py flagged it as a
  // county outline or a multi-county region (then it says nothing about a parcel).
  function siteAcres(s) {
    if (s.acreage_flag) return null;
    return num(s.acreage) ? s.acreage : num(s.parcel_acreage) ? s.parcel_acreage : null;
  }
  const notFlood = s => s.in_sfha === true ? false : s.in_sfha === false ? true : null;

  const SCREENS = {};
  function define(key, spec) { SCREENS[key] = Object.freeze({key, ...spec}); }

  // ---- Sources ----
  const SRC = {
    epaRepower: {title: "EPA RE-Powering screening criteria (utility-scale PV)",
      url: "https://www.epa.gov/re-powering/5-data-documentation-mapping-and-screening-criteria-renewable-energy-generation"},
    fema: {title: "FEMA flood zones (Special Flood Hazard Area)", url: "https://www.fema.gov/about/glossary/flood-zones"},
    hifld: {title: "HIFLD Electric Power Transmission Lines",
      url: "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer/0"},
    tiger: {title: "Census TIGER primary roads and railroads", url: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer"},
    eo14318: {title: "EO 14318: qualifying data-center projects exceed 100 MW",
      url: "https://www.whitehouse.gov/presidential-actions/2025/07/accelerating-federal-permitting-of-data-center-infrastructure/"},
    afLease: {title: "Air Force AI data-center lease parcels (AFCEC-26-R-0002): 73 to 560 acres each",
      url: "https://www.edwards.af.mil/News/Display/Article/4354128/have-questions-about-the-solicitation-for-ai-data-centers-we-got-answers/"},
    ports: {title: "BTS/USACE Principal Ports (NTAD)", url: "https://www.bts.gov/ntad"},
    usgs: {title: "USGS streamgage annual mean flow", url: "https://waterdata.usgs.gov/"},
    nickel: {title: "Project analogs: Westwin Elements (Lawton OK, ~480 ac), Vale Long Harbour (~371 ac)",
      url: "https://github.com/pranava0x0/brownfield-opportunities/blob/main/research/nickel-refining-siting-2026-09.md"},
  };

  // ---- Corpus screens (Superfund, ACRES, FUDS, BRAC sites) ----
  const lineKv = s => num(s.transmission_kv) ? `${s.transmission_kv} kV · ${miles(s.transmission_mi)}` : miles(s.transmission_mi);
  const lineAtLeast = (kv, mi) => s => {
    if (!num(s.transmission_mi)) return null;
    if (s.transmission_mi > mi) return false;
    return num(s.transmission_kv) ? s.transmission_kv >= kv : null;
  };
  const landAtLeast = min => s => { const a = siteAcres(s); return a === null ? null : a >= min; };
  const landShow = s => s.acreage_flag ? "area not a parcel" : acres(siteAcres(s));
  const floodShow = s => s.in_sfha === true ? "in flood zone" : s.in_sfha === false ? "outside" : "unknown";

  define("dc", {
    label: "Data center", universe: "corpus",
    method: "No federal siting standard exists for data centers. Four checks on public layers: transmission, land, flood, road.",
    criteria: [
      {id: "grid", label: "Line ≥115 kV within 5 mi", rule: "transmission_kv ≥ 115 and transmission_mi ≤ 5", kind: "P",
        note: "A >100 MW load (EO 14318 threshold) is normally served at transmission voltage.",
        source: SRC.hifld, test: lineAtLeast(115, 5), show: lineKv},
      {id: "land", label: "Land ≥100 acres", rule: "acreage ≥ 100", kind: "P",
        note: "Air Force AI data-center parcels ran 73–560 acres.", source: SRC.afLease, test: landAtLeast(100), show: landShow},
      {id: "flood", label: "Outside flood zone", rule: "in_sfha = false", kind: "R", source: SRC.fema, test: notFlood, show: floodShow},
      {id: "road", label: "Primary road within 10 mi", rule: "highway_mi ≤ 10", kind: "P", source: SRC.tiger,
        test: atMost("highway_mi", 10), show: s => miles(s.highway_mi)},
    ],
    tieBreak: {label: "nearest transmission line", value: s => s.transmission_mi},
  });

  define("solar", {
    label: "Solar farm", universe: "corpus",
    method: "EPA's own RE-Powering thresholds for utility-scale solar, plus FEMA flood zones.",
    criteria: [
      {id: "land", label: "Land ≥35 acres", rule: "acreage ≥ 35", kind: "R", source: SRC.epaRepower, test: landAtLeast(35), show: landShow},
      {id: "grid", label: "Line ≥69 kV within 10 mi", rule: "transmission_kv ≥ 69 and transmission_mi ≤ 10", kind: "R",
        source: SRC.epaRepower, test: lineAtLeast(69, 10), show: lineKv},
      {id: "road", label: "Road within 10 mi", rule: "highway_mi ≤ 10", kind: "R", source: SRC.epaRepower,
        test: atMost("highway_mi", 10), show: s => miles(s.highway_mi)},
      {id: "flood", label: "Outside flood zone", rule: "in_sfha = false", kind: "R", source: SRC.fema, test: notFlood, show: floodShow},
    ],
    tieBreak: {label: "largest acreage", dir: "desc", value: siteAcres},
  });

  define("port", {
    label: "Port industry", universe: "corpus",
    applies: s => num(s.port_mi) && s.port_mi <= 25,
    scope: "sites within 25 mi of a principal port",
    method: "Heavy industry that ships by water: principal port, land, transmission and flood. Channel depth and berths are not assessed.",
    criteria: [
      {id: "port", label: "Principal port within 10 mi", rule: "port_mi ≤ 10 (to the port area's center)", kind: "P",
        source: SRC.ports, test: atMost("port_mi", 10), show: s => `${miles(s.port_mi)}${s.port_name ? " · " + s.port_name : ""}`},
      {id: "land", label: "Land ≥100 acres", rule: "acreage ≥ 100", kind: "P", source: SRC.afLease, test: landAtLeast(100), show: landShow},
      {id: "grid", label: "Line ≥115 kV within 5 mi", rule: "transmission_kv ≥ 115 and transmission_mi ≤ 5", kind: "P",
        source: SRC.hifld, test: lineAtLeast(115, 5), show: lineKv},
      {id: "flood", label: "Outside flood zone", rule: "in_sfha = false", kind: "R", source: SRC.fema, test: notFlood, show: floodShow},
    ],
    tieBreak: {label: "nearest port", value: s => s.port_mi},
  });

  define("nickel", {
    label: "Nickel refinery", universe: "corpus",
    method: "Hydrometallurgical refinery checks taken from two built projects. Water is annual mean flow, not low flow.",
    criteria: [
      {id: "land", label: "Land ≥300 acres", rule: "acreage ≥ 300", kind: "P", source: SRC.nickel, test: landAtLeast(300), show: landShow},
      {id: "rail", label: "Rail within 1 mi", rule: "rail_mi ≤ 1", kind: "P", source: SRC.tiger, test: atMost("rail_mi", 1), show: s => miles(s.rail_mi)},
      {id: "grid", label: "Line ≥115 kV within 5 mi", rule: "transmission_kv ≥ 115 and transmission_mi ≤ 5", kind: "P",
        source: SRC.hifld, test: lineAtLeast(115, 5), show: lineKv},
      {id: "water", label: "River ≥100 cfs within 10 mi", rule: "water_gage_mi ≤ 10 and water_flow_cfs ≥ 100", kind: "P", source: SRC.usgs,
        test: s => !num(s.water_gage_mi) || !num(s.water_flow_cfs) ? null : s.water_gage_mi <= 10 && s.water_flow_cfs >= 100,
        show: s => num(s.water_flow_cfs) ? `${Math.round(s.water_flow_cfs).toLocaleString("en-US")} cfs · ${miles(s.water_gage_mi)}` : "unknown"},
      {id: "feed", label: "Port ≤10 mi or feedstock ≤100 mi", rule: "port_mi ≤ 10 or nickel_feedstock_mi ≤ 100", kind: "P", source: SRC.nickel,
        test: s => (num(s.port_mi) && s.port_mi <= 10) || (num(s.nickel_feedstock_mi) && s.nickel_feedstock_mi <= 100) ? true
          : num(s.port_mi) || num(s.nickel_feedstock_mi) ? false : null,
        show: s => num(s.port_mi) && s.port_mi <= 10 ? `port ${miles(s.port_mi)}` : num(s.nickel_feedstock_mi) ? `feed ${Math.round(s.nickel_feedstock_mi)} mi` : "unknown"},
    ],
    tieBreak: {label: "largest acreage", dir: "desc", value: siteAcres},
  });

  function evaluate(site, key) {
    const screen = SCREENS[key];
    if (!screen) throw new Error(`unknown screen ${key}`);
    const s = site || {};
    const results = screen.criteria.map(c => {
      const r = c.test(s);
      return {id: c.id, label: c.label, status: r === true ? "pass" : r === false ? "fail" : "unknown",
        value: c.show ? c.show(s) : ""};
    });
    const met = results.filter(r => r.status === "pass").length;
    const unknown = results.filter(r => r.status === "unknown").length;
    return {key, met, unknown, total: results.length, results};
  }

  // Order: criteria met (desc), unknown (asc), tie-breaker, then name.
  function rank(sites, key) {
    const screen = SCREENS[key];
    const tb = screen.tieBreak;
    const rows = sites.filter(s => !screen.applies || screen.applies(s)).map(site => ({site, ev: evaluate(site, key)}));
    rows.sort((a, b) => b.ev.met - a.ev.met || a.ev.unknown - b.ev.unknown
      || (tb ? tieValue(tb, a.site) - tieValue(tb, b.site) : 0)
      || String(a.site.name || a.site.id).localeCompare(String(b.site.name || b.site.id)));
    return rows;
  }
  // Ascending sort key; a missing value sorts last.
  function tieValue(tb, s) {
    const v = tb.value(s);
    if (!num(v)) return Infinity;
    return tb.dir === "desc" ? -v : v;
  }

  const api = {VERSION, SCREENS, evaluate, rank, gridMi, siteAcres, miles, acres, define,
    helpers: {num, atMost, atLeast, notFlood}};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.SiteScreens = api;
})(typeof window !== "undefined" ? window : null);
