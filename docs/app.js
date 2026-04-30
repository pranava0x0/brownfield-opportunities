// Brownfield Opportunities — static dashboard
// Loads docs/data/sites.json (Superfund, fast first paint) and lazy-loads
// docs/data/epa-acres.json when the user toggles brownfields on. Renders a
// Leaflet map + sortable table with filters, URL state sharing, CSV export,
// and a theme toggle.

const PRIMARY_DATA_URL = "data/sites.json";
const ACRES_DATA_URL = "data/epa-acres.json";
// Vector basemap: US states (always) + US counties (lazy at zoom ≥ COUNTY_MIN_ZOOM).
// No tiles — Canada/Mexico literally don't exist on the map. Choropleth-style
// look (think CNN election tracker / datacenterbans.com) with bold state borders
// and CSS-var-driven fills so the same render works in light and dark.
const STATES_DATA_URL = "data/us-states.json";
const COUNTIES_DATA_URL = "data/us-counties-topo.json";
const COUNTY_MIN_ZOOM = 7;
const BASEMAP_ATTRIB =
  'Boundaries: <a href="https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html">US Census</a>';

const DEFAULT_VIEW = { center: [39.5, -98.35], zoom: 4 };
// Continental US (lower 48) + a strip below it where AK/HI/PR/Pacific insets
// live (classic US-map-with-insets layout — see INSETS below).
const US_BOUNDS = L.latLngBounds([18, -127], [51, -65]);
const MIN_ZOOM = 4;

// Cartographic insets: states/territories whose real coordinates fall outside
// the lower-48 view get linearly remapped into labeled boxes at the bottom of
// the map. Real coords are preserved on `lat_real`/`lon_real` for the detail
// panel and CSV export. `states` lists every state/territory code routed into
// each box; `src` is the source bbox of the real coords; `dst` is where the
// box sits within US_BOUNDS.
const INSETS = [
  {
    key: "AK",
    label: "ALASKA",
    states: ["AK"],
    src: { south: 51, north: 72, west: -180, east: -130 },
    dst: { south: 19.2, north: 25.2, west: -125.5, east: -115.5 },
  },
  {
    key: "HI",
    label: "HAWAII",
    states: ["HI"],
    src: { south: 18.5, north: 22.5, west: -161, east: -154 },
    dst: { south: 19.2, north: 21.6, west: -114.0, east: -109.0 },
  },
  {
    key: "CARIB",
    label: "PR / USVI",
    states: ["PR", "VI"],
    src: { south: 17.5, north: 18.7, west: -67.5, east: -64.5 },
    dst: { south: 19.2, north: 21.0, west: -107.5, east: -102.5 },
  },
  {
    key: "PAC",
    label: "GU / MP / AS",
    states: ["GU", "MP", "AS", "FM"],
    src: { south: -15, north: 16, west: 144, east: 146 },
    dst: { south: 19.2, north: 20.6, west: -101.0, east: -96.0 },
  },
];
const INSET_BY_STATE = (() => {
  const m = {};
  for (const inset of INSETS) for (const st of inset.states) m[st] = inset;
  return m;
})();

// Linearly remap (lat, lon) from inset.src into inset.dst. Mutates the record:
// stashes the original on lat_real/lon_real and overwrites lat/lon with the
// display coords used for marker placement.
function applyInsetRemap(record) {
  if (record.lat == null || record.lon == null) return;
  const inset = INSET_BY_STATE[record.state];
  if (!inset) return;
  const lat = Math.max(inset.src.south, Math.min(inset.src.north, record.lat));
  const lon = Math.max(inset.src.west, Math.min(inset.src.east, record.lon));
  const fLat = (lat - inset.src.south) / (inset.src.north - inset.src.south);
  const fLon = (lon - inset.src.west) / (inset.src.east - inset.src.west);
  record.lat_real = record.lat;
  record.lon_real = record.lon;
  record.lat = inset.dst.south + fLat * (inset.dst.north - inset.dst.south);
  record.lon = inset.dst.west + fLon * (inset.dst.east - inset.dst.west);
  record._inset = inset.key;
}

// Marker decimation: at low zoom levels with thousands of markers, drawing
// every point is wasteful. Hash-based sampling keeps a stable subset visible.
const DECIMATION = [
  { maxZoom: 4, keepEvery: 8 },
  { maxZoom: 5, keepEvery: 4 },
  { maxZoom: 6, keepEvery: 2 },
  { maxZoom: Infinity, keepEvery: 1 },
];

// NPL status filter options — pill colors still vary by status (see CSS), but
// markers are colored by program only (see PROGRAM_LEGEND).
const STATUS_LEGEND = [
  { code: "F", label: "Final NPL", cssVar: "--status-final" },
  { code: "P", label: "Proposed", cssVar: "--status-proposed" },
  { code: "D", label: "Deleted", cssVar: "--status-deleted" },
  { code: "N", label: "Not on NPL", cssVar: "--status-other" },
];
// Map legend / marker colors are program-based: one dot per program.
const PROGRAM_LEGEND = [
  { program: "superfund", label: "Superfund (NPL)", cssVar: "--program-superfund" },
  { program: "brownfield", label: "Brownfield (ACRES)", cssVar: "--program-brownfield" },
];
const PROGRAM_COLOR_BY_PROGRAM = Object.fromEntries(
  PROGRAM_LEGEND.map((p) => [p.program, p.cssVar])
);
const PROGRAM_LABEL = {
  superfund: "Superfund (NPL)",
  brownfield: "Brownfield (ACRES)",
};

