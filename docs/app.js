// Brownfield Opportunities — static dashboard
// Loads docs/data/sites.json (Superfund, fast first paint) and lazy-loads
// docs/data/epa-acres.json when the user toggles brownfields on. Renders a
// Leaflet map + sortable table with filters, URL state sharing, CSV export,
// and a theme toggle.

const PRIMARY_DATA_URL = "data/sites.json";
const ACRES_DATA_URL = "data/epa-acres.json";
// Two-layer basemap: clean landmasses always, labels only when zoomed in.
// At low zoom users see the US silhouette + state borders without world clutter;
// county/city labels fade in at zoom ≥ LABEL_MIN_ZOOM.
const TILE_BASE_URL = "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png";
const TILE_LABELS_URL = "https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png";
const LABEL_MIN_ZOOM = 5;
const TILE_ATTRIB =
  '&copy; <a href="https://openstreetmap.org/copyright">OSM</a> · &copy; <a href="https://carto.com/attributions">CARTO</a>';

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
    renderTable();
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
      addMarkersForRecords(payload.sites || []);
      populateStateFilter();
      renderTable();
      rerenderLegend();
      applyFilter();
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
  }).fitBounds(US_BOUNDS, { padding: [10, 10], animate: false });

  L.tileLayer(TILE_BASE_URL, {
    attribution: TILE_ATTRIB,
    maxZoom: 19,
    minZoom: MIN_ZOOM,
    detectRetina: true,
    crossOrigin: true,
    bounds: US_BOUNDS,
    noWrap: true,
  }).addTo(map);

  // Labels (states/counties/cities) only appear once the user zooms in past
  // the country level — keeps the low-zoom view clean and US-focused.
  L.tileLayer(TILE_LABELS_URL, {
    attribution: "",
    maxZoom: 19,
    minZoom: LABEL_MIN_ZOOM,
    detectRetina: true,
    crossOrigin: true,
    bounds: US_BOUNDS,
    noWrap: true,
    pane: "shadowPane",
  }).addTo(map);

  drawInsetBoxes();

  markerLayer = L.layerGroup().addTo(map);
  window.__markerLayer = markerLayer;
  window.__map = map;

  addMarkersForRecords(sites);
  addLegend();

  // Re-evaluate decimation on zoom.
  map.on("zoomend", applyFilter);
}

