// Brownfield Opportunities — static dashboard
// Loads docs/data/sites.json and renders a Leaflet map + sortable table.
// Click a marker or row to open the side panel.

const DATA_URL = "data/sites.json";
// Pre-rendered light tiles — avoids CSS filter on every tile during pan/zoom.
const TILE_URL = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
const TILE_ATTRIB =
  '&copy; <a href="https://openstreetmap.org/copyright">OSM</a> · &copy; <a href="https://carto.com/attributions">CARTO</a>';

// US continental view as default.
const DEFAULT_VIEW = { center: [39.5, -98.35], zoom: 4 };

// Hard cap to US-only panning. Wide enough to include AK Aleutians (lon ~-176)
// and PR (lon ~-65, lat ~18); tight enough to keep South America and most of
// Canada/Mexico out of the visible area at minZoom.
const US_BOUNDS = L.latLngBounds([15, -180], [72, -60]);
const MIN_ZOOM = 3;

const STATUS_LEGEND = [
  { code: "F", label: "Final NPL" },
  { code: "P", label: "Proposed" },
  { code: "D", label: "Deleted" },
  { code: "N", label: "Not on NPL" },
];

const el = (id) => document.getElementById(id);
const fmt = {
  acres: (n) => (n == null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 0 }) + " ac"),
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
const markersById = new Map(); // epa_id -> Leaflet marker
const tableRowsById = new Map(); // epa_id -> tr
let selectedId = null;
let sortKey = "acreage";
let sortDir = "desc";

// ----- Boot -----
fetch(DATA_URL)
  .then((r) => {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  })
  .then((payload) => {
    sites = payload.sites || [];
    el("meta").textContent =
      `${payload.count} sites · ${payload.source} · refreshed ${fmt.date(payload.generated_at)}`;
    initMap();
    renderTable();
    wireTabs();
    wireDetailPanel();
  })
  .catch((err) => {
    el("meta").textContent = "Failed to load site data: " + err.message;
    console.error(err);
  });

// ----- Map -----
function initMap() {
  const renderer = L.canvas({ padding: 0.5 });
  map = L.map("map", {
    preferCanvas: true,
    renderer,
    zoomControl: true,
    tap: false, // avoid double-fire on touch devices
    minZoom: MIN_ZOOM,
    maxBounds: US_BOUNDS,
    maxBoundsViscosity: 1.0,
    worldCopyJump: false,
  }).setView(DEFAULT_VIEW.center, DEFAULT_VIEW.zoom);

  L.tileLayer(TILE_URL, {
    attribution: TILE_ATTRIB,
    maxZoom: 19,
    minZoom: MIN_ZOOM,
    detectRetina: true,
    crossOrigin: true,
    bounds: US_BOUNDS, // skip tile fetches outside the US
    noWrap: true,
  }).addTo(map);

  markerLayer = L.layerGroup().addTo(map);

  for (const s of sites) {
    if (s.lat == null || s.lon == null) continue;
    const color = colorForStatus(s.npl_status_code);
    const marker = L.circleMarker([s.lat, s.lon], {
      renderer,
      radius: radiusForAcreage(s.acreage),
      color,
      weight: 1.5,
      fillColor: color,
      fillOpacity: 0.65,
    }).bindTooltip(s.name, { direction: "top" });

    marker.on("click", () => selectSite(s.epa_id, { fromMap: true }));
    markerLayer.addLayer(marker);
    markersById.set(s.epa_id, marker);
  }

  addLegend();
}

function addLegend() {
  const legend = L.control({ position: "bottomright" });
  legend.onAdd = () => {
    const div = L.DomUtil.create("div", "legend");
    const rows = STATUS_LEGEND.map(
      (s) =>
        `<div class="legend-row"><span class="legend-dot" style="color:${colorForStatus(
          s.code
        )}"></span>${s.label}</div>`
    ).join("");
    div.innerHTML =
      `<div class="legend-title">NPL Status</div>${rows}` +
      `<div class="legend-foot">Marker size ∝ acreage (log)</div>`;
    L.DomEvent.disableClickPropagation(div);
    return div;
  };
  legend.addTo(map);
}