// Postal-code → full name. Splits states from territories so the dropdown can
// group territories into a separate <optgroup> rather than letting "AS"
// (American Samoa) sort alphabetically before "AZ" (Arizona).
const STATE_NAMES = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California",
  CO: "Colorado", CT: "Connecticut", DE: "Delaware", FL: "Florida", GA: "Georgia",
  HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa",
  KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi",
  MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada", NH: "New Hampshire",
  NJ: "New Jersey", NM: "New Mexico", NY: "New York", NC: "North Carolina",
  ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania",
  RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee",
  TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington",
  WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming", DC: "District of Columbia",
};
const TERRITORY_NAMES = {
  AS: "American Samoa", GU: "Guam", MP: "Northern Mariana Islands",
  PR: "Puerto Rico", VI: "U.S. Virgin Islands", FM: "Micronesia",
};

const el = (id) => document.getElementById(id);
const fmt = {
  acres: (n) => {
    if (n == null) return "N/A";
    const rounded = Math.round(n * 10) / 10;
    return rounded.toLocaleString(undefined, { maximumFractionDigits: 1 }) + " ac";
  },
  date: (s) => {
    if (!s) return "—";
    const d = new Date(typeof s === "number" ? s : Date.parse(s));
    if (isNaN(d.getTime())) return "—";
    return d.toISOString().slice(0, 10);
  },
  text: (s) => (s == null || s === "" ? "—" : String(s)),
};

// ----- State -----
let sites = [];
let map, markerLayer;
const markersById = new Map(); // id -> Leaflet marker
const tableRowsById = new Map(); // id -> tr
const sitesById = new Map();
let selectedId = null;
let sortKey = "acreage";
let sortDir = "desc";

// Filter state. Defaults match URL parsing below.
// Both programs are on by default — Superfund paints first, brownfields lazy-load.
const filterState = {
  q: "",
  programs: new Set(["superfund", "brownfield"]),
  state: "",
  statuses: new Set(),
  minAcreage: 0, // log10 base; 0 means "show all" (incl. null acreage)
};

let acresLoadingPromise = null; // de-dup parallel toggles

// Programmatic ready signal so UAT / Playwright / agent automation can wait
// on a stable event instead of polling network responses. Fires once after
// Superfund first paint AND, if brownfields are enabled, after the chunked
// ACRES marker hydration completes.
function markAppReady() {
  if (window.__APP_READY__) return;
  window.__APP_READY__ = true;
  try {
    document.dispatchEvent(new CustomEvent("brownfield:ready"));
  } catch (e) {
    // Older browsers may not have CustomEvent constructor — ignore.
  }
}

// ----- CSS-var color resolver ----- //
// Single source of truth for status colors lives in CSS. JS reads via
// getComputedStyle so a dark-mode swap is automatic.
function cssColor(varName, fallback = "#1f6fcf") {
  const v = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  return v || fallback;
}
function colorForRecord(s) {
  const cssVar = PROGRAM_COLOR_BY_PROGRAM[s.program] || "--program-superfund";
  return cssColor(cssVar);
}

// ----- Boot -----
loadInitialTheme();
loadInitialFiltersFromUrl();
fetch(PRIMARY_DATA_URL)
  .then((r) => {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  })
  .then((payload) => {
    ingestSites(payload.sites || []);
    const refreshed = fmt.date(payload.generated_at);
    el("meta").textContent = filterState.programs.has("brownfield")
      ? `${sites.length.toLocaleString()} Superfund sites · loading brownfields… · refreshed ${refreshed}`
      : `${sites.length.toLocaleString()} Superfund sites · refreshed ${refreshed}`;
    initMap();
    populateStatusFilter();
    populateStateFilter();
    rebuildTable();
    wireTabs();
    wireDetailPanel();
    wireSearch();
    wireFilters();
    wireExportCsv();
    wireThemeToggle();
    applyUrlSelection();
    window.__sitesLoaded = true; // e2e hook
    // If the URL asked for brownfields, kick off the lazy load now.
    if (filterState.programs.has("brownfield")) {
      ensureAcresLoaded();
    } else {
      // Brownfields are off — Superfund-only first paint is the final state.
      markAppReady();
    }
  })
  .catch((err) => {
    el("meta").textContent = "Failed to load site data: " + err.message;
    console.error(err);
  });

function ingestSites(records) {
  for (const s of records) {
    if (sitesById.has(s.id)) continue;
    applyInsetRemap(s);
    sitesById.set(s.id, s);
  }
  sites = Array.from(sitesById.values());
}

// ----- Lazy ACRES load -----
function ensureAcresLoaded() {
  if (acresLoadingPromise) return acresLoadingPromise;
  if (sites.some((s) => s.program === "brownfield")) {
    return Promise.resolve();
  }
  el("meta").textContent =
    `${sites.length.toLocaleString()} Superfund sites · loading brownfields…`;
  acresLoadingPromise = fetch(ACRES_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      const before = sites.length;
      ingestSites(payload.sites || []);
      const added = sites.length - before;
      el("meta").textContent =
        `${sites.length.toLocaleString()} sites (${before.toLocaleString()} Superfund + ${added.toLocaleString()} brownfields)`;
      populateStateFilter();
      rebuildTable();
      rerenderLegend();
      // Chunk marker hydration so the main thread stays responsive while
      // the 36k ACRES markers light up. We resolve `acresLoadingPromise`
      // (and dispatch `brownfield:ready`) only after the last batch lands.
      return hydrateMarkersChunked(payload.sites || []).then(() => {
        applyFilter();
        markAppReady();
      });
    })
    .catch((err) => {
      el("meta").textContent =
        `${sites.length.toLocaleString()} Superfund sites · brownfields failed to load (${err.message})`;
      console.error(err);
      acresLoadingPromise = null; // allow retry
    });
  return acresLoadingPromise;
}

