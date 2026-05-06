// Brownfield Opportunities — static dashboard
// Loads docs/data/sites.json (Superfund, fast first paint) and lazy-loads
// docs/data/epa-acres.json when the user toggles brownfields on. Renders a
// Leaflet map + sortable table with filters, URL state sharing, CSV export,
// and a theme toggle.

const PRIMARY_DATA_URL = "data/sites.json";
const ACRES_DATA_URL = "data/epa-acres.json";
const FUDS_DATA_URL = "data/dod-fuds.json";
const BRAC_DATA_URL = "data/dod-brac.json";
const REDEV_DATA_URL = "data/epa-redev.json";
const SUPERFUND_DOCS_URL = "data/epa-superfund-docs.json";
const INFRA_DATA_URL = "data/infra-proximity.json";
const ECHO_DATA_URL = "data/epa-echo.json";
const AI_SUMMARY_URL = "data/ai-summary.json";
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
  { program: "fuds", label: "FUDS (Defense)", cssVar: "--program-fuds" },
  { program: "brac", label: "BRAC (Bases)", cssVar: "--program-brac" },
];
const PROGRAM_COLOR_BY_PROGRAM = Object.fromEntries(
  PROGRAM_LEGEND.map((p) => [p.program, p.cssVar])
);
const PROGRAM_LABEL = {
  superfund: "Superfund (NPL)",
  brownfield: "Brownfield (ACRES)",
  fuds: "FUDS (Defense)",
  brac: "BRAC (Bases)",
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
  // Distance in miles, null → "Not available". Sub-mile precision rounded
  // to 0.1 — matches the connector's emit precision.
  miles: (n) => {
    if (n == null) return "Not available";
    const rounded = Math.round(n * 10) / 10;
    if (rounded < 0.1) return "<0.1 mi";
    return rounded.toLocaleString(undefined, { maximumFractionDigits: 1 }) + " mi";
  },
  // Compact numeric formatter for KPI deck: 47k / 3.2M / 1.9B style.
  // Falls back to comma-grouped for browsers without compact notation.
  compact: (n) => {
    if (n == null || isNaN(n)) return "—";
    try {
      return new Intl.NumberFormat(undefined, {
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(n);
    } catch {
      return Math.round(n).toLocaleString();
    }
  },
};

// ----- Place-name prettifier (display-time fix for ALL CAPS source data) -----
//
// EPA Superfund + ACRES + USACE FUDS ship cities/counties as either ALL CAPS
// or mixed case. The frontend used to render them verbatim, leaking
// "GREEN BAY", "KODIAK ISLAND BOROUGH", etc. into the table and detail panel.
// We title-case at display time only — the underlying data file is unchanged
// so re-running connectors won't regress, and connector logic stays simple.
//
// Also strips a few sentinel placeholders the source uses for "unknown":
//   - "-- Not Defined --"  (EPA Superfund)
//   - "_NULL_"             (occasional ACRES rows)
const PLACE_SENTINELS = new Set(["-- not defined --", "_null_", "n/a", "na", "none", ""]);
const PLACE_KEEP_LOWER = new Set(["of", "and", "the", "in", "on", "at", "by", "for"]);
const PLACE_KEEP_UPPER = new Set(["us", "usa", "ne", "nw", "se", "sw", "ii", "iii", "iv", "afb", "aap"]);

function prettyPlace(s) {
  if (s == null) return "";
  const trimmed = String(s).trim();
  if (!trimmed || PLACE_SENTINELS.has(trimmed.toLowerCase())) return "";
  // Already mixed case → trust the source.
  if (trimmed !== trimmed.toUpperCase()) return trimmed;
  // ALL CAPS → title case word-by-word with small-word + initialism rules.
  return trimmed.split(/(\s+|[-/])/g).map((tok, i) => {
    if (/^\s+$/.test(tok) || tok === "-" || tok === "/") return tok;
    const lower = tok.toLowerCase();
    if (i > 0 && PLACE_KEEP_LOWER.has(lower)) return lower;
    if (PLACE_KEEP_UPPER.has(lower)) return lower.toUpperCase();
    // O'Brien, McAllister — keep the bump after an apostrophe / Mc prefix.
    if (lower.startsWith("mc") && lower.length > 2) {
      return "Mc" + lower.charAt(2).toUpperCase() + lower.slice(3);
    }
    if (lower.includes("'")) {
      return lower.split("'").map((p, j) => j === 0
        ? p.charAt(0).toUpperCase() + p.slice(1)
        : p.charAt(0).toUpperCase() + p.slice(1)).join("'");
    }
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  }).join("");
}

// ----- Site-name prettifier (display-time fix for ALL CAPS source data) -----
//
// EPA Superfund / USACE FUDS / DOD BRAC ship site names ALL CAPS in ~94% of
// records. Title-casing them is more delicate than place names because EPA
// names embed federal acronyms (USDOE, NRDA, PCB, AAP, AFB, …) that simple
// title-casing would mangle ("Usdoe", "Nrda"). The acronym whitelist below
// is seeded from a frequency scan of the actual dataset (10k+ ALL-CAPS
// names across the three programs). When a new acronym shows up that the
// list doesn't catch, add it here — it will Just Work for every record on
// next ingest.
//
// Like prettyPlace(), this runs in ingestSites() and the original source
// is preserved on `s.name_raw` so future per-source connector-side fixes
// can compare against the raw value.
const NAME_KEEP_UPPER = new Set([
  // Military / DOD
  "AFB", "AAF", "AAFB", "AFS", "AFR", "USARC", "USAF", "USAFR",
  "USMC", "USMCR", "USCG", "USCGA", "USN", "USNR", "USA", "USS",
  "NAS", "NAVSTA", "NAVFAC", "NAVMAR", "DOD", "ANG", "NG", "NIKE",
  "AAA", "OLF", "POW", "ROTC", "USACE", "AFRC", "NORAD", "STRATCOM",
  // Federal civilian
  "EPA", "USEPA", "USDOE", "DOE", "DOT", "DOJ", "DOI", "DOC", "DOL",
  "USDA", "USFS", "USFWS", "USGS", "USPS", "GSA", "TVA", "VA", "FAA",
  "FBI", "NASA", "BLM", "NPS", "NRC", "FERC", "FRS",
  // Chemical / contamination
  "PCB", "PCBS", "PFAS", "PFOS", "PFOA", "TCE", "PCE", "VOC", "VOCS",
  "NRDA", "AAP", "MEW", "RCRA", "CERCLA", "NPL", "ROD", "ESD",
  // Geographic / political
  "US", "USVI", "DC", "PR", "USA",
  // Compass
  "NE", "NW", "SE", "SW", "NNE", "NNW", "SSE", "SSW",
  // Roman numerals 1–10 (II..X — single "I" is too risky as a one-letter token)
  "II", "III", "IV", "VI", "VII", "VIII", "IX",
  // Range / nominal-number prefixes
  "NO",
]);
// Words that should drop to lowercase when they aren't the leading token.
const NAME_KEEP_LOWER = new Set([
  "of", "and", "the", "in", "on", "at", "by", "for", "to", "or",
  "vs", "an", "a",
]);

function prettyName(s) {
  if (s == null) return "";
  const trimmed = String(s).trim();
  if (!trimmed) return "";
  // Already mixed case → trust the source. EPA / DOD ship names ALL CAPS;
  // a record that's mixed-case has already been normalized somewhere
  // upstream and we shouldn't undo that.
  if (trimmed !== trimmed.toUpperCase()) return trimmed;
  return trimmed.split(/(\s+|[/\-(),])/g).map((tok, i) => {
    if (/^\s+$/.test(tok) || /^[/\-(),]$/.test(tok)) return tok;
    const upper = tok.toUpperCase();
    if (NAME_KEEP_UPPER.has(upper)) return upper;
    const lower = tok.toLowerCase();
    if (i > 0 && NAME_KEEP_LOWER.has(lower)) return lower;
    if (lower.startsWith("mc") && lower.length > 2) {
      return "Mc" + lower.charAt(2).toUpperCase() + lower.slice(3);
    }
    if (lower.includes("'")) {
      return lower.split("'").map((p) =>
        p.length ? p.charAt(0).toUpperCase() + p.slice(1) : p
      ).join("'");
    }
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  }).join("");
}

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
  programs: new Set(["superfund", "brownfield", "fuds", "brac"]),
  state: "",
  statuses: new Set(),
  minAcreage: 0, // log10 base; 0 means "show all" (incl. null acreage)
};

let acresLoadingPromise = null; // de-dup parallel toggles
let fudsLoadingPromise = null;
let bracLoadingPromise = null;
let redevLoadingPromise = null;
let superfundDocsLoadingPromise = null;
let infraLoadingPromise = null;
let echoLoadingPromise = null;
let summariesLoadingPromise = null;

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

// ----- Hero / KPI deck / footer / meta -----
//
// All numbers are derived from the in-memory `sites` array; no extra fetches.
// Called after each lazy-load lands so the deck progressively fills in.
function setHeroRefresh(dateStr) {
  if (!dateStr || dateStr === "—") return;
  const heroEl = el("hero-refresh");
  if (heroEl) heroEl.textContent = `Updated ${dateStr}`;
  const footerEl = el("footer-refresh");
  if (footerEl) footerEl.textContent = `Refreshed ${dateStr}`;
}

// Compose the topbar subtitle from the actual per-program counts so it
// can't drift after lazy loads land. Replaces the previous hardcoded
// "X Superfund + Y brownfields" template that mislabeled the breakdown
// once FUDS / BRAC also lazy-loaded.
const PROGRAM_META_LABEL = {
  superfund: "Superfund",
  brownfield: "brownfields",
  fuds: "FUDS",
  brac: "BRAC",
};
function updateMetaText({ loadingLabel = null } = {}) {
  const counts = {};
  for (const s of sites) {
    if (!s.program) continue;
    counts[s.program] = (counts[s.program] || 0) + 1;
  }
  const total = sites.length;
  const parts = [];
  for (const program of ["superfund", "brownfield", "fuds", "brac"]) {
    if (counts[program]) {
      parts.push(`${counts[program].toLocaleString()} ${PROGRAM_META_LABEL[program]}`);
    }
  }
  const refreshed = window.__refreshedAt;
  let text = `${total.toLocaleString()} sites`;
  if (parts.length) text += ` (${parts.join(" + ")})`;
  if (loadingLabel) text += ` · loading ${loadingLabel}…`;
  if (refreshed && refreshed !== "—") text += ` · refreshed ${refreshed}`;
  const node = el("meta");
  if (node) node.textContent = text;
}

function updateKpiDeck() {
  const total = sites.length;
  let acreSum = 0;
  let acreCount = 0;
  let dcCount = 0;
  const stateSet = new Set();
  const programSet = new Set();
  for (const s of sites) {
    if (typeof s.acreage === "number") {
      acreSum += s.acreage;
      acreCount++;
    }
    if (s.data_center_reuse_candidate === true) dcCount++;
    if (s.state) stateSet.add(s.state);
    if (s.program) programSet.add(s.program);
  }
  const set = (id, value) => {
    const node = el(id);
    if (node) node.textContent = value;
  };
  set("kpi-total", fmt.compact(total));
  set("kpi-total-sub", `across ${programSet.size} program${programSet.size === 1 ? "" : "s"}`);
  set("kpi-acres", fmt.compact(acreSum));
  set("kpi-acres-sub", `${fmt.compact(acreCount)} sites with reported area`);
  set("kpi-dc", fmt.compact(dcCount));
  set("kpi-states", String(stateSet.size));
}

// Active-filter chip count on the gear icon. Also updates aria-label on the
// filter button so screen readers know the active count.
function updateFilterChip() {
  let count = 0;
  if (filterState.q) count++;
  if (filterState.state) count++;
  count += filterState.statuses.size;
  if (filterState.minAcreage > 0) count++;
  // Default is all four programs on; any deselection counts as a filter.
  if (filterState.programs.size && filterState.programs.size < PROGRAM_LEGEND.length) count++;
  const chip = el("filters-chip");
  const btn = el("filters-toggle");
  if (chip) {
    if (count > 0) {
      chip.hidden = false;
      chip.textContent = String(count);
    } else {
      chip.hidden = true;
    }
  }
  if (btn) btn.setAttribute("aria-label", count ? `Filters (${count} active)` : "Filters");
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
    window.__refreshedAt = refreshed;
    setHeroRefresh(refreshed);
    updateMetaText({
      loadingLabel: filterState.programs.has("brownfield") ? "brownfields" : null,
    });
    updateKpiDeck();
    try { initMap(); } catch (e) { console.error("initMap error (non-fatal):", e); }
    populateStatusFilter();
    populateStateFilter();
    rebuildTable();
    wireTabs();
    wireDetailPanel();
    wireSearch();
    wireFilters();
    wireExportCsv();
    wireThemeToggle();
    window.__sitesLoaded = true; // e2e hook
    // Expose data + a programmatic site-selector so e2e tests can target
    // an enriched record by id without depending on table sort order.
    // Use a getter — `sites` is reassigned by ingestSites (`sites =
    // Array.from(sitesById.values())`), so a snapshot would go stale.
    Object.defineProperty(window, "__sites", {
      configurable: true,
      get: () => sites,
    });
    window.__selectSite = selectSite;
    // Expose tableState so e2e can verify the cached visible bbox.
    window.__tableState = tableState;
    // Expose the prettifiers + CSV schema so e2e tests can exercise the
    // curated column set without intercepting a download.
    window.__prettyName = prettyName;
    window.__csvColumns = CSV_COLUMNS;
    window.__buildCsv = () => {
      const rows = [CSV_COLUMNS.map((c) => c.label)];
      for (const s of sites) {
        if (!siteMatchesFilters(s)) continue;
        rows.push(CSV_COLUMNS.map((c) => csvCell(s, c)));
      }
      return rows.map(csvRow).join("\n");
    };
    // Kick off lazy loads for enabled programs BEFORE applyUrlSelection()
    // so the *LoadingPromise globals are populated — applyUrlSelection
    // waits on them when the requested ?site= ID points at a record from
    // a program that hasn't streamed in yet (e.g. ?site=FUDS-XXX during
    // the FUDS lazy-load window).
    const lazyLoads = [];
    if (filterState.programs.has("brownfield")) lazyLoads.push(ensureAcresLoaded());
    if (filterState.programs.has("fuds")) lazyLoads.push(ensureFudsLoaded());
    if (filterState.programs.has("brac")) lazyLoads.push(ensureBracLoaded());
    lazyLoads.push(ensureRedevLoaded());
    lazyLoads.push(ensureSuperfundDocsLoaded());
    lazyLoads.push(ensureInfraLoaded());
    lazyLoads.push(ensureEchoLoaded());
    lazyLoads.push(ensureSummariesLoaded());
    applyUrlSelection();
    if (lazyLoads.length === 0) {
      markAppReady();
    } else {
      Promise.allSettled(lazyLoads).then(() => markAppReady());
    }
  })
  .catch((err) => {
    el("meta").textContent = "Failed to load site data: " + err.message;
    console.error(err);
  });

