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

  // ---- Nuclear screens: 14 curated military installations ----
  const NUC = {
    pop: {title: "10 CFR 100.3: population center of about 25,000 residents", url: "https://www.law.cornell.edu/cfr/text/10/100.3"},
    census: {title: "Census Vintage 2024 place estimates", url: "https://www.census.gov/data/tables/time-series/demo/popest/2020s-total-cities-and-towns.html"},
    seismic: {title: "AP1000 certified seismic design: 0.30 g peak ground acceleration (NRC DCD Tier 2 §3.7)", url: "https://www.nrc.gov/docs/ML1117/ML11171A430.pdf"},
    vogtle: {title: "Vogtle 3&4 EIS: two units withdraw about 1% of average river flow", url: "https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf"},
    army: {title: "Army Janus program: five installations selected Aug 26 2026", url: "https://www.world-nuclear-news.org/articles/us-army-selects-five-microreactor-vendors-to-power-bases"},
    armyCriteria: {title: "Army Janus criteria include grid maturity", url: "https://www.army.mil/article/294897/army_selects_fort_drum_for_janus_program_microreactor"},
    nrc: {title: "NRC new-reactor licensing status", url: "https://www.nrc.gov/reactors/new-reactors.html"},
  };
  // Land for an installation: the Air Force offered-parcel area where there is
  // one (that is what a developer could lease), otherwise analyst-estimated
  // developable acreage.
  const installationAcres = s => num(s.af_rflp_acres) ? s.af_rflp_acres : num(s.developable_acreage) ? s.developable_acreage : null;
  const popCheck = {id: "pop", label: "No city ≥25,000 within 10 mi", rule: "pop_center_mi > 10 (to the city's center point)", kind: "P",
    note: "Census-incorporated places only; the regulatory test also needs the low-population-zone radius.",
    source: NUC.pop, test: s => num(s.pop_center_mi) ? s.pop_center_mi > 10 : null,
    show: s => num(s.pop_center_mi) ? `${s.pop_center_name} ${miles(s.pop_center_mi)}` : "unknown"};
  const seismicCheck = {id: "seismic", label: "Ground motion ≤0.30 g", rule: "usgs_pgam ≤ 0.30", kind: "P",
    note: "USGS building-code PGA compared with the AP1000 certified envelope; an NRC site needs site-specific motion.",
    source: NUC.seismic, test: atMost("usgs_pgam", 0.30), show: s => num(s.usgs_pgam) ? `${s.usgs_pgam.toFixed(2)} g` : "unknown"};
  const riverCheck = (withdrawalCfs, label) => ({id: "water", label, rule: `supply_flow_cfs ≥ 100 × ${withdrawalCfs} cfs`, kind: "P",
    note: "River supply only; groundwater and reservoir supplies fail. Annual mean flow, not low flow.",
    source: NUC.vogtle, test: s => s.supply_source ? (num(s.supply_flow_cfs) ? s.supply_flow_cfs >= 100 * withdrawalCfs : false) : null,
    show: s => num(s.supply_flow_cfs) ? `${Math.round(s.supply_flow_cfs).toLocaleString("en-US")} cfs · ${s.supply_source}` : (s.supply_source || "unknown")});
  const landCheck = min => ({id: "land", label: `Land ≥${min} acres`, rule: `af_rflp_acres or developable_acreage ≥ ${min}`, kind: "P",
    note: "Offered lease parcel where the Air Force named one; otherwise analyst estimate.",
    source: {title: "Analyst estimate; AF lease parcels from AFCEC-26-R-0002", url: SRC.afLease.url},
    test: s => { const a = installationAcres(s); return a === null ? null : a >= min; }, show: s => acres(installationAcres(s))});

  define("ap1000", {
    label: "Large reactor (AP1000)", universe: "installations",
    method: "Population, earthquake, river, grid and land checks against the AP1000 design. A screen, not an NRC site finding.",
    criteria: [popCheck, seismicCheck, riverCheck(41.5, "River ≥4,150 cfs (100× one unit)"),
      {id: "grid", label: "Line ≥230 kV within 5 mi", rule: "transmission_kv ≥ 230 and transmission_mi ≤ 5", kind: "P",
        source: SRC.hifld, test: lineAtLeast(230, 5), show: lineKv},
      landCheck(500)],
    tieBreak: {label: "largest river flow", dir: "desc", value: s => s.supply_flow_cfs},
  });
  define("smr", {
    label: "Small modular reactor (300 MW)", universe: "installations",
    method: "Same checks scaled to a 300 MW unit (AP300 class): about a third of the water and land.",
    criteria: [popCheck, seismicCheck, riverCheck(12.3, "River ≥1,230 cfs (100× one unit)"),
      {id: "grid", label: "Line ≥115 kV within 5 mi", rule: "transmission_kv ≥ 115 and transmission_mi ≤ 5", kind: "P",
        source: SRC.hifld, test: lineAtLeast(115, 5), show: lineKv},
      landCheck(100)],
    tieBreak: {label: "largest river flow", dir: "desc", value: s => s.supply_flow_cfs},
  });
  define("micro", {
    label: "Microreactor (Army Janus)", universe: "installations",
    applies: s => s.janus_site === true,
    scope: "the nine Janus candidate installations",
    method: "The Army's own selection plus its stated grid-maturity criterion.",
    criteria: [
      {id: "selected", label: "Selected by the Army", rule: "janus_status starts 'Selected'", kind: "R", source: NUC.army,
        test: s => typeof s.janus_status === "string" ? s.janus_status.startsWith("Selected") : null, show: s => s.janus_status || "unknown"},
      {id: "grid", label: "Line within 5 mi", rule: "transmission_mi ≤ 5", kind: "P", source: NUC.armyCriteria,
        test: atMost("transmission_mi", 5), show: s => miles(s.transmission_mi)},
      popCheck],
    tieBreak: {label: "nearest line", value: s => s.transmission_mi},
  });

  // ---- Civilian nuclear sites (existing plants and announced projects) ----
  const LICENSE_STAGE = ["construction_permit_issued", "under_construction", "restarting", "col_issued", "partial_construction",
    "esp_approved", "col_application_filed", "esp_under_review", "pre_application", "site_characterization", "possible_restart",
    "operating_expansion", "col_suspended", "col_withdrawn", "col_terminated"];
  define("civilian", {
    label: "Civilian nuclear sites", universe: "civilian",
    method: "NRC licensing status first, then whether the site already hosts a reactor and how close the nearest city is.",
    criteria: [
      {id: "license", label: "Permit or license in force", rule: "status is construction permit, COL, construction or restart", kind: "R",
        source: NUC.nrc, test: s => ["construction_permit_issued", "under_construction", "restarting", "col_issued", "partial_construction"].includes(s.status),
        show: s => String(s.status || "unknown").replace(/_/g, " ")},
      {id: "existing", label: "Existing reactor site", rule: "status is operating expansion or restart", kind: "R", source: NUC.nrc,
        test: s => ["operating_expansion", "restarting", "possible_restart"].includes(s.status),
        show: s => ["operating_expansion", "restarting", "possible_restart"].includes(s.status) ? "operating or recent plant" : "new site"},
      popCheck],
    tieBreak: {label: "licensing stage", value: s => { const i = LICENSE_STAGE.indexOf(s.status); return i < 0 ? 99 : i; }},
  });

  // ---- Coal plants (EIA-860M, every plant with >=100 MW of coal retired or retiring) ----
  const COAL = {
    eia: {title: "EIA-860M generator inventory", url: "https://www.eia.gov/electricity/data/eia860m/"},
    ferc: {title: "FERC Order 2023: surplus interconnection and generator replacement", url: "https://www.ferc.gov/explainer-interconnection-final-rule"},
  };
  define("coal", {
    label: "Coal plant reuse", universe: "coal",
    method: "EIA status, a free interconnection point and a high-voltage line. Reusing a retired plant's connection still needs a utility study.",
    criteria: [
      {id: "retired", label: "All coal units retired", rule: "status = retired (EIA-860M Retired sheet)", kind: "R", source: COAL.eia,
        test: s => s.status ? s.status === "retired" : null,
        show: s => s.status === "retired" ? `retired ${s.retire_year || ""}` : `retiring ${s.retire_year || ""}`},
      {id: "poi", label: "No other unit ≥50 MW running", rule: "other_operating_mw < 50", kind: "P",
        note: "A converted gas unit or new plant at the site usually holds the interconnection.",
        source: COAL.ferc, test: s => num(s.other_operating_mw) ? s.other_operating_mw < 50 : null,
        show: s => num(s.other_operating_mw) && s.other_operating_mw > 0 ? `${Math.round(s.other_operating_mw)} MW running` : "none"},
      {id: "grid", label: "Line ≥230 kV within 2 mi", rule: "line_kv ≥ 230 and line_mi ≤ 2", kind: "P", source: SRC.hifld,
        test: s => !num(s.line_mi) ? null : s.line_mi > 2 ? false : num(s.line_kv) ? s.line_kv >= 230 : null,
        show: s => num(s.line_kv) ? `${s.line_kv} kV · ${miles(s.line_mi)}` : miles(s.line_mi)},
    ],
    tieBreak: {label: "largest coal capacity", dir: "desc", value: s => s.coal_mw},
  });

  // ---- Retired heavy industry (EPA GHGRP facilities that stopped reporting) ----
  const GHG = {title: "EPA GHGRP: facilities may stop reporting after closure or sustained low emissions (40 CFR 98.2(i))",
    url: "https://www.ecfr.gov/current/title-40/chapter-I/subchapter-C/part-98/subpart-A/section-98.2"};
  define("retired", {
    label: "Retired heavy industry", universe: "retired",
    method: "Facilities that stopped EPA greenhouse-gas reporting. Stopping is not proof of closure; these checks favor the likeliest closures with land records nearby.",
    criteria: [
      {id: "reason", label: "EPA accepted the reason", rule: "reporting_status = valid_reason", kind: "R", source: GHG,
        test: s => s.reporting_status ? s.reporting_status === "valid_reason" : null,
        show: s => s.reporting_status === "valid_reason" ? `last report ${s.last_report_year}` : `no reason · ${s.last_report_year}`},
      {id: "plant", label: "Plant, not a mine", rule: "category = Manufacturing", kind: "P",
        note: "Some mines that stopped reporting still operate (Hecla Greens Creek).", source: GHG,
        test: s => s.category ? s.category === "Manufacturing" : null, show: s => s.sector || s.category || ""},
      {id: "tracked", label: "Cleanup record within 1 mi", rule: "tracked_site_mi ≤ 1", kind: "P",
        note: "A Superfund, ACRES, FUDS or BRAC record nearby carries owner and cleanup data.",
        source: {title: "Join to this atlas's site records", url: "https://pranava0x0.github.io/brownfield-opportunities/"},
        test: s => num(s.tracked_site_mi) ? s.tracked_site_mi <= 1 : false,
        show: s => num(s.tracked_site_mi) ? `${s.tracked_site_name} · ${miles(s.tracked_site_mi)}` : "none"},
    ],
    tieBreak: {label: "most recent last report", dir: "desc", value: s => s.last_report_year},
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