// ----- Map -----
function initMap() {
  const renderer = L.canvas({ padding: 0.5 });
  map = L.map("map", {
    preferCanvas: true,
    renderer,
    zoomControl: true,
    tap: false,
    minZoom: MIN_ZOOM,
    maxBounds: US_BOUNDS,
    maxBoundsViscosity: 1.0,
    worldCopyJump: false,
    attributionControl: true,
  }).fitBounds(US_BOUNDS, { padding: [10, 10], animate: false });

  map.attributionControl.setPrefix("").addAttribution(BASEMAP_ATTRIB);
  // The Leaflet container background is the "ocean" outside CONUS.
  document.getElementById("map").style.background = cssColor("--map-ocean");

  drawBasemap();
  drawInsetBoxes();

  markerLayer = L.layerGroup().addTo(map);
  window.__markerLayer = markerLayer;
  window.__map = map;

  addMarkersForRecords(sites);
  addLegend();

  // Re-evaluate decimation + counties visibility on zoom. Only marker
  // visibility changes — the filtered set and table are unaffected by zoom.
  map.on("zoomend", () => {
    updateCountyVisibility();
    applyMarkerVisibility();
  });
  // Direct entry at high zoom (via ?site= or detail-panel auto-zoom) skips the
  // zoomend hook because there's no zoom transition. Hook moveend so any view
  // change triggers the county lazy-load.
  map.on("moveend", updateCountyVisibility);
}

// ----- Vector basemap -----
let statesLayer = null;
let countiesLayer = null;
let countiesLoadPromise = null;

function statesStyle() {
  return {
    color: cssColor("--map-state-stroke"),
    weight: 1.4,
    fillColor: cssColor("--map-land"),
    fillOpacity: 1,
    lineJoin: "round",
    lineCap: "round",
  };
}
function countiesStyle() {
  return {
    color: cssColor("--map-county-stroke"),
    weight: 0.6,
    fill: false,
    opacity: 0.9,
  };
}

// Names in us-states.json for states/territories whose markers are remapped
// into inset boxes — we filter these features out so the basemap doesn't
// render their real-world polygons (AK at top-left, HI at far-bottom-left,
// PR floating off the right edge) while their markers sit in inset boxes.
const NON_CONUS_STATE_NAMES = new Set(["Alaska", "Hawaii", "Puerto Rico"]);