function ingestSites(records) {
  for (const s of records) {
    if (sitesById.has(s.id)) continue;
    // Title-case ALL CAPS city/county/address/name at ingest time so search,
    // filter, table, detail panel, marker tooltip, and CSV export all see
    // the prettified form. Source data is preserved on `*_raw` for debugging.
    if (s.name) {
      const pretty = prettyName(s.name);
      if (pretty && pretty !== s.name) { s.name_raw = s.name; s.name = pretty; }
    }
    if (s.city) {
      const pretty = prettyPlace(s.city);
      if (pretty && pretty !== s.city) { s.city_raw = s.city; s.city = pretty; }
      else if (!pretty) s.city = null;
    }
    if (s.county) {
      const pretty = prettyPlace(s.county);
      if (pretty && pretty !== s.county) { s.county_raw = s.county; s.county = pretty; }
      else if (!pretty) s.county = null;
    }
    if (s.address) {
      const pretty = prettyPlace(s.address);
      if (pretty && pretty !== s.address) { s.address_raw = s.address; s.address = pretty; }
      else if (!pretty) s.address = null;
    }
    applyInsetRemap(s);
    // Pre-build a lowercased search index once at ingest time. `siteMatchesQuery`
    // does an `includes` against this — every keystroke would otherwise rebuild
    // the same string for all 47k sites and re-allocate.
    s._searchKey = [s.name, s.city, s.county, s.state]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
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
  updateMetaText({ loadingLabel: "brownfields" });
  acresLoadingPromise = fetch(ACRES_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      ingestSites(payload.sites || []);
      updateMetaText();
      populateStateFilter();
      rebuildTable();
      rerenderLegend();
      updateKpiDeck();
      // Chunk marker hydration so the main thread stays responsive while
      // the 36k ACRES markers light up. We resolve `acresLoadingPromise`
      // (and dispatch `brownfield:ready`) only after the last batch lands.
      return hydrateMarkersChunked(payload.sites || []).then(() => {
        applyFilter();
        markAppReady();
      });
    })
    .catch((err) => {
      updateMetaText();
      const node = el("meta");
      if (node) node.textContent += ` · brownfields failed (${err.message})`;
      console.error(err);
      acresLoadingPromise = null; // allow retry
    });
  return acresLoadingPromise;
}

