// Verification map: draw the actual power lines, rail, roads, gas pipelines,
// plants and substations around one site, re-measure the distance to each, and
// set the result beside what the atlas claims.
//
//   verify.html?site=<id>            any corpus id, nuclear / coal / retired overlay id
//   verify.html?lat=..&lon=..&name=  an arbitrary point (no atlas claims to compare)
//
// Everything is fetched live from the public services the atlas's own
// connectors read (HIFLD, Census TIGERweb, OpenStreetMap), so this page checks
// the stored number against the source, not against itself.
(function () {
  "use strict";
  const MATCH_MI = 0.35;                 // 0.1 mi rounding on both sides plus projection drift
  const MAX_AUTO_RADIUS = 45;
  const PAGE = 2000;
  const HIFLD = "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services";
  const GAS = "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Natural_Gas_Interstate_and_Intrastate_Pipelines_1/FeatureServer/0/query";
  const PLANTS = "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Power_Plants_in_the_US/FeatureServer/0/query";
  const TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer";
  const OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"];   // the main instance often answers 502 under load

  // The atlas drops these OSM substation roles (connectors/infra_proximity.py), so the check must too.
  const NON_ELECTRIC_ROLES = new Set(["gas", "valve", "compression", "heat-exchanger", "internet"]);
  const KV_COLORS = [[345, "#7a1fa2"], [230, "#c62828"], [115, "#ef6c00"], [69, "#1565c0"], [0, "#607d8b"]];
  const kvColor = kv => (KV_COLORS.find(([min]) => kv >= min) || KV_COLORS[4])[1];

  // ---------------------------------------------------------------- geometry
  const R_LAT = 110540 / 1609.344;                         // miles per degree of latitude (same constants as the atlas's spatial index)
  const rLon = lat => 111320 * Math.cos(lat * Math.PI / 180) / 1609.344;

  // Nearest point on a set of polylines to (lat, lon), local equirectangular.
  function nearestOnPaths(lat, lon, paths) {
    const sx = rLon(lat), sy = R_LAT;
    let best = null;
    for (const path of paths) {
      for (let i = 0; i + 1 < path.length; i++) {
        const ax = (path[i][0] - lon) * sx, ay = (path[i][1] - lat) * sy;
        const bx = (path[i + 1][0] - lon) * sx, by = (path[i + 1][1] - lat) * sy;
        const dx = bx - ax, dy = by - ay, den = dx * dx + dy * dy;
        const t = den ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / den)) : 0;
        const px = ax + t * dx, py = ay + t * dy, d = Math.hypot(px, py);
        if (best === null || d < best.mi) best = {mi: d, lat: lat + py / sy, lon: lon + px / sx};
      }
    }
    return best;
  }
  function haversineMi(lat1, lon1, lat2, lon2) {
    const r = Math.PI / 180, dLat = (lat2 - lat1) * r, dLon = (lon2 - lon1) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dLon / 2) ** 2;
    return 3958.7613 * 2 * Math.asin(Math.sqrt(h));
  }

  // ----------------------------------------------------------------- fetches
  async function arcgisBox(url, lat, lon, radiusMi, {where = "1=1", outFields = ""} = {}) {
    const dLat = radiusMi / 69, dLon = radiusMi / (69 * Math.max(Math.cos(lat * Math.PI / 180), 0.05));
    const all = [];
    for (let offset = 0, pages = 0; pages < 6; pages++, offset += PAGE) {
      const p = new URLSearchParams({geometry: `${lon - dLon},${lat - dLat},${lon + dLon},${lat + dLat}`,
        geometryType: "esriGeometryEnvelope", inSR: "4326", outSR: "4326", spatialRel: "esriSpatialRelIntersects",
        outFields, returnGeometry: "true", f: "json", where, resultOffset: String(offset), resultRecordCount: String(PAGE)});
      const res = await fetch(`${url}?${p}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      if (j.error) throw new Error(j.error.message || "service error");   // ArcGIS reports errors with HTTP 200
      all.push(...(j.features || []));
      if (!j.exceededTransferLimit) return {features: all, truncated: false};
    }
    return {features: all, truncated: true};
  }
  async function overpassSubstations(lat, lon, radiusMi) {
    const dLat = radiusMi / 69, dLon = radiusMi / (69 * Math.cos(lat * Math.PI / 180));
    const bbox = [lat - dLat, lon - dLon, lat + dLat, lon + dLon].map(v => v.toFixed(5)).join(",");
    const q = `[out:json][timeout:25];(node["power"="substation"](${bbox});way["power"="substation"](${bbox}););out center tags;`;
    let j = null, last = "";
    for (const endpoint of OVERPASS) {
      try {
        const res = await fetch(endpoint, {method: "POST", body: "data=" + encodeURIComponent(q), headers: {"Content-Type": "application/x-www-form-urlencoded"}});
        if (res.ok) { j = await res.json(); break; }
        last = `HTTP ${res.status}`;
      } catch (e) { last = e.message; }
    }
    if (!j) throw new Error(last || "Overpass unavailable");
    if (j.remark || !Array.isArray(j.elements)) throw new Error("Overpass returned a partial answer");   // same refusal as the connector
    return {features: (j.elements || []).map(e => ({lat: e.lat ?? e.center?.lat, lon: e.lon ?? e.center?.lon, tags: e.tags || {}, id: `${e.type}/${e.id}`}))
      .filter(f => f.lat != null && !NON_ELECTRIC_ROLES.has(f.tags.substation)), truncated: false};
  }

  // ------------------------------------------------------------ layer table
  // `claim` names the atlas field the layer is checked against; `claimKv` maps
  // voltage-qualified claims (transmission_<kv>kv_mi) to the same features.
  const LAYERS = [
    {key: "transmission", label: "Transmission lines", claim: "transmission_mi", color: "#c62828", kind: "line",
      fetch: (la, lo, r) => arcgisBox(`${HIFLD}/Electric_Power_Transmission_Lines/FeatureServer/0/query`, la, lo, r, {outFields: "VOLTAGE,VOLT_CLASS,OWNER,STATUS"}),
      style: f => ({color: kvColor(f.attributes.VOLTAGE > 0 ? f.attributes.VOLTAGE : 0), weight: 3}),
      describe: a => `${a.VOLTAGE > 0 ? a.VOLTAGE + " kV" : (a.VOLT_CLASS || "voltage not reported")} · ${a.OWNER || "owner not reported"}`},
    {key: "substation", label: "Substations (OpenStreetMap)", claim: "substation_mi", color: "#6a1b9a", kind: "point",
      fetch: overpassSubstations, describe: t => `${t.name || "unnamed"} · ${t.voltage ? t.voltage + " V" : "voltage not tagged"}`},
    {key: "plant", label: "Power plants", claim: "power_plant_mi", color: "#2e7d32", kind: "point",
      fetch: (la, lo, r) => arcgisBox(PLANTS, la, lo, r, {outFields: "Plant_Name,Total_MW,PrimSource"}),
      describe: a => `${a.Plant_Name} · ${a.Total_MW} MW · ${a.PrimSource}`},
    {key: "gas", label: "Gas pipelines", claim: "gas_pipeline_mi", color: "#f9a825", kind: "line",
      fetch: (la, lo, r) => arcgisBox(GAS, la, lo, r, {outFields: "*"}), describe: () => "natural gas pipeline"},
    {key: "rail", label: "Railroads", claim: "rail_mi", color: "#455a64", kind: "line",
      fetch: (la, lo, r) => arcgisBox(`${TIGER}/9/query`, la, lo, r, {outFields: "NAME"}), describe: a => a.NAME || "railroad"},
    {key: "highway", label: "Primary roads", claim: "highway_mi", color: "#00838f", kind: "line",
      fetch: (la, lo, r) => arcgisBox(`${TIGER}/2/query`, la, lo, r, {outFields: "NAME", where: "MTFCC='S1100'"}), describe: a => a.NAME || "primary road"},
  ];
  const KV_CLAIMS = [[69, "transmission_69kv_mi"], [115, "transmission_115kv_mi"], [230, "transmission_230kv_mi"]];

  // -------------------------------------------------------- site resolution
  const CLAIM_ALIASES = {line_mi: "transmission_mi", line_69kv_mi: "transmission_69kv_mi", line_115kv_mi: "transmission_115kv_mi", line_230kv_mi: "transmission_230kv_mi"};
  async function getJson(path) { const r = await fetch(path); if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`); return r.json(); }
  function listOf(payload) { return payload.sites || payload.plants || payload.records || []; }

  async function resolveSite(id) {
    const overlays = {"EIA-": ["data/coal-plants.json", "coal plant"], "GHGRP-": ["data/retired-industrial.json", "retired industrial facility"]};
    for (const [prefix, [file, kind]] of Object.entries(overlays)) {
      if (id.startsWith(prefix)) { const s = listOf(await getJson(file)).find(x => x.id === id); if (s) return {site: s, kind, claims: normalizeClaims(s)}; }
    }
    for (const [file, kind] of [["data/ap1000-sites.json", "military installation"], ["data/nuclear-civilian-sites.json", "civilian nuclear site"]]) {
      const s = listOf(await getJson(file)).find(x => x.id === id);
      if (s) return {site: s, kind, claims: normalizeClaims(s)};
    }
    const program = id.startsWith("ACRES-") ? "data/epa-acres.json" : id.startsWith("FUDS-") ? "data/dod-fuds.json"
      : id.startsWith("BRAC-") ? "data/dod-brac.json" : "data/sites.json";
    const s = listOf(await getJson(program)).find(x => x.id === id);
    if (!s) return null;
    const core = listOf(await getJson("data/infra-proximity-core.json")).find(x => x.id === id) || {};
    return {site: s, kind: "brownfield record", claims: normalizeClaims(core), complete: true};
  }
  function normalizeClaims(rec) {
    const out = {};
    for (const [k, v] of Object.entries(rec)) { const key = CLAIM_ALIASES[k] || k; if (/_mi$/.test(key) && typeof v === "number") out[key] = v; }
    return out;
  }

  // ---------------------------------------------------------------- compare
  function compare(claimed, measured, radius) {
    if (measured === null) {
      if (claimed == null) return {cls: "muted", text: "nothing in view; atlas has none"};
      return claimed >= radius - 0.6 ? {cls: "ok", text: `beyond the ${radius.toFixed(0)} mi view, as claimed`}
        : {cls: "bad", text: `atlas says ${claimed} mi but nothing within ${radius.toFixed(0)} mi`};
    }
    if (claimed == null) return {cls: "warn", text: "source has one; atlas shows none"};
    const d = Math.abs(measured - claimed);
    return d <= MATCH_MI ? {cls: "ok", text: "matches"} : {cls: "bad", text: `differs by ${d.toFixed(2)} mi`};
  }
  const fmt = v => v == null ? "none" : v < 0.05 ? "<0.1 mi" : `${v.toFixed(1)} mi`;

  // ------------------------------------------------------------------- page
  window.VerifyGeo = {nearestOnPaths, haversineMi, compare, MATCH_MI};
  const $ = id => document.getElementById(id);
  const params = new URLSearchParams(location.search);

  function say(msg, cls) { const el = $("status"); el.textContent = msg; el.className = "note " + (cls || ""); }
  function el(tag, props, ...kids) { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; }

  async function main() {
    let resolved = null, lat, lon, name;
    if (params.get("site")) {
      try { resolved = await resolveSite(params.get("site")); } catch (e) { say(`Could not load the site: ${e.message}`, "bad"); return; }
      if (!resolved) { say(`No site with id "${params.get("site")}".`, "bad"); return; }
      ({lat, lon, name} = resolved.site);
      lat = resolved.site.lat_real ?? lat; lon = resolved.site.lon_real ?? lon;
    } else if (params.get("lat") && params.get("lon")) {
      lat = Number(params.get("lat")); lon = Number(params.get("lon")); name = params.get("name") || "Chosen point";
    }
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) { say("Add ?site=<id> or ?lat=..&lon=.. to the address.", "bad"); return; }

    $("who").textContent = `${name} · ${resolved ? resolved.kind : "point"} · ${lat.toFixed(4)}, ${lon.toFixed(4)}`;
    document.title = `Verify: ${name}`;
    const claims = resolved ? resolved.claims : {};
    // For corpus records an absent field means "nothing within 100 mi"; for an overlay row it means the atlas stores no figure.
    const stored = key => !resolved || resolved.complete || key in claims;
    fiberPanel(lat, lon);

    const map = L.map("map", {preferCanvas: true}).setView([lat, lon], 11);
    window.__verifyMap = map;
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors"}).addTo(map);
    L.circleMarker([lat, lon], {radius: 8, color: "#000", weight: 2, fillColor: "#ffeb3b", fillOpacity: 1}).addTo(map).bindTooltip(el("span", {}, name));   // an element, not a string: Leaflet sets string tooltips as HTML and ?name= is user input
    const groups = {};
    const rows = new Map();

    const layerBox = $("layers"), tbody = document.querySelector("#results tbody");
    for (const L_ of LAYERS) {
      const group = L.layerGroup().addTo(map); groups[L_.key] = group;
      const cb = el("input", {type: "checkbox", checked: true});
      cb.addEventListener("change", () => cb.checked ? group.addTo(map) : map.removeLayer(group));
      layerBox.append(el("label", {className: "layer"}, cb, el("span", {className: "sw", style: `background:${L_.color}`}), L_.label));
      const status = el("td"), measured = el("td", {className: "num"}), claimedTd = el("td", {className: "num"});
      claimedTd.textContent = !resolved ? "—" : stored(L_.claim) ? fmt(claims[L_.claim]) : "not stored"; measured.textContent = "…"; status.textContent = "loading";
      tbody.append(el("tr", {}, el("td", {}, L_.label), claimedTd, measured, status));
      rows.set(L_.key, {measured, status});
    }
    for (const [kv, field] of KV_CLAIMS) {
      if (!(field in claims) && !("transmission_mi" in claims)) continue;
      const m = el("td", {className: "num"}, "…"), s = el("td"), c = el("td", {className: "num"});
      c.textContent = fmt(claims[field]);
      tbody.append(el("tr", {}, el("td", {}, `Lines ≥ ${kv} kV`), c, m, s));
      rows.set("kv" + kv, {measured: m, status: s});
    }

    let runId = 0;
    async function run() {
      const mine = ++runId;                       // a newer run supersedes this one; stale results are dropped
      const sel = $("radius").value;
      for (const L_ of LAYERS) { groups[L_.key].clearLayers(); }
      let n = 0;
      await Promise.all(LAYERS.map(async L_ => {
        const radius = sel === "auto" ? Math.min(MAX_AUTO_RADIUS, Math.max(6, (claims[L_.claim] || 0) * 1.5 + 2)) : Number(sel);
        const r = rows.get(L_.key);
        try {
          const {features, truncated} = await L_.fetch(lat, lon, radius);
          if (mine !== runId) return;             // superseded while the request was in flight
          const near = draw(L_, features, groups[L_.key], lat, lon);
          const cmp = stored(L_.claim) && resolved ? compare(claims[L_.claim], near ? near.mi : null, radius) : {cls: "muted", text: "no atlas figure to compare"};
          r.measured.textContent = near ? `${fmt(near.mi)} (${features.length} in ${radius.toFixed(0)} mi)` : `none in ${radius.toFixed(0)} mi`;
          r.status.textContent = cmp.text + (truncated ? " · view truncated, nearest feature may be missing" : ""); r.status.className = truncated ? "warn" : cmp.cls;
          if (L_.key === "transmission") kvRows(features, lat, lon, radius, claims, rows, truncated);
          n++;
        } catch (e) {
          if (mine !== runId) return;
          r.measured.textContent = "unavailable"; r.status.textContent = `source error: ${e.message}`; r.status.className = "warn";
        }
      }));
      if (mine !== runId) return;
      say(`Checked ${n} of ${LAYERS.length} layers against live sources.`, n === LAYERS.length ? "" : "warn");
      window.__verifyDone = true;
    }
    $("radius").addEventListener("change", () => { window.__verifyDone = false; say("Re-checking…"); run(); });
    say("Fetching live source layers…");
    run();
  }

  // Draw one layer and return the nearest feature's distance and point.
  function draw(L_, features, group, lat, lon) {
    let best = null;
    if (L_.kind === "line") {
      for (const f of features) {
        const paths = (f.geometry && f.geometry.paths) || [];
        const near = nearestOnPaths(lat, lon, paths);
        if (near && (!best || near.mi < best.mi)) best = near;
        const style = L_.style ? L_.style(f) : {color: L_.color, weight: 3};
        L.polyline(paths.map(p => p.map(([x, y]) => [y, x])), Object.assign({opacity: 0.85}, style))
          .bindPopup(() => el("div", {}, L_.describe(f.attributes || {}))).addTo(group);
      }
    } else {
      for (const f of features) {
        const a = f.geometry ? {lat: f.geometry.y, lon: f.geometry.x} : {lat: f.lat, lon: f.lon};
        const mi = haversineMi(lat, lon, a.lat, a.lon);
        if (!best || mi < best.mi) best = {mi, lat: a.lat, lon: a.lon};
        L.circleMarker([a.lat, a.lon], {radius: 5, color: L_.color, weight: 2, fillOpacity: 0.7})
          .bindPopup(() => el("div", {}, L_.describe(f.attributes || f.tags || {}))).addTo(group);
      }
    }
    if (best) L.polyline([[lat, lon], [best.lat, best.lon]], {color: L_.color, weight: 2, dashArray: "6 6"})
      .bindTooltip(`${L_.label}: ${best.mi.toFixed(2)} mi`, {sticky: true}).addTo(group);
    return best;
  }

  function kvRows(features, lat, lon, radius, claims, rows, truncated) {
    for (const [kv, field] of KV_CLAIMS) {
      const r = rows.get("kv" + kv);
      if (!r) continue;
      const paths = features.filter(f => (f.attributes.VOLTAGE || -1) >= kv).flatMap(f => (f.geometry && f.geometry.paths) || []);
      const near = nearestOnPaths(lat, lon, paths);
      const cmp = compare(claims[field], near ? near.mi : null, radius);
      r.measured.textContent = near ? fmt(near.mi) : `none in ${radius.toFixed(0)} mi`;
      r.status.textContent = cmp.text + (truncated ? " · view truncated, nearest feature may be missing" : ""); r.status.className = truncated ? "warn" : cmp.cls;
    }
  }

  function fiberPanel(lat, lon) {
    $("fiber-note").textContent = "No public source publishes fiber routes as map geometry, so the atlas holds no fiber distance and this page draws none. "
      + "These open the nearest public evidence instead: which providers the FCC records at addresses here, and what OpenStreetMap has tagged.";
    const links = [
      [`https://broadbandmap.fcc.gov/home?lat=${lat.toFixed(5)}&lon=${lon.toFixed(5)}&zoom=14`, "FCC National Broadband Map at this point (fiber availability by address)"],
      [`https://www.openstreetmap.org/#map=13/${lat.toFixed(5)}/${lon.toFixed(5)}`, "OpenStreetMap here (telecom cables are tagged on a minority of routes)"],
    ];
    const ul = $("fiber-links");
    for (const [href, text] of links) ul.append(el("li", {}, el("a", {href, target: "_blank", rel: "noopener"}, text)));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => window.addEventListener("load", main));
  else window.addEventListener("load", main);
})();