function drawBasemap() {
  fetch(STATES_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((gj) => {
      const filtered = {
        type: gj.type,
        features: (gj.features || []).filter(
          (f) => !NON_CONUS_STATE_NAMES.has(f?.properties?.name)
        ),
      };
      // States sit on Leaflet's tilePane so they render under markers/insets.
      statesLayer = L.geoJSON(filtered, {
        style: statesStyle,
        interactive: false,
        pane: "tilePane",
      }).addTo(map);
    })
    .catch((err) => {
      console.error("Failed to load states basemap:", err);
    });
}

function ensureCountiesLoaded() {
  if (countiesLayer) return Promise.resolve();
  if (countiesLoadPromise) return countiesLoadPromise;
  countiesLoadPromise = fetch(COUNTIES_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((topo) => {
      if (!window.topojson || !topo.objects || !topo.objects.counties) {
        throw new Error("topojson-client not loaded or counties topo malformed");
      }
      const gj = window.topojson.feature(topo, topo.objects.counties);
      countiesLayer = L.geoJSON(gj, {
        style: countiesStyle,
        interactive: false,
        pane: "tilePane",
      });
      // Only attach if user is still zoomed in by the time it lands.
      if (map.getZoom() >= COUNTY_MIN_ZOOM) countiesLayer.addTo(map);
    })
    .catch((err) => {
      console.error("Failed to load counties basemap:", err);
      countiesLoadPromise = null; // allow retry
    });
  return countiesLoadPromise;
}

function updateCountyVisibility() {
  if (!map) return;
  const shouldShow = map.getZoom() >= COUNTY_MIN_ZOOM;
  if (shouldShow) {
    ensureCountiesLoaded();
    if (countiesLayer && !map.hasLayer(countiesLayer)) countiesLayer.addTo(map);
  } else if (countiesLayer && map.hasLayer(countiesLayer)) {
    map.removeLayer(countiesLayer);
  }
}

function refreshBasemapColors() {
  document.getElementById("map").style.background = cssColor("--map-ocean");
  if (statesLayer) statesLayer.setStyle(statesStyle());
  if (countiesLayer) countiesLayer.setStyle(countiesStyle());
}

// Shared canvas renderer — instantiated once so chunked hydration shares it
// instead of allocating a new renderer per batch.
let _markerRenderer = null;
function markerRenderer() {
  if (!_markerRenderer) _markerRenderer = L.canvas({ padding: 0.5 });
  return _markerRenderer;
}

function addOneMarker(s, strokeColor) {
  if (s.lat == null || s.lon == null) return;
  if (markersById.has(s.id)) return;
  const color = colorForRecord(s);
  const marker = L.circleMarker([s.lat, s.lon], {
    renderer: markerRenderer(),
    radius: radiusForAcreage(s.acreage),
    // Thin theme-aware ring around the program-colored fill so markers stay
    // legible against both the light land fill and the dark land fill.
    color: strokeColor,
    weight: 1,
    fillColor: color,
    fillOpacity: 0.85,
    opacity: 0.9,
  }).bindTooltip(s.name || "(unnamed site)", { direction: "top" });

  marker.on("click", () => selectSite(s.id, { fromMap: true }));
  markerLayer.addLayer(marker);
  markersById.set(s.id, marker);
}

function addMarkersForRecords(records) {
  const stroke = cssColor("--map-marker-stroke");
  for (const s of records) addOneMarker(s, stroke);
}

// Chunked marker hydration. Used for the 36k ACRES dataset so Leaflet doesn't
// freeze the main thread for 30+ seconds. requestIdleCallback yields between
// batches so input/scroll/zoom stay responsive while the markers light up.
function hydrateMarkersChunked(records, batchSize = 800) {
  return new Promise((resolve) => {
    if (!records.length) return resolve();
    const stroke = cssColor("--map-marker-stroke");
    const sched =
      window.requestIdleCallback
        ? (cb) => window.requestIdleCallback(cb, { timeout: 200 })
        : (cb) => setTimeout(cb, 0);
    let i = 0;
    const tick = () => {
      const end = Math.min(i + batchSize, records.length);
      for (let j = i; j < end; j++) addOneMarker(records[j], stroke);
      i = end;
      if (i < records.length) sched(tick);
      else resolve();
    };
    sched(tick);
  });
}

// Draws an opaque rectangle for each inset (covering the underlying basemap
// so AK/HI/PR markers don't sit visually on top of Mexican land/ocean) plus a
// label tag at the top-left of the box.
let insetLayer = null;
function drawInsetBoxes() {
  if (insetLayer) {
    insetLayer.remove();
  }
  insetLayer = L.layerGroup().addTo(map);
  const fill = cssColor("--inset-bg", "#ffffff");
  const stroke = cssColor("--inset-stroke", "#4a5568");
  for (const inset of INSETS) {
    const bounds = [
      [inset.dst.south, inset.dst.west],
      [inset.dst.north, inset.dst.east],
    ];
    L.rectangle(bounds, {
      color: stroke,
      weight: 1,
      fillColor: fill,
      fillOpacity: 1,
      interactive: false,
    }).addTo(insetLayer);
    // Label sits just above the top edge of the box so labels don't crowd
    // adjacent insets; bottom-left of the label anchors at the box NW corner.
    L.marker([inset.dst.north, inset.dst.west], {
      icon: L.divIcon({
        className: "inset-label",
        html: inset.label,
        iconAnchor: [-2, 20],
      }),
      interactive: false,
      keyboard: false,
    }).addTo(insetLayer);
  }
}

function addLegend() {
  const legend = L.control({ position: "bottomright" });
  legend.onAdd = () => {
    const div = L.DomUtil.create("div", "legend");
    // Only show rows for programs that exist in the currently-loaded data.
    const programsPresent = new Set(sites.map((s) => s.program));
    const rows = PROGRAM_LEGEND.filter((p) => programsPresent.has(p.program))
      .map(
        (p) =>
          `<div class="legend-row"><span class="legend-dot" style="color:${cssColor(
            p.cssVar
          )}"></span>${p.label}</div>`
      )
      .join("");
    div.innerHTML =
      `<div class="legend-title">Program</div>${rows}` +
      `<div class="legend-foot">Marker size ∝ acreage (log)</div>`;
    L.DomEvent.disableClickPropagation(div);
    return div;
  };
  legend.addTo(map);
}

function rerenderLegend() {
  document.querySelectorAll(".legend").forEach((n) => n.remove());
  if (map) addLegend();
}

function radiusForAcreage(a) {
  if (a == null) return 3;
  return Math.max(4, Math.min(16, 3 + Math.log10(a)));
}

function decimateKeep(zoom) {
  for (const tier of DECIMATION) {
    if (zoom <= tier.maxZoom) return tier.keepEvery;
  }
  return 1;
}

// Stable hash → keep `1 / keepEvery` markers visible at low zoom.
function shouldDecimateOut(id, keepEvery) {
  if (keepEvery <= 1) return false;
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return (Math.abs(h) % keepEvery) !== 0;
}

// ----- Filters -----
function siteMatchesQuery(s, q) {
  if (!q) return true;
  const hay = [s.name, s.city, s.county, s.state].filter(Boolean).join("|").toLowerCase();
  return hay.includes(q);
}

function siteMatchesFilters(s, opts = {}) {
  if (filterState.programs.size && !filterState.programs.has(s.program)) return false;
  if (filterState.state && s.state !== filterState.state) return false;
  if (filterState.statuses.size && !filterState.statuses.has(s.npl_status_code || "")) return false;
  // Acreage slider is log-base-10; min=0 → 1ac threshold off (keep nulls).
  if (filterState.minAcreage > 0) {
    if (s.acreage == null) return false;
    if (s.acreage < Math.pow(10, filterState.minAcreage)) return false;
  }
  if (!siteMatchesQuery(s, opts.q ?? filterState.q)) return false;
  return true;
}

// Update only the marker visibility on the map (used by zoomend, where the
// filtered set hasn't changed but decimation thresholds may have).
function applyMarkerVisibility() {
  if (!map || !markerLayer) return;
  const zoom = map.getZoom();
  const keepEvery = decimateKeep(zoom);
  const q = filterState.q.trim().toLowerCase();
  for (const [id, marker] of markersById) {
    const s = sitesById.get(id);
    if (!s) continue;
    const match = siteMatchesFilters(s, { q });
    const decimated = match && shouldDecimateOut(id, keepEvery);
    const showOnMap = match && !decimated;
    const onMap = markerLayer.hasLayer(marker);
    if (showOnMap && !onMap) markerLayer.addLayer(marker);
    else if (!showOnMap && onMap) markerLayer.removeLayer(marker);
  }
}

function updateCountText() {
  const q = filterState.q.trim().toLowerCase();
  let visible = 0;
  let acreSum = 0;
  let acreSites = 0;
  for (const s of sites) {
    if (!siteMatchesFilters(s, { q })) continue;
    visible++;
    if (typeof s.acreage === "number") {
      acreSum += s.acreage;
      acreSites++;
    }
  }
  const countEl = el("search-count");
  if (q || filtersActive()) {
    const acresLabel = acreSites
      ? ` · ${Math.round(acreSum).toLocaleString()} ac` +
        (acreSites < visible ? ` (${acreSites.toLocaleString()} w/ acreage)` : "")
      : "";
    const stateLabel = filterState.state ? ` in ${filterState.state}` : "";
    countEl.textContent =
      `${visible.toLocaleString()} of ${sites.length.toLocaleString()}${stateLabel}${acresLabel}`;
  } else {
    countEl.textContent = "";
  }
}

// Full filter pass: refresh markers, rebuild paginated table, update count.
function applyFilter() {
  applyMarkerVisibility();
  refreshTableForFilter();
  updateCountText();
  syncUrl();
}

// Auto-fit the map to the visible (filtered) markers. Called only on user
// filter changes — NOT from zoomend, otherwise zooming would fight itself.
// Heuristics:
//   - 0 visible → leave the view alone (so an empty state doesn't blank the map).
//   - >5,000 visible → leave the view alone (the user didn't narrow much).
//   - 1 visible → zoom to it at zoom 12.
//   - else fitBounds to the visible-set bbox at maxZoom 11, but only if the
//     bbox covers materially less than the current viewport. This avoids
//     refitting when a filter narrows the count without narrowing the
//     geographic spread (e.g. "Final NPL only" still spans the whole US).
function refitMapToFilters() {
  if (!map) return;
  const lats = [];
  const lons = [];
  for (const s of sites) {
    if (s.lat == null || s.lon == null) continue;
    if (!siteMatchesFilters(s)) continue;
    lats.push(s.lat);
    lons.push(s.lon);
  }
  if (lats.length === 0 || lats.length > 5000) return;
  if (lats.length === 1) {
    map.setView([lats[0], lons[0]], 12, { animate: true });
    return;
  }
  const bbox = L.latLngBounds(
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)]
  );
  const cur = map.getBounds();
  const curArea =
    Math.abs(cur.getNorth() - cur.getSouth()) *
    Math.abs(cur.getEast() - cur.getWest());
  const bbArea =
    Math.abs(bbox.getNorth() - bbox.getSouth()) *
    Math.abs(bbox.getEast() - bbox.getWest());
  // Skip when the visible set still spans most of the current view.
  if (curArea > 0 && bbArea > curArea * 0.5) return;
  map.fitBounds(bbox, { maxZoom: 11, padding: [40, 40], animate: true });
}