function ensureFudsLoaded() {
  if (fudsLoadingPromise) return fudsLoadingPromise;
  if (sites.some((s) => s.program === "fuds")) return Promise.resolve();
  fudsLoadingPromise = fetch(FUDS_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      ingestSites(payload.sites || []);
      updateMetaText();
      populateStateFilter();
      rebuildTable();
      rerenderLegend();
      updateKpiDeck();
      return hydrateMarkersChunked(payload.sites || []).then(() => {
        applyFilter();
      });
    })
    .catch((err) => {
      console.error("FUDS load failed:", err);
      fudsLoadingPromise = null;
    });
  return fudsLoadingPromise;
}

function ensureBracLoaded() {
  if (bracLoadingPromise) return bracLoadingPromise;
  if (sites.some((s) => s.program === "brac")) return Promise.resolve();
  bracLoadingPromise = fetch(BRAC_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      ingestSites(payload.sites || []);
      updateMetaText();
      populateStateFilter();
      rebuildTable();
      rerenderLegend();
      updateKpiDeck();
      addMarkersForRecords(payload.sites || []);
      applyFilter();
    })
    .catch((err) => {
      console.error("BRAC load failed:", err);
      bracLoadingPromise = null;
    });
  return bracLoadingPromise;
}

function ensureRedevLoaded() {
  if (redevLoadingPromise) return redevLoadingPromise;
  redevLoadingPromise = fetch(REDEV_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id || rec.epa_id);
        if (!existing) continue;
        if (rec.near_electric_transmission) existing.near_electric_transmission = rec.near_electric_transmission;
        if (rec.near_highway) existing.near_highway = rec.near_highway;
        if (rec.near_railroad) existing.near_railroad = rec.near_railroad;
        if (rec.near_water_supply) existing.near_water_supply = rec.near_water_supply;
        if (rec.near_wastewater) existing.near_wastewater = rec.near_wastewater;
        if (rec.pop_density) existing.pop_density = rec.pop_density;
        if (rec.in_opp_zone) existing.in_opp_zone = rec.in_opp_zone;
        if (rec.in_reuse) existing.in_reuse = rec.in_reuse;
        if (rec.data_center_reuse_candidate != null) existing.data_center_reuse_candidate = rec.data_center_reuse_candidate;
        if (rec.acreage != null && existing.acreage == null) existing.acreage = rec.acreage;
      }
      // DC candidate count + acreage totals can change after enrichment.
      updateKpiDeck();
    })
    .catch((err) => {
      console.error("Redev enrichment load failed:", err);
      redevLoadingPromise = null;
    });
  return redevLoadingPromise;
}