function addMarkersForRecords(records) {
  const renderer = L.canvas({ padding: 0.5 });
  for (const s of records) {
    if (s.lat == null || s.lon == null) continue;
    if (markersById.has(s.id)) continue;
    const color = colorForRecord(s);
    const marker = L.circleMarker([s.lat, s.lon], {
      renderer,
      radius: radiusForAcreage(s.acreage),
      color,
      weight: 1.2,
      fillColor: color,
      fillOpacity: 0.6,
    }).bindTooltip(s.name || "(unnamed site)", { direction: "top" });

    marker.on("click", () => selectSite(s.id, { fromMap: true }));
    markerLayer.addLayer(marker);
    markersById.set(s.id, marker);
  }
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
  const fill = cssColor("--surface", "#ffffff");
  const stroke = cssColor("--border", "#d8dde6");
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

function applyFilter() {
  const q = filterState.q.trim().toLowerCase();
  const zoom = map ? map.getZoom() : DEFAULT_VIEW.zoom;
  const keepEvery = decimateKeep(zoom);
  let visible = 0;
  let mapVisible = 0;
  let acreSum = 0;
  let acreSites = 0;
  for (const s of sites) {
    const match = siteMatchesFilters(s, { q });
    if (match) {
      visible++;
      if (typeof s.acreage === "number") {
        acreSum += s.acreage;
        acreSites++;
      }
    }

    const row = tableRowsById.get(s.id);
    if (row) row.hidden = !match;

    const marker = markersById.get(s.id);
    if (marker) {
      const decimated = match && shouldDecimateOut(s.id, keepEvery);
      const showOnMap = match && !decimated;
      if (showOnMap) mapVisible++;
      const onMap = markerLayer.hasLayer(marker);
      if (showOnMap && !onMap) markerLayer.addLayer(marker);
      else if (!showOnMap && onMap) markerLayer.removeLayer(marker);
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
  syncUrl();
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
  input.addEventListener("input", () => {
    filterState.q = input.value;
    applyFilter();
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
  };
  progBoxes.superfund.addEventListener("change", onProgramChange);
  progBoxes.brownfield.addEventListener("change", onProgramChange);

  const stateSel = el("f-state");
  stateSel.addEventListener("change", () => {
    filterState.state = stateSel.value;
    applyFilter();
  });

  el("f-status").addEventListener("change", (ev) => {
    const selected = Array.from(ev.target.selectedOptions).map((o) => o.value);
    filterState.statuses = new Set(selected);
    applyFilter();
  });

  const acreEl = el("f-acreage");
  const acreVal = el("f-acreage-val");
  acreEl.addEventListener("input", () => {
    filterState.minAcreage = parseFloat(acreEl.value);
    acreVal.textContent =
      filterState.minAcreage === 0 ? "0" : Math.round(Math.pow(10, filterState.minAcreage)).toLocaleString() + " ac";
    applyFilter();
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
    for (const opt of el("f-status").options) opt.selected = false;
    acreEl.value = "0";
    acreVal.textContent = "0";
    applyFilter();
  });
}

function populateStateFilter() {
  const sel = el("f-state");
  const states = new Set();
  for (const s of sites) if (s.state) states.add(s.state);
  const sorted = Array.from(states).sort();
  // Preserve current selection across re-population.
  const current = sel.value;
  sel.innerHTML = '<option value="">All states</option>' +
    sorted.map((st) => `<option value="${escapeAttr(st)}">${escapeHtml(st)}</option>`).join("");
  if (sorted.includes(current)) sel.value = current;
  else if (sorted.includes(filterState.state)) sel.value = filterState.state;
}

function populateStatusFilter() {
  const sel = el("f-status");
  sel.innerHTML = STATUS_LEGEND.map(
    (s) => `<option value="${escapeAttr(s.code)}"${
      filterState.statuses.has(s.code) ? " selected" : ""
    }>${escapeHtml(s.label)}</option>`
  ).join("");
}

// ----- Table -----
function renderTable() {
  const tbody = document.querySelector("#sites-table tbody");
  tbody.innerHTML = "";
  tableRowsById.clear();
  const sorted = [...sites].sort(makeComparator(sortKey, sortDir));
  const frag = document.createDocumentFragment();
  for (const s of sorted) {
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
    frag.appendChild(tr);
    tableRowsById.set(s.id, tr);
  }
  tbody.appendChild(frag);
  updateSortIndicators();
  applyFilter();
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
    renderTable();
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
    el("d-fed").textContent = s.federal_facility ? `Code ${s.federal_facility}` : "—";
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

  el("detail").hidden = false;

  if (!fromMap && s.lat != null && s.lon != null) {
    map.setView([s.lat, s.lon], Math.max(map.getZoom(), 8), { animate: true });
    markersById.get(id)?.openTooltip();
  }
  syncUrl();
}

function closeDetail() {
  el("detail").hidden = true;
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
    // Restyle markers + legend + inset boxes with new CSS-var values.
    refreshMarkerColors();
    rerenderLegend();
    drawInsetBoxes();
  });
}

function refreshMarkerColors() {
  for (const [id, marker] of markersById) {
    const s = sitesById.get(id);
    if (!s) continue;
    const c = colorForRecord(s);
    marker.setStyle({ color: c, fillColor: c });
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
  if (id && sitesById.has(id)) {
    selectSite(id);
    el("tab-table")?.click ? null : null; // no-op; just ensure selection happens after init
  }
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