// Lightweight non-blocking toast. Used for "site not found" and could be
// reused for future hydration messages.
let _toastTimer = null;
function showToast(message, { ms = 4000 } = {}) {
  let toast = document.getElementById("toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    toast.className = "toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add("visible");
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    toast.classList.remove("visible");
    _toastTimer = null;
  }, ms);
}

function filtersActive() {
  return (
    filterState.state !== "" ||
    filterState.statuses.size > 0 ||
    filterState.minAcreage > 0 ||
    filterState.programs.size !== 2
  );
}

function wireSearch() {
  const input = el("search");
  if (filterState.q) input.value = filterState.q;
  // Debounce the geographic refit so we don't fitBounds on every keystroke.
  let refitTimer = null;
  const queueRefit = () => {
    if (refitTimer) clearTimeout(refitTimer);
    refitTimer = setTimeout(refitMapToFilters, 350);
  };
  input.addEventListener("input", () => {
    filterState.q = input.value;
    applyFilter();
    queueRefit();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && input.value) {
      e.stopPropagation();
      input.value = "";
      filterState.q = "";
      applyFilter();
    }
  });
}

function wireFilters() {
  const toggle = el("filters-toggle");
  toggle.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!expanded));
    el("filters").hidden = expanded;
    if (map) setTimeout(() => map.invalidateSize(), 50);
  });

  const progBoxes = {
    superfund: el("f-program-superfund"),
    brownfield: el("f-program-brownfield"),
  };
  // Reflect URL state into the checkboxes.
  for (const [program, box] of Object.entries(progBoxes)) {
    box.checked = filterState.programs.has(program);
  }
  const onProgramChange = () => {
    const next = new Set();
    for (const [program, box] of Object.entries(progBoxes)) {
      if (box.checked) next.add(program);
    }
    // Avoid the empty-set degenerate case that would hide everything.
    if (!next.size) {
      progBoxes.superfund.checked = true;
      next.add("superfund");
    }
    filterState.programs = next;
    if (filterState.programs.has("brownfield")) ensureAcresLoaded();
    applyFilter();
    refitMapToFilters();
  };
  progBoxes.superfund.addEventListener("change", onProgramChange);
  progBoxes.brownfield.addEventListener("change", onProgramChange);

  const stateSel = el("f-state");
  stateSel.addEventListener("change", () => {
    filterState.state = stateSel.value;
    applyFilter();
    refitMapToFilters();
  });

  // NPL Status checkboxes — delegated change handler so we don't have to
  // re-bind each time `populateStatusFilter()` re-renders the inputs.
  el("f-status-checks").addEventListener("change", (ev) => {
    if (!(ev.target instanceof HTMLInputElement)) return;
    const code = ev.target.dataset.status;
    if (code == null) return;
    if (ev.target.checked) filterState.statuses.add(code);
    else filterState.statuses.delete(code);
    applyFilter();
    refitMapToFilters();
  });

  const acreEl = el("f-acreage");
  const acreVal = el("f-acreage-val");
  // Debounce the slider refit so dragging doesn't fitBounds every frame.
  let acreRefitTimer = null;
  acreEl.addEventListener("input", () => {
    filterState.minAcreage = parseFloat(acreEl.value);
    acreVal.textContent =
      filterState.minAcreage === 0 ? "0" : Math.round(Math.pow(10, filterState.minAcreage)).toLocaleString() + " ac";
    applyFilter();
    if (acreRefitTimer) clearTimeout(acreRefitTimer);
    acreRefitTimer = setTimeout(refitMapToFilters, 350);
  });
  // Initial label
  acreEl.value = String(filterState.minAcreage);
  acreVal.textContent =
    filterState.minAcreage === 0 ? "0" : Math.round(Math.pow(10, filterState.minAcreage)).toLocaleString() + " ac";

  el("filters-reset").addEventListener("click", () => {
    filterState.programs = new Set(["superfund", "brownfield"]);
    filterState.state = "";
    filterState.statuses = new Set();
    filterState.minAcreage = 0;
    filterState.q = "";
    el("search").value = "";
    progBoxes.superfund.checked = true;
    progBoxes.brownfield.checked = true;
    if (filterState.programs.has("brownfield")) ensureAcresLoaded();
    stateSel.value = "";
    for (const cb of el("f-status-checks").querySelectorAll("input[type=checkbox]")) cb.checked = false;
    acreEl.value = "0";
    acreVal.textContent = "0";
    applyFilter();
    // Reset zooms back out to the lower-48 default.
    if (map) map.fitBounds(US_BOUNDS, { padding: [10, 10], animate: true });
  });
}