// EPA Superfund Documents enrichment. Per-EPA_ID list of public-facing
// documents (RODs, ESDs, Five Year Reviews, fact sheets, technical reports)
// pulled from the SEMS cachejson API by the epa-superfund-docs connector.
// Only sites the connector has covered so far are present — coverage grows
// as the connector's `--docs-limit` re-runs land more sites.
function ensureSuperfundDocsLoaded() {
  if (superfundDocsLoadingPromise) return superfundDocsLoadingPromise;
  superfundDocsLoadingPromise = fetch(SUPERFUND_DOCS_URL)
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id || rec.epa_id);
        if (!existing) continue;
        if (Array.isArray(rec.documents) && rec.documents.length) {
          existing.documents = rec.documents;
        }
      }
    })
    .catch((err) => {
      console.error("Superfund docs enrichment load failed:", err);
      superfundDocsLoadingPromise = null;
    });
  return superfundDocsLoadingPromise;
}

// EPA ECHO enforcement enrichment. Per-site enforcement summary (5yr
// inspections, formal/informal actions, penalties, current compliance,
// last violation date) pulled from the public ECHO REST service by the
// `epa-echo` connector. Open enforcement is a transactability red flag.
function ensureEchoLoaded() {
  if (echoLoadingPromise) return echoLoadingPromise;
  echoLoadingPromise = fetch(ECHO_DATA_URL)
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id || rec.epa_id);
        if (!existing) continue;
        if (rec.enforcement && typeof rec.enforcement === "object") {
          existing.enforcement = rec.enforcement;
        }
      }
    })
    .catch((err) => {
      console.error("ECHO enrichment load failed:", err);
      echoLoadingPromise = null;
    });
  return echoLoadingPromise;
}

// AI-generated site summaries (Claude Haiku output). Per-site 3-paragraph
// plain-English narrative, content-hash-cached at refresh time. Coverage
// grows as `--source ai-summary --ai-limit N` re-runs land more sites.
function ensureSummariesLoaded() {
  if (summariesLoadingPromise) return summariesLoadingPromise;
  summariesLoadingPromise = fetch(AI_SUMMARY_URL)
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        if (rec.summary) existing.summary = rec.summary;
        if (rec.summary_meta) existing.summary_meta = rec.summary_meta;
      }
      if (selectedId) {
        const sel = sitesById.get(selectedId);
        if (sel) renderSummary(sel);
      }
    })
    .catch((err) => {
      console.error("AI summary load failed:", err);
      summariesLoadingPromise = null;
    });
  return summariesLoadingPromise;
}

// Universal infrastructure-proximity enrichment. Joins onto every program
// (Superfund, ACRES, FUDS, BRAC) by `id` to add `transmission_mi`,
// `rail_mi`, `highway_mi`. Computed at refresh time from HIFLD + Census
// TIGER by the `infra-proximity` connector. Distances >100 mi are absent
// (treated as out-of-range / out-of-CONUS).
function ensureInfraLoaded() {
  if (infraLoadingPromise) return infraLoadingPromise;
  infraLoadingPromise = fetch(INFRA_DATA_URL)
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        if (rec.transmission_mi != null) existing.transmission_mi = rec.transmission_mi;
        if (rec.rail_mi != null) existing.rail_mi = rec.rail_mi;
        if (rec.highway_mi != null) existing.highway_mi = rec.highway_mi;
      }
    })
    .catch((err) => {
      console.error("Infra-proximity enrichment load failed:", err);
      infraLoadingPromise = null;
    });
  return infraLoadingPromise;
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
    // Per-program count for the per-row tally on the right.
    const counts = {};
    for (const s of sites) {
      if (!s.program) continue;
      counts[s.program] = (counts[s.program] || 0) + 1;
    }
    const programsPresent = new Set(Object.keys(counts));
    const rows = PROGRAM_LEGEND.filter((p) => programsPresent.has(p.program))
      .map(
        (p) =>
          `<div class="legend-row">` +
          `<span class="legend-dot" style="color:${cssColor(p.cssVar)}"></span>` +
          `<span class="legend-label">${escapeHtml(p.label)}</span>` +
          `<span class="legend-num">${(counts[p.program] || 0).toLocaleString()}</span>` +
          `</div>`
      )
      .join("");
    div.innerHTML =
      `<div class="legend-title"><span>Program</span></div>${rows}` +
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
  // `_searchKey` is built once at ingest time (see `ingestSites`). Falling
  // back to a fresh join here would defeat the optimization, so just bail
  // if a record was added through some other path that skipped the index.
  return (s._searchKey || "").includes(q);
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
  updateFilterChip();
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
  // Read the cached bbox built by `refreshTableForFilter()` rather than
  // rescanning all sites — every event handler that calls this also calls
  // `applyFilter()` first, so the bbox is always fresh.
  const bb = tableState.visibleBBox;
  if (!bb || bb.count === 0 || bb.count > 5000) return;
  if (bb.count === 1) {
    map.setView([bb.minLat, bb.minLon], 12, { animate: true });
    return;
  }
  const bbox = L.latLngBounds(
    [bb.minLat, bb.minLon],
    [bb.maxLat, bb.maxLon]
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
    filterState.programs.size !== PROGRAM_LEGEND.length
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

  const progBoxes = {};
  for (const p of PROGRAM_LEGEND) {
    progBoxes[p.program] = el("f-program-" + p.program);
  }
  for (const [program, box] of Object.entries(progBoxes)) {
    if (box) box.checked = filterState.programs.has(program);
  }
  const onProgramChange = () => {
    const next = new Set();
    for (const [program, box] of Object.entries(progBoxes)) {
      if (box && box.checked) next.add(program);
    }
    if (!next.size) {
      if (progBoxes.superfund) progBoxes.superfund.checked = true;
      next.add("superfund");
    }
    filterState.programs = next;
    if (filterState.programs.has("brownfield")) ensureAcresLoaded();
    if (filterState.programs.has("fuds")) ensureFudsLoaded();
    if (filterState.programs.has("brac")) ensureBracLoaded();
    applyFilter();
    refitMapToFilters();
  };
  for (const box of Object.values(progBoxes)) {
    if (box) box.addEventListener("change", onProgramChange);
  }

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
    // Restore *all* programs in PROGRAM_LEGEND, not a hardcoded subset —
    // when FUDS / BRAC were added in v1.7 this handler stayed at v1.6's
    // [superfund, brownfield] and silently dropped the new programs on
    // every Reset click (UAT-007). Iterate the legend so future programs
    // pick up the reset for free.
    filterState.programs = new Set(PROGRAM_LEGEND.map((p) => p.program));
    filterState.state = "";
    filterState.statuses = new Set();
    filterState.minAcreage = 0;
    filterState.q = "";
    el("search").value = "";
    for (const [program, box] of Object.entries(progBoxes)) {
      if (box) box.checked = filterState.programs.has(program);
    }
    if (filterState.programs.has("brownfield")) ensureAcresLoaded();
    if (filterState.programs.has("fuds")) ensureFudsLoaded();
    if (filterState.programs.has("brac")) ensureBracLoaded();
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
  // Bounding box of the visible (filtered) set, recomputed by
  // `refreshTableForFilter()` so `refitMapToFilters()` doesn't have to
  // re-scan all 47k records on every filter toggle.
  visibleBBox: null, // { minLat, maxLat, minLon, maxLon, count } | null
};
let _tableSentinel = null;
let _tableObserver = null;