function radiusForAcreage(a) {
  if (!a) return 5;
  // log scale: 100 ac -> ~5px, 10000 ac -> ~9px, 1M ac -> ~14px
  return Math.max(4, Math.min(16, 3 + Math.log10(a)));
}

function colorForStatus(code) {
  switch (code) {
    case "F": return "#c83838"; // Currently on Final NPL
    case "P": return "#b8821a"; // Proposed
    case "D": return "#8a94a3"; // Deleted
    case "N": return "#3f7a3f"; // Not on NPL
    default:  return "#1f6fcf";
  }
}

// ----- Table -----
function renderTable() {
  const tbody = document.querySelector("#sites-table tbody");
  tbody.innerHTML = "";
  const sorted = [...sites].sort(makeComparator(sortKey, sortDir));
  const frag = document.createDocumentFragment();
  for (const s of sorted) {
    const tr = document.createElement("tr");
    tr.dataset.id = s.epa_id;
    tr.innerHTML = `
      <td>${escapeHtml(s.name || "—")}</td>
      <td>${escapeHtml(s.state || "—")}</td>
      <td class="num">${fmt.acres(s.acreage)}</td>
      <td><span class="pill" data-status="${escapeAttr(s.npl_status_code || "")}">${escapeHtml(s.npl_status || "Unknown")}</span></td>
      <td>${escapeHtml(s.city || "—")}</td>
      <td>${escapeHtml(s.county || "—")}</td>
    `;
    tr.addEventListener("click", () => selectSite(s.epa_id, { fromTable: true }));
    frag.appendChild(tr);
    tableRowsById.set(s.epa_id, tr);
  }
  tbody.appendChild(frag);
  updateSortIndicators();
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
    else { sortKey = key; sortDir = key === "acreage" ? "desc" : "asc"; }
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
  const s = sites.find((x) => x.epa_id === id);
  if (!s) return;
  if (selectedId && tableRowsById.has(selectedId)) {
    tableRowsById.get(selectedId).classList.remove("selected");
  }
  selectedId = id;
  tableRowsById.get(id)?.classList.add("selected");

  el("detail-title").textContent = s.name || "—";
  const locParts = [s.city, s.state].filter(Boolean).join(", ");
  el("detail-loc").textContent = locParts || "Location unknown";
  el("d-acreage").textContent = fmt.acres(s.acreage);
  const statusEl = el("d-status");
  statusEl.innerHTML = `<span class="pill" data-status="${escapeAttr(s.npl_status_code || "")}">${escapeHtml(s.npl_status || "Unknown")}</span>`;
  el("d-epaid").textContent = fmt.text(s.epa_id);
  el("d-fed").textContent = s.federal_facility ? `Code ${s.federal_facility}` : "—";
  el("d-region").textContent = s.region != null ? `Region ${s.region}` : "—";
  el("d-addr").textContent = [s.address, s.city, s.state, s.zip].filter(Boolean).join(", ") || "—";
  el("d-coord").textContent = s.lat != null && s.lon != null ? `${s.lat.toFixed(4)}, ${s.lon.toFixed(4)}` : "—";
  el("d-updated").textContent = fmt.date(s.last_updated);

  const profile = el("d-profile");
  if (s.profile_url) {
    profile.href = s.profile_url;
    profile.style.display = "";
  } else {
    profile.style.display = "none";
  }

  el("detail").hidden = false;

  if (!fromMap && s.lat != null && s.lon != null) {
    map.setView([s.lat, s.lon], Math.max(map.getZoom(), 8), { animate: true });
    markersById.get(id)?.openTooltip();
  }
}

function closeDetail() {
  el("detail").hidden = true;
  if (selectedId && tableRowsById.has(selectedId)) {
    tableRowsById.get(selectedId).classList.remove("selected");
  }
  selectedId = null;
}

// ----- Utils -----
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function escapeAttr(s) { return escapeHtml(s); }