function populateStateFilter() {
  const sel = el("f-state");
  const codes = new Set();
  for (const s of sites) if (s.state) codes.add(s.state);
  // Preserve current selection across re-population.
  const current = sel.value;
  // Split into states (alphabetical by full name) and territories (separate
  // optgroup so AS doesn't sort before AZ).
  const labelFor = (c) => STATE_NAMES[c] || TERRITORY_NAMES[c] || c;
  const present = Array.from(codes);
  const stateCodes = present
    .filter((c) => STATE_NAMES[c])
    .sort((a, b) => labelFor(a).localeCompare(labelFor(b)));
  const territoryCodes = present
    .filter((c) => TERRITORY_NAMES[c])
    .sort((a, b) => labelFor(a).localeCompare(labelFor(b)));
  const otherCodes = present
    .filter((c) => !STATE_NAMES[c] && !TERRITORY_NAMES[c])
    .sort();
  const renderOpt = (c) =>
    `<option value="${escapeAttr(c)}">${escapeHtml(labelFor(c))} (${escapeHtml(c)})</option>`;
  let html = '<option value="">All states</option>' + stateCodes.map(renderOpt).join("");
  if (territoryCodes.length) {
    html +=
      `<optgroup label="Territories">` +
      territoryCodes.map(renderOpt).join("") +
      `</optgroup>`;
  }
  if (otherCodes.length) {
    html +=
      `<optgroup label="Other">` +
      otherCodes.map(renderOpt).join("") +
      `</optgroup>`;
  }
  sel.innerHTML = html;
  const all = new Set(present);
  if (all.has(current)) sel.value = current;
  else if (all.has(filterState.state)) sel.value = filterState.state;
}

function populateStatusFilter() {
  const wrap = el("f-status-checks");
  wrap.innerHTML = STATUS_LEGEND.map(
    (s) =>
      `<label class="check"><input type="checkbox" data-status="${escapeAttr(s.code)}"${
        filterState.statuses.has(s.code) ? " checked" : ""
      }> ${escapeHtml(s.label)}</label>`
  ).join("");
}

// ----- Table (paginated) -----
//
// Rendering all ~38k <tr> elements at once balloons the document to ~265k
// elements and freezes the main thread on cold load. We paginate instead:
// a sorted+filtered list lives in memory; we render one page (TABLE_PAGE_SIZE
// rows) into the DOM at a time. A sentinel <tr> at the bottom of the visible
// rows is observed by IntersectionObserver — when it scrolls into view (with
// a buffer) we append the next page. Filter / sort changes reset back to the
// first page.
const TABLE_PAGE_SIZE = 250;
const tableState = {
  sorted: [],   // all sites, sorted by current key
  filtered: [], // sorted ∩ current filter
  rendered: 0,  // count of rows actually in DOM
};
let _tableSentinel = null;
let _tableObserver = null;

function makeRow(s) {
  const tr = document.createElement("tr");
  tr.dataset.id = s.id;
  const programLabel = PROGRAM_LABEL[s.program] || s.program || "—";
  const statusHtml = s.npl_status_code
    ? `<span class="pill" data-status="${escapeAttr(s.npl_status_code)}">${escapeHtml(s.npl_status || "Unknown")}</span>`
    : `<span class="pill" data-program="${escapeAttr(s.program)}">${escapeHtml(programLabel)}</span>`;
  tr.innerHTML = `
    <td>${escapeHtml(s.name || "—")}</td>
    <td><span class="pill" data-program="${escapeAttr(s.program)}">${escapeHtml(programLabel)}</span></td>
    <td>${escapeHtml(s.state || "—")}</td>
    <td class="num">${fmt.acres(s.acreage)}</td>
    <td>${statusHtml}</td>
    <td>${escapeHtml(s.city || "—")}</td>
    <td>${escapeHtml(s.county || "—")}</td>
  `;
  tr.addEventListener("click", () => selectSite(s.id, { fromTable: true }));
  return tr;
}

// Re-sort the in-memory list and reset the rendered table. Use after data
// ingest or sort-key change.
function rebuildTable() {
  tableState.sorted = [...sites].sort(makeComparator(sortKey, sortDir));
  refreshTableForFilter();
  updateSortIndicators();
}

// Re-evaluate the filter, reset to page 1, render. Use after filter changes.
function refreshTableForFilter() {
  tableState.filtered = tableState.sorted.filter((s) => siteMatchesFilters(s));
  const tbody = document.querySelector("#sites-table tbody");
  tbody.innerHTML = "";
  tableRowsById.clear();
  tableState.rendered = 0;
  appendNextPage();
  setupTableInfiniteScroll();
  if (selectedId) tableRowsById.get(selectedId)?.classList.add("selected");
}

function appendNextPage() {
  if (tableState.rendered >= tableState.filtered.length) return;
  const tbody = document.querySelector("#sites-table tbody");
  const end = Math.min(
    tableState.rendered + TABLE_PAGE_SIZE,
    tableState.filtered.length
  );
  const frag = document.createDocumentFragment();
  for (let i = tableState.rendered; i < end; i++) {
    const s = tableState.filtered[i];
    const tr = makeRow(s);
    frag.appendChild(tr);
    tableRowsById.set(s.id, tr);
  }
  tbody.appendChild(frag);
  tableState.rendered = end;
}

function setupTableInfiniteScroll() {
  const wrap = document.querySelector(".table-wrap");
  if (!wrap) return;
  if (_tableObserver) _tableObserver.disconnect();
  if (!_tableSentinel) {
    _tableSentinel = document.createElement("div");
    _tableSentinel.className = "table-sentinel";
    _tableSentinel.setAttribute("aria-hidden", "true");
  }
  // Always re-append so the sentinel stays at the end after table reset.
  wrap.appendChild(_tableSentinel);
  _tableObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((e) => e.isIntersecting)) appendNextPage();
    },
    { root: wrap, rootMargin: "300px" }
  );
  _tableObserver.observe(_tableSentinel);
}