function makeRow(s) {
  const tr = document.createElement("tr");
  tr.dataset.id = s.id;
  const programLabel = PROGRAM_LABEL[s.program] || s.program || "—";
  // STATUS column is NPL-specific. For Superfund, show the NPL pill.
  // For FUDS, surface eligibility (the most actionable cleanup-status
  // signal — Eligible / Ineligible / No Further Action / Categorical
  // Exclusion). ACRES + BRAC have no comparable status field, so render
  // an em-dash rather than duplicating the PROGRAM pill (UAT-009).
  let statusHtml;
  if (s.npl_status_code) {
    statusHtml = `<span class="pill" data-status="${escapeAttr(s.npl_status_code)}">${escapeHtml(s.npl_status || "Unknown")}</span>`;
  } else if (s.program === "fuds" && s.eligibility) {
    statusHtml = escapeHtml(s.eligibility);
  } else {
    statusHtml = '<span class="muted-cell">—</span>';
  }
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
  // Same pass: capture the bbox of the visible set so `refitMapToFilters`
  // doesn't sweep all 47k records again on every filter toggle.
  let minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity;
  let count = 0;
  for (const s of tableState.filtered) {
    if (s.lat == null || s.lon == null) continue;
    if (s.lat < minLat) minLat = s.lat;
    if (s.lat > maxLat) maxLat = s.lat;
    if (s.lon < minLon) minLon = s.lon;
    if (s.lon > maxLon) maxLon = s.lon;
    count++;
  }
  tableState.visibleBBox = count > 0
    ? { minLat, maxLat, minLon, maxLon, count }
    : null;
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
    th.removeAttribute("data-sort-glyph");
    if (th.dataset.sort === sortKey) {
      th.setAttribute("aria-sort", sortDir === "asc" ? "ascending" : "descending");
      th.setAttribute("data-sort-glyph", sortDir === "asc" ? "▲" : "▼");
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
  wireDetailTabs();
}

// Tabs inside the detail panel: Overview (default) vs Summary (AI card).
// Default-back-to-Overview every time selectSite() opens a new site so
// the user always lands on the structured-fields view first.
function wireDetailTabs() {
  const tabs = [
    { btn: el("dtab-overview"), pane: el("dpane-overview") },
    { btn: el("dtab-summary"), pane: el("dpane-summary") },
  ];
  for (const t of tabs) {
    if (!t.btn || !t.pane) continue;
    t.btn.addEventListener("click", () => {
      for (const other of tabs) {
        const isMe = other === t;
        other.btn.classList.toggle("active", isMe);
        other.btn.setAttribute("aria-selected", String(isMe));
        other.pane.hidden = !isMe;
      }
    });
  }
}

function resetDetailTabs() {
  const ov = el("dtab-overview"), sm = el("dtab-summary");
  const ovp = el("dpane-overview"), smp = el("dpane-summary");
  if (ov) { ov.classList.add("active"); ov.setAttribute("aria-selected", "true"); }
  if (sm) { sm.classList.remove("active"); sm.setAttribute("aria-selected", "false"); }
  if (ovp) ovp.hidden = false;
  if (smp) smp.hidden = true;
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
  // Program pill, plus three optional badges:
  //   - "DC candidate" when the redev enrichment flagged this site as
  //     data-center reuse-suitable (power + ≥50 ac + water service area).
  //   - "Cleanup Complete" for NPL Deleted Superfund sites — the strongest
  //     "site is transactable today" signal in the dataset (zero new fetch).
  //   - "Active Reuse" when EPA's RedevelopmentAppSitePoints `In_Reuse`
  //     field is "Yes" — the site is already being put to productive use.
  const programPill = `<span class="pill" data-program="${escapeAttr(s.program)}">${escapeHtml(PROGRAM_LABEL[s.program] || s.program || "—")}</span>`;
  const dcPill = s.data_center_reuse_candidate === true
    ? ` <span class="pill dc-pill" title="Power, ≥50 acres, water service area">DC candidate</span>`
    : "";
  const cleanupPill = (s.program === "superfund" && s.npl_status_code === "D")
    ? ` <span class="pill cleanup-pill" title="Site has been deleted from the National Priorities List — cleanup complete">Cleanup Complete</span>`
    : "";
  const reusePill = (typeof s.in_reuse === "string" && /^yes/i.test(s.in_reuse))
    ? ` <span class="pill reuse-pill" title="Site is currently in active reuse (EPA Superfund Redevelopment mapper)">Active Reuse</span>`
    : "";
  el("d-program").innerHTML = programPill + cleanupPill + reusePill + dcPill;
  // The acreage `<dd>` carries an inline note `<span>` for FUDS records
  // missing acreage. Replace only the text node so the note span isn't
  // clobbered, then toggle the note for the FUDS-no-boundary case.
  const acreageEl = el("d-acreage");
  const acreageNote = el("d-acreage-note");
  acreageEl.firstChild && acreageEl.firstChild.nodeType === Node.TEXT_NODE
    ? (acreageEl.firstChild.nodeValue = fmt.acres(s.acreage))
    : acreageEl.insertBefore(document.createTextNode(fmt.acres(s.acreage)), acreageNote || null);
  if (acreageNote) {
    if (s.program === "fuds" && s.acreage == null) {
      acreageNote.textContent = "Boundary not digitized in USACE source.";
      acreageNote.hidden = false;
    } else {
      acreageNote.textContent = "";
      acreageNote.hidden = true;
    }
  }

  // Status / ID labels vary by program.
  const statusEl = el("d-status");
  if (s.program === "superfund") {
    el("d-status-label").textContent = "NPL Status";
    statusEl.innerHTML = `<span class="pill" data-status="${escapeAttr(s.npl_status_code || "")}">${escapeHtml(s.npl_status || "Unknown")}</span>`;
    el("d-id-label").textContent = "EPA ID";
    el("d-epaid").textContent = fmt.text(s.epa_id || s.id);
    el("d-fed-label").textContent = "Federal Facility";
    el("d-fed").textContent = s.federal_facility
      ? String(s.federal_facility).replace(/\s+/g, " ").trim()
      : "—";
    el("d-updated-label").textContent = "Last Updated";
    el("d-updated").textContent = fmt.date(s.last_updated);
  } else if (s.program === "fuds") {
    el("d-status-label").textContent = "NPL Status";
    statusEl.textContent = fmt.text(s.npl_status);
    el("d-id-label").textContent = "FUDS Property ID";
    el("d-epaid").textContent = (s.id || "").replace(/^FUDS-/, "") || "—";
    el("d-fed-label").textContent = "Current Owner";
    el("d-fed").textContent = fmt.text(s.current_owner);
    el("d-updated-label").textContent = "Congressional District";
    el("d-updated").textContent = fmt.text(s.congressional_district);
  } else if (s.program === "brac") {
    el("d-status-label").textContent = "Status";
    statusEl.textContent = "BRAC";
    el("d-id-label").textContent = "Installation ID";
    el("d-epaid").textContent = (s.id || "").replace(/^BRAC-/, "") || "—";
    el("d-fed-label").textContent = "Component";
    el("d-fed").textContent = fmt.text(s.component);
    el("d-updated-label").textContent = "Last Updated";
    el("d-updated").textContent = "—";
  } else {
    el("d-status-label").textContent = "Status";
    statusEl.textContent = "—";
    el("d-id-label").textContent = "Property ID";
    el("d-epaid").textContent = (s.id || "").replace(/^ACRES-/, "") || "—";
    el("d-fed-label").textContent = "Federal Facility";
    el("d-fed").textContent = "—";
    el("d-updated-label").textContent = "Last Updated";
    el("d-updated").textContent = "—";
  }

  // FUDS-specific detail block
  const fudsBlock = el("d-fuds-block");
  if (fudsBlock) {
    if (s.program === "fuds") {
      fudsBlock.hidden = false;
      el("d-eligibility").textContent = fmt.text(s.eligibility);
      el("d-fuds-status").textContent = fmt.text(s.fuds_status);
      el("d-has-projects").textContent = fmt.text(s.has_projects);
    } else {
      fudsBlock.hidden = true;
    }
  }

  // Universal infrastructure-proximity (from infra-proximity enrichment —
  // computed for every program against HIFLD + Census TIGER).
  setMileCell("d-transmission-mi", s.transmission_mi);
  setMileCell("d-rail-mi", s.rail_mi);
  setMileCell("d-highway-mi", s.highway_mi);
  // EPA RE-Powering qualitative indicators (Superfund-only — only present
  // for the ~1.9k sites the EPA Redevelopment mapper covers).
  el("d-near-elec").textContent = fmt.text(s.near_electric_transmission);
  el("d-near-hwy").textContent = fmt.text(s.near_highway);
  el("d-near-rr").textContent = fmt.text(s.near_railroad);
  el("d-near-water").textContent = fmt.text(s.near_water_supply);
  el("d-near-ww").textContent = fmt.text(s.near_wastewater);
  el("d-pop-density").textContent = fmt.text(s.pop_density);
  el("d-dc-candidate").textContent = s.data_center_reuse_candidate === true ? "Yes" : s.data_center_reuse_candidate === false ? "No" : "—";

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

  // Populate owner if available (FUDS provides current_owner; future
  // connectors may add ACRES PPF, Regrid parcel, etc.). The source label
  // sits below so users can cite the upstream feed.
  const ownerEl = document.getElementById("d-owner");
  if (ownerEl) {
    ownerEl.textContent = s.current_owner || "Not available";
    ownerEl.className = s.current_owner ? "" : "muted-cell";
  }
  const ownerSrcEl = document.getElementById("d-owner-source");
  if (ownerSrcEl) {
    if (s.current_owner && s.current_owner_source) {
      ownerSrcEl.textContent = s.current_owner_source;
      ownerSrcEl.className = "";
    } else {
      ownerSrcEl.textContent = "—";
      ownerSrcEl.className = "muted-cell";
    }
  }

  renderDocuments(s);
  renderEnforcement(s);
  renderSummary(s);
  resetDetailTabs();

  const profile = el("d-profile");
  if (s.profile_url) {
    profile.href = s.profile_url;
    const profileLabels = { brownfield: "ACRES property profile", fuds: "FUDS property profile", brac: "Installation profile" };
    profile.textContent = profileLabels[s.program] || "EPA Site Profile";
    profile.style.display = "";
  } else {
    profile.style.display = "none";
  }

  const detail = el("detail");
  // Program-color top stripe — set as a CSS var so the ::before reads it
  // without inline-style churn on every reflow.
  detail.style.setProperty("--detail-stripe", colorForRecord(s));
  detail.hidden = false;
  detail.setAttribute("aria-hidden", "false");

  if (!fromMap && s.lat != null && s.lon != null) {
    map.setView([s.lat, s.lon], Math.max(map.getZoom(), 8), { animate: true });
    markersById.get(id)?.openTooltip();
  }
  syncUrl();
}

// Render the per-site federal documents block. Hidden when the site has
// none — coverage grows over time as the epa-superfund-docs connector
// processes more sites in batches. The "all documents on EPA" link always
// resolves so users can pivot to the canonical SEMS docdata page even when
// our cached enrichment is empty.
function renderDocuments(s) {
  const block = el("d-docs-block");
  if (!block) return;
  const docs = Array.isArray(s.documents) ? s.documents : [];
  const list = el("d-docs");
  const countEl = el("d-docs-count");
  const moreLink = el("d-docs-more");

  if (!docs.length) {
    block.hidden = true;
    list.innerHTML = "";
    return;
  }

  block.hidden = false;
  countEl.textContent = `(${docs.length})`;

  list.innerHTML = docs
    .map((d) => {
      const date = d.date ? `<span class="doc-date">${escapeHtml(d.date)}</span>` : "";
      const cat = d.category ? `<span class="doc-cat">${escapeHtml(d.category)}</span>` : "";
      const meta = [date, cat].filter(Boolean).join(" · ");
      const sizeBits = [d.pages ? `${d.pages} pp` : null, d.size].filter(Boolean).join(", ");
      const sizeStr = sizeBits ? ` <span class="doc-size">(${escapeHtml(sizeBits)})</span>` : "";
      const safeTitle = escapeHtml(d.title || `Document ${d.doc_id}`);
      const safeUrl = escapeAttr(d.url || "#");
      return `<li><a href="${safeUrl}" target="_blank" rel="noopener">${safeTitle}</a>${sizeStr}${meta ? `<div class="doc-meta">${meta}</div>` : ""}</li>`;
    })
    .join("");

  // Direct deep-link to the EPA SEMS Site Documents & Data page for full coverage.
  if (s.program === "superfund" && (s.epa_id || s.id)) {
    moreLink.href = `https://cumulis.epa.gov/supercpad/SiteProfiles/index.cfm?fuseaction=second.docdata&id=${encodeURIComponent(s.epa_id || s.id)}`;
    moreLink.style.display = "";
  } else {
    moreLink.style.display = "none";
  }
}

// Render the EPA ECHO enforcement block. Hidden when the site has no
// `enforcement` enrichment on file. Coverage grows as the epa-echo
// connector backfills more sites in batches.
function renderEnforcement(s) {
  const block = el("d-echo-block");
  if (!block) return;
  const enf = s.enforcement;
  if (!enf || typeof enf !== "object") {
    block.hidden = true;
    return;
  }
  block.hidden = false;
  const setCell = (id, value, { violation = false } = {}) => {
    const node = el(id);
    if (!node) return;
    if (value == null || value === "") {
      node.textContent = "Not available";
      node.classList.add("muted-cell");
      node.classList.remove("violation");
    } else {
      node.textContent = value;
      node.classList.remove("muted-cell");
      node.classList.toggle("violation", !!violation);
    }
  };
  setCell("d-echo-compliance", enf.current_compliance);
  setCell(
    "d-echo-insp",
    enf.inspections_5yr != null ? enf.inspections_5yr.toLocaleString() : null,
  );
  // Formal enforcement actions render as a violation when nonzero — the
  // single highest-signal due-diligence flag we surface.
  const formal = enf.formal_actions_5yr;
  setCell(
    "d-echo-formal",
    formal != null ? formal.toLocaleString() : null,
    { violation: typeof formal === "number" && formal > 0 },
  );
  setCell(
    "d-echo-informal",
    enf.informal_actions_5yr != null ? enf.informal_actions_5yr.toLocaleString() : null,
  );
  const pen = enf.penalties_5yr_usd;
  setCell(
    "d-echo-penalties",
    pen != null
      ? "$" + Math.round(pen).toLocaleString()
      : null,
    { violation: typeof pen === "number" && pen > 0 },
  );
  setCell("d-echo-last-viol", enf.last_violation_date);
  setCell("d-echo-last-insp", enf.last_inspection_date);
  setCell("d-echo-last-formal", enf.last_formal_action_date);
  setCell(
    "d-echo-programs",
    Array.isArray(enf.programs) && enf.programs.length ? enf.programs.join(", ") : null,
  );
  const dfr = el("d-echo-dfr");
  if (dfr) {
    if (enf.dfr_url) {
      dfr.href = enf.dfr_url;
      dfr.style.display = "";
    } else if (enf.registry_id) {
      dfr.href = `https://echo.epa.gov/detailed-facility-report?fid=${encodeURIComponent(enf.registry_id)}`;
      dfr.style.display = "";
    } else {
      dfr.style.display = "none";
    }
  }
}

// Render the AI-generated summary card. Splits the model output into
// paragraphs and renders each as a <p> so styling can target them. Shows
// the empty-state message when the site hasn't been summarized yet.
function renderSummary(s) {
  const empty = el("d-summary-empty");
  const body = el("d-summary-body");
  const meta = el("d-summary-meta");
  if (!body || !empty || !meta) return;
  if (!s.summary) {
    empty.hidden = false;
    body.hidden = true;
    body.innerHTML = "";
    meta.hidden = true;
    meta.textContent = "";
    return;
  }
  empty.hidden = true;
  body.hidden = false;
  // Model output: paragraphs separated by blank lines. Defensive fallback
  // to a single paragraph if the model emitted no double newlines.
  const paragraphs = String(s.summary)
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
  body.innerHTML = (paragraphs.length ? paragraphs : [s.summary])
    .map((p) => `<p>${escapeHtml(p)}</p>`)
    .join("");
  if (s.summary_meta && (s.summary_meta.model || s.summary_meta.generated_at)) {
    const bits = [];
    if (s.summary_meta.model) bits.push(s.summary_meta.model);
    if (s.summary_meta.generated_at) bits.push(`generated ${s.summary_meta.generated_at.slice(0, 10)}`);
    meta.textContent = "AI-generated · " + bits.join(" · ");
    meta.hidden = false;
  } else {
    meta.textContent = "";
    meta.hidden = true;
  }
}

function closeDetail() {
  const detail = el("detail");
  detail.hidden = true;
  detail.setAttribute("aria-hidden", "true");
  if (selectedId && tableRowsById.has(selectedId)) {
    tableRowsById.get(selectedId).classList.remove("selected");
  }
  // Marker tooltip (opened by selectSite for off-table selections) was sticking
  // open after the panel closed. Close it explicitly.
  if (selectedId) markersById.get(selectedId)?.closeTooltip();
  selectedId = null;
  syncUrl();
}

// ----- CSV export -----
//
// Curated wide schema. The pre-v1.11.1 export was 12 columns (id, program,
// name, state, city, county, acreage, npl_status_code, npl_status, lat, lon,
// profile_url) which silently dropped every enrichment field — users
// downloading the filtered set lost the FUDS owner labels, the universal
// infra distances, the data-center reuse flag, and the entire ECHO
// enforcement summary. Today's schema mirrors what the detail panel surfaces.
//
// `key` supports dotted paths (`enforcement.formal_actions_5yr`) and a
// `.length` shortcut for array sizes (`documents.length`). Empty fields stay
// empty so spreadsheet column widths stay stable across exports.
const CSV_COLUMNS = [
  // Identity
  { key: "id", label: "id" },
  { key: "program", label: "program" },
  { key: "name", label: "name" },
  // Location
  { key: "address", label: "address" },
  { key: "city", label: "city" },
  { key: "county", label: "county" },
  { key: "state", label: "state" },
  { key: "zip", label: "zip" },
  { key: "lat_real", label: "lat", fallback: "lat" },
  { key: "lon_real", label: "lon", fallback: "lon" },
  // Scale + status
  { key: "acreage", label: "acreage" },
  { key: "epa_id", label: "epa_id" },
  { key: "npl_status_code", label: "npl_status_code" },
  { key: "npl_status", label: "npl_status" },
  { key: "federal_facility", label: "federal_facility" },
  { key: "region", label: "epa_region" },
  // FUDS-specific
  { key: "eligibility", label: "fuds_eligibility" },
  { key: "fuds_status", label: "fuds_status" },
  { key: "has_projects", label: "fuds_has_projects" },
  { key: "congressional_district", label: "congressional_district" },
  // BRAC-specific
  { key: "component", label: "brac_component" },
  // Owner provenance
  { key: "current_owner", label: "current_owner" },
  { key: "current_owner_source", label: "current_owner_source" },
  // Universal infra-proximity (v1.10)
  { key: "transmission_mi", label: "transmission_mi" },
  { key: "rail_mi", label: "rail_mi" },
  { key: "highway_mi", label: "highway_mi" },
  // EPA RE-Powering qualitative (Superfund-only, v1.7)
  { key: "near_electric_transmission", label: "near_electric_transmission" },
  { key: "near_water_supply", label: "near_water_supply" },
  { key: "near_wastewater", label: "near_wastewater" },
  { key: "pop_density", label: "pop_density" },
  { key: "data_center_reuse_candidate", label: "dc_reuse_candidate" },
  // ECHO enforcement (v1.11)
  { key: "enforcement.inspections_5yr", label: "echo_inspections_5yr" },
  { key: "enforcement.formal_actions_5yr", label: "echo_formal_actions_5yr" },
  { key: "enforcement.informal_actions_5yr", label: "echo_informal_actions_5yr" },
  { key: "enforcement.penalties_5yr_usd", label: "echo_penalties_5yr_usd" },
  { key: "enforcement.current_compliance", label: "echo_compliance" },
  { key: "enforcement.last_violation_date", label: "echo_last_violation_date" },
  { key: "enforcement.last_inspection_date", label: "echo_last_inspection_date" },
  { key: "enforcement.last_formal_action_date", label: "echo_last_formal_action_date" },
  // Documents enrichment (v1.9)
  { key: "documents.length", label: "doc_count" },
  // Source link
  { key: "profile_url", label: "profile_url" },
];

function pickCsvField(obj, key) {
  // ".length" shortcut → length of the array at the dotted path.
  if (key.endsWith(".length")) {
    const v = pickCsvField(obj, key.slice(0, -".length".length));
    return Array.isArray(v) ? v.length : 0;
  }
  if (!key.includes(".")) return obj == null ? null : obj[key];
  let cur = obj;
  for (const part of key.split(".")) {
    if (cur == null) return null;
    cur = cur[part];
  }
  return cur;
}

function csvCell(s, col) {
  let v = pickCsvField(s, col.key);
  if ((v == null || v === "") && col.fallback) v = pickCsvField(s, col.fallback);
  if (v == null) return "";
  if (typeof v === "boolean") return v ? "true" : "false";
  return v;
}

function wireExportCsv() {
  el("export-csv").addEventListener("click", () => {
    const rows = [CSV_COLUMNS.map((c) => c.label)];
    for (const s of sites) {
      if (!siteMatchesFilters(s)) continue;
      rows.push(CSV_COLUMNS.map((c) => csvCell(s, c)));
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
  // ID provided but not loaded yet. ACRES, FUDS, and BRAC all lazy-load
  // post-Superfund first paint — wait for any in-flight program-data
  // fetch to settle before declaring the ID unknown. (Pre-fix: only
  // ACRES was checked, so direct navigation to ?site=FUDS-XXX or
  // ?site=BRAC-XXX showed a premature "not found" toast while those
  // datasets were still streaming in.)
  const pending = [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise]
    .filter(Boolean);
  if (pending.length) {
    Promise.allSettled(pending).then(() => {
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
    const isDefaultProgram = filterState.programs.size === PROGRAM_LEGEND.length &&
      PROGRAM_LEGEND.every((p) => filterState.programs.has(p.program));
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

// Render a distance-in-miles cell, swapping the muted-cell class so populated
// values look like real data instead of "Not available" placeholder text.
function setMileCell(id, value) {
  const node = el(id);
  if (!node) return;
  if (value == null) {
    node.textContent = "Not available";
    node.classList.add("muted-cell");
  } else {
    node.textContent = fmt.miles(value);
    node.classList.remove("muted-cell");
  }
}