// Ensure the row for `id` has been rendered into the DOM — used by selectSite
// when the user opens a marker whose row is far past the rendered window.
function ensureRowRendered(id) {
  if (tableRowsById.has(id)) return true;
  const idx = tableState.filtered.findIndex((s) => s.id === id);
  if (idx < 0) return false;
  while (tableState.rendered <= idx) {
    const before = tableState.rendered;
    appendNextPage();
    if (tableState.rendered === before) break; // safety
  }
  return tableRowsById.has(id);
}

function makeComparator(key, dir) {
  const mul = dir === "asc" ? 1 : -1;
  return (a, b) => {
    const av = a[key], bv = b[key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * mul;
    return String(av).localeCompare(String(bv)) * mul;
  };
}

function updateSortIndicators() {
  document.querySelectorAll("#sites-table thead th").forEach((th) => {
    th.removeAttribute("aria-sort");
    if (th.dataset.sort === sortKey) {
      th.setAttribute("aria-sort", sortDir === "asc" ? "ascending" : "descending");
    }
  });
}

document.querySelectorAll("#sites-table thead th").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (!key) return;
    if (key === sortKey) sortDir = sortDir === "asc" ? "desc" : "asc";
    else { sortKey = key; sortDir = (key === "acreage") ? "desc" : "asc"; }
    rebuildTable();
    if (selectedId) tableRowsById.get(selectedId)?.classList.add("selected");
  });
});

// ----- Tabs -----
function wireTabs() {
  const mapTab = el("tab-map"), tableTab = el("tab-table");
  const setView = (which) => {
    const onMap = which === "map";
    mapTab.classList.toggle("active", onMap);
    tableTab.classList.toggle("active", !onMap);
    mapTab.setAttribute("aria-selected", onMap);
    tableTab.setAttribute("aria-selected", !onMap);
    el("view-map").classList.toggle("active", onMap);
    el("view-table").classList.toggle("active", !onMap);
    el("view-map").hidden = !onMap;
    el("view-table").hidden = onMap;
    if (onMap) setTimeout(() => map.invalidateSize(), 50);
  };
  mapTab.addEventListener("click", () => setView("map"));
  tableTab.addEventListener("click", () => setView("table"));
}

// ----- Detail panel -----
function wireDetailPanel() {
  el("detail-close").addEventListener("click", closeDetail);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDetail();
  });
}

function selectSite(id, { fromMap = false, fromTable = false } = {}) {
  const s = sitesById.get(id);
  if (!s) return;
  if (selectedId && tableRowsById.has(selectedId)) {
    tableRowsById.get(selectedId).classList.remove("selected");
  }
  selectedId = id;
  // Paginated table: the row may be past the rendered window. Page rows in
  // until it lands so the highlight + scroll-into-view work consistently.
  ensureRowRendered(id);
  tableRowsById.get(id)?.classList.add("selected");

  el("detail-title").textContent = s.name || "—";
  const locParts = [s.city, s.state].filter(Boolean).join(", ");
  el("detail-loc").textContent = locParts || "Location unknown";
  el("d-program").innerHTML = `<span class="pill" data-program="${escapeAttr(s.program)}">${escapeHtml(PROGRAM_LABEL[s.program] || s.program || "—")}</span>`;
  el("d-acreage").textContent = fmt.acres(s.acreage);

  // Status / ID labels vary by program.
  const statusEl = el("d-status");
  if (s.program === "superfund") {
    el("d-status-label").textContent = "NPL Status";
    statusEl.innerHTML = `<span class="pill" data-status="${escapeAttr(s.npl_status_code || "")}">${escapeHtml(s.npl_status || "Unknown")}</span>`;
    el("d-id-label").textContent = "EPA ID";
    el("d-epaid").textContent = fmt.text(s.epa_id || s.id);
    el("d-fed-label").textContent = "Federal Facility";
    // EPA's `federal_facility` is already the decoded human label
    // (e.g. "Federal Facility", "Not a  Federal Facility"). Collapse the
    // upstream double-space and print directly — don't prepend "Code ".
    el("d-fed").textContent = s.federal_facility
      ? String(s.federal_facility).replace(/\s+/g, " ").trim()
      : "—";
    el("d-updated-label").textContent = "Last Updated";
    el("d-updated").textContent = fmt.date(s.last_updated);
  } else {
    el("d-status-label").textContent = "Status";
    statusEl.textContent = "—";
    el("d-id-label").textContent = "ACRES Property ID";
    el("d-epaid").textContent = (s.id || "").replace(/^ACRES-/, "") || "—";
    el("d-fed-label").textContent = "Federal Facility";
    el("d-fed").textContent = "—";
    el("d-updated-label").textContent = "Last Updated";
    el("d-updated").textContent = "—";
  }

  el("d-region").textContent = s.region != null ? `Region ${s.region}` : "—";
  el("d-addr").textContent = [s.address, s.city, s.state, s.zip].filter(Boolean).join(", ") || "—";
  // Show real coordinates in the detail panel — `s.lat`/`s.lon` may be the
  // remapped inset display coords for AK/HI/PR/Pacific records.
  const realLat = s.lat_real ?? s.lat;
  const realLon = s.lon_real ?? s.lon;
  el("d-coord").textContent =
    realLat != null && realLon != null ? `${realLat.toFixed(4)}, ${realLon.toFixed(4)}` : "—";

  // Children block — only Superfund sites with rolled-up sub-sites.
  const childBlock = el("d-children-block");
  if (Array.isArray(s.children) && s.children.length) {
    childBlock.hidden = false;
    el("d-children-count").textContent = String(s.children.length);
    const ul = el("d-children");
    ul.innerHTML = s.children
      .map((c) => `<li>${escapeHtml(c.name || c.id || "—")}</li>`)
      .join("");
  } else {
    childBlock.hidden = true;
  }

  const profile = el("d-profile");
  if (s.profile_url) {
    profile.href = s.profile_url;
    profile.textContent = s.program === "brownfield" ? "ACRES property profile" : "EPA Site Profile";
    profile.style.display = "";
  } else {
    profile.style.display = "none";
  }

  const detail = el("detail");
  detail.hidden = false;
  detail.setAttribute("aria-hidden", "false");

  if (!fromMap && s.lat != null && s.lon != null) {
    map.setView([s.lat, s.lon], Math.max(map.getZoom(), 8), { animate: true });
    markersById.get(id)?.openTooltip();
  }
  syncUrl();
}

function closeDetail() {
  const detail = el("detail");
  detail.hidden = true;
  detail.setAttribute("aria-hidden", "true");
  if (selectedId && tableRowsById.has(selectedId)) {
    tableRowsById.get(selectedId).classList.remove("selected");
  }
  selectedId = null;
  syncUrl();
}

// ----- CSV export -----
function wireExportCsv() {
  el("export-csv").addEventListener("click", () => {
    const rows = [];
    rows.push([
      "id", "program", "name", "state", "city", "county", "acreage",
      "npl_status_code", "npl_status", "lat", "lon", "profile_url",
    ]);
    for (const s of sites) {
      if (!siteMatchesFilters(s)) continue;
      rows.push([
        s.id, s.program, s.name || "", s.state || "", s.city || "", s.county || "",
        s.acreage ?? "", s.npl_status_code || "", s.npl_status || "",
        (s.lat_real ?? s.lat) ?? "", (s.lon_real ?? s.lon) ?? "", s.profile_url || "",
      ]);
    }
    const csv = rows.map(csvRow).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `brownfield-sites-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}

function csvRow(values) {
  return values
    .map((v) => {
      const s = String(v ?? "");
      if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
      return s;
    })
    .join(",");
}

// ----- Theme toggle -----
function loadInitialTheme() {
  const stored = localStorage.getItem("theme");
  const theme = stored || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  applyTheme(theme);
}
function applyTheme(theme) {
  if (theme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
    document.getElementById("theme-color-meta")?.setAttribute("content", "#0e131a");
  } else {
    document.documentElement.removeAttribute("data-theme");
    document.getElementById("theme-color-meta")?.setAttribute("content", "#ffffff");
  }
  const icon = document.getElementById("theme-icon");
  if (icon) icon.textContent = theme === "dark" ? "☀" : "☾";
}
function wireThemeToggle() {
  el("theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    localStorage.setItem("theme", next);
    applyTheme(next);
    // Restyle markers + legend + inset boxes + basemap with new CSS-var values.
    refreshMarkerColors();
    rerenderLegend();
    drawInsetBoxes();
    refreshBasemapColors();
  });
}

function refreshMarkerColors() {
  const stroke = cssColor("--map-marker-stroke");
  for (const [id, marker] of markersById) {
    const s = sitesById.get(id);
    if (!s) continue;
    const c = colorForRecord(s);
    marker.setStyle({ color: stroke, fillColor: c });
  }
}

// ----- URL state sharing -----
function loadInitialFiltersFromUrl() {
  const p = new URLSearchParams(location.search);
  if (p.has("q")) filterState.q = p.get("q") || "";
  if (p.has("state")) filterState.state = p.get("state") || "";
  if (p.has("status")) {
    filterState.statuses = new Set((p.get("status") || "").split(",").filter(Boolean));
  }
  if (p.has("program")) {
    const progs = (p.get("program") || "").split(",").filter(Boolean);
    if (progs.length) filterState.programs = new Set(progs);
  }
  if (p.has("min_ac")) {
    const v = parseFloat(p.get("min_ac") || "0");
    if (!isNaN(v) && v >= 0 && v <= 6) filterState.minAcreage = v;
  }
}

function applyUrlSelection() {
  const p = new URLSearchParams(location.search);
  // Support both ?site=ID (new) and ?epa_id=ID (legacy).
  const id = p.get("site") || p.get("epa_id");
  if (!id) return;
  if (sitesById.has(id)) {
    selectSite(id);
    return;
  }
  // ID provided but not loaded yet. Brownfields lazy-load, so wait once for
  // ACRES to land before declaring the ID unknown.
  if (filterState.programs.has("brownfield") && acresLoadingPromise) {
    acresLoadingPromise.then(() => {
      if (sitesById.has(id)) selectSite(id);
      else showToast(`Site "${id}" not found — check the EPA ID.`);
    });
    return;
  }
  showToast(`Site "${id}" not found — check the EPA ID.`);
}

let _syncUrlPending = null;
function syncUrl() {
  // Debounce to avoid spamming history during slider drags.
  if (_syncUrlPending) clearTimeout(_syncUrlPending);
  _syncUrlPending = setTimeout(() => {
    _syncUrlPending = null;
    const p = new URLSearchParams();
    if (filterState.q) p.set("q", filterState.q);
    if (filterState.state) p.set("state", filterState.state);
    if (filterState.statuses.size) p.set("status", Array.from(filterState.statuses).join(","));
    // Only encode programs when they differ from the default (both programs on).
    const isDefaultProgram =
      filterState.programs.size === 2 &&
      filterState.programs.has("superfund") &&
      filterState.programs.has("brownfield");
    if (!isDefaultProgram) p.set("program", Array.from(filterState.programs).join(","));
    if (filterState.minAcreage > 0) p.set("min_ac", String(filterState.minAcreage));
    if (selectedId) p.set("site", selectedId);
    const qs = p.toString();
    const newUrl = qs ? `${location.pathname}?${qs}` : location.pathname;
    if (newUrl !== location.pathname + location.search) {
      history.replaceState(null, "", newUrl);
    }
  }, 200);
}

// ----- Utils -----
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function escapeAttr(s) { return escapeHtml(s); }
