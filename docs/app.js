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
const OPP_ZONE_URL = "data/opportunity-zone.json";
const TRIBAL_AREAS_URL = "data/tribal-areas.json";
const CLIMATE_ZONE_URL = "data/climate-zone.json";
const ISO_RTO_URL = "data/iso-rto.json";
const ECHO_DATA_URL = "data/epa-echo.json";
const PARCEL_OWNER_URL = "data/parcel-owner.json";
const AI_SUMMARY_URL = "data/ai-summary.json";
const ACRES_CLEANUP_URL = "data/acres-cleanup.json";
const RETIRED_PLANTS_URL = "data/eia-retired-plants.json";
const REFERENCE_CAMPUSES_URL = "data/reference-campuses.json";
const RETIRED_INDUSTRIAL_URL = "data/retired-industrial.json";
const PLANNED_RETIREMENTS_URL = "data/planned-retirements.json";
const PLANNED_RETIRE_PROX_URL = "data/planned-retirements-proximity.json";
const COORD_QUALITY_URL = "data/coord-quality.json";
const IRA_EC_URL = "data/ira-energy-community.json";
const AP1000_SITES_URL = "data/ap1000-sites.json";
const NUCLEAR_SITES_URL = "data/nuclear-civilian-sites.json";
const NUCLEAR_BROWNFIELD_PROX_URL = "data/nuclear-brownfield-proximity.json";
const MICRO_FLEET_URL = "data/microreactor-fleet.json";
const JANUS_NEPA_URL = "data/janus-nepa.json";
const FEMA_NRI_URL = "data/fema-nri.json";
const COAL_CONVERSIONS_URL = "data/coal-conversions.json";
const COAL_PROX_URL = "data/coal-conversions-proximity.json";
const FEDERAL_CLEAN_ENERGY_URL = "data/federal-clean-energy.json";
const HANFORD_E2E_URL = "data/hanford-e2e.json";
const COAL_NEPA_URL = "data/coal-nepa.json";
const PORT_PROXIMITY_URL = "data/port-proximity.json";
const PORTS_URL = "data/ports.json";
const WATER_PROXIMITY_URL = "data/water-proximity.json";
const NICKEL_ANCHOR_PROX_URL = "data/nickel-anchor-proximity.json";
const NICKEL_ANCHORS_URL = "data/nickel-anchors.json";
const SHIPYARDS_URL = "data/shipyards.json";
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
const MIN_ZOOM = 2;

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
// Thresholds tightened 2026-05-07: with ~47k markers across all four programs,
// the previous 1/8 at zoom ≤4 still left ~5,900 markers on the canvas and
// pan latency was perceptibly degraded. 1/16 keeps ~3k visible, which still
// reads as a continuous national density layer at zoom 4.
const DECIMATION = [
  { maxZoom: 4, keepEvery: 16 },
  { maxZoom: 5, keepEvery: 8 },
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
const ISO_RTO_LABELS = {
  CAISO: "CAISO",
  ERCOT: "ERCOT",
  "ISO-NE": "ISO-NE",
  MISO: "MISO",
  NYISO: "NYISO",
  PJM: "PJM",
  SPP: "SPP",
  "non-RTO": "Non-RTO",
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
  // to 0.1 — matches the connector's emit precision. Values < 0.05 round to
  // 0.0 in the source data; render as "Adjacent" instead of "0.0 mi" / "<0.1 mi"
  // so passing-through-the-boundary cases read as a feature, not a bug.
  miles: (n) => {
    if (n == null) return "Not available";
    if (n < 0.05) return "Adjacent";
    const rounded = Math.round(n * 10) / 10;
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

// ----- Data-center scoring (Tier 0, v0) -----
//
// Concrete thresholds — see `backlog.md` "Data-center suitability scoring"
// for the source citations (EPA Brownfields, Datacenters.com, EPA RE-Powering,
// USPE Global, Equinix, ASHRAE 169). Each tier is the minimum bar a site must
// meet to qualify; `compute_dc_score()` returns the highest tier matched.
//
// Ladder rungs (smallest → largest):
//   - "edge"        ≥ 5 ac, transmission ≤1 mi (any voltage)
//   - "colo"        ≥ 25 ac, transmission ≤1 mi at ≥138 kV
//   - "hyperscale"  ≥ 100 ac (matches EPA), transmission ≤1 mi at ≥230 kV
//   - "mega"        ≥ 500 ac, transmission ≤1 mi at ≥500 kV
//
// V0 of the rubric uses only fields already on disk (`acreage`,
// `transmission_mi`, `transmission_kv`, `near_water_supply`); future Tier 1+
// data sources will tighten the criteria (gas pipeline proximity, RTO region,
// flood zone, SDC, etc.). Sites with null transmission_kv but populated
// transmission_mi can only score up to "edge" — ≥138 kV is unverified.
const DC_TIERS = [
  { id: "mega",       label: "500+ acres · 500 kV nearby", minAcres: 500, maxTxMi: 1.0, minKv: 500, color: "var(--readiness-ready)" },
  { id: "hyperscale", label: "100+ acres · 230 kV nearby", minAcres: 100, maxTxMi: 1.0, minKv: 230, color: "var(--readiness-ready)" },
  { id: "colo",       label: "25+ acres · 138 kV nearby", minAcres: 25, maxTxMi: 1.0, minKv: 138, color: "var(--accent)" },
  { id: "edge",       label: "5+ acres · mapped line nearby", minAcres: 5, maxTxMi: 1.0, minKv: 0, color: "var(--accent)" },
];
const DC_TIER_LABEL = Object.fromEntries(DC_TIERS.map((t) => [t.id, t.label]));
// Persona presets surface the same ladder as one-tap filters in the strip.
// `?dc_tier=hyperscale` round-trips through the URL; `Reset` clears it.
const PERSONA_PRESETS = [...DC_TIERS].slice().reverse(); // edge → mega for UI

function computeDcScore(s) {
  if (!s || s.acreage == null) return null;
  const acres = s.acreage;
  const tx = s.transmission_mi;
  const kv = s.transmission_kv;
  if (tx == null || tx > 1.0) return null;
  // Iterate from highest tier down; return the first that matches. Tiers are
  // intentionally non-strict on `minKv: 0` (edge) so a transmission_mi-only
  // record without a kV signal still qualifies for edge.
  for (const tier of DC_TIERS) {
    if (acres < tier.minAcres) continue;
    if (tier.minKv > 0) {
      if (kv == null) continue;
      if (kv < tier.minKv) continue;
    }
    return tier.id;
  }
  return null;
}

// ----- State data-center tax incentives lookup (Tier 0, static) -----
//
// Audit history:
//   2026-05-07 — initial table compiled from NCSL / Tax Foundation / NAIOP
//                aggregator round-ups. URLs pointed at top-level state EDA /
//                DOR landing pages (not citation-grade).
//   2026-05-08 (pass 1) — accuracy audit on 16 high-stakes rows. ~18% of rows
//                had material factual errors; ~16% had stale status flags
//                driven by 2025-2026 reform activity. Corrections: NC
//                ($150M→$75M two-program conflation), OH (added $1.5M/yr
//                payroll floor), CT (added $50M EZ / $200M general
//                thresholds), FL (restricted → under_reform; HB 7031 raised
//                15→100 MW Aug 2025), IA (expanded → under_reform; 2025
//                rollback w/ 10-15yr cap), MN (Tier 2 → Tier 3; electricity
//                exemption repealed 2025), UT (Tier 3 → Tier 2; ≥150k sq ft
//                exemption since 2020), OK (active → under_reform; 2021
//                excluded new DCs from property-tax exemption), TX (per-cert
//                10-15yr term noted), AR (threshold $500M→$100M per Act 548),
//                CO (added pending_legislation flag for HB 26-1030). NE/AR/
//                ID/ND `needs_verification` flags removed — all confirmed real.
//   2026-05-08 (pass 2) — backfill of the 35 remaining `verified_at: null`
//                rows against state DOR / EDC / statute. Material corrections:
//                TN ($250M→$100M, +15 jobs per Tenn. Code § 67-6-206(c) /
//                SB 2537 of 2016); IL (sunset 2029→2056, program-level vs
//                cert-level); WI ($50M / pop-tiered, was null); IN ($25M /
//                pop-tiered, was null); PA ($75M / 25 jobs, was null);
//                MD ($5M statewide vs $2M Tier-1-Area-only); MS ($20M / 20
//                jobs per SB 3106 of 2024, was $50M / 50); KY ($100M / HB
//                775 of 2025, was null); WV ($2.5M / 10 jobs per HB 4013
//                of 2026, was generic "expanded"); WA (35 jobs / 20,000 sq
//                ft / sunset 2035, was null); WY (sunset 2042 per 2025
//                extension, status `under_reform` → `active`); NY (Tier 3
//                → Tier 2 — has had Internet DC Sales Tax Exemption for
//                years per NY Tax Law § 1115(a)(35)(37)); ME (Tier 3 →
//                Tier 2 — 36 M.R.S. § 2021 active program); AK (status
//                "none" → "no_state_sales_tax" — AK has no state sales tax).
//                Confirmed-correct rows (just bumped verified_at): AZ, NV,
//                SC, AL, LA, KS, OR, MT, MA, DE, NH, SD, VT, RI, HI, NM,
//                CA, NJ, DC.
//
// `verified_at` field on each row tracks freshness:
//   - "YYYY-MM-DD"  = audited against a primary source (statute, DOR page,
//                     state EDC, or NCSL snapshot row) on that date
//   - null          = inherited from the 2026-05-07 aggregator pass; not
//                     re-verified. Treat the values as indicative, not
//                     citation-grade. Future audits should prioritize these.
//
// Tiers:
//   1 = broad sales-tax exemption + active policy + competitive power
//   2 = some incentives, reasonable cost
//   3 = no/minimal incentive, high power, restrictive politics, or no income tax
//
// `status` values: "active" | "expanded" | "under_reform" | "restricted" |
//                  "restrictive" | "none" | "no_state_sales_tax" |
//                  "partially_repealed" | "pending_legislation"
const STATE_DC_INCENTIVES = {
  // Tier 1 — most attractive
  VA: { tier: 1, program: "Data Center Sales & Use Tax Exemption", min_investment_usd: 150_000_000, min_jobs: 50, sunset: 2035, status: "under_reform", verified_at: "2026-05-08", url: "https://www.vedp.org/incentive/data-center-retail-sales-use-tax-exemption" },
  TX: { tier: 1, program: "Qualified Data Center (10-15yr per cert)", min_investment_usd: 200_000_000, min_jobs: 20, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://comptroller.texas.gov/taxes/data-centers/" },
  GA: { tier: 1, program: "Data Center Sales & Use Tax Exemption", min_investment_usd: 100_000_000, min_jobs: 20, sunset: 2033, status: "active", verified_at: "2026-05-08", url: "https://dor.georgia.gov/data-centers-sales-use-tax-exemption-aggregate-expenditures-county" },
  IA: { tier: 1, program: "Data Center Sales & Use Tax Exemption", min_investment_usd: 1_000_000, min_jobs: null, sunset: null, status: "under_reform", verified_at: "2026-05-08", url: "https://www.ncsl.org/fiscal/policy-snapshot-data-center-incentives" },
  OH: { tier: 1, program: "Data Center Tax Abatement ($1.5M/yr payroll required)", min_investment_usd: 100_000_000, min_jobs: null, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://codes.ohio.gov/ohio-revised-code/section-122.175" },
  AZ: { tier: 3, program: "Computer Data Center exemption (A.R.S. § 41-1519) PAUSED for new applicants 2026-07-01 → 2029-06-30; existing agreements honored", min_investment_usd: 25_000_000, min_jobs: null, sunset: null, status: "paused", verified_at: "2026-07-26", url: "https://azcapitoltimes.com/news/2026/07/09/data-centers-dominated-2026-session-lawmakers-answered-with-3-year-tax-incentive-pause/" },
  NV: { tier: 1, program: "Data Center Abatement (10yr / 20yr tiers, NRS § 360.754)", min_investment_usd: 25_000_000, min_jobs: 10, sunset: 2056, status: "active", verified_at: "2026-05-08", url: "https://law.justia.com/codes/nevada/chapter-360/statute-360-754/" },
  NC: { tier: 1, program: "Qualifying Data Center Sales Tax Exemption", min_investment_usd: 75_000_000, min_jobs: null, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://edpnc.com/incentives/data-centers-sales-use-tax-exemptions/" },
  TN: { tier: 1, program: "Qualified Data Center Sales Tax Exemption (Tenn. Code § 67-6-206(c))", min_investment_usd: 100_000_000, min_jobs: 15, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://www.tn.gov/content/dam/tn/revenue/documents/forms/sales/f1325001.pdf" },

  // Tier 2 — moderate
  IL: { tier: 3, program: "Data Center Investment Program PAUSED for new applications 2026-07-01 → 2028-07-01 (Gov. directive; existing agreements honored)", min_investment_usd: 250_000_000, min_jobs: 20, sunset: 2056, status: "paused", verified_at: "2026-07-26", url: "https://capitolnewsillinois.com/news/gov-jb-pritzker-to-suspend-tax-breaks-for-data-centers-urging-more-discussion/" },
  MI: { tier: 2, program: "Enterprise DC Sales & Use Tax Exemption (sunset 2065 for brownfield sites)", min_investment_usd: 250_000_000, min_jobs: 30, sunset: 2050, status: "expanded", verified_at: "2026-05-08", url: "https://legislature.mi.gov/documents/2023-2024/billanalysis/Senate/htm/2023-SFA-0237-U.htm" },
  WI: { tier: 2, program: "Qualified DC Sales Tax Exemption (pop-tiered, $50M floor, Wis. Stat. § 238.40)", min_investment_usd: 50_000_000, min_jobs: null, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://wedc.org/programs/data-center-sales-and-use-tax-exemption/" },
  IN: { tier: 2, program: "DC Gross Retail & Use Tax Exemption (county-pop tiered, $25M floor, IC 6-2.5-15-16)", min_investment_usd: 25_000_000, min_jobs: null, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://iedc.in.gov/indiana-advantages/investments/data-center-sales-tax-exemption/overview" },
  OK: { tier: 2, program: "DC Equipment Sales Tax Exemption (out-of-state revenue gated)", min_investment_usd: null, min_jobs: null, sunset: null, status: "under_reform", verified_at: "2026-05-08", url: "https://stateline.org/2026/02/24/data-center-tax-breaks-are-on-the-chopping-block-in-some-states/" },
  PA: { tier: 2, program: "Computer DC Equipment Sales & Use Tax Exemption ($75M / 25 jobs floor)", min_investment_usd: 75_000_000, min_jobs: 25, sunset: null, status: "under_reform", verified_at: "2026-05-08", url: "https://www.pa.gov/agencies/revenue/incentives-credits-and-programs/computer-data-center-equipment-program" },
  MD: { tier: 2, program: "Data Center Maryland ($5M statewide / $2M Tier-1-Area)", min_investment_usd: 5_000_000, min_jobs: 5, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://commerce.maryland.gov/fund/data-center-maryland-sales-and-use-tax-exemption-incentive-program" },
  SC: { tier: 2, program: "Certified DC Sales & Use Tax Exemption (SC Code § 12-36-2120(79))", min_investment_usd: 50_000_000, min_jobs: 25, sunset: 2032, status: "active", verified_at: "2026-05-08", url: "https://law.justia.com/codes/south-carolina/title-12/chapter-36/section-12-36-2120/" },
  MS: { tier: 2, program: "DC Sales Tax Exemption (SB 3106 of 2024)", min_investment_usd: 20_000_000, min_jobs: 20, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://www.salestaxinstitute.com/resources/mississippi-amends-and-creates-data-center-exemptions" },
  AL: { tier: 2, program: "DC Tax Abatement (30yr tier per HB 399 of 2025)", min_investment_usd: 400_000_000, min_jobs: 20, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://www.revenue.alabama.gov/tax-incentives/chapter-9b-abatements/" },
  LA: { tier: 2, program: "DC Sales & Use Tax Rebate (Act 730 of 2024, 20yr + 10yr renewal)", min_investment_usd: 200_000_000, min_jobs: 50, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://www.opportunitylouisiana.gov/data-center" },
  MO: { tier: 2, program: "New / Existing DC Exemption (RSMo § 144.810, tiered)", min_investment_usd: 25_000_000, min_jobs: 10, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://revisor.mo.gov/main/OneSection.aspx?section=144.810" },
  NE: { tier: 2, program: "ImagiNE Nebraska (DC tier: $25M / 10 jobs entry → $400M premium)", min_investment_usd: 25_000_000, min_jobs: 10, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://revenue.nebraska.gov/sites/default/files/doc/incentives/annual_report/ImagiNE_Key_Employer_FYE_6-30-25_Final_Copy.pdf" },
  KS: { tier: 2, program: "SB98 DC Sales & Use Tax Exemption (20yr, eff. July 2025)", min_investment_usd: 250_000_000, min_jobs: 20, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://www.kansascommerce.gov/program/business-incentives-and-services/sb-98-data-center-sales-tax-exemption/" },
  KY: { tier: 2, program: "DC Sales & Use Tax Exemption (HB 775 of 2025; up to 50yr at $450M+)", min_investment_usd: 100_000_000, min_jobs: null, sunset: null, status: "expanded", verified_at: "2026-05-08", url: "https://www.stites.com/resources/client-alerts/kentucky-vastly-expands-data-center-tax-incentives/" },
  WV: { tier: 2, program: "Mountaineer Flexible Tax Credit (HB 4013 of 2026)", min_investment_usd: 2_500_000, min_jobs: 10, sunset: null, status: "expanded", verified_at: "2026-05-08", url: "https://wvpolicy.org/house-moving-tax-credit-bill-with-big-tax-break-for-new-data-centers/" },
  AR: { tier: 2, program: "Qualified DC Sales Tax Exemption (Act 548 of 2025)", min_investment_usd: 100_000_000, min_jobs: null, sunset: null, status: "expanded", verified_at: "2026-05-08", url: "https://www.salestaxinstitute.com/resources/arkansas-data-center-tax-exemption-expansion-2025" },
  WA: { tier: 2, program: "Rural DC Sales Tax Exemption (≥20,000 sq ft, RCW 82.08.986)", min_investment_usd: null, min_jobs: 35, sunset: 2035, status: "active", verified_at: "2026-05-08", url: "https://dor.wa.gov/forms-publications/publications-subject/tax-topics/data-centers-sales-and-use-tax-exemption-eligibility" },
  OR: { tier: 2, program: "Long-Term Rural Enterprise Zone (15yr property-tax abatement)", min_investment_usd: null, min_jobs: null, sunset: null, status: "no_state_sales_tax", verified_at: "2026-05-08", url: "https://www.oregon.gov/biz/programs/enterprisezones/long-termruralenterprisezone/pages/default.aspx" },
  MT: { tier: 2, program: "Class 17 Property Tax Reduction (Mont. Code § 15-6-162)", min_investment_usd: 50_000_000, min_jobs: null, sunset: null, status: "no_state_sales_tax", verified_at: "2026-05-08", url: "https://mca.legmt.gov/bills/mca/title_0150/chapter_0060/part_0010/section_0620/0150-0060-0010-0620.html" },
  WY: { tier: 2, program: "DC Sales & Use Tax Exemption (Tier I $5M / Tier II $50M, Wyo. Stat. § 39-15-105)", min_investment_usd: 5_000_000, min_jobs: null, sunset: 2042, status: "active", verified_at: "2026-05-08", url: "https://www.businesswyoming.com/workforce/workforce-programs/p/item/1775/data-center-sales-tax-exemption" },
  ID: { tier: 2, program: "Data Center Sales Tax Exemption (HB 521 / 2024 refinements)", min_investment_usd: null, min_jobs: null, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://commerce.idaho.gov/incentives/data-center-sales-tax-exemption/" },
  MA: { tier: 2, program: "Qualified DC Sales & Use Tax Exemption (Ch. 238 of 2024, 20yr, ≥100,000 sq ft)", min_investment_usd: 50_000_000, min_jobs: 100, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://www.mass.gov/info-details/notice-regarding-qualified-data-center-tax-exemption" },
  CT: { tier: 2, program: "Data Infrastructure Tax Incentive (≥$50M EZ / $200M general)", min_investment_usd: 200_000_000, min_jobs: null, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://portal.ct.gov/decd/content/business-development/data-infrastructure-administration-and-security/" },
  FL: { tier: 2, program: "DC Sales & Use Tax Exemption (≥100 MW per HB 7031)", min_investment_usd: null, min_jobs: null, sunset: null, status: "under_reform", verified_at: "2026-05-08", url: "https://ryan.com/about-ryan/news-and-insights/2025/florida-hb7031-data-center-tax/" },
  ND: { tier: 2, program: "DC Sales Tax Exemption (≥16,000 sq ft post-2020)", min_investment_usd: null, min_jobs: null, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://www.ncsl.org/fiscal/policy-snapshot-data-center-incentives" },
  UT: { tier: 2, program: "DC Sales & Use Tax Exemption (≥150,000 sq ft, since 2020)", min_investment_usd: null, min_jobs: null, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://www.edcutah.org/recent-news/utah-levels-the-playing-field-for-data-centers-five-questions-for-thomas-wadsworth-of-goed" },
  NY: { tier: 2, program: "Internet Data Center Sales Tax Exemption (NY Tax Law § 1115(a)(35)(37); Form ST-121.5)", min_investment_usd: null, min_jobs: null, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://www.tax.ny.gov/pubs_and_bulls/tg_bulletins/st/internet_data_centers.htm" },
  ME: { tier: 2, program: "Maine Qualified Data Center Refund/Exemption (36 M.R.S. § 2021, ≥20,000 sq ft)", min_investment_usd: null, min_jobs: null, sunset: null, status: "under_reform", verified_at: "2026-05-08", url: "https://www.salestaxsolutions.us/data-center-tax-exemption-states/" },

  // Tier 3 — least attractive
  CA: { tier: 3, program: "None enacted (SB 58 stripped 2025)", min_investment_usd: null, min_jobs: null, sunset: null, status: "restrictive", verified_at: "2026-05-08", url: "https://news.bloombergtax.com/tax-insights-and-commentary/california-data-center-bill-shows-skepticism-of-development-costs" },
  NJ: { tier: 3, program: "None enacted (case-by-case via NJEDA Aspire/ERG)", min_investment_usd: null, min_jobs: null, sunset: null, status: "none", verified_at: "2026-05-08", url: "https://insideclimatenews.org/news/26022026/new-jersey-data-center-tax-break/" },
  NM: { tier: 3, program: "None enacted (case-by-case via LEDA + Industrial Revenue Bonds)", min_investment_usd: null, min_jobs: null, sunset: null, status: "none", verified_at: "2026-05-08", url: "https://www.ncsl.org/fiscal/policy-snapshot-data-center-incentives" },
  CO: { tier: 3, program: null, min_investment_usd: null, min_jobs: null, sunset: null, status: "pending_legislation", verified_at: "2026-05-08", url: "https://coloradonewsline.com/2026/01/21/tax-breaks-for-data-centers-colorado/" },
  MN: { tier: 3, program: null, min_investment_usd: null, min_jobs: null, sunset: null, status: "partially_repealed", verified_at: "2026-05-08", url: "https://www.ncsl.org/fiscal/policy-snapshot-data-center-incentives" },
  DE: { tier: 3, program: null, min_investment_usd: null, min_jobs: null, sunset: null, status: "no_state_sales_tax", verified_at: "2026-05-08", url: "https://taxfoundation.org/location/delaware/" },
  SD: { tier: 3, program: null, min_investment_usd: null, min_jobs: null, sunset: null, status: "none", verified_at: "2026-05-08", url: "https://southdakotasearchlight.com/2026/01/30/clock-is-ticking-on-data-center-incentive-proposal-as-elections-loom/" },
  VT: { tier: 3, program: null, min_investment_usd: null, min_jobs: null, sunset: null, status: "none", verified_at: "2026-05-08", url: "https://accd.vermont.gov/" },
  NH: { tier: 3, program: null, min_investment_usd: null, min_jobs: null, sunset: null, status: "no_state_sales_tax", verified_at: "2026-05-08", url: "https://www.nheconomy.com/" },
  RI: { tier: 3, program: null, min_investment_usd: null, min_jobs: null, sunset: null, status: "none", verified_at: "2026-05-08", url: "https://www.bostonglobe.com/2026/03/12/metro/ri-bills-tax-incentives-data-centers/" },
  AK: { tier: 3, program: null, min_investment_usd: null, min_jobs: null, sunset: null, status: "no_state_sales_tax", verified_at: "2026-05-08", url: "https://taxfoundation.org/location/alaska/" },
  HI: { tier: 3, program: null, min_investment_usd: null, min_jobs: null, sunset: null, status: "none", verified_at: "2026-05-08", url: "https://invest.hawaii.gov/" },
  DC: { tier: 3, program: "QHTC sales-tax exemption repealed 2019; no replacement", min_investment_usd: null, min_jobs: null, sunset: null, status: "none", verified_at: "2026-05-08", url: "https://www.salestaxinstitute.com/resources/district-of-columbia-repeals-sales-tax-exemption-for-qualified-high-technology-companies" },
};

// State data-center REGULATORY climate — the flip side of STATE_DC_INCENTIVES.
// In 2025-26 "Regulation" rose to a Tier-3 site-selection filter (moratorium
// bills, by-right zoning repeals, ratepayer cost-shift laws). This raises
// timeline/cost risk for a DC build and feeds a DC-lens-only score penalty
// (dc-score.js:_regulatoryPenalty) + a "Zoning" Signals badge. Deliberately
// CONSERVATIVE: only states with a documented, currently-live restrictive
// signal are listed — every other state is treated as neutral (no penalty).
// `climate`: "restrictive" (−8) | "cautionary" (−4). Dead/failed bills are
// excluded (e.g. ME's failed veto override, MN's bills died May 2026).
// Sources are 2026 trackers; re-audit quarterly — this space moves monthly.
// See CLAUDE.md "STATE_DC_REGULATION audit history."
const STATE_DC_REGULATION = {
  NY: { climate: "restrictive", note: "Executive Order 62 (2026-07-14) pauses DEC environmental permits for new 50 MW+ hyperscale data centers for up to a year — the first in-force statewide pause; the legislature's 20 MW+ Responsible Data Center Development Act passed both chambers and awaits signature.", verified_at: "2026-07-26", url: "https://www.governor.ny.gov/executive-order/no-62-establishing-temporary-moratorium-data-centers-new-york-while-state-develops" },
  VA: { climate: "cautionary", note: "Downgraded from restrictive 2026-07-26: the statewide moratorium (HB1515) failed and carried to 2027. What's live is friction, not a block — HB153/SB94 require a noise/sound-profile assessment before local rezoning/SUP approval of high-energy-use facilities and HB507 sets generator standards (both eff. 2026-07-01).", verified_at: "2026-07-26", url: "https://www.multistate.us/insider/2026/3/30/virginia-lawmakers-pass-15-data-center-bills-as-tax-exemption-fight-looms" },
  VT: { climate: "cautionary", note: "H.727 (data-center pause) passed tripartisan but died on a failed veto override (2026-05-29); S.205 (10 MW+ pause to July 2030) remains pending in Senate Finance — restriction appetite is clearly live.", verified_at: "2026-07-26", url: "https://legislature.vermont.gov/bill/status/2026/S.205" },
  FL: { climate: "cautionary", note: "SB 484 (eff. 2026-07-01) bars shifting data-center grid costs to other ratepayers AND affirmatively empowers localities to set stricter standards or deny projects outright; the state is otherwise pro-DC.", verified_at: "2026-07-26", url: "https://www.flsenate.gov/Session/Bill/2026/484" },
  // OK removed 2026-07-26 (was restrictive): its enacted law (HB2992) is a
  // cost-causation tariff — the deliberately-excluded category (protective of
  // ratepayers, not a siting block) — and the actual moratorium (SB1488)
  // missed deadlines, dead for 2026. WATCH for next quarter's audit: OK
  // re-attempts; MI statewide bills reintroduced Jun 2026 (no committee
  // action, Gov. opposed); OH AEP 85%-minimum-demand tariff under OMA legal
  // challenge (briefing closed 2026-03-24, decision pending).
};
const TAX_TIER_LABEL = {
  1: "Tier 1 incentive (most attractive)",
  2: "Tier 2 incentive",
  3: "No DC tax incentive",
};
const TAX_STATUS_NOTE = {
  active: "",
  expanded: " · recently expanded",
  under_reform: " · under legislative reform",
  restricted: " · restricted (100 MW+)",
  restrictive: " · restrictive policy",
  partially_repealed: " · partially repealed (2025)",
  pending_legislation: " · DC bill pending",
  paused: " · new applications paused",
  none: "",
  no_state_sales_tax: " · no state sales tax (neutral)",
};

// ----- State -----
let sites = [];
let map, markerLayer, referenceCampusLayer, retiredIndustrialLayer, plannedRetirementLayer, nuclearSiteLayer, coalConversionLayer, federalCleanEnergyLayer, portLayer, shipyardLayer, nickelAnchorLayer;
const markersById = new Map(); // id -> Leaflet marker
const tableRowsById = new Map(); // id -> tr
const sitesById = new Map();
// O(1) program-loaded check. Each ensure*Loaded() bails early when its program
// is already in this set; populated by ingestSites() so the existence check
// doesn't require an O(n) sites.some() scan over up to 47k records.
const loadedPrograms = new Set();
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
  // Data-center suitability tier filter (Tier 0). One of:
  //   "" (any) | "edge" | "colo" | "hyperscale" | "mega"
  // Selecting "hyperscale" filters to sites scoring at hyperscale OR mega
  // (mega is a strict superset). URL state: ?dc_tier=hyperscale.
  dcTier: "",
  // EPA RE-Powering data-center reuse candidate boolean (`s.data_center_reuse_candidate`).
  // Wired from the "Datacenter-ready" KPI cell click-to-filter shortcut.
  // URL state: ?dc_candidate=1. Independent of `dcTier` — Tier 0 score includes
  // sites that aren't EPA-flagged, and EPA flags some sites that don't score.
  dcCandidate: false,
  // Treasury Opportunity Zone boolean. When true, only show sites inside a
  // QOZ (`s.in_opportunity_zone === true`). Wired from the "Show only OZ
  // sites" filter checkbox. URL state: ?oz=1.
  oppZone: false,
  // Regional grid-operator filter. Empty = all. Values come from EIA/HIFLD
  // RTO polygons: CAISO / ERCOT / ISO-NE / MISO / NYISO / PJM / SPP /
  // non-RTO. URL state: ?iso_rto=PJM.
  isoRto: "",
  // Show only sites that are meaningfully "available" for redevelopment:
  // Superfund = NPL deleted, ACRES = cleanup completed, FUDS = eligible +
  // non-federal owner, BRAC = always false (no reliable signal).
  // URL state: ?available=1.
  availableOnly: false,
};

let acresLoadingPromise = null; // de-dup parallel toggles
let fudsLoadingPromise = null;
let bracLoadingPromise = null;
let redevLoadingPromise = null;
let superfundDocsLoadingPromise = null;
let infraLoadingPromise = null;
let oppZoneLoadingPromise = null;
let tribalAreasLoadingPromise = null;
let climateZoneLoadingPromise = null;
let isoRtoLoadingPromise = null;
let echoLoadingPromise = null;
let parcelOwnerLoadingPromise = null;
let summariesLoadingPromise = null;
let acresCleanupLoadingPromise = null;
let retiredPlantsLoadingPromise = null;
let plannedRetireProxLoadingPromise = null;
let coordQualityLoadingPromise = null;
let referenceCampusesLoadingPromise = null;
let retiredIndustrialLoadingPromise = null;
let retiredIndustrialSites = []; // raw payload, for the Retired Sites stats tab
let plannedRetirementsLoadingPromise = null;
let ap1000LoadingPromise = null;
let ap1000Sites = []; // raw payload, for the AP1000 siting tab
let nuclearSitesLoadingPromise = null;
let nuclearSitesLoadFailed = false;   // drives the tab section's error state
let nuclearSitesLoadSettled = false;  // distinguishes "still loading" from "loaded empty"
let nuclearProxFailed = false;        // proximity fetch failed — popups must not claim "none nearby"
let nuclearLoadAttempt = 0;           // generation token: a superseded attempt's late failure must not stamp state
let nuclearCivilianSites = [];        // raw payload, for the Nuclear Siting tab
let nuclearProximityById = new Map(); // nuclear_site_id -> nearby Superfund records
let nuclearMarkersById = new Map();   // nuclear_site_id -> Leaflet marker
let microFleetLoadingPromise = null;
let microFleetLoadFailed = false;     // drives the Microreactors tab error state
let microFleet = null;                // raw payload: vendors, commitments, sectors
let microCommitmentLayer = null;      // ⬣ markers for the 24 sited commitments
let janusNepaLoadingPromise = null;
let janusNepaLoadFailed = false;
let janusNepa = null;                 // PNNL nepa-mcp screen for 9 Army sites
let janusNepaLayer = null;            // selected site's lazy GeoJSON overlay
let hanfordLoadingPromise = null;
let hanfordLoadFailed = false;        // drives the Hanford tab error state
let hanfordData = null;               // the E2E dossier payload (9 parcels)
let hanfordParcelLayer = null;        // ▣ markers for the named land units
let hanfordNepaLayer = null;          // selected parcel's lazy GeoJSON overlay
let coalConversionsLoadingPromise = null;
let coalConversionsSettled = false;     // a load completed (even if empty)
let coalConversionsLoadFailed = false;  // last attempt errored — retryable
let coalProxLoadingPromise = null;
let federalCleanEnergyLoadingPromise = null;
let coalConversionAssets = [];
const coalMarkersByName = new Map();
let coalNepaLoadingPromise = null;
let coalNepaLoadFailed = false;   // fetch errored — drawer offers retry
let coalNepaByPlant = null;       // null = not loaded yet; Map when settled
let iraEcLoadingPromise = null;
let femaNriLoadingPromise = null;
let portProximityLoadingPromise = null;
let waterProximityLoadingPromise = null;
let nickelAnchorProxLoadingPromise = null;
let nickelAnchorsLoadingPromise = null;
let portsLoadingPromise = null;
let shipyardsLoadingPromise = null;

// Programmatic ready signal so UAT / Playwright / agent automation can wait
// on a stable event instead of polling network responses. Fires once after
// Superfund first paint AND, if brownfields are enabled, after the chunked
// ACRES marker hydration completes.
function markAppReady() {
  if (!lazyLoadsSettled || window.__APP_READY__) return;
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
// The single "last refreshed" readout on the page — lives next to the
// title. Used to be repeated in the hero, the footer, AND the tagline;
// three dates in three places invited drift and was visual noise, so this
// is now the only one (2026-08-24).
function setHeroRefresh(dateStr) {
  if (!dateStr || dateStr === "—") return;
  const topbarEl = el("topbar-refresh");
  if (topbarEl) topbarEl.textContent = `Compiled ${dateStr}`;
}

// Tracks the freshest `generated_at` across EVERY data file the page loads —
// the eager sites.json plus all lazy program / enrichment files — and keeps
// the max. Each load path reports its payload's generated_at here, so the
// hero, footer, and subtitle reflect the most recent refresh and tick forward
// as fresher files land after first paint. The core Superfund set and the
// enrichment layers (docs, AI summaries, infra, …) refresh on independent
// cadences; pinning the displayed date to sites.json alone understated
// freshness whenever an enrichment file was newer. Basemap files
// (us-states / us-counties) carry no generated_at and are ignored.
let _freshestRefreshTs = -Infinity;
// Per-data-file as-of dates, keyed by the file's URL. Feeds the
// "Sources & evidence" panel so each claim reports when ITS file was
// refreshed rather than the global max across all files.
window.__sourceDates = {};
function recordRefreshDate(generatedAt, sourceFile) {
  if (!generatedAt) return;
  // Per-file as-of dates. The hero/footer show the freshest date across all
  // files, but the evidence panel needs to say when EACH claim was pulled —
  // infra-proximity and epa-superfund-docs refresh on different cadences,
  // so one global date would misdate most rows.
  if (sourceFile) window.__sourceDates[sourceFile] = fmt.date(generatedAt);
  const ts = Date.parse(generatedAt);
  if (isNaN(ts) || ts <= _freshestRefreshTs) return;
  _freshestRefreshTs = ts;
  const refreshed = fmt.date(generatedAt);
  window.__refreshedAt = refreshed;
  setHeroRefresh(refreshed);
  // Re-render the subtitle so its "· refreshed <date>" suffix follows the new
  // freshest date — enrichment loaders don't otherwise call updateMetaText.
  // It reads window.__refreshedAt and recomputes per-program counts from the
  // in-memory `sites` array (cheap; fires at most once per data file).
  updateMetaText();
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
  let text = `${total.toLocaleString()} sites`;
  if (parts.length) text += ` (${parts.join(" + ")})`;
  if (loadingLabel) text += ` · loading ${loadingLabel}…`;
  // The refreshed date lives next to the title (#topbar-refresh) — one
  // readout on the page, not repeated here too.
  const node = el("meta");
  if (node) node.textContent = text;
}

// Category rendering is shared by every corpus lens and export.
function evidenceCell(e) {
  return `<span class="evidence-finding" data-status="${escapeAttr(e.status)}">${escapeHtml(e.finding)}</span>`
    + `<span class="evidence-confidence">${e.confidence ? escapeHtml(e.confidence) + " confidence" : "Not assessed"}</span>`;
}
function evidenceDetails(s, lens = "dc") {
  sanitizeGeographicEvidence(s);
  const a = SiteEvidence.assessSite(s, lens);
  const keys = [...SiteEvidence.PRIMARY, "grid_capacity", "water_reliability", "water_rights", "hazards"];
  if (lens === "micro") keys.push("demand", "regulatory");
  if (lens === "nickel") keys.push("feedstock");
  const note = s._evidenceInvalidation ? `<p class="evidence-invalidation">Location changed in the source. ${s._evidenceInvalidation.clear_fields.length} stale fields withheld pending recomputation. <a href="${INVALIDATIONS_URL}" target="_blank" rel="noopener">Change record</a></p>` : s._evidenceValidationUnavailable ? "<p>Coordinate validation unavailable; geographic evidence withheld.</p>" : "";
  return `${note}<div class="evidence-details">${keys.map(k => {
    const e = a[k];
    return `<details class="evidence-category" data-category="${k}"><summary><strong>${escapeHtml(e.label)}</strong> ${evidenceCell(e)}</summary>`
      + `<p>${escapeHtml(e.reason)}</p>${e.sources.map((u,i) => `<a href="${escapeAttr(u)}" target="_blank" rel="noopener">Source${e.sources.length > 1 ? " " + (i+1) : ""} ↗</a>`).join(" · ")}</details>`;
  }).join("")}</div>`;
}
function evidenceNameOrder(a,b) { return String(a.name || a.id).localeCompare(String(b.name || b.id)) || String(a.id).localeCompare(String(b.id)); }
function evidenceRow(s, lens = "dc") {
  sanitizeGeographicEvidence(s);
  const tr = document.createElement("tr"); tr.dataset.id = s.id;
  const a = SiteEvidence.assessSite(s,lens);
  tr.innerHTML = `<td class="cand-name"><button class="site-evidence-open" type="button">${escapeHtml(s.name || s.id)}</button><span class="micro-sub">${escapeHtml([s.city,s.state].filter(Boolean).join(", "))} · ${escapeHtml(PROGRAM_LABEL[s.program] || s.program || "")}</span></td>`
    + SiteEvidence.PRIMARY.map(k => `<td data-category="${k}" data-label="${SiteEvidence.LABELS[k]}">${evidenceCell(a[k])}</td>`).join("");
  tr.addEventListener("click", () => selectSite(s.id,{fromTable:true}));
  return tr;
}
function evidenceCsvColumns(pick = s => s) {
  return Object.keys(SiteEvidence.LABELS).flatMap(key => ["finding","confidence","reason","sources"].map(field => ({
    label: `${key}_${field}`, compute: (row, assessment) => {const e=(assessment || SiteEvidence.assessSite(pick(row)))[key]; return field === "sources" ? e.sources.join(" | ") : e[field] || "Unknown";}
  })));
}

function updateKpiDeck() {
  const pool = tableState?.filtered || sites;
  const set = (id,n) => {if (el(id)) el(id).textContent = fmt.compact(n);};
  set("kpi-total", pool.length); set("kpi-summary-total",pool.length);
  set("kpi-acres",pool.filter(s => s.acreage != null || s.parcel_acreage != null).length);
  set("kpi-dc",pool.filter(s => s.transmission_mi != null || s.substation_mi != null).length);
  set("kpi-hyperscale",pool.filter(s => s.water_gage_mi != null).length);
  set("kpi-generation",pool.filter(s => !!s.fiber_source_url).length);
  set("kpi-summary-dc",pool.filter(s => s.acreage == null && s.parcel_acreage == null).length);
}

// Active-filter chip count on the gear icon. Also updates aria-label on the
// filter button so screen readers know the active count.
function updateFilterChip() {
  let count = 0;
  const active = [];
  if (filterState.q) { count++; active.push(`search "${filterState.q}"`); }
  if (filterState.state) {
    count++;
    const stateLabel = STATE_NAMES[filterState.state] || TERRITORY_NAMES[filterState.state] || filterState.state;
    active.push(`state ${stateLabel}`);
  }
  if (filterState.statuses.size) {
    count += filterState.statuses.size;
    active.push(`NPL ${Array.from(filterState.statuses).join("/")}`);
  }
  if (filterState.minAcreage > 0) {
    count++;
    const min = Math.round(Math.pow(10, filterState.minAcreage));
    active.push(`≥${min.toLocaleString()} ac`);
  }
  if (filterState.programs.size && filterState.programs.size < PROGRAM_LEGEND.length) {
    count++;
    active.push(`${filterState.programs.size}/${PROGRAM_LEGEND.length} programs`);
  }
  if (filterState.dcTier) {
    count++;
    const tier = DC_TIERS.find((t) => t.id === filterState.dcTier);
    active.push(tier?.label || filterState.dcTier);
  }
  if (filterState.dcCandidate) {
    count++;
    active.push("DC candidates");
  }
  if (filterState.oppZone) {
    count++;
    active.push("Opportunity Zone");
  }
  if (filterState.isoRto) {
    count++;
    active.push(`ISO/RTO ${ISO_RTO_LABELS[filterState.isoRto] || filterState.isoRto}`);
  }
  if (filterState.availableOnly) {
    count++;
    active.push("Cleanup / transfer reported");
  }
  const evidenceStatus=el("evidence-status-filter")?.value;
  const evidenceConfidence=el("evidence-confidence-filter")?.value;
  if(evidenceStatus || evidenceConfidence) {count++; active.push(`${SiteEvidence.LABELS[el("evidence-category-filter")?.value] || "Evidence"}: ${[evidenceStatus,evidenceConfidence].filter(Boolean).join(" / ")}`);}
  const chip = el("filters-chip");
  const btn = el("filters-toggle");
  if (chip) {
    if (count > 0) {
      chip.hidden = false;
      chip.textContent = String(count);
      // Tooltip surfaces *which* filters are active so a user returning
      // to a bookmarked URL doesn't see a mystery "1" badge.
      chip.title = `Active: ${active.join(" · ")}`;
    } else {
      chip.hidden = true;
      chip.removeAttribute("title");
    }
  }
  if (btn) btn.setAttribute("aria-label", count ? `Filters (${count} active: ${active.join(", ")})` : "Filters");
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

// ----- JTBD quick-start strip -----
//
// "What are you siting?" → one click routes to the view + lens that answers
// it. Routing deliberately CLICKS the real tab / lens buttons rather than
// duplicating their logic, so lens state, the active-button classes, the
// rebuild, and the ?lens= URL sync all stay on one code path.
const JTBD_ROUTES = {
  dc:      { lens: "dc",  tab: "tab-candidates" },
  gen:     { lens: "gen", tab: "tab-candidates" },
  mfg:     { lens: "mfg", tab: "tab-candidates" },
  reactor: { lens: null,  tab: "tab-ap1000" },
};
const JTBD_DISMISS_KEY = "jtbdDismissed";

function jtbdIsDismissed() {
  try {
    return localStorage.getItem(JTBD_DISMISS_KEY) === "1";
  } catch {
    return false; // private mode / storage disabled — show the strip
  }
}

// Runs at top level (alongside loadInitialTheme) rather than inside the boot
// .then() so a dismissed strip never flashes before the data fetch resolves.
function hideJtbdIfDismissed() {
  if (!jtbdIsDismissed()) return;
  const strip = el("jtbd-strip");
  if (strip) strip.hidden = true;
}

function wireJtbdStrip() {
  const strip = el("jtbd-strip");
  if (!strip) return;
  for (const btn of strip.querySelectorAll("[data-jtbd]")) {
    btn.addEventListener("click", () => {
      const route = JTBD_ROUTES[btn.dataset.jtbd];
      if (!route) return;
      // Lens first, then tab: setting the lens while the view is inactive
      // skips a throwaway build, and the tab activation then renders once
      // with the right lens.
      if (route.lens) {
        const lensBtn = document.querySelector(`[data-cand-lens="${route.lens}"]`);
        if (lensBtn) lensBtn.click();
      }
      const tabBtn = el(route.tab);
      if (tabBtn) tabBtn.click();
    });
  }
  const dismiss = el("jtbd-dismiss");
  if (dismiss) {
    dismiss.addEventListener("click", () => {
      try { localStorage.setItem(JTBD_DISMISS_KEY, "1"); } catch { /* storage disabled */ }
      strip.hidden = true;
    });
  }
}

// ----- Boot -----
loadInitialTheme();
hideJtbdIfDismissed();
loadInitialFiltersFromUrl();
fetch(PRIMARY_DATA_URL)
  .then((r) => {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  })
  .then((payload) => {
    ingestSites(payload.sites || [], payload.source_url);
    recordRefreshDate(payload.generated_at, PRIMARY_DATA_URL);
    updateMetaText({
      loadingLabel: filterState.programs.has("brownfield") ? "brownfields" : null,
    });
    updateKpiDeck();
    try { initMap(); } catch (e) { console.error("initMap error (non-fatal):", e); }
    populateStatusFilter();
    populateStateFilter();
    populateIsoRtoFilter();
    rebuildTable();
    wireTabs();
    wireJtbdStrip();
    wireCandidatesFilters();
    wireDetailPanel();
    wireSearch();
    wireFilters();
    wirePersonaButtons();
    wireKpiClicks();
    wireEvidenceDisclosure();
    wireNearbyClicks();
    wireExportCsv();
    wireAp1000ExportCsv();
    wireThemeToggle();
    wireKpiDisclosure();
    wireDetailSections();
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
    // The Leaflet instance itself, for e2e zoom/center assertions —
    // window.map is shadowed by the div#map DOM global, so tests (and
    // debugging) need an explicit handle.
    window.__leafletMap = map;
    // Expose tableState so e2e can verify the cached visible bbox.
    window.__tableState = tableState;
    // Expose the prettifiers + CSV schema so e2e tests can exercise the
    // curated column set without intercepting a download.
    window.__prettyName = prettyName;
    window.__renderSuitability = renderSuitability;
    window.__csvColumns = CSV_COLUMNS;
    window.__buildCsv = buildSiteCsv;
    // Kick off lazy loads for enabled programs BEFORE applyUrlSelection()
    // so the *LoadingPromise globals are populated — applyUrlSelection
    // waits on them when the requested ?site= ID points at a record from
    // a program that hasn't streamed in yet (e.g. ?site=FUDS-XXX during
    // the FUDS lazy-load window).
    const lazyLoads = [];
    if (filterState.programs.has("brownfield")) lazyLoads.push(ensureAcresLoaded());
    if (filterState.programs.has("fuds")) lazyLoads.push(ensureFudsLoaded());
    if (filterState.programs.has("brac")) lazyLoads.push(ensureBracLoaded());
    lazyLoads.push(ensureEvidenceInvalidationsLoaded());
    lazyLoads.push(ensureRedevLoaded());
    lazyLoads.push(ensureInfraLoaded());
    lazyLoads.push(ensureOppZoneLoaded());
    lazyLoads.push(ensureIsoRtoLoaded());
    lazyLoads.push(ensureParcelOwnerLoaded());
    lazyLoads.push(ensureAcresCleanupLoaded());
    lazyLoads.push(ensureCoordQualityLoaded());
    // Water is part of the category evidence needed for initial exploration.
    lazyLoads.push(ensureWaterProximityLoaded());
    applyUrlSelection();
    if (lazyLoads.length === 0) {
      lazyLoadsSettled = true;
      markAppReady();
      maybeRefreshCandidates();
    } else {
      Promise.allSettled(lazyLoads).then(() => { lazyLoadsSettled = true; applyFilter(); renderSourceCoverage(); markAppReady(); maybeRefreshCandidates(); maybeRefreshMaritime(); maybeRefreshNickel(); maybeRefreshMicro(); });
    }
  })
  .catch((err) => {
    el("meta").textContent = "Failed to load site data: " + err.message;
    console.error(err);
  });

const INVALIDATIONS_URL = "data/evidence-invalidations.json";
let evidenceInvalidations = {};
let invalidationsFailed = false;
let invalidationsPromise = null;
function ensureEvidenceInvalidationsLoaded() {
  if (invalidationsPromise) return invalidationsPromise;
  invalidationsPromise = fetch(INVALIDATIONS_URL).then(r => {if(!r.ok) throw new Error(`HTTP ${r.status}`); return r.json();}).then(payload => {
    if(payload.schema_version !== 1 || !payload.by_id) throw new Error("Invalid coordinate evidence manifest");
    evidenceInvalidations = payload.by_id; invalidationsFailed = false;
    recordRefreshDate(payload.generated_at, INVALIDATIONS_URL);
    return Promise.allSettled([acresLoadingPromise,fudsLoadingPromise,bracLoadingPromise].filter(Boolean));
  }).then(() => {applyFilter(); if(selectedId) selectSite(selectedId);}).catch(error => {
    console.error("Coordinate evidence validation failed:", error); invalidationsFailed = true;
    applyFilter();
  });
  return invalidationsPromise;
}
function sanitizeGeographicEvidence(site) {
  const invalidation = evidenceInvalidations[site.id];
  if (invalidation?.invalidate) {
    for (const field of invalidation.clear_fields || []) delete site[field];
    Object.assign(site,invalidation.restore_core_fields || {});
    site._evidenceInvalidation = invalidation;
  }
  if (invalidationsFailed) {
    for (const field of ["transmission_mi","transmission_kv","substation_mi","substation_kv","rail_mi","highway_mi","water_gage_mi","water_flow_cfs","port_mi","shipyard_mi","parcel_acreage","in_sfha"]) delete site[field];
    site._evidenceValidationUnavailable = true;
  }
  return site;
}

function ingestSites(records, sourceUrl = null) {
  for (const s of records) {
    if (sitesById.has(s.id)) continue;
    if (sourceUrl) s._coreSourceUrl = sourceUrl;
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
    // Stamp the state DC regulatory climate once at ingest so the DC-lens
    // score penalty (dc-score.js) and the "Zoning" badge are O(1) lookups.
    const reg = s.state && STATE_DC_REGULATION[s.state];
    if (reg) s.dc_regulatory_climate = reg.climate;
    sitesById.set(s.id, s);
    if (s.program) loadedPrograms.add(s.program);
  }
  sites = Array.from(sitesById.values());
}

// ----- Lazy ACRES load -----
function ensureAcresLoaded() {
  if (acresLoadingPromise) return acresLoadingPromise;
  if (loadedPrograms.has("brownfield")) {
    return Promise.resolve();
  }
  updateMetaText({ loadingLabel: "brownfields" });
  acresLoadingPromise = fetch(ACRES_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, ACRES_DATA_URL);
      ingestSites(payload.sites || [], payload.source_url);
      updateMetaText();
      populateStateFilter();
      rebuildTable();
      rerenderLegend();
      updateKpiDeck();
      // Chunk marker hydration so the main thread stays responsive while
      // the 36k ACRES markers light up. We resolve `acresLoadingPromise`
      // (and dispatch `brownfield:ready`) only after the last batch lands.
      return hydrateMarkersChunked(payload.sites || []).then(() => {
        // Re-apply enrichment joins that may have landed while this program
        // was skipped by a `?program=` URL (see applyCoalProxJoin).
        applyCoalProxJoin();
        applyPortProximityJoin({ refresh: true });
        applyWaterProximityJoin({ refresh: true });
        applyNickelAnchorJoin({ refresh: true });
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
  if (loadedPrograms.has("fuds")) return Promise.resolve();
  fudsLoadingPromise = fetch(FUDS_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, FUDS_DATA_URL);
      ingestSites(payload.sites || [], payload.source_url);
      updateMetaText();
      populateStateFilter();
      rebuildTable();
      rerenderLegend();
      updateKpiDeck();
      return hydrateMarkersChunked(payload.sites || []).then(() => {
        applyCoalProxJoin(); // late-program re-apply (see its comment)
        applyPortProximityJoin({ refresh: true });
        applyWaterProximityJoin({ refresh: true });
        applyNickelAnchorJoin({ refresh: true });
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
  if (loadedPrograms.has("brac")) return Promise.resolve();
  bracLoadingPromise = fetch(BRAC_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, BRAC_DATA_URL);
      ingestSites(payload.sites || [], payload.source_url);
      updateMetaText();
      populateStateFilter();
      rebuildTable();
      rerenderLegend();
      updateKpiDeck();
      addMarkersForRecords(payload.sites || []);
      applyCoalProxJoin(); // late-program re-apply (see its comment)
      applyPortProximityJoin({ refresh: true });
      applyWaterProximityJoin({ refresh: true });
      applyNickelAnchorJoin({ refresh: true });
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
  redevLoadingPromise = fetch(REDEV_DATA_URL, { priority: "low" })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, REDEV_DATA_URL);
      const truthyKeys = [
        "near_electric_transmission", "near_highway", "near_railroad",
        "near_water_supply", "near_wastewater", "pop_density",
        "in_opp_zone", "in_reuse",
      ];
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id || rec.epa_id);
        if (!existing) continue;
        const patch = {};
        for (const k of truthyKeys) if (rec[k]) patch[k] = rec[k];
        if (rec.data_center_reuse_candidate != null) patch.data_center_reuse_candidate = rec.data_center_reuse_candidate;
        if (rec.rau_status) patch.rau_status = rec.rau_status;
        if (rec.acreage != null && existing.acreage == null) patch.acreage = rec.acreage;
        Object.assign(existing, patch);
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
  superfundDocsLoadingPromise = fetch(SUPERFUND_DOCS_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, SUPERFUND_DOCS_URL);
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id || rec.epa_id);
        if (!existing) continue;
        if (Array.isArray(rec.documents) && rec.documents.length) {
          existing.documents = rec.documents;
        }
      }
      // If the user already opened a site, re-render its documents block.
      if (selectedId) {
        const sel = sitesById.get(selectedId);
        if (sel) renderDocuments(sel);
      }
      // A DOE Sites drawer open on an NPL sub-area reads rec.documents from
      // the same join (_doeDecisionDocsHtml) — if it was mounted before this
      // enrichment landed, its "prior federal decision documents" section
      // rendered empty and never refreshed on its own (Codex PR #24
      // finding). buildHanfordView() no-ops when the tab was never visited.
      if (typeof buildHanfordView === "function" && el("hanford-content")) buildHanfordView();
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
  echoLoadingPromise = fetch(ECHO_DATA_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, ECHO_DATA_URL);
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

// Parcel-owner enrichment — verified owner name from public state/county
// cadastral records (parcel_owner connector). Fill-if-empty: don't clobber a
// program-provided owner (e.g. FUDS's USACE current_owner); only populate the
// ~38k sites that have none. The detail panel's owner row + source line pick
// these up automatically (no extra wiring).
function ensureParcelOwnerLoaded() {
  if (parcelOwnerLoadingPromise) return parcelOwnerLoadingPromise;
  parcelOwnerLoadingPromise = fetch(PARCEL_OWNER_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, PARCEL_OWNER_URL);
      // All-programs join — wait on ACRES/FUDS/BRAC first or the `!existing`
      // guard below can silently drop them (load-order race, see CLAUDE.md).
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        // Owner: fill-if-empty (don't clobber a source-provided owner, e.g. FUDS).
        if (rec.current_owner && !existing.current_owner) {
          existing.current_owner = rec.current_owner;
          existing.current_owner_source = rec.current_owner_source || "Public parcel records";
        }
        // Parcel acreage / id: the actual developable land size from the
        // cadastral parcel. The only land-size signal for ACRES sites
        // (acreage == null). Fill-if-empty so a program-reported parcel value
        // (none today) would win.
        if (rec.parcel_acreage != null && existing.parcel_acreage == null) {
          existing.parcel_acreage = rec.parcel_acreage;
          existing.parcel_id = rec.parcel_id || null;
          if (!existing.current_owner_source) {
            existing.current_owner_source = rec.current_owner_source || "Public parcel records";
          }
        }
      }
      // Re-render an already-open detail panel so the owner row goes live the
      // moment this lazy load lands (matches the docs / summary / infra loaders).
      if (selectedId && sitesById.has(selectedId)) {
        try { selectSite(selectedId); } catch {}
      }
    })
    .catch((err) => {
      console.error("Parcel-owner enrichment load failed:", err);
      parcelOwnerLoadingPromise = null;
    });
  return parcelOwnerLoadingPromise;
}

// AI-generated site summaries (Claude Haiku output). Per-site 3-paragraph
// plain-English narrative, content-hash-cached at refresh time. Coverage
// grows as `--source ai-summary --ai-limit N` re-runs land more sites.
function ensureSummariesLoaded() {
  if (summariesLoadingPromise) return summariesLoadingPromise;
  summariesLoadingPromise = fetch(AI_SUMMARY_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, AI_SUMMARY_URL);
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

// EPA ACRES cleanup status + brownfield grant history. Lazy-loaded; joins onto
// ACRES brownfield records in sitesById by id. Fields merged: cleanup_status,
// cleanup_complete_date, grant_total_usd, grant_count, grant_types.
// 404 → treated as "no data yet" (connector not run) rather than an error.
function ensureAcresCleanupLoaded() {
  if (acresCleanupLoadingPromise) return acresCleanupLoadingPromise;
  acresCleanupLoadingPromise = fetch(ACRES_CLEANUP_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      // ACRES-only join — wait on the ACRES load first or the `!existing`
      // guard below can silently drop it (load-order race, see CLAUDE.md).
      if (acresLoadingPromise) await Promise.allSettled([acresLoadingPromise]);
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        if (rec.cleanup_status != null) existing.cleanup_status = rec.cleanup_status;
        if (rec.cleanup_complete_date != null) existing.cleanup_complete_date = rec.cleanup_complete_date;
        if (rec.grant_total_usd != null) existing.grant_total_usd = rec.grant_total_usd;
        if (rec.grant_count != null) existing.grant_count = rec.grant_count;
        if (rec.grant_types != null) existing.grant_types = rec.grant_types;
      }
      if (selectedId) {
        const sel = sitesById.get(selectedId);
        if (sel) renderGrants(sel);
      }
    })
    .catch((err) => {
      console.error("ACRES cleanup load failed:", err);
      acresCleanupLoadingPromise = null;
    });
  return acresCleanupLoadingPromise;
}

// Cross-program "available for redevelopment" heuristic:
//   Superfund  — NPL status Deleted (D) = remediation complete, removed from list.
//   ACRES      — cleanup_status === "Completed" (from acres-cleanup enrichment).
//   FUDS       — Eligible tier + non-federal current owner (transferred).
//   BRAC       — no reliable public signal yet; always false.
function siteIsAvailable(s) {
  if (s.program === "superfund") return s.npl_status_code === "D";
  if (s.program === "brownfield") return s.cleanup_status === "Completed";
  if (s.program === "fuds") {
    const owner = (s.current_owner || "").toLowerCase();
    const notFederal = owner && !owner.startsWith("federal") && !owner.startsWith("fed:");
    return s.eligibility === "Eligible" && notFederal;
  }
  return false;
}

// Universal infrastructure-proximity enrichment. Joins onto every program
// (Superfund, ACRES, FUDS, BRAC) by `id` to add `transmission_mi`,
// `rail_mi`, `highway_mi`, `gas_pipeline_mi`, plus the v1.13.3 additions
// `substation_mi/kv`, `power_plant_mi/mw/fuel`, and `flood_zone/in_sfha`.
// Computed at refresh time from HIFLD + Census TIGER + OSM Overpass + FEMA
// NFHL by the `infra-proximity` connector. Distances >100 mi are absent
// (treated as out-of-range / out-of-CONUS); flood_zone is null outside any
// mapped FEMA study area.
function ensureInfraLoaded() {
  if (infraLoadingPromise) return infraLoadingPromise;
  infraLoadingPromise = fetch(INFRA_DATA_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, INFRA_DATA_URL);
      // infra-proximity.json is large enough to usually resolve AFTER ACRES/
      // FUDS/BRAC, which is why this join "accidentally" worked — but that's
      // file-size luck, not a guarantee (load-order race, see CLAUDE.md).
      // Wait on the in-flight program loads first so the `!existing` guard
      // below can't silently drop every non-Superfund join.
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        const patch = {_infraSourceMetadata: payload.source_metadata || {}, infra_evidence: rec.infra_evidence || {}};
        const fields = ["transmission_mi","transmission_kv","substation_mi","substation_kv","substation_role","rail_mi","highway_mi","gas_pipeline_mi","power_plant_mi","power_plant_mw","power_plant_fuel","power_plant_name","flood_zone","in_sfha","transmission_asset_id","substation_asset_id","power_plant_asset_id","infra_assessed_lat","infra_assessed_lon"];
        for (const key of fields) {
          // New evidence payloads replace their layer fields, including cleared
          // observations. Otherwise a removed/inferred voltage survives the join.
          if (rec.infra_evidence || rec[key] != null) patch[key] = rec[key] ?? null;
        }
        patch.power_plant_name = rec.power_plant_name || payload.source_metadata?.power_plant?.assets_by_id?.[rec.power_plant_asset_id]?.name || null;
        patch._infraChecked = true;
        Object.assign(existing, patch);
      }
      // Re-run KPI deck (hyperscale-ready count depends on transmission_kv)
      // and re-render an open detail panel so the new pill / chip lights up
      // without requiring the user to reselect the site.
      updateKpiDeck();
      maybeRefreshMicro();
      if (selectedId && sitesById.has(selectedId)) {
        try { selectSite(selectedId); } catch {}
      }
    })
    .catch((err) => {
      console.error("Infra-proximity enrichment load failed:", err);
      infraLoadingPromise = null;
    });
  return infraLoadingPromise;
}

// Port / shipyard proximity enrichment (connectors/port_proximity.py). Joins
// onto every program by `id` to add port_mi/port_name/port_type/
// port_hurricane_freq and shipyard_mi/shipyard_name/shipyard_capability —
// feeds the two Maritime Siting lenses in maritime-score.js.
//
// The payload is CACHED and the apply is IDEMPOTENT — same pattern as
// applyCoalProxJoin(): a page that boots with a restricted `?program=` URL
// only reaches eager Superfund records on the first apply, so
// ensureAcresLoaded()/ensureFudsLoaded()/ensureBracLoaded() call
// applyPortProximityJoin() again as their records land (Codex review,
// this PR). `_portChecked` doubles as the skip-if-already-applied guard —
// it's the same "we looked" marker the score gate reads.
let portProximityRecords = null; // settled payload (even if empty)
// Set once the whole boot fan-out has settled. Per-join flags were tried
// first and are not enough: the joins land in a varying order, and a view
// rebuilt between two of them can see an empty ranked set while both of its
// own flags are already true. Until every lazy load has settled, an empty
// list is a loading state, never a filter result.
let lazyLoadsSettled = false;
// Loaders the Nickel Refining tab CANNOT rank without. Their own catch blocks
// swallow the rejection (and a 404 becomes an empty payload), so
// `Promise.allSettled` settles either way and the view would otherwise report
// a failed fetch as "no sites match the current filters" — telling the user
// their filters are wrong when the data never arrived (Codex round 2).
const nickelDataErrors = new Set();
function applyPortProximityJoin({ refresh = false } = {}) {
  if (!portProximityRecords) return;
  let applied = 0;
  for (const rec of portProximityRecords) {
    const existing = sitesById.get(rec.id);
    if (!existing || existing._portChecked) continue;
    if (rec.port_mi != null) existing.port_mi = rec.port_mi;
    if (rec.port_name != null) existing.port_name = rec.port_name;
    if (rec.port_type != null) existing.port_type = rec.port_type;
    if (rec.port_hurricane_freq != null) existing.port_hurricane_freq = rec.port_hurricane_freq;
    if (rec.shipyard_mi != null) existing.shipyard_mi = rec.shipyard_mi;
    if (rec.shipyard_name != null) existing.shipyard_name = rec.shipyard_name;
    if (rec.shipyard_capability != null) existing.shipyard_capability = rec.shipyard_capability;
    // Marker, not data: both maritime lenses gate on this — a null port_mi
    // means "off-coast" only once the join has actually run. See
    // maritimeScorable() in maritime-score.js.
    existing._portChecked = true;
    applied++;
  }
  if (refresh && applied) {
    if (selectedId && sitesById.has(selectedId)) {
      try { selectSite(selectedId); } catch {}
    }
    maybeRefreshMaritime();
    // The Nickel import lens ranks on `port_mi`, so it needs this join too —
    // refreshing only Maritime left that tab empty after a late port load
    // (Codex round 2).
    maybeRefreshNickel();
  }
}

function ensurePortProximityLoaded() {
  if (portProximityLoadingPromise) return portProximityLoadingPromise;
  portProximityLoadingPromise = fetch(PORT_PROXIMITY_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, PORT_PROXIMITY_URL);
      nickelDataErrors.delete("port");    // a retry succeeded
      portProximityRecords = payload.sites || [];
      // All-programs join — wait on ACRES/FUDS/BRAC first or the `!existing`
      // guard above can silently drop them (load-order race, see CLAUDE.md).
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      applyPortProximityJoin({ refresh: true });
    })
    .catch((err) => {
      console.error("Port-proximity enrichment load failed:", err);
      nickelDataErrors.add("port");
      portProximityLoadingPromise = null;
      maybeRefreshNickel();
    });
  return portProximityLoadingPromise;
}

// Opportunity Zone enrichment. Joins onto every program by `id` to add
// `in_opportunity_zone` (boolean), `oz_tract_geoid` (11-digit GEOID10),
// and `oz_rural` (boolean). Distinct from the legacy `in_opp_zone` field
// (a string from EPA RE-Powering, Superfund-only) which stays unchanged.
function ensureOppZoneLoaded() {
  if (oppZoneLoadingPromise) return oppZoneLoadingPromise;
  oppZoneLoadingPromise = fetch(OPP_ZONE_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, OPP_ZONE_URL);
      // All-programs join — wait on ACRES/FUDS/BRAC first or the `!existing`
      // guard below can silently drop them (load-order race, see CLAUDE.md).
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        // Always set in_opportunity_zone (true OR false — both are meaningful).
        if (rec.in_opportunity_zone != null) {
          existing.in_opportunity_zone = rec.in_opportunity_zone;
        }
        if (rec.oz_tract_geoid != null) existing.oz_tract_geoid = rec.oz_tract_geoid;
        if (rec.oz_rural != null) existing.oz_rural = rec.oz_rural;
      }
      updateKpiDeck();
      // Re-run filter so sites that flipped IN/OUT of OZ visibility update.
      if (typeof applyFilter === "function") applyFilter();
      if (selectedId && sitesById.has(selectedId)) {
        try { selectSite(selectedId); } catch {}
      }
    })
    .catch((err) => {
      console.error("Opportunity-Zone enrichment load failed:", err);
      oppZoneLoadingPromise = null;
    });
  return oppZoneLoadingPromise;
}

// Census TIGERweb AIANNHA containment. This is consultation-planning context,
// not title and not a determination of which governments must be consulted.
function ensureTribalAreasLoaded() {
  if (tribalAreasLoadingPromise) return tribalAreasLoadingPromise;
  tribalAreasLoadingPromise = fetch(TRIBAL_AREAS_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, TRIBAL_AREAS_URL);
      // This all-program enrichment often downloads before ACRES/FUDS. Wait
      // so those joins are not silently discarded by the !existing guard.
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        if (rec.in_aiannha_area != null) existing.in_aiannha_area = rec.in_aiannha_area;
        if (rec.aiannha_area_count != null) existing.aiannha_area_count = rec.aiannha_area_count;
        if (Array.isArray(rec.aiannha_areas)) existing.aiannha_areas = rec.aiannha_areas;
      }
      if (selectedId && sitesById.has(selectedId)) selectSite(selectedId);
      maybeRefreshCandidates();
    })
    .catch((err) => {
      console.error("Tribal-area enrichment load failed:", err);
      tribalAreasLoadingPromise = null;
    });
  return tribalAreasLoadingPromise;
}

// IRA Energy Community enrichment. Joins onto every program by `id` to add
// `in_energy_community` (boolean), `energy_community_type` (coal_closure |
// fossil_fuel_employment), and `energy_community_detail` (human-readable
// provenance). A clean-energy project on an energy community earns a +10pp
// ITC/PTC bonus under IRA §45/48 — a financial signal that stacks with OZ.
function ensureIraEnergyCommunityLoaded() {
  if (iraEcLoadingPromise) return iraEcLoadingPromise;
  iraEcLoadingPromise = fetch(IRA_EC_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, IRA_EC_URL);
      // All-programs join — wait on ACRES/FUDS/BRAC first or the `!existing`
      // guard below can silently drop them (load-order race, see CLAUDE.md).
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        // Always set in_energy_community (true OR false — both are meaningful).
        if (rec.in_energy_community != null) {
          existing.in_energy_community = rec.in_energy_community;
        }
        if (rec.energy_community_type != null) existing.energy_community_type = rec.energy_community_type;
        if (rec.energy_community_detail != null) existing.energy_community_detail = rec.energy_community_detail;
      }
      // Re-run filter so the score-driven KPIs / table pick up the readiness bump.
      if (typeof applyFilter === "function") applyFilter();
      if (selectedId && sitesById.has(selectedId)) {
        try { selectSite(selectedId); } catch {}
      }
    })
    .catch((err) => {
      console.error("IRA energy-community enrichment load failed:", err);
      iraEcLoadingPromise = null;
    });
  return iraEcLoadingPromise;
}

// FEMA National Risk Index enrichment. Joins onto every program by `id` to
// add `nri_risk_score` + `nri_risk_rating` (composite) and the three
// DC-relevant per-hazard ratings (wildfire / drought / heat wave). Feeds a
// climate-risk penalty in dc-score.js (wildfire/drought ≥ Relatively High).
function ensureFemaNriLoaded() {
  if (femaNriLoadingPromise) return femaNriLoadingPromise;
  femaNriLoadingPromise = fetch(FEMA_NRI_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, FEMA_NRI_URL);
      // All-programs join — wait on ACRES/FUDS/BRAC first or the `!existing`
      // guard below can silently drop them (load-order race, see CLAUDE.md).
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        if (rec.nri_risk_score != null) existing.nri_risk_score = rec.nri_risk_score;
        if (rec.nri_risk_rating != null) existing.nri_risk_rating = rec.nri_risk_rating;
        if (rec.nri_wildfire_rating != null) existing.nri_wildfire_rating = rec.nri_wildfire_rating;
        if (rec.nri_drought_rating != null) existing.nri_drought_rating = rec.nri_drought_rating;
        if (rec.nri_heatwave_rating != null) existing.nri_heatwave_rating = rec.nri_heatwave_rating;
      }
      // Climate penalty can change scores → re-run filter so KPIs/table update.
      if (typeof applyFilter === "function") applyFilter();
      if (selectedId && sitesById.has(selectedId)) {
        try { selectSite(selectedId); } catch {}
      }
    })
    .catch((err) => {
      console.error("FEMA NRI enrichment load failed:", err);
      femaNriLoadingPromise = null;
    });
  return femaNriLoadingPromise;
}

// County-level IECC / ASHRAE climate-zone enrichment. Joins onto every
// program by `id` to add `climate_zone` (e.g. 5B / 3A), used as a DC
// cooling-climate signal in the detail panel and CSV export.
function ensureClimateZoneLoaded() {
  if (climateZoneLoadingPromise) return climateZoneLoadingPromise;
  climateZoneLoadingPromise = fetch(CLIMATE_ZONE_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, CLIMATE_ZONE_URL);
      // All-programs join — wait on ACRES/FUDS/BRAC first or the `!existing`
      // guard below can silently drop them (load-order race, see CLAUDE.md).
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        if (rec.climate_zone != null) existing.climate_zone = rec.climate_zone;
      }
      if (selectedId && sitesById.has(selectedId)) {
        try { selectSite(selectedId); } catch {}
      }
    })
    .catch((err) => {
      console.error("Climate-zone enrichment load failed:", err);
      climateZoneLoadingPromise = null;
    });
  return climateZoneLoadingPromise;
}

// EIA/HIFLD ISO/RTO region enrichment. Joins onto lower-48/DC sites by `id`
// to add `iso_rto`, which drives the ISO/RTO filter and detail-panel row.
function ensureIsoRtoLoaded() {
  if (isoRtoLoadingPromise) return isoRtoLoadingPromise;
  isoRtoLoadingPromise = fetch(ISO_RTO_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, ISO_RTO_URL);
      // All-programs join — wait on ACRES/FUDS/BRAC first or the `!existing`
      // guard below can silently drop them (load-order race, see CLAUDE.md).
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        if (rec.iso_rto != null) existing.iso_rto = rec.iso_rto;
      }
      populateIsoRtoFilter();
      if (typeof applyFilter === "function") applyFilter();
      if (selectedId && sitesById.has(selectedId)) {
        try { selectSite(selectedId); } catch {}
      }
    })
    .catch((err) => {
      console.error("ISO/RTO enrichment load failed:", err);
      isoRtoLoadingPromise = null;
    });
  return isoRtoLoadingPromise;
}

// EIA-860M retired-plants enrichment. Joins onto all programs by `id` to
// add `retired_plant_mi`, `retired_plant_mw`, `retired_plant_fuel`,
// `retired_plant_year`, and `retired_plant_name`. Drives the "Ret. Plant"
// badge and the grid-inheritance scoring tier.
function ensureRetiredPlantsLoaded() {
  if (retiredPlantsLoadingPromise) return retiredPlantsLoadingPromise;
  retiredPlantsLoadingPromise = fetch(RETIRED_PLANTS_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, RETIRED_PLANTS_URL);
      // All-programs join — wait on ACRES/FUDS/BRAC first or the `!existing`
      // guard below can silently drop them (load-order race, see CLAUDE.md).
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        if (rec.retired_plant_mi  != null) existing.retired_plant_mi   = rec.retired_plant_mi;
        if (rec.retired_plant_mw  != null) existing.retired_plant_mw   = rec.retired_plant_mw;
        if (rec.retired_plant_fuel)        existing.retired_plant_fuel  = rec.retired_plant_fuel;
        if (rec.retired_plant_year != null) existing.retired_plant_year = rec.retired_plant_year;
        if (rec.retired_plant_name)        existing.retired_plant_name  = rec.retired_plant_name;
      }
      if (typeof applyFilter === "function") applyFilter();
      if (selectedId && sitesById.has(selectedId)) {
        try { selectSite(selectedId); } catch {}
      }
    })
    .catch((err) => {
      console.error("Retired-plants enrichment load failed:", err);
      retiredPlantsLoadingPromise = null;
    });
  return retiredPlantsLoadingPromise;
}

// Lazy-load the planned-retirements proximity join (planned-retirements-
// proximity.json) and copy the `planned_retirement_*` fields onto matching
// records. Feeds the generation lens's grid_reuse component (a plant with
// an ANNOUNCED retirement frees its interconnect on a known date — the
// forward-looking counterpart to eia-retired-plants) and the detail panel.

// Coordinate-quality flags. Only sites with a KNOWN location problem appear
// in this file, so absence means "no issue found" — the join is additive and
// the vast majority of records are untouched.
//
// Same load-order hazard as ensurePlannedRetireProxLoaded(): at ~390 KB this
// resolves long before epa-acres.json (~10.9 MB), so without awaiting the
// program loads the `!existing` guard would silently drop every ACRES / FUDS
// / BRAC flag — which is most of them, since ACRES is where the bad
// coordinates concentrate.
function ensureCoordQualityLoaded() {
  if (coordQualityLoadingPromise) return coordQualityLoadingPromise;
  coordQualityLoadingPromise = fetch(COORD_QUALITY_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, COORD_QUALITY_URL);
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        if (rec.coord_flags)                  existing.coord_flags = rec.coord_flags;
        if (rec.coord_actual_state)           existing.coord_actual_state = rec.coord_actual_state;
        if (rec.coord_state_gap_mi != null)   existing.coord_state_gap_mi = rec.coord_state_gap_mi;
        if (rec.coord_shared_count != null)   existing.coord_shared_count = rec.coord_shared_count;
      }
      if (selectedId && sitesById.has(selectedId)) {
        try { selectSite(selectedId); } catch {}
      }
    })
    .catch((err) => {
      console.error("Coordinate-quality load failed:", err);
      coordQualityLoadingPromise = null;
    });
  return coordQualityLoadingPromise;
}

function ensurePlannedRetireProxLoaded() {
  if (plannedRetireProxLoadingPromise) return plannedRetireProxLoadingPromise;
  plannedRetireProxLoadingPromise = fetch(PLANNED_RETIRE_PROX_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, PLANNED_RETIRE_PROX_URL);
      // This file is tiny (~130 KB) and can resolve BEFORE the much larger
      // ACRES / FUDS / BRAC program files finish ingesting into sitesById.
      // Without waiting, the `!existing` guard below would silently drop
      // every brownfield / FUDS / BRAC join (the majority of the 614
      // records). Wait on the in-flight program loads first — the same
      // guard applyUrlSelection() uses for ?site= deep-links. Promises are
      // null for programs skipped via ?program=, so filter them out.
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        if (rec.planned_retirement_mi   != null) existing.planned_retirement_mi   = rec.planned_retirement_mi;
        if (rec.planned_retirement_mw   != null) existing.planned_retirement_mw   = rec.planned_retirement_mw;
        if (rec.planned_retirement_fuel)         existing.planned_retirement_fuel  = rec.planned_retirement_fuel;
        if (rec.planned_retirement_year != null) existing.planned_retirement_year = rec.planned_retirement_year;
        if (rec.planned_retirement_name)         existing.planned_retirement_name  = rec.planned_retirement_name;
      }
      if (typeof applyFilter === "function") applyFilter();
      if (selectedId && sitesById.has(selectedId)) {
        try { selectSite(selectedId); } catch {}
      }
    })
    .catch((err) => {
      console.error("Planned-retirements proximity load failed:", err);
      plannedRetireProxLoadingPromise = null;
    });
  return plannedRetireProxLoadingPromise;
}

function ensureReferenceCampusesLoaded() {
  if (referenceCampusesLoadingPromise) return referenceCampusesLoadingPromise;
  referenceCampusesLoadingPromise = fetch(REFERENCE_CAMPUSES_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { campuses: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      if (!referenceCampusLayer) return; // map not yet initialized
      for (const campus of payload.campuses || []) {
        if (campus.lat == null || campus.lon == null) continue;
        const icon = L.divIcon({
          className: "ref-campus-icon",
          html: "<span>★</span>",
          iconSize: [22, 22],
          iconAnchor: [11, 11],
          popupAnchor: [0, -13],
        });
        const marker = L.marker([campus.lat, campus.lon], { icon, zIndexOffset: 500 });
        const acreStr = campus.acreage != null ? `${campus.acreage.toLocaleString()} ac` : null;
        const mwStr = campus.capacity_mw != null ? `${campus.capacity_mw.toLocaleString()} MW` : null;
        const sizeStr = [acreStr, mwStr].filter(Boolean).join(" · ") || "";
        const yearStr = campus.year_operational
          ? `Operational ${campus.year_operational}`
          : campus.year_announced
            ? `Announced ${campus.year_announced}`
            : "";
        const statusClass = campus.status === "operational" ? "ref-status-operational"
          : campus.status === "under development" || campus.status === "under construction" ? "ref-status-active"
          : "ref-status-planned";
        marker.bindPopup(
          `<div class="ref-campus-popup">` +
          `<strong>${escapeHtml(campus.name)}</strong>` +
          `<div class="ref-campus-company">${escapeHtml(campus.company)}</div>` +
          `<div class="ref-campus-prev">${escapeHtml(campus.previous_use)}</div>` +
          `<div class="ref-campus-meta">` +
            (sizeStr ? `<span>${escapeHtml(sizeStr)}</span>` : "") +
            (yearStr ? `<span>${escapeHtml(yearStr)}</span>` : "") +
            `<span class="${statusClass}">${escapeHtml(campus.status)}</span>` +
          `</div>` +
          `<a href="${escapeHtml(campus.source_url)}" target="_blank" rel="noopener" class="ref-campus-link">Source ↗</a>` +
          `</div>`,
          { maxWidth: 280 }
        );
        referenceCampusLayer.addLayer(marker);
      }
      rerenderLegend();
    })
    .catch((err) => {
      console.error("Reference campuses load failed:", err);
      referenceCampusesLoadingPromise = null;
    });
  return referenceCampusesLoadingPromise;
}

// ----- Water proximity -----------------------------------------------------
// The corpus's first quantitative water signal. Everything collected before
// it moves electrons, freight or fuel; the only water fields on a record were
// EPA RE-Powering's qualitative `near_water_supply` / `near_water_body`,
// covering ~1,905 Superfund sites out of 46,759.
//
// Cached payload + idempotent apply, same contract as
// applyPortProximityJoin() — a page booted with a restricted `?program=` URL
// reaches only the eager Superfund records on the first pass, so the ACRES /
// FUDS / BRAC loaders re-run the join as their records land.
let waterProximityRecords = null;
let waterSourceMetadata = {};

function applyWaterProximityJoin({ refresh = false } = {}) {
  if (!waterProximityRecords) return;
  let applied = 0;
  for (const rec of waterProximityRecords) {
    const existing = sitesById.get(rec.id);
    if (!existing || existing._waterChecked) continue;
    if (rec.water_gage_mi != null) existing.water_gage_mi = rec.water_gage_mi;
    if (rec.water_flow_cfs != null) existing.water_flow_cfs = rec.water_flow_cfs;
    if (rec.water_gage_name != null) existing.water_gage_name = rec.water_gage_name;
    if (rec.water_gage_id != null) existing.water_gage_id = rec.water_gage_id;
    // Marker, not data. Both nickel lenses gate on it: before the join lands
    // every site would look water-less and score zero on a 20-point
    // component. Same guard the microreactor lens applies with
    // `_infraChecked`.
    const waterFields = {...(waterSourceMetadata.gages_by_id?.[rec.water_gage_id] || {}), ...rec};
    for (const key of Object.keys(waterFields)) if (key.startsWith("water_")) existing[key] = waterFields[key];
    existing.water_statistic = rec.water_statistic || waterSourceMetadata.statistic;
    existing._waterChecked = true;
    applied++;
  }
  if (refresh && applied) {
    if (selectedId && sitesById.has(selectedId)) {
      try { selectSite(selectedId); } catch {}
    }
    maybeRefreshNickel();
  }
}

function ensureWaterProximityLoaded() {
  if (waterProximityLoadingPromise) return waterProximityLoadingPromise;
  waterProximityLoadingPromise = fetch(WATER_PROXIMITY_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, WATER_PROXIMITY_URL);
      nickelDataErrors.delete("water");   // a retry succeeded
      waterSourceMetadata = payload.source_metadata || {};
      waterProximityRecords = payload.sites || [];
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      applyWaterProximityJoin({ refresh: true });
    })
    .catch((err) => {
      console.error("Water proximity load failed:", err);
      nickelDataErrors.add("water");
      waterProximityLoadingPromise = null;
      maybeRefreshNickel();
    });
  return waterProximityLoadingPromise;
}

// ----- Nickel supply-chain proximity ---------------------------------------
let nickelAnchorRecords = null;
let nickelAnchorMetadata = {};
function applyNickelAnchorJoin({ refresh = false } = {}) {
  if (!nickelAnchorRecords) return;
  let applied = 0;
  for (const rec of nickelAnchorRecords) {
    const existing = sitesById.get(rec.id);
    if (!existing || existing._nickelChecked) continue;
    for (const k of ["nickel_anchor_mi", "nickel_anchor_name", "nickel_anchor_kind",
                     "nickel_feedstock_mi", "nickel_demand_mi", "nickel_acid_mi", "nickel_feedstock_id", "nickel_demand_id", "nickel_acid_id"]) {
      if (rec[k] != null) existing[k] = rec[k];
    }
    const feedstock = nickelAnchorMetadata[rec.nickel_feedstock_id];
    if (feedstock) {
      existing.nickel_feedstock_name = feedstock.name;
      existing.nickel_feedstock_source_url = feedstock.source_url;
      existing.nickel_feedstock_verified_at = feedstock.verified_at;
    }
    existing._nickelChecked = true;
    applied++;
  }
  if (refresh && applied) {
    if (selectedId && sitesById.has(selectedId)) {
      try { selectSite(selectedId); } catch {}
    }
    maybeRefreshNickel();
  }
}

function ensureNickelAnchorProxLoaded() {
  if (nickelAnchorProxLoadingPromise) return nickelAnchorProxLoadingPromise;
  nickelAnchorProxLoadingPromise = fetch(NICKEL_ANCHOR_PROX_URL, { priority: "low" })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, NICKEL_ANCHOR_PROX_URL);
      nickelDataErrors.delete("supply chain");  // a retry succeeded
      nickelAnchorRecords = payload.sites || [];
      nickelAnchorMetadata = payload.source_metadata?.anchors_by_id || {};
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      applyNickelAnchorJoin({ refresh: true });
    })
    .catch((err) => {
      console.error("Nickel anchor proximity load failed:", err);
      nickelDataErrors.add("supply chain");
      nickelAnchorProxLoadingPromise = null;
      maybeRefreshNickel();
    });
  return nickelAnchorProxLoadingPromise;
}

// Nickel supply-chain anchors (◈) — map overlay for the Nickel Refining tab.
// Feedstock, offtake, bulk acid, and the one site in the country that has
// actually been a nickel refinery before. Curated, each row cited; see
// scripts/build_nickel_anchors.py.
const NICKEL_ANCHOR_KIND_LABEL = {
  feedstock_mine: "Feedstock — mine or mill",
  feedstock_recycled: "Feedstock — recycled",
  refinery_planned: "Refinery — planned",
  refinery_historic: "Refinery — historic",
  demand_battery: "Demand — battery",
  demand_stainless: "Demand — stainless",
  reagent_acid: "Bulk sulfuric acid",
};

function ensureNickelAnchorsLoaded() {
  if (nickelAnchorsLoadingPromise) return nickelAnchorsLoadingPromise;
  nickelAnchorsLoadingPromise = fetch(NICKEL_ANCHORS_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      if (!nickelAnchorLayer) return;
      for (const a of payload.sites || []) {
        if (a.lat == null || a.lon == null) continue;
        // Every overlay needs this the moment it gains a non-CONUS row; these
        // are all lower-48 today, and the call costs nothing.
        applyInsetRemap(a);
        const icon = L.divIcon({
          className: "nickel-anchor-icon",
          html: "◈",
          iconSize: [16, 16],
          iconAnchor: [8, 8],
          popupAnchor: [0, -8],
        });
        const marker = L.marker([a.lat, a.lon], { icon, zIndexOffset: 300 });
        const kind = NICKEL_ANCHOR_KIND_LABEL[a.kind] || a.kind;
        // coord_precision is disclosed in the popup, not silently upgraded: a
        // `locality` row is the Census Gazetteer internal point for a named
        // place, good to a few miles, and must never read as a facility
        // coordinate.
        const precisionNote = a.coord_precision === "locality"
          ? `<div class="ref-campus-company"><span class="micro-note">Located to ${escapeHtml(a.locality || "the named place")}, not the facility</span></div>`
          : "";
        marker.bindPopup(
          `<div class="ref-campus-popup">` +
          `<strong>${escapeHtml(a.name)}</strong>` +
          `<div class="ref-campus-meta"><span>${escapeHtml(kind)}</span>` +
          (a.status ? `<span>${escapeHtml(a.status)}</span>` : "") + `</div>` +
          precisionNote +
          `<p class="ref-campus-note">${escapeHtml(a.note)}</p>` +
          `<a href="${escapeHtml(a.source_url)}" target="_blank" rel="noopener" class="ref-campus-link">Source ↗</a>` +
          `</div>`,
          { maxWidth: 300 }
        );
        nickelAnchorLayer.addLayer(marker);
      }
      rerenderLegend();
    })
    .catch((err) => {
      console.error("Nickel anchors overlay load failed:", err);
      nickelAnchorsLoadingPromise = null;
    });
  return nickelAnchorsLoadingPromise;
}

// BTS/USACE Principal Ports (⚓) — map overlay for the Maritime Siting tab.
// Mirrors the reference-campus overlay pattern (lazy-loaded, own layer +
// legend row). Generated live by scripts/build_ports_overlay.py.
function ensurePortsLoaded() {
  if (portsLoadingPromise) return portsLoadingPromise;
  portsLoadingPromise = fetch(PORTS_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      if (!portLayer) return; // map not yet initialized
      for (const port of payload.sites || []) {
        if (port.lat == null || port.lon == null) continue;
        // AK/HI/PR/VI ports use raw coordinates otherwise and are
        // unreachable outside the lower-48 US_BOUNDS (Codex review, this PR
        // — the same latent gap every other overlay has until it gains a
        // non-CONUS row; see CLAUDE.md).
        applyInsetRemap(port);
        const icon = L.divIcon({
          className: "port-icon",
          html: "⚓",
          iconSize: [16, 16],
          iconAnchor: [8, 8],
          popupAnchor: [0, -8],
        });
        const marker = L.marker([port.lat, port.lon], { icon, zIndexOffset: 300 });
        const hurr = port.hurricane_freq != null
          ? `${port.hurricane_freq.toFixed(2)} hurricanes/yr (FEMA NRI)` : null;
        marker.bindPopup(
          `<div class="ref-campus-popup">` +
          `<strong>${escapeHtml(port.name)}</strong>` +
          (port._inset ? `<div class="ref-campus-company"><span class="micro-note">shown in the ${escapeHtml(port._inset)} inset ` +
            `(${port.lat_real.toFixed(3)}, ${port.lon_real.toFixed(3)})</span></div>` : "") +
          `<div class="ref-campus-meta"><span>${escapeHtml(port.port_type)} port</span>` +
          (hurr ? `<span>${escapeHtml(hurr)}</span>` : "") + `</div>` +
          `<a href="${escapeHtml(port.source_url)}" target="_blank" rel="noopener" class="ref-campus-link">Source ↗</a>` +
          `</div>`,
          { maxWidth: 260 }
        );
        portLayer.addLayer(marker);
      }
      rerenderLegend();
    })
    .catch((err) => {
      console.error("Ports overlay load failed:", err);
      portsLoadingPromise = null;
    });
  return portsLoadingPromise;
}

// Curated major US shipyards (⚒) — map overlay for the Maritime Siting tab.
// Generated by scripts/build_shipyards.py (no public GIS layer exists).
function ensureShipyardsLoaded() {
  if (shipyardsLoadingPromise) return shipyardsLoadingPromise;
  shipyardsLoadingPromise = fetch(SHIPYARDS_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      if (!shipyardLayer) return; // map not yet initialized
      const CAPABILITY_LABEL = {
        heavy_module: "Heavy-module fabrication",
        large_hull: "Large-hull new construction",
        naval_repair: "Naval repair / overhaul",
      };
      for (const yard of payload.sites || []) {
        if (yard.lat == null || yard.lon == null) continue;
        const icon = L.divIcon({
          className: "shipyard-icon",
          html: "⚒",
          iconSize: [18, 18],
          iconAnchor: [9, 9],
          popupAnchor: [0, -9],
        });
        const marker = L.marker([yard.lat, yard.lon], { icon, zIndexOffset: 300 });
        marker.bindPopup(
          `<div class="ref-campus-popup">` +
          `<strong>${escapeHtml(yard.name)}</strong>` +
          `<div class="ref-campus-company">${escapeHtml(yard.operator)}</div>` +
          `<div class="ref-campus-meta"><span>${escapeHtml(CAPABILITY_LABEL[yard.capability] || yard.capability)}</span>` +
          `<span>${escapeHtml(yard.city)}, ${escapeHtml(yard.state)}</span></div>` +
          (yard.note ? `<div class="ref-campus-prev">${escapeHtml(yard.note)}</div>` : "") +
          `<a href="${escapeHtml(yard.source_url)}" target="_blank" rel="noopener" class="ref-campus-link">Source ↗</a>` +
          `</div>`,
          { maxWidth: 300 }
        );
        shipyardLayer.addLayer(marker);
      }
      rerenderLegend();
    })
    .catch((err) => {
      console.error("Shipyards overlay load failed:", err);
      shipyardsLoadingPromise = null;
    });
  return shipyardsLoadingPromise;
}

// Retired heavy-industrial overlay — large closed smelters / mills / plants
// (EPA GHGRP facilities that ceased reporting). Each is a candidate DC site:
// a closed aluminum smelter or steel mill leaves a large stranded grid
// interconnection. Generated by scripts/build_retired_industrial.py. Mirrors
// the reference-campus overlay pattern (lazy-loaded, own layer + legend row).
function ensureRetiredIndustrialLoaded() {
  if (retiredIndustrialLoadingPromise) return retiredIndustrialLoadingPromise;
  retiredIndustrialLoadingPromise = fetch(RETIRED_INDUSTRIAL_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, RETIRED_INDUSTRIAL_URL); // can be the freshest artifact in a GHGRP refresh
      retiredIndustrialSites = payload.sites || []; // feed the Retired Sites tab
      maybeRefreshRetired();
      if (!retiredIndustrialLayer) return; // map not yet initialized
      for (const s of retiredIndustrialSites) {
        if (s.lat == null || s.lon == null) continue;
        const icon = L.divIcon({
          className: "retired-industrial-icon",
          html: "<span>◆</span>",
          iconSize: [18, 18],
          iconAnchor: [9, 9],
          popupAnchor: [0, -10],
        });
        const marker = L.marker([s.lat, s.lon], { icon, zIndexOffset: 400 });
        const place = [s.city, s.state].filter(Boolean).join(", ");
        const reason = s.reporting_status === "valid_reason"
          ? "ceased GHGRP reporting (a reason was stated)"
          : "ceased GHGRP reporting (reason unknown — could be closed, idled, or below threshold)";
        // Stable per-facility citation page, derivable from the GHGRP id
        // (verified 200 as of 2026-07-02): EPA Envirofacts GHG facility detail.
        const efUrl = `https://enviro.epa.gov/envirofacts/ghg/facility-detail/${encodeURIComponent(String(s.id).replace("GHGRP-", ""))}`;
        // Nearby tracked-program context. This is centroid/geocode proximity,
        // not proof of parcel identity, ownership, or availability.
        const trackedHtml = s.tracked_site_id
          ? `<div class="ref-campus-prev" style="margin-top:6px"><strong>Nearby tracked record (proximity only):</strong> ${escapeHtml(s.tracked_site_program || "brownfield")} record ${fmt.miles(s.tracked_site_mi)} away — <a href="?site=${encodeURIComponent(s.tracked_site_id)}">${escapeHtml(s.tracked_site_name || s.tracked_site_id)} →</a>. This point match does not establish that the records share a parcel; verify boundaries and ownership independently.</div>`
          : `<div class="ref-campus-prev" style="margin-top:6px">No Superfund, ACRES, FUDS, or BRAC record found within 1 mi. Parcel availability remains unverified.</div>`;
        marker.bindPopup(
          `<div class="ref-campus-popup">` +
          `<strong>${escapeHtml(s.name)}</strong>` +
          `<div class="ref-campus-company">${escapeHtml(s.sector)}</div>` +
          (place ? `<div class="ref-campus-prev">${escapeHtml(place)}</div>` : "") +
          `<div class="ref-campus-meta">` +
            (s.last_report_year ? `<span>Last reported ${escapeHtml(String(s.last_report_year))}</span>` : "") +
            (s.parent_company ? `<span>${escapeHtml(s.parent_company)}</span>` : "") +
          `</div>` +
          `<div class="ref-campus-prev" style="margin-top:6px">Screening signal — ${escapeHtml(reason)}. A former large-load facility may retain reusable grid infrastructure worth diligence; not a confirmed-available or still-connected site. <a href="${efUrl}" target="_blank" rel="noopener">EPA facility record →</a></div>` +
          trackedHtml +
          `</div>`,
          { maxWidth: 280 }
        );
        retiredIndustrialLayer.addLayer(marker);
      }
      rerenderLegend();
    })
    .catch((err) => {
      console.error("Retired industrial overlay load failed:", err);
      retiredIndustrialLoadingPromise = null;
    });
  return retiredIndustrialLoadingPromise;
}

// Announced-retirement power plants — OPERATING plants ≥100 MW with a filed
// retirement date (EIA-860M Operating sheet). Forward-looking counterpart to
// the retired-plant / retired-industrial overlays: the interconnect frees up
// on a known date (the Homer City pattern — deal struck before the lights go
// out). Generated by scripts/build_planned_retirements.py.
function ensurePlannedRetirementsLoaded() {
  if (plannedRetirementsLoadingPromise) return plannedRetirementsLoadingPromise;
  plannedRetirementsLoadingPromise = fetch(PLANNED_RETIREMENTS_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, PLANNED_RETIREMENTS_URL);
      if (!plannedRetirementLayer) return; // map not yet initialized
      for (const s of payload.sites || []) {
        if (s.lat == null || s.lon == null) continue;
        const icon = L.divIcon({
          className: "planned-retirement-icon",
          html: "<span>⬢</span>",
          iconSize: [18, 18],
          iconAnchor: [9, 9],
          popupAnchor: [0, -10],
        });
        const marker = L.marker([s.lat, s.lon], { icon, zIndexOffset: 400 });
        const place = [s.county, s.state].filter(Boolean).join(" County, ");
        const years = s.first_retirement_year === s.last_retirement_year
          ? String(s.first_retirement_year)
          : `${s.first_retirement_year}–${s.last_retirement_year}`;
        marker.bindPopup(
          `<div class="ref-campus-popup">` +
          `<strong>${escapeHtml(s.name)}</strong>` +
          `<div class="ref-campus-company">${escapeHtml(Math.round(s.mw).toLocaleString())} MW ${escapeHtml(s.fuel)} · retiring ${escapeHtml(years)}</div>` +
          (place ? `<div class="ref-campus-prev">${escapeHtml(place)}</div>` : "") +
          `<div class="ref-campus-meta">` +
            (s.balancing_authority ? `<span>${escapeHtml(s.balancing_authority)}</span>` : "") +
            (s.operator ? `<span>${escapeHtml(s.operator)}</span>` : "") +
          `</div>` +
          `<div class="ref-campus-prev" style="margin-top:6px">Announced retirement (EIA-860M) — a dated hand-off of a large grid interconnection. Candidate for replacement generation (nuclear / gas / solar+storage) or a co-located large load; dates can slip.</div>` +
          `</div>`,
          { maxWidth: 280 }
        );
        plannedRetirementLayer.addLayer(marker);
      }
      rerenderLegend();
    })
    .catch((err) => {
      console.error("Planned retirements overlay load failed:", err);
      plannedRetirementsLoadingPromise = null;
    });
  return plannedRetirementsLoadingPromise;
}

// Coal reinvestment (nuclear / data center) conversion overlay (Spec 04)
function ensureCoalConversionsLoaded() {
  if (coalConversionsLoadingPromise) return coalConversionsLoadingPromise;
  coalConversionsLoadingPromise = fetch(COAL_CONVERSIONS_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { assets: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, COAL_CONVERSIONS_URL);
      coalConversionAssets = payload.assets || [];
      coalConversionsSettled = true;      // even a genuine empty is settled
      coalConversionsLoadFailed = false;  // — not retryable, unlike a failure
      window.__coalAssets = coalConversionAssets; // e2e hook, like __sites
      if (!coalConversionLayer) return;
      for (const s of coalConversionAssets) {
        if (s.latitude == null || s.longitude == null) continue;
        // Glyph directly in the icon div (no inner span) — halves marker DOM
        // cost; the 5,000-node first-paint budget has ~60 nodes of headroom.
        const icon = L.divIcon({
          className: "coal-repowering-icon",  // class name kept stable (CSS + e2e)
          html: "⬢",
          iconSize: [18, 18],
          iconAnchor: [9, 9],
          popupAnchor: [0, -10],
        });
        const marker = L.marker([s.latitude, s.longitude], { icon, zIndexOffset: 410 });
        coalMarkersByName.set(s.plant_name, marker);
        const place = [s.county, s.state].filter(Boolean).join(" County, ");
        const strandedM = (s.est_stranded_asset_value_usd / 1_000_000).toFixed(1);
        const statusLabel = COAL_STATUS_LABELS[s.status] || s.status;
        marker.bindPopup(
          `<div class="ref-campus-popup">` +
          `<strong>${escapeHtml(s.plant_name)}</strong>` +
          `<div class="ref-campus-company">${escapeHtml(Math.round(s.nameplate_coal_mw).toLocaleString())} MW Coal (${escapeHtml(statusLabel)}) · ${escapeHtml(s.switchyard_kv)} kV Switchyard</div>` +
          (place ? `<div class="ref-campus-prev">${escapeHtml(place)} · ${escapeHtml(s.iso_rto)}</div>` : "") +
          `<div class="ref-campus-meta">` +
            `<span>Modeled value: ~$${strandedM}M</span>` +
            (s.has_water_intake ? `<span>Water intake</span>` : "") +
            (s.has_rail ? `<span>Rail loop</span>` : "") +
            (s.queue_transfer_eligible ? `<span style="color:var(--readiness-ready)">Interconnection review needed</span>` : "") +
          `</div>` +
          `<div class="ref-campus-prev" style="margin-top:6px">Reported plant assets may warrant reuse investigation. DOE/INL modeled 15–35% savings for studied coal-to-nuclear scenarios; no site-specific savings, asset availability or transferable rights are verified here. Value is a modeled estimate.</div>` +
          `<button type="button" class="coal-popup-btn">Explore in Coal Tab &rarr;</button>` +
          `</div>`,
          { maxWidth: 290 }
        );
        // Bind the popup button on open with the closured name — inline
        // onclick + hand-rolled quote escaping is how names with apostrophes
        // become injection/SyntaxError bugs (code review 2026-08-23 #1).
        marker.on("popupopen", (ev) => {
          const btn = ev.popup.getElement()?.querySelector(".coal-popup-btn");
          if (btn) btn.addEventListener("click", () => window.__openCoalTabForPlant(s.plant_name), { once: true });
        });
        coalConversionLayer.addLayer(marker);
      }
      rerenderLegend();
    })
    .catch((err) => {
      console.error("Coal conversions overlay load failed:", err);
      coalConversionsLoadFailed = true;
      coalConversionsLoadingPromise = null; // nulled so the next call retries
      if (typeof buildCoalView === "function") buildCoalView();
    });
  return coalConversionsLoadingPromise;
}

// Federal land-program overlay — DOE EM / OCED CEML (Spec 08)
function ensureFederalCleanEnergyLoaded() {
  if (federalCleanEnergyLoadingPromise) return federalCleanEnergyLoadingPromise;
  federalCleanEnergyLoadingPromise = fetch(FEDERAL_CLEAN_ENERGY_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, FEDERAL_CLEAN_ENERGY_URL);
      if (!federalCleanEnergyLayer) return;
      for (const s of payload.sites || []) {
        if (s.latitude == null || s.longitude == null) continue;
        const icon = L.divIcon({
          className: "federal-site-icon",
          html: "🏛",
          iconSize: [20, 20],
          iconAnchor: [10, 10],
          popupAnchor: [0, -10],
        });
        const marker = L.marker([s.latitude, s.longitude], { icon, zIndexOffset: 420 });
        const place = [s.county, s.state].filter(Boolean).join(" County, ");
        // Render enum slugs as prose ("RFQ_Awarded" → "RFQ Awarded",
        // "datacenter_ai" → "datacenter ai") — no raw underscores to users.
        const deslug = (v) => String(v || "").replace(/_/g, " ");
        const techList = (s.target_technologies || []).map(deslug).join(", ");
        // Offered/developable acreage is the actionable number when the
        // program has named one; the reservation total is context, not land
        // on the table (INL offers ~44k of 570k ac — never conflate).
        const acresLabel = s.offered_acreage != null
          ? `${Math.round(s.offered_acreage).toLocaleString()} ac offered of ${Math.round(s.available_acreage).toLocaleString()}-ac site`
          : `${Math.round(s.available_acreage).toLocaleString()} Acres`;
        marker.bindPopup(
          `<div class="ref-campus-popup">` +
          `<strong>${escapeHtml(s.site_name)}</strong>` +
          `<div class="ref-campus-company">${escapeHtml(s.managing_office)} · ${escapeHtml(acresLabel)} (${escapeHtml(deslug(s.program_stage))})</div>` +
          (place ? `<div class="ref-campus-prev">${escapeHtml(place)}</div>` : "") +
          (s.commercial_partner ? `<div class="ref-campus-meta"><span>Partner: ${escapeHtml(s.commercial_partner)}</span></div>` : "") +
          `<div class="ref-campus-meta"><span>Target: ${escapeHtml(techList)}</span></div>` +
          (s.solicitation_url ? `<div style="margin-top:6px"><a href="${escapeHtml(s.solicitation_url)}" target="_blank" rel="noopener noreferrer" style="color:var(--accent);font-weight:600">View Federal Solicitation &rarr;</a></div>` : "") +
          `</div>`,
          { maxWidth: 300 }
        );
        federalCleanEnergyLayer.addLayer(marker);
      }
      rerenderLegend();
    })
    .catch((err) => {
      console.error("Federal energy-program overlay load failed:", err);
      federalCleanEnergyLoadingPromise = null;
    });
  return federalCleanEnergyLoadingPromise;
}

// Coal conversions proximity join (Spec 04)
//
// The payload is CACHED and the apply is IDEMPOTENT: when the page boots
// with a restricted `?program=` URL the ACRES/FUDS/BRAC promises are null,
// so the initial apply only reaches eager Superfund records — the three
// program loaders call applyCoalProxJoin() again as their records land
// (Codex review 2026-08-23 round 3), and the skip-if-present guard makes
// every re-apply a cheap no-op for already-joined ids.
let coalProxMatches = null;      // settled payload (even if empty)
let coalProxLoadFailed = false;  // last attempt errored — retryable
function applyCoalProxJoin({ refresh = false } = {}) {
  if (!coalProxMatches) return;
  let applied = 0;
  for (const rec of coalProxMatches) {
    const existing = sitesById.get(rec.id);
    if (!existing || existing.coal_conversion_plant_name != null) continue;
    existing.coal_conversion_plant_name = rec.coal_conversion_plant_name;
    if (rec.coal_conversion_plant_mi != null) existing.coal_conversion_plant_mi = rec.coal_conversion_plant_mi;
    if (rec.coal_conversion_mw != null) existing.coal_conversion_mw = rec.coal_conversion_mw;
    if (rec.coal_conversion_switchyard_kv != null) existing.coal_conversion_switchyard_kv = rec.coal_conversion_switchyard_kv;
    if (rec.coal_conversion_rail != null) existing.coal_conversion_rail = rec.coal_conversion_rail;
    if (rec.coal_conversion_water != null) existing.coal_conversion_water = rec.coal_conversion_water;
    if (rec.coal_conversion_stranded_val_usd != null) existing.coal_conversion_stranded_val_usd = rec.coal_conversion_stranded_val_usd;
    if (rec.coal_conversion_queue_fasttrack != null) existing.coal_conversion_queue_fasttrack = rec.coal_conversion_queue_fasttrack;
    applied++;
  }
  if (refresh && applied) {
    applyFilter();
    if (selectedId && sitesById.has(selectedId)) {
      // Fail loud: a broken re-render here would otherwise leave a stale
      // open detail panel with no diagnosable signal (Codex round 6).
      try {
        selectSite(selectedId);
      } catch (err) {
        console.error("selectSite re-render after coal join failed:", err);
      }
    }
  }
}

function ensureCoalConversionsProxLoaded() {
  if (coalProxLoadingPromise) return coalProxLoadingPromise;
  coalProxLoadingPromise = fetch(COAL_PROX_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { matches: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(async (payload) => {
      recordRefreshDate(payload.generated_at, COAL_PROX_URL);
      coalProxMatches = payload.matches || [];
      coalProxLoadFailed = false;
      await Promise.allSettled(
        [acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)
      );
      applyCoalProxJoin({ refresh: true });
    })
    .catch((err) => {
      console.error("Coal conversions proximity load failed:", err);
      coalProxLoadFailed = true;
      coalProxLoadingPromise = null; // nulled so the next call retries
    });
  return coalProxLoadingPromise;
}

// ----- Civilian nuclear pipeline overlay -----
//
// docs/data/nuclear-civilian-sites.json — existing and planned CIVILIAN
// nuclear sites, tiered by Idaho National Laboratory's Aug-2024 AP1000
// deployment study (INL/MIS-24-80216) and extended with announced restarts
// and post-study entrants. Like reference-campuses / retired-industrial /
// planned-retirements this is an OVERLAY, not a SiteRecord set — it never
// joins into `sitesById`, so the enrichment load-order race rule doesn't
// apply. The companion proximity file lists the tracked Superfund sites
// within 50 mi of each nuclear site (rendered in the popup).
//
// Only the four promising tiers get markers; the yellow / red tiers stay
// data-only (29 markers vs 68 rows keeps the map readable).
const NUCLEAR_CATEGORIES = {
  dark_green:  { label: "AP1000 ready",              cls: "nuclear-cat-ready",    chip: "cat-ready",    order: 0 },
  light_green: { label: "AP1000 feasible",           cls: "nuclear-cat-feasible", chip: "cat-feasible", order: 1 },
  blue:        { label: "Restart / SMR",             cls: "nuclear-cat-restart",  chip: "cat-restart",  order: 2 },
  post_study:  { label: "New entrant (post-2024 study)", cls: "nuclear-cat-restart", chip: "cat-restart", order: 3 },
};
// Iterate this — never hardcode the member list or a count (same drift rule
// as PROGRAM_LEGEND / UAT-007). A new promising tier only needs an entry in
// NUCLEAR_CATEGORIES plus its slug here.
const NUCLEAR_MAPPED_CATEGORIES = ["dark_green", "light_green", "blue", "post_study"];

function nuclearIsMapped(site) {
  return NUCLEAR_MAPPED_CATEGORIES.includes(site && site.inl_category);
}

// Source vocabularies are snake_case slugs (`col_issued`, `esp_approved`,
// `nrc_pre_application`). Render them as prose without a hardcoded label
// table that would go stale when the source adds a value.
const NUCLEAR_ACRONYMS = new Set(["nrc", "col", "cola", "esp", "smr", "inl", "tva", "ser", "eis", "noi"]);
function nuclearLabel(v) {
  if (!v) return "—";
  const words = String(v).split("_").filter(Boolean);
  return words
    .map((w, i) => {
      if (NUCLEAR_ACRONYMS.has(w)) return w.toUpperCase();
      if (i === 0) return w.charAt(0).toUpperCase() + w.slice(1);
      return w;
    })
    .join(" ");
}

function nuclearCapacityText(s) {
  if (s.units_planned == null && s.mwe_per_unit == null) return null;
  const units = s.units_planned != null ? s.units_planned : "?";
  const mwe = s.mwe_per_unit != null ? s.mwe_per_unit.toLocaleString() : "?";
  return `${units} × ${mwe} MWe`;
}

function nuclearPopupHtml(s) {
  const cat = NUCLEAR_CATEGORIES[s.inl_category] || { label: s.inl_category, chip: "cat-restart" };
  const capacity = nuclearCapacityText(s);
  const place = [s.city, s.county ? `${s.county} County` : null, s.state].filter(Boolean).join(", ");
  const notes = s.notes && s.notes.length > 200 ? s.notes.slice(0, 197).trimEnd() + "…" : s.notes;
  const sourceUrl = s.nrc_url || s.reference_url;
  const nearby = (nuclearProximityById.get(s.id) || []).slice(0, 3);
  // An unavailable proximity file must render as UNAVAILABLE — the definitive
  // "No tracked Superfund site within 50 mi" claim is reserved for data we
  // actually loaded (never turn a fetch failure into a false negative).
  const nearbyHtml = nearby.length
    ? `<div class="nuke-pop-near"><strong>Nearby tracked brownfields</strong><ul>` +
      nearby
        .map(
          (n) =>
            `<li><a href="?site=${encodeURIComponent(n.id)}">${escapeHtml(prettyName(n.name) || n.id)}</a>` +
            ` · ${fmt.miles(n.distance_mi)}</li>`
        )
        .join("") +
      `</ul></div>`
    : nuclearProxFailed
    ? `<div class="nuke-pop-near muted">Nearby-brownfield data unavailable.</div>`
    : `<div class="nuke-pop-near">No tracked Superfund site within 50 mi.</div>`;
  return (
    `<div class="ref-campus-popup">` +
    `<strong>${escapeHtml(s.name)}</strong>` +
    `<div class="nuke-pop-cat ${cat.chip}">${escapeHtml(cat.label)}</div>` +
    (place ? `<div class="ref-campus-company">${escapeHtml(place)}</div>` : "") +
    `<div class="ref-campus-meta">` +
      `<span>${escapeHtml(nuclearLabel(s.status))}</span>` +
      `<span>COL: ${escapeHtml(nuclearLabel(s.col_status))}</span>` +
      (capacity ? `<span>${escapeHtml(capacity)}</span>` : "") +
      (s.iso_rto ? `<span>${escapeHtml(s.iso_rto)}</span>` : "") +
    `</div>` +
    (s.owner_operator ? `<div class="ref-campus-prev">${escapeHtml(s.owner_operator)}</div>` : "") +
    (notes ? `<div class="ref-campus-prev" style="font-style:normal">${escapeHtml(notes)}</div>` : "") +
    nearbyHtml +
    (sourceUrl
      ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener" class="ref-campus-link">Source ↗</a>`
      : "") +
    `</div>`
  );
}

function ensureNuclearSitesLoaded() {
  if (nuclearSitesLoadingPromise) return nuclearSitesLoadingPromise;
  // A fresh attempt clears BOTH prior failure flags — a recovered retry must
  // let a legitimately-empty proximity list render as the verified negative
  // again, not a stale "unavailable" (Codex review #6, PR #20).
  nuclearSitesLoadFailed = false;
  nuclearProxFailed = false;
  const attempt = ++nuclearLoadAttempt;
  // Any non-OK response (404 included) throws. For the PRIMARY dataset that
  // routes to the section's error state; for the SECONDARY proximity file the
  // catch below tolerates the failure but flags it, so popups say
  // "unavailable" rather than claiming a verified no-sites-nearby (Codex
  // reviews #2 and #5 — a 404 on either file must never masquerade as data).
  const grab = (url) =>
    fetch(url, { priority: "low" })
      .then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      });
  nuclearSitesLoadingPromise = Promise.all([
    grab(NUCLEAR_SITES_URL),
    // Small (~180 KB) and needed the moment a popup opens, so it rides along
    // with the main file rather than paying a second round-trip on click.
    grab(NUCLEAR_BROWNFIELD_PROX_URL).catch((err) => {
      // Tolerated (the overlay still works) but FLAGGED: popups must render
      // "unavailable", never the false-negative "No tracked Superfund site
      // within 50 mi" (Codex reviews #4 + #5, PR #20 — includes 404s).
      // Guard on the attempt token: a superseded attempt's zombie fetch
      // failing late must not stamp stale failure state onto a newer,
      // successful attempt (Codex review #7 — defensive: bound popups are
      // static HTML and were already immune, but the flag stays honest).
      console.error("Nuclear brownfield-proximity load failed:", err);
      if (attempt === nuclearLoadAttempt) nuclearProxFailed = true;
      return { records: [] };
    }),
  ])
    .then(([payload, prox]) => {
      // Both files carry generated_at and can be the freshest artifact on
      // disk — see CLAUDE.md "Last-update date".
      recordRefreshDate(payload.generated_at, NUCLEAR_SITES_URL);
      recordRefreshDate(prox.generated_at, NUCLEAR_BROWNFIELD_PROX_URL);
      nuclearCivilianSites = payload.sites || [];
      nuclearSitesLoadSettled = true;
      for (const rec of prox.records || []) {
        nuclearProximityById.set(rec.nuclear_site_id, rec.nearby_brownfields || []);
      }
      maybeRefreshNuclearCivilian();
      if (!nuclearSiteLayer) return; // map not yet initialized
      for (const s of nuclearCivilianSites) {
        if (s.lat == null || s.lon == null) continue;
        if (!nuclearIsMapped(s)) continue;
        const cat = NUCLEAR_CATEGORIES[s.inl_category];
        const icon = L.divIcon({
          // Glyph goes straight in the icon div — no inner <span> like the
          // older overlays. 29 markers × 1 node instead of 2 keeps the
          // first-paint DOM budget (see CLAUDE.md "Paginated table").
          className: `nuclear-site-icon ${cat.cls}`,
          // U+FE0E forces TEXT presentation — without it the atom renders as
          // a pale color emoji that ignores the CSS tier color.
          html: "⚛︎",
          iconSize: [22, 22],
          iconAnchor: [11, 11],
          popupAnchor: [0, -12],
        });
        const marker = L.marker([s.lat, s.lon], { icon, zIndexOffset: 450 });
        marker.bindPopup(nuclearPopupHtml(s), { maxWidth: 300 });
        nuclearSiteLayer.addLayer(marker);
        nuclearMarkersById.set(s.id, marker);
      }
      rerenderLegend();
    })
    .catch((err) => {
      console.error("Civilian nuclear overlay load failed:", err);
      // Reset for retry AND surface the failure — without this the tab
      // section sits on "Loading…" forever (Codex review, PR #20).
      nuclearSitesLoadingPromise = null;
      nuclearSitesLoadFailed = true;
      maybeRefreshNuclearCivilian();
    });
  return nuclearSitesLoadingPromise;
}

// ----- Map -----
function initMap() {
  const renderer = L.canvas({ padding: 0.5 });
  // Don't chain `.fitBounds()` on the constructor. If the map container is
  // 0×0 at first paint (headless preview, hidden tab, zero-size embed),
  // Leaflet's `_limitCenter` divides by container size and produces NaN
  // coordinates, which throws "Invalid LatLng object: (NaN, NaN)". Before
  // 2026-05-06 that throw bubbled out of `initMap()` BEFORE `markerLayer`
  // was created, leaving the layer `undefined` and crashing every
  // subsequent `markerLayer.addLayer(...)` call (UAT-011). Create the map
  // first; defer fitBounds to `fitUsBoundsSafely()` which retries on resize.
  map = L.map("map", {
    preferCanvas: true,
    center: [37, -96],
    zoom: 4,
    renderer,
    zoomControl: true,
    tap: false,
    minZoom: MIN_ZOOM,
    maxBounds: US_BOUNDS,
    maxBoundsViscosity: 1.0,
    worldCopyJump: false,
    attributionControl: true,
  });

  map.attributionControl.setPrefix("").addAttribution(BASEMAP_ATTRIB);
  // The Leaflet container background is the "ocean" outside CONUS.
  document.getElementById("map").style.background = cssColor("--map-ocean");

  // markerLayer must exist before any caller tries to add markers — the
  // BRAC / FUDS / ACRES lazy-loads run via `Promise.allSettled` and assume
  // the layer is ready. Create it BEFORE `fitUsBoundsSafely()` so a deferred
  // fitBounds (zero-size container) doesn't strand callers with `undefined`.
  markerLayer = L.layerGroup().addTo(map);
  window.__markerLayer = markerLayer;
  window.__map = map;
  // Reference campus star markers sit above program markers (higher z-index).
  referenceCampusLayer = L.layerGroup().addTo(map);
  // Retired heavy-industrial overlay (candidate sites with stranded grid).
  retiredIndustrialLayer = L.layerGroup().addTo(map);
  // Announced-retirement power plants (interconnects freeing up 2026+).
  plannedRetirementLayer = L.layerGroup().addTo(map);
  // Civilian nuclear pipeline (⚛) — existing/planned reactor sites.
  nuclearSiteLayer = L.layerGroup().addTo(map);
  microCommitmentLayer = L.layerGroup().addTo(map);
  coalConversionLayer = L.layerGroup().addTo(map);
  federalCleanEnergyLayer = L.layerGroup().addTo(map);
  // Hanford E2E parcel markers (▣) — nine named land units of one DOE site.
  hanfordParcelLayer = L.layerGroup().addTo(map);
  // Principal ports (⚓) and curated shipyards (⚒) — Maritime Siting tab.
  portLayer = L.layerGroup().addTo(map);
  nickelAnchorLayer = L.layerGroup().addTo(map);
  shipyardLayer = L.layerGroup().addTo(map);

  // The first visible Map activation fits the overview. Do not register a
  // hidden-container resize fit that can overwrite a later parcel target.

  drawBasemap();
  drawInsetBoxes();

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

// Run `fitBounds(US_BOUNDS)` if the container has real dimensions; otherwise
// defer to the first `ResizeObserver` tick that reports a non-zero size and
// retry. The throw path on a 0×0 container is caught silently — Leaflet's
// inner state isn't corrupted, only the bounds-fit math fails. After a
// successful retry we call `invalidateSize()` so any cached zero-viewport
// state is recomputed before tiles/markers paint.
let _fitBoundsObserver = null;
function fitUsBoundsSafely() {
  const mapEl = document.getElementById("map");
  const tryFit = () => {
    try {
      map.fitBounds(US_BOUNDS, { padding: [10, 10], animate: false });
      return true;
    } catch (e) {
      // Expected when container is 0×0; we'll retry on resize. Log at
      // warn level so the existing "non-fatal" outer catch isn't tripped.
      console.warn("fitBounds deferred (zero-size container):", e?.message || e);
      return false;
    }
  };
  if (mapEl && mapEl.getBoundingClientRect().width > 0 && tryFit()) {
    _fitBoundsObserver?.disconnect();
    _fitBoundsObserver = null;
    return;
  }
  if (_fitBoundsObserver || typeof ResizeObserver === "undefined") return;
  _fitBoundsObserver = new ResizeObserver(() => {
    if (!mapEl || mapEl.getBoundingClientRect().width === 0) return;
    if (tryFit()) {
      _fitBoundsObserver.disconnect();
      _fitBoundsObserver = null;
      map.invalidateSize();
    }
  });
  _fitBoundsObserver.observe(mapEl);
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

let mapMarkersEnabled = false;
let mapReadyPromise = null;
let mapOverviewShown = false;
function ensureMapMarkersReady() {
  if (mapReadyPromise) return mapReadyPromise;
  mapMarkersEnabled = true;
  const core = window.__APP_READY__ ? Promise.resolve() : new Promise(resolve => document.addEventListener("brownfield:ready", resolve, {once:true}));
  mapReadyPromise = core.then(() => hydrateMarkersChunked(sites)).then(() => {
    applyMarkerVisibility(); window.__MAP_READY__ = true; document.dispatchEvent(new CustomEvent("brownfield:map-ready"));
  });
  return mapReadyPromise;
}

function addOneMarker(s, strokeColor) {
  if (!mapMarkersEnabled) return;
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
  if (!mapMarkersEnabled) return Promise.resolve();
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

let legendExpanded = window.matchMedia("(min-width: 640px)").matches;

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
    // Reference campus row — shown after program rows when campuses are loaded.
    const refRow = (referenceCampusLayer && referenceCampusLayer.getLayers().length > 0)
      ? `<div class="legend-row legend-row-ref">` +
        `<span class="legend-star">★</span>` +
        `<span class="legend-label">Confirmed deal</span>` +
        `<span class="legend-num">${referenceCampusLayer.getLayers().length}</span>` +
        `</div>`
      : "";
    // Retired heavy-industrial row — candidate sites with stranded grid.
    const retRow = (retiredIndustrialLayer && retiredIndustrialLayer.getLayers().length > 0)
      ? `<div class="legend-row legend-row-ref">` +
        `<span class="legend-diamond">◆</span>` +
        `<span class="legend-label">Retired industrial</span>` +
        `<span class="legend-num">${retiredIndustrialLayer.getLayers().length}</span>` +
        `</div>`
      : "";
    // Announced-retirement plants — interconnects freeing up on a known date.
    const plannedRow = (plannedRetirementLayer && plannedRetirementLayer.getLayers().length > 0)
      ? `<div class="legend-row legend-row-ref">` +
        `<span class="legend-hex">⬢</span>` +
        `<span class="legend-label">Retiring plant</span>` +
        `<span class="legend-num">${plannedRetirementLayer.getLayers().length}</span>` +
        `</div>`
      : "";
    // Civilian nuclear pipeline — ONE row (the readiness tier lives in the
    // popup; three sub-rows would overwhelm a five-row legend).
    const nukeRow = (nuclearSiteLayer && nuclearSiteLayer.getLayers().length > 0)
      ? `<div class="legend-row legend-row-ref">` +
        `<span class="legend-atom">⚛︎</span>` +
        `<span class="legend-label">Nuclear pipeline site</span>` +
        `<span class="legend-num">${nuclearSiteLayer.getLayers().length}</span>` +
        `</div>`
      : "";
    // Named microreactor commitments — ANPI base pairings, Janus candidate
    // installations, DOE pilot reactors, and sited commercial deals.
    const microRow = (microCommitmentLayer && microCommitmentLayer.getLayers().length > 0)
      ? `<div class="legend-row legend-row-ref">` +
        `<span class="legend-hexagon">\u2b23</span>` +
        `<span class="legend-label">Microreactor commitment</span>` +
        `<span class="legend-num">${microCommitmentLayer.getLayers().length}</span>` +
        `</div>`
      : "";
    // Coal reinvestment assets (EIA/DOE)
    const coalRow = (coalConversionLayer && coalConversionLayer.getLayers().length > 0)
      ? `<div class="legend-row legend-row-ref">` +
        `<span class="legend-coal">⬢</span>` +
        `<span class="legend-label">Coal reinvestment asset</span>` +
        `<span class="legend-num">${coalConversionLayer.getLayers().length}</span>` +
        `</div>`
      : "";
    // Federal land-program reservations (DOE EM / OCED CEML)
    const fedRow = (federalCleanEnergyLayer && federalCleanEnergyLayer.getLayers().length > 0)
      ? `<div class="legend-row legend-row-ref">` +
        `<span class="legend-federal">🏛</span>` +
        `<span class="legend-label">Federal energy program</span>` +
        `<span class="legend-num">${federalCleanEnergyLayer.getLayers().length}</span>` +
        `</div>`
      : "";
    // DOE-site dossier parcels (Hanford + the lazy-loaded sibling sites).
    // Static glyph/label plus an integer count — nothing untrusted.
    const hanfordRow = (hanfordParcelLayer && hanfordParcelLayer.getLayers().length > 0)
      ? `<div class="legend-row legend-row-ref">` +
        `<span class="legend-hanford">▣</span>` +
        `<span class="legend-label">DOE site parcel</span>` +
        `<span class="legend-num">${hanfordParcelLayer.getLayers().length}</span>` +
        `</div>`
      : "";
    div.innerHTML =
      `<div class="legend-title"><span>Program</span></div>${rows}${refRow}${retRow}${plannedRow}${coalRow}${fedRow}${nukeRow}${microRow}${hanfordRow}` +
      `<div class="legend-foot">Marker size ∝ acreage (log)</div>`;
    // Principal ports (⚓) and shipyards (⚒) — built via safe DOM methods
    // (createElement/textContent, no HTML-string interpolation) rather than
    // appended into the innerHTML template above.
    const foot = div.querySelector(".legend-foot");
    _appendLegendGlyphRow(div, foot, "⚓", "Principal port", portLayer);
    _appendLegendGlyphRow(div, foot, "⚒", "Shipyard", shipyardLayer);
    _appendLegendGlyphRow(div, foot, "◈", "Nickel supply chain", nickelAnchorLayer);
    const disclosure = document.createElement("details");
    disclosure.className = "legend-disclosure";
    disclosure.open = legendExpanded;
    const summary = document.createElement("summary");
    summary.textContent = "Map legend";
    summary.style.cssText = "cursor:pointer;min-height:28px;display:list-item;list-style-position:inside";
    disclosure.appendChild(summary);
    while (div.firstChild) disclosure.appendChild(div.firstChild);
    div.appendChild(disclosure);
    disclosure.addEventListener("toggle", () => { legendExpanded = disclosure.open; });
    L.DomEvent.disableClickPropagation(div);
    return div;
  };
  legend.addTo(map);
}

// Inserts one `<div class="legend-row legend-row-ref">` before `before`,
// via createElement/textContent — no HTML-string parsing, so it needs no
// escaping and no innerHTML call. `layer` is a Leaflet layerGroup; the row
// is omitted entirely when it holds no markers.
function _appendLegendGlyphRow(container, before, glyph, label, layer) {
  if (!layer || layer.getLayers().length === 0) return;
  const row = document.createElement("div");
  row.className = "legend-row legend-row-ref";
  const glyphSpan = document.createElement("span");
  glyphSpan.className = "legend-anchor";
  glyphSpan.textContent = glyph;
  const labelSpan = document.createElement("span");
  labelSpan.className = "legend-label";
  labelSpan.textContent = label;
  const numSpan = document.createElement("span");
  numSpan.className = "legend-num";
  numSpan.textContent = layer.getLayers().length.toLocaleString();
  row.append(glyphSpan, labelSpan, numSpan);
  container.insertBefore(row, before);
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
  return (s._searchKey || "").includes(String(q).trim().toLowerCase());
}

// Tier ordering for the dcTier filter — higher rank = stricter tier.
// "any matched tier ≥ rank(filterState.dcTier)" is the inclusion test, so
// picking "colo" includes colo + hyperscale + mega; "hyperscale" includes
// hyperscale + mega; "mega" is the strictest.
const DC_TIER_RANK = { edge: 1, colo: 2, hyperscale: 3, mega: 4 };

function siteMatchesFilters(s, opts = {}) {
  sanitizeGeographicEvidence(s);
  if (filterState.programs.size && !filterState.programs.has(s.program)) return false;
  if (filterState.state && s.state !== filterState.state) return false;
  if (filterState.statuses.size && !filterState.statuses.has(s.npl_status_code || "")) return false;
  // Acreage slider is log-base-10; min=0 → 1ac threshold off (keep nulls).
  if (filterState.minAcreage > 0) {
    if (s.acreage == null) return false;
    if (s.acreage < Math.pow(10, filterState.minAcreage)) return false;
  }
  if (filterState.dcTier) {
    const tier = computeDcScore(s);
    if (!tier) return false;
    const need = DC_TIER_RANK[filterState.dcTier] || 0;
    const got = DC_TIER_RANK[tier] || 0;
    if (got < need) return false;
  }
  if (filterState.dcCandidate && s.data_center_reuse_candidate !== true) return false;
  if (filterState.oppZone && s.in_opportunity_zone !== true) return false;
  if (filterState.isoRto && s.iso_rto !== filterState.isoRto) return false;
  if (filterState.availableOnly && !siteIsAvailable(s)) return false;
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
  // Read from `tableState`, which was populated in `refreshTableForFilter()`
  // — every caller of `updateCountText()` runs that first via `applyFilter()`,
  // so the cache is always fresh and we avoid a second 47k-record scan.
  const q = filterState.q.trim().toLowerCase();
  const visible = tableState.filtered.length;
  const acreSum = tableState.filteredAcreSum || 0;
  const acreSites = tableState.filteredAcreSites || 0;
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
  updateKpiDeck();
  // The candidates view sources from tableState.filtered — rebuild it when
  // it's the active tab so global filter changes apply live there too.
  maybeRefreshCandidates();
  // Same contract for the microreactor siting screen — it ranks
  // tableState.filtered, so a filter change has to rebuild it live.
  maybeRefreshMicro();
  // Same contract for the Maritime Siting screen — it ranks
  // tableState.filtered too.
  maybeRefreshMaritime();
  // And the Nickel Refining screen, for the same reason.
  maybeRefreshNickel();
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
    filterState.programs.size !== PROGRAM_LEGEND.length ||
    filterState.dcTier !== "" ||
    filterState.dcCandidate ||
    filterState.oppZone ||
    filterState.isoRto !== "" ||
    filterState.availableOnly
  );
}

// Detail-panel accordions — session-memory for the four collapsible
// sections (owner / docs / infra / echo). On phones the default is closed
// (more compact bottom-sheet); on desktop the default is open (the panel
// has 100vh to work with). Once the user clicks a <summary>, their choice
// is recorded in DETAIL_SECTION_PREFS and replayed across site selections
// in the same session. Reload resets to the defaults.
const DETAIL_SECTION_IDS = ["owner", "docs", "infra", "echo"];
const DETAIL_SECTION_PREFS = new Map(); // sectionId -> bool (user's choice)
const DETAIL_SECTION_MQ = window.matchMedia("(max-width: 640px)");

function applyDetailSectionDefaults() {
  const mobile = DETAIL_SECTION_MQ.matches;
  for (const id of DETAIL_SECTION_IDS) {
    const section = document.querySelector(`.d-section[data-section="${id}"]`);
    if (!section) continue;
    if (DETAIL_SECTION_PREFS.has(id)) {
      section.open = DETAIL_SECTION_PREFS.get(id);
    } else {
      section.open = !mobile;
    }
  }
}

function wireDetailSections() {
  for (const id of DETAIL_SECTION_IDS) {
    const section = document.querySelector(`.d-section[data-section="${id}"]`);
    if (!section) continue;
    section.addEventListener("toggle", () => {
      DETAIL_SECTION_PREFS.set(id, section.open);
    });
  }
  // Resize / rotation handling — only re-apply if the user hasn't recorded
  // a preference (otherwise we'd thrash their explicit choice).
  const onChange = () => {
    const mobile = DETAIL_SECTION_MQ.matches;
    for (const id of DETAIL_SECTION_IDS) {
      if (DETAIL_SECTION_PREFS.has(id)) continue;
      const section = document.querySelector(`.d-section[data-section="${id}"]`);
      if (section) section.open = !mobile;
    }
  };
  if (DETAIL_SECTION_MQ.addEventListener) DETAIL_SECTION_MQ.addEventListener("change", onChange);
  else if (DETAIL_SECTION_MQ.addListener) DETAIL_SECTION_MQ.addListener(onChange);
}

// The KPI deck is always-open on every breakpoint — mobile used to collapse
// it behind a tap-to-expand summary chip, but the extra tap was the
// problem, not a feature; the deck now renders directly as a horizontally
// scrollable strip (see the mobile media query in style.css) with no
// disclosure interaction at all. `<summary>` stays in the DOM (`<details>`
// needs one child of that type) but is hidden on every breakpoint.
function wireKpiDisclosure() {
  const disc = el("kpi-disclosure");
  if (!disc) return;
  disc.open = window.matchMedia("(min-width: 640px)").matches;
}

function wireSearch() {
  const input = el("search");
  const dropdown = el("search-typeahead");
  if (filterState.q) input.value = filterState.q;
  // Debounce the geographic refit so we don't fitBounds on every keystroke.
  let refitTimer = null;
  const queueRefit = () => {
    if (refitTimer) clearTimeout(refitTimer);
    refitTimer = setTimeout(refitMapToFilters, 350);
  };
  let typeaheadIdx = -1; // currently highlighted suggestion (-1 = none)
  let typeaheadResults = [];
  const closeTypeahead = () => {
    if (!dropdown) return;
    dropdown.hidden = true;
    dropdown.innerHTML = "";
    typeaheadIdx = -1;
    typeaheadResults = [];
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  };
  const renderTypeahead = (q) => {
    if (!dropdown) return;
    const query = q.trim().toLowerCase();
    if (query.length < 2) { closeTypeahead(); return; }
    // Search the in-memory site index. Cap at 8 results — primary purpose is
    // "jump directly to a known site," not browse-via-typeahead.
    const matches = [];
    for (const s of sites) {
      if (!s._searchKey || !s.name) continue;
      if (!s._searchKey.includes(query)) continue;
      matches.push(s);
      if (matches.length >= 50) break; // Hard cap before sorting for perf.
    }
    // Rank: name-prefix > name-contains > city/state-contains.
    matches.sort((a, b) => {
      const an = (a.name || "").toLowerCase();
      const bn = (b.name || "").toLowerCase();
      const ap = an.startsWith(query) ? 0 : an.includes(query) ? 1 : 2;
      const bp = bn.startsWith(query) ? 0 : bn.includes(query) ? 1 : 2;
      if (ap !== bp) return ap - bp;
      return an.localeCompare(bn);
    });
    typeaheadResults = matches.slice(0, 8);
    if (!typeaheadResults.length) { closeTypeahead(); return; }
    dropdown.innerHTML = typeaheadResults.map((s, i) => {
      const programLabel = PROGRAM_LABEL[s.program] || s.program;
      const place = [s.city, s.state].filter(Boolean).join(", ");
      return `<li class="typeahead-item" role="option" id="typeahead-opt-${i}" data-id="${escapeAttr(s.id)}" data-program="${escapeAttr(s.program)}">` +
        `<span class="typeahead-name">${escapeHtml(s.name)}</span>` +
        (place ? `<span class="typeahead-meta">${escapeHtml(place)}</span>` : "") +
        `<span class="typeahead-program">${escapeHtml(programLabel)}</span>` +
        `</li>`;
    }).join("");
    dropdown.hidden = false;
    typeaheadIdx = -1;
    input.setAttribute("aria-expanded", "true");
  };
  const highlightTypeahead = (idx) => {
    if (!dropdown) return;
    const items = dropdown.querySelectorAll(".typeahead-item");
    items.forEach((li, i) => li.classList.toggle("active", i === idx));
    if (idx >= 0 && items[idx]) {
      input.setAttribute("aria-activedescendant", items[idx].id);
      items[idx].scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
    typeaheadIdx = idx;
  };
  const pickTypeahead = (idx) => {
    const s = typeaheadResults[idx];
    if (!s) return;
    closeTypeahead();
    input.blur();
    if (typeof window.__selectSite === "function") window.__selectSite(s.id);
    else selectSite(s.id);
  };
  input.addEventListener("input", () => {
    filterState.q = input.value;
    applyFilter();
    queueRefit();
    renderTypeahead(input.value);
  });
  input.addEventListener("focus", () => {
    if (input.value) renderTypeahead(input.value);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && (input.value || (dropdown && !dropdown.hidden))) {
      e.stopPropagation();
      closeTypeahead();
      if (input.value) {
        input.value = "";
        filterState.q = "";
        applyFilter();
      }
      return;
    }
    if (dropdown && !dropdown.hidden && typeaheadResults.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        highlightTypeahead((typeaheadIdx + 1) % typeaheadResults.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        highlightTypeahead(typeaheadIdx <= 0 ? typeaheadResults.length - 1 : typeaheadIdx - 1);
      } else if (e.key === "Enter" && typeaheadIdx >= 0) {
        e.preventDefault();
        pickTypeahead(typeaheadIdx);
      }
    }
  });
  if (dropdown) {
    dropdown.addEventListener("mousedown", (e) => {
      // mousedown (not click) so we fire before blur tears the dropdown down.
      const li = e.target.closest(".typeahead-item");
      if (!li) return;
      e.preventDefault();
      const idx = [...dropdown.children].indexOf(li);
      if (idx >= 0) pickTypeahead(idx);
    });
  }
  document.addEventListener("click", (e) => {
    if (!dropdown || dropdown.hidden) return;
    if (e.target === input || dropdown.contains(e.target)) return;
    closeTypeahead();
  });
}

// matchMedia for the bottom-sheet filter pattern. On phones, opening the
// filters dims a backdrop behind the sheet so the map underneath reads as
// "deferred"; closing it hides the backdrop. Desktop just toggles the
// inline strip's [hidden] attr — no backdrop, no body scroll lock.
const FILTER_SHEET_MQ = window.matchMedia("(max-width: 640px)");

function openFiltersUi() {
  const filters = el("filters");
  const toggle = el("filters-toggle");
  const backdrop = el("filters-backdrop");
  filters.hidden = false;
  toggle.setAttribute("aria-expanded", "true");
  if (FILTER_SHEET_MQ.matches && backdrop) backdrop.hidden = false;
  if (map) setTimeout(() => map.invalidateSize(), 50);
}

function closeFiltersUi() {
  const filters = el("filters");
  const toggle = el("filters-toggle");
  const backdrop = el("filters-backdrop");
  filters.hidden = true;
  toggle.setAttribute("aria-expanded", "false");
  if (backdrop) backdrop.hidden = true;
  if (map) setTimeout(() => map.invalidateSize(), 50);
}

function wireFilters() {
  const toggle = el("filters-toggle");
  toggle.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") === "true";
    if (expanded) closeFiltersUi();
    else openFiltersUi();
  });

  // Bottom-sheet specific controls — backdrop click, × button, "Done"
  // button all close the sheet. The desktop strip ignores these because
  // the sheet header/footer/backdrop are `display: none` above 640px.
  const backdrop = el("filters-backdrop");
  if (backdrop) backdrop.addEventListener("click", closeFiltersUi);
  const closeBtn = el("filters-sheet-close");
  if (closeBtn) closeBtn.addEventListener("click", closeFiltersUi);
  const doneBtn = el("filters-sheet-apply");
  if (doneBtn) doneBtn.addEventListener("click", closeFiltersUi);
  const sheetReset = el("filters-sheet-reset");
  if (sheetReset) {
    sheetReset.addEventListener("click", () => {
      // Delegate to the existing inline reset so we don't duplicate the
      // multi-step reset logic. The desktop Reset button is `display: none`
      // on mobile but its click handler still fires programmatically.
      const inlineReset = el("filters-reset");
      if (inlineReset) inlineReset.click();
    });
  }
  // Escape closes the sheet on mobile too.
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    if (toggle.getAttribute("aria-expanded") === "true") closeFiltersUi();
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

  const isoSel = el("f-iso-rto");
  if (isoSel) {
    isoSel.addEventListener("change", () => {
      filterState.isoRto = isoSel.value;
      applyFilter();
      refitMapToFilters();
    });
  }

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

  // Opportunity Zone filter checkbox. Reflects current filterState.oppZone
  // (set from URL on page load if `?oz=1`). Refit map after toggle so the
  // view zooms to whatever's left visible.
  const ozBox = el("f-opp-zone");
  if (ozBox) {
    ozBox.checked = filterState.oppZone;
    ozBox.addEventListener("change", () => {
      filterState.oppZone = !!ozBox.checked;
      applyFilter();
      refitMapToFilters();
    });
  }

  const availBox = el("f-available");
  if (availBox) {
    availBox.checked = filterState.availableOnly;
    availBox.addEventListener("change", () => {
      filterState.availableOnly = !!availBox.checked;
      if (filterState.availableOnly) ensureAcresCleanupLoaded();
      applyFilter();
      refitMapToFilters();
    });
  }

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
    filterState.dcTier = "";
    for (const id of ["evidence-status-filter","evidence-confidence-filter"]) if(el(id)) el(id).value="";
    filterState.dcCandidate = false;
    filterState.oppZone = false;
    filterState.isoRto = "";
    filterState.availableOnly = false;
    el("search").value = "";
    refreshPersonaButtons();
    refreshKpiActiveStates();
    // Reset must also un-check the OZ filter checkbox and available-only checkbox.
    const ozBox = el("f-opp-zone");
    if (ozBox) ozBox.checked = false;
    const availBox = el("f-available");
    if (availBox) availBox.checked = false;
    for (const [program, box] of Object.entries(progBoxes)) {
      if (box) box.checked = filterState.programs.has(program);
    }
    if (filterState.programs.has("brownfield")) ensureAcresLoaded();
    if (filterState.programs.has("fuds")) ensureFudsLoaded();
    if (filterState.programs.has("brac")) ensureBracLoaded();
    stateSel.value = "";
    if (isoSel) isoSel.value = "";
    for (const cb of el("f-status-checks").querySelectorAll("input[type=checkbox]")) cb.checked = false;
    acreEl.value = "0";
    acreVal.textContent = "0";
    applyFilter();
    // Reset zooms back out to the lower-48 default.
    if (map) map.fitBounds(US_BOUNDS, { padding: [10, 10], animate: true });
  });
}

// Persona presets — single tap toggles a `dcTier` constraint that funnels
// the visible set to "this minimum tier and stricter." Buttons act like
// radio: tapping the active one clears it. Iterates `PERSONA_PRESETS` so
// future tiers Just Work via the same drift-safe pattern as PROGRAM_LEGEND.
function wirePersonaButtons() {
  const wrap = el("f-personas");
  if (!wrap) return;
  wrap.innerHTML = PERSONA_PRESETS
    .map((t) =>
      `<button type="button" class="persona-btn" data-tier="${escapeAttr(t.id)}" aria-pressed="false">` +
      `<span class="persona-label">${escapeHtml(t.label)}</span>` +
      `<span class="persona-min">≥${t.minAcres.toLocaleString()} ac</span>` +
      `</button>`
    ).join("");
  wrap.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-tier]");
    if (!btn) return;
    const tier = btn.dataset.tier;
    if (filterState.dcTier === tier) {
      filterState.dcTier = "";  // toggle off
    } else {
      filterState.dcTier = tier;
    }
    refreshPersonaButtons();
    refreshKpiActiveStates();
    applyFilter();
    refitMapToFilters();
  });
  refreshPersonaButtons();
}

function refreshPersonaButtons() {
  const wrap = el("f-personas");
  if (!wrap) return;
  for (const btn of wrap.querySelectorAll("button[data-tier]")) {
    const active = btn.dataset.tier === filterState.dcTier;
    btn.setAttribute("aria-pressed", String(active));
    btn.classList.toggle("active", active);
  }
}

// KPI deck click-to-filter shortcuts. Two cells are wired:
//   data-kpi="hyperscale" → toggle the Hyperscale persona filter
//   data-kpi="dc"         → toggle the EPA RE-Powering DC candidate filter
// The other three cells (total / acreage / states) are non-actionable —
// they show overview metrics, not filterable predicates. Each actionable
// cell gets `role="button"` + `tabindex=0` + keyboard activation so the
// shortcut is a11y-equivalent to the filter panel.
function wireKpiClicks() {
  const map = {dc:"grid",hyperscale:"water",generation:"fiber",acreage:"land",acres:"land"};
  for (const cell of document.querySelectorAll("#kpi-deck [data-kpi]")) {
    const key=map[cell.dataset.kpi]; if(!key) continue;
    cell.setAttribute("role","button"); cell.tabIndex=0;
    const handler=()=>{window.__setView("candidates"); el("evidence-category-filter").value=key; el("evidence-status-filter").value="context"; el("evidence-confidence-filter").value=""; buildCandidatesView();};
    cell.addEventListener("click",handler); cell.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();handler();}});
  }
}
function refreshKpiActiveStates() {}

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

function populateIsoRtoFilter() {
  const sel = el("f-iso-rto");
  if (!sel) return;
  const current = sel.value || filterState.isoRto;
  const values = new Set();
  for (const s of sites) if (s.iso_rto) values.add(s.iso_rto);
  const ordered = Object.keys(ISO_RTO_LABELS).filter((value) => values.has(value));
  sel.innerHTML = `<option value="">Any ISO/RTO</option>` +
    ordered.map((value) =>
      `<option value="${escapeAttr(value)}">${escapeHtml(ISO_RTO_LABELS[value] || value)}</option>`
    ).join("");
  if (current && values.has(current)) {
    sel.value = current;
    filterState.isoRto = current;
  } else if (filterState.isoRto && values.size > 0) {
    filterState.isoRto = "";
    sel.value = "";
  } else {
    sel.value = "";
  }
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
  // The "not applicable" em-dash carries `muted-cell` on the <td> itself
  // rather than in a wrapper <span>. That span cost one DOM node per
  // affected cell on every one of the 250 rendered rows, and because the
  // number of rows needing it swings with which programs have finished
  // lazy-loading, it also made `test_dom_size_under_5k_nodes` measure a
  // moving target (255 muted spans vs 37 across two runs of the same
  // commit — the whole 218-node spread). Styling the cell is visually
  // identical and makes first-paint DOM deterministic. See issues.md
  // 2026-08-25 and the `#sites-table td.muted-cell` rule in style.css.
  let statusHtml;
  let statusCls = "";
  if (s.npl_status_code) {
    statusHtml = `<span class="pill" data-status="${escapeAttr(s.npl_status_code)}">${escapeHtml(s.npl_status || "Unknown")}</span>`;
  } else if (s.program === "fuds" && s.eligibility) {
    statusHtml = escapeHtml(s.eligibility);
  } else if (s.program === "brownfield" && s.cleanup_status) {
    const cls = s.cleanup_status === "Completed" ? " ready" : "";
    statusHtml = `<span class="cleanup-status${cls}">${escapeHtml(s.cleanup_status)}</span>`;
  } else {
    statusHtml = "—";
    statusCls = "muted-cell";
  }
  const dcScoreHtml = escapeHtml(SiteEvidence.assessSite(s).grid.finding);
  const dcScoreCls = "evidence-grid-cell";
  tr.innerHTML = `
    <td>${escapeHtml(s.name || "—")}</td>
    <td><span class="pill" data-program="${escapeAttr(s.program)}">${escapeHtml(programLabel)}</span></td>
    <td>${escapeHtml(s.state || "—")}</td>
    <td class="num">${fmt.acres(s.acreage)}</td>
    <td${statusCls ? ` class="${statusCls}"` : ""}>${statusHtml}</td>
    <td>${escapeHtml(s.city || "—")}</td>
    <td>${escapeHtml(s.county || "—")}</td>
    <td class="${dcScoreCls}">${dcScoreHtml}</td>
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
  // Same pass: capture the bbox of the visible set + counts/acreage totals
  // so `refitMapToFilters` and `updateCountText` don't sweep all 47k records
  // again on every filter toggle.
  let minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity;
  let count = 0;
  let acreSum = 0;
  let acreSites = 0;
  for (const s of tableState.filtered) {
    if (typeof s.acreage === "number") { acreSum += s.acreage; acreSites++; }
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
  tableState.filteredAcreSum = acreSum;
  tableState.filteredAcreSites = acreSites;
  const tbody = document.querySelector("#sites-table tbody");
  tbody.innerHTML = "";
  tableRowsById.clear();
  tableState.rendered = 0;
  if (el("view-table")?.classList.contains("active")) { appendNextPage(); setupTableInfiniteScroll(); }
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
      if (!entries.some((e) => e.isIntersecting)) return;
      const tableView = el("view-table");
      // A hidden table has a zero-height scroll root. Chromium can still
      // report its sentinel as intersecting, and the zero geometry makes the
      // remaining-scroll calculation below look exactly like "at bottom".
      // Ignore observer work until the Table tab owns a real viewport.
      if (!tableView?.classList.contains("active") || wrap.clientHeight <= 0) {
        return;
      }
      // Scroll-position guard. During the Map→Table tab transition (and in
      // headless contexts where layout settles in multiple passes) the
      // observer can fire several times before the sentinel's position
      // stabilises, prefetching up to 8 pages and inflating DOM size 8×.
      // Only honour the firing when the user has actually scrolled close
      // to the bottom of the rendered set. The 400px threshold matches the
      // 300px rootMargin + a small buffer for sub-pixel rounding.
      const remaining =
        wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight;
      if (remaining > 400) return;
      appendNextPage();
    },
    { root: wrap, rootMargin: "300px" }
  );
  _tableObserver.observe(_tableSentinel);
}

// Ensure the row for `id` has been rendered into the DOM — used by selectSite
// when the user opens a marker whose row is far past the rendered window.
function ensureRowRendered(id) {
  if (!el("view-table")?.classList.contains("active")) return false;
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

// Cached header NodeList — same set across the document's lifetime, so we
// don't need to re-query it on every sort-indicator update.
let _sortHeaders = null;
function getSortHeaders() {
  if (!_sortHeaders) _sortHeaders = document.querySelectorAll("#sites-table thead th");
  return _sortHeaders;
}

function updateSortIndicators() {
  for (const th of getSortHeaders()) {
    th.removeAttribute("aria-sort");
    th.removeAttribute("data-sort-glyph");
    if (th.dataset.sort === sortKey) {
      th.setAttribute("aria-sort", sortDir === "asc" ? "ascending" : "descending");
      th.setAttribute("data-sort-glyph", sortDir === "asc" ? "▲" : "▼");
    }
  }
}

// Single delegated listener on <thead> instead of one-per-column. Survives
// future column additions without rebinding.
const _sortThead = document.querySelector("#sites-table thead");
if (_sortThead) {
  _sortThead.addEventListener("click", (event) => {
    const th = event.target.closest("th[data-sort]");
    if (!th || !_sortThead.contains(th)) return;
    const key = th.dataset.sort;
    if (!key) return;
    if (key === sortKey) sortDir = sortDir === "asc" ? "desc" : "asc";
    else { sortKey = key; sortDir = (key === "acreage" || key === "dc_score") ? "desc" : "asc"; }
    rebuildTable();
    if (selectedId) tableRowsById.get(selectedId)?.classList.add("selected");
  });
}

// ----- Tabs -----
function wireTabs() {
  const mapTab = el("tab-map");
  const tableTab = el("tab-table");
  const candidatesTab = el("tab-candidates");
  const retiredTab = el("tab-retired");
  const coalTab = el("tab-coal");
  const ap1000Tab = el("tab-ap1000");
  const microTab = el("tab-micro");
  const hanfordTab = el("tab-hanford");
  const maritimeTab = el("tab-maritime");
  const nickelTab = el("tab-nickel");
  const aboutTab = el("tab-about");
  const setView = (which) => {
    const onMap = which === "map";
    const onTable = which === "table";
    const onCandidates = which === "candidates";
    const onRetired = which === "retired";
    const onCoal = which === "coal";
    const onAp1000 = which === "ap1000";
    const onMicro = which === "micro";
    const onHanford = which === "hanford";
    const onMaritime = which === "maritime";
    const onNickel = which === "nickel";
    const onAbout = which === "about";
    for (const [tab, active] of [
      [mapTab, onMap], [tableTab, onTable],
      [candidatesTab, onCandidates], [retiredTab, onRetired],
      [coalTab, onCoal],
      [ap1000Tab, onAp1000], [microTab, onMicro],
      [hanfordTab, onHanford], [maritimeTab, onMaritime], [nickelTab, onNickel], [aboutTab, onAbout],
    ]) {
      if (!tab) continue;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    }
    const mapView = el("view-map");
    const tableView = el("view-table");
    const candidatesView = el("view-candidates");
    const retiredView = el("view-retired");
    const coalView = el("view-coal");
    const ap1000View = el("view-ap1000");
    const microView = el("view-micro");
    const hanfordView = el("view-hanford");
    const maritimeView = el("view-maritime");
    const nickelView = el("view-nickel");
    const aboutView = el("view-about");
    if (mapView)        { mapView.classList.toggle("active", onMap);               mapView.hidden = !onMap; }
    if (tableView)      { tableView.classList.toggle("active", onTable);           tableView.hidden = !onTable; }
    if (candidatesView) { candidatesView.classList.toggle("active", onCandidates); candidatesView.hidden = !onCandidates; }
    if (retiredView)    { retiredView.classList.toggle("active", onRetired);       retiredView.hidden = !onRetired; }
    if (coalView)       { coalView.classList.toggle("active", onCoal);             coalView.hidden = !onCoal; }
    if (ap1000View)     { ap1000View.classList.toggle("active", onAp1000);         ap1000View.hidden = !onAp1000; }
    if (microView)      { microView.classList.toggle("active", onMicro);           microView.hidden = !onMicro; }
    if (hanfordView)    { hanfordView.classList.toggle("active", onHanford);       hanfordView.hidden = !onHanford; }
    if (maritimeView)   { maritimeView.classList.toggle("active", onMaritime);     maritimeView.hidden = !onMaritime; }
    if (nickelView)     { nickelView.classList.toggle("active", onNickel);         nickelView.hidden = !onNickel; }
    if (aboutView)      { aboutView.classList.toggle("active", onAbout);           aboutView.hidden = !onAbout; }
    const globalExportCsv = el("export-csv");
    if (globalExportCsv) globalExportCsv.hidden = onAp1000 || onMicro || onCoal || onHanford || onMaritime || onNickel;
    // Search only makes sense against the corpus views that read
    // tableState.filtered (map/table/rankings/microreactors — the
    // microreactor siting screen's microRankedSites() sources from the same
    // globally-filtered set Rankings does, so it needs the same controls;
    // Codex PR #23 review). Maritime Siting reads the same tableState.filtered
    // for the same reason. The remaining curated tabs (Retired, Coal,
    // Nuclear Siting, Hanford, About) have their own local content and read
    // no global filter state at all.
    const searchOnThisTab = onMap || onTable || onCandidates || onMicro || onMaritime || onNickel;
    const searchWrapEl = el("search-wrap");
    if (searchWrapEl) searchWrapEl.hidden = !searchOnThisTab;
    const searchCountEl = el("search-count");
    if (searchCountEl) searchCountEl.hidden = !searchOnThisTab;
    // Same scope as search — the filters panel only filters the corpus
    // views. Force-close it when navigating to a curated tab so it can't
    // be left open with no visible toggle to close it.
    const filtersToggleEl = el("filters-toggle");
    if (filtersToggleEl) {
      filtersToggleEl.hidden = !searchOnThisTab;
      if (!searchOnThisTab && filtersToggleEl.getAttribute("aria-expanded") === "true") {
        closeFiltersUi();
      }
    }
    // The headline stat deck (and the per-program tagline folded into it)
    // is a summary of the CORPUS, not of a curated tab's own content — show
    // it only where the corpus is actually on screen.
    const kpiDisclosureEl = el("kpi-disclosure");
    if (kpiDisclosureEl) kpiDisclosureEl.hidden = !(onMap || onTable || onCandidates);
    if (onMap) {
      ensureMapMarkersReady();
      ensureMapOverlayData();
      // Layout is visible now. Fit before a caller applies a parcel/plant target;
      // a deferred overview fit would overwrite that explicit navigation.
      map.invalidateSize();
      if (!mapOverviewShown) {
        mapOverviewShown = true;
        if (!selectedId && !new URLSearchParams(location.search).has("site") && !new URLSearchParams(location.search).has("epa_id")) fitUsBoundsSafely();
      }
    }
    if (onTable) refreshTableForFilter();
    if (onCandidates) buildCandidatesView();
    if (onRetired) { mountRetiredView(); ensureRetiredIndustrialLoaded(); buildRetiredView(); }
    if (onCoal) { mountCoalView(); ensureCoalConversionsLoaded().then(() => buildCoalView()); }
    if (onAbout) mountAboutView();
    if (onAp1000) {
      ensureAp1000Loaded(); buildAp1000View();
      ensureNuclearSitesLoaded(); buildNuclearCivilianView();
    }
    if (onMicro) {
      ensureMicroFleetLoaded();
      ensureJanusNepaLoaded();
      buildMicroView();
    }
    if (onHanford) {
      // Mount BEFORE anything queries the view's interior (the lazy-mount
      // rule every templated view follows), then render from whatever state
      // the eager loader has reached — buildHanfordView handles loading,
      // failed, and loaded states itself.
      mountHanfordView();
      ensureHanfordLoaded();
      ensureSuperfundDocsLoaded();
      ensureTribalAreasLoaded();
      buildHanfordView();
    }
    if (onMaritime) {
      mountMaritimeView();
      ensurePortProximityLoaded();
      ensurePortsLoaded();
      ensureShipyardsLoaded();
      buildMaritimeView();
    }
    if (onNickel) {
      mountNickelView();
      ensureWaterProximityLoaded();
      ensureNickelAnchorProxLoaded();
      ensureNickelAnchorsLoaded();
      // The import lens ranks on `port_mi`. If the eager port fetch failed at
      // boot, its catch cleared the promise, so this retries it rather than
      // leaving the default ranking empty until a reload or a visit to the
      // Maritime tab (Codex round 2).
      ensurePortProximityLoaded();
      buildNickelView();
    }
    if (onAbout) {
      renderSourceCoverage();
      const d = el("about-refresh-date");
      if (d && window.__refreshedAt) d.textContent = window.__refreshedAt;
    }
    // Update URL hash so the active tab can be bookmarked / shared.
    // Map is the default; omit its hash to keep URLs clean.
    const newHash = which === "candidates" ? "" : "#" + which;
    history.replaceState(null, "", location.pathname + location.search + newHash);
  };
  window.__setView = setView;
  mapTab.addEventListener("click", () => setView("map"));
  tableTab.addEventListener("click", () => setView("table"));
  if (candidatesTab) candidatesTab.addEventListener("click", () => setView("candidates"));
  if (retiredTab) retiredTab.addEventListener("click", () => setView("retired"));
  if (coalTab) coalTab.addEventListener("click", () => setView("coal"));
  if (ap1000Tab) ap1000Tab.addEventListener("click", () => setView("ap1000"));
  if (microTab) microTab.addEventListener("click", () => setView("micro"));
  if (hanfordTab) hanfordTab.addEventListener("click", () => setView("hanford"));
  if (maritimeTab) maritimeTab.addEventListener("click", () => setView("maritime"));
  if (nickelTab) nickelTab.addEventListener("click", () => setView("nickel"));
  if (aboutTab) aboutTab.addEventListener("click", () => setView("about"));

  // Honor hash on initial load (e.g. shared URL with #ap1000).
  const VALID_TABS = new Set(["map", "table", "candidates", "retired", "coal", "ap1000", "micro", "hanford", "maritime", "nickel", "about"]);
  const initialHash = location.hash.replace(/^#/, "").toLowerCase();
  if (VALID_TABS.has(initialHash)) setView(initialHash);
  else setView(new URLSearchParams(location.search).has("site") ? "map" : "candidates");

  // Handle manual hash edits in the address bar (browser back/forward not
  // relevant since we use replaceState, but covers direct hash navigation).
  window.addEventListener("hashchange", () => {
    const tab = location.hash.replace(/^#/, "").toLowerCase();
    if (VALID_TABS.has(tab)) setView(tab);
  });
}

// ----- Retired Sites stats view -----
// Renders a by-prior-use breakdown of the retired-industrial overlay
// (docs/data/retired-industrial.json). Pure DOM + CSS bars (no chart lib).
function maybeRefreshRetired() {
  const v = el("view-retired");
  if (v && v.classList.contains("active")) buildRetiredView();
}

function buildRetiredView() {
  const host = el("retired-stats");
  if (!host) return;
  const sites = retiredIndustrialSites;
  if (!sites.length) {
    host.innerHTML = '<p class="muted">Loading retired-site data…</p>';
    return;
  }
  const total = sites.length;
  const byCat = {};
  const bySector = {};
  const byState = {};
  for (const s of sites) {
    const cat = s.category || "Other";
    byCat[cat] = (byCat[cat] || 0) + 1;
    if (s.sector) bySector[s.sector] = (bySector[s.sector] || 0) + 1;
    if (s.state) byState[s.state] = (byState[s.state] || 0) + 1;
  }
  const sectors = Object.entries(bySector).sort((a, b) => b[1] - a[1]);
  const states = Object.entries(byState).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const maxSector = sectors.length ? sectors[0][1] : 1;
  const maxState = states.length ? states[0][1] : 1;
  const pct = (n, max) => Math.max(2, Math.round((n / max) * 100));

  const catCards = Object.entries(byCat).sort((a, b) => b[1] - a[1]).map(([c, n]) =>
    `<div class="retired-kpi"><span class="retired-kpi-num">${n.toLocaleString()}</span>`
    + `<span class="retired-kpi-label">${escapeHtml(c)}</span></div>`).join("");

  const sectorRows = sectors.map(([name, n]) =>
    `<div class="retired-bar-row">`
    + `<span class="retired-bar-label" title="${escapeAttr(name)}">${escapeHtml(name)}</span>`
    + `<span class="retired-bar-track"><span class="retired-bar-fill" style="width:${pct(n, maxSector)}%"></span></span>`
    + `<span class="retired-bar-num">${n.toLocaleString()}</span>`
    + `</div>`).join("");

  const stateRows = states.map(([st, n]) =>
    `<div class="retired-bar-row">`
    + `<span class="retired-bar-label">${escapeHtml(STATE_NAMES[st] || st)}</span>`
    + `<span class="retired-bar-track"><span class="retired-bar-fill alt" style="width:${pct(n, maxState)}%"></span></span>`
    + `<span class="retired-bar-num">${n.toLocaleString()}</span>`
    + `</div>`).join("");

  host.innerHTML =
    `<div class="retired-kpis"><div class="retired-kpi"><span class="retired-kpi-num">${total.toLocaleString()}</span>`
    + `<span class="retired-kpi-label">Retired sites</span></div>${catCards}</div>`
    + `<div class="retired-cols">`
    + `<section class="retired-col"><h3>Top prior uses</h3><div class="retired-bars">${sectorRows}</div></section>`
    + `<section class="retired-col"><h3>Top states</h3><div class="retired-bars">${stateRows}</div></section>`
    + `</div>`
    + `<p class="retired-foot muted">Source: <a href="https://www.epa.gov/ghgreporting" target="_blank" rel="noopener">EPA Greenhouse Gas Reporting Program</a> facilities that ceased reporting (closed, idled, or below threshold), queried by <code>reporting_status</code> via the <a href="https://www.epa.gov/enviro/envirofacts-data-service-api" target="_blank" rel="noopener">Envirofacts data service</a>; every ◆ marker's popup deep-links to that facility's <a href="https://enviro.epa.gov/envirofacts/ghg/search" target="_blank" rel="noopener">EPA Envirofacts GHG record</a>. This is a screening signal for reusable grid infrastructure — verify ownership, interconnection, and closure before treating any site as available. <strong>Nearby records:</strong> ${retiredIndustrialSites.filter((s) => s.tracked_site_id).length.toLocaleString()} sites have a Superfund, ACRES, FUDS, or BRAC point within 1 mi. Those links are proximity context only, not parcel matches or availability evidence. Use the rust ◆ markers on the Map to locate them.</p>`;
}

// ----- About: lazy view mount -----
// The whole About view (~190 static DOM nodes incl. the System Architecture
// flow-card grid) lives in <template id="about-template"> and mounts on
// first About activation. Template content is not part of the rendered
// document, so first paint stays under the 5,000-node budget
// (see test_dom_size_under_5k_nodes). Anything that writes into About
// content (e.g. #about-refresh-date) must run AFTER this in setView.
let aboutMounted = false;
function renderSourceCoverage() {
  const host=el("about-source-coverage"); if(!host) return;
  const pool=sites.map(sanitizeGeographicEvidence);
  const meta=pool.find(s=>s._infraSourceMetadata)?._infraSourceMetadata || {};
  const descriptors=[
    ["Transmission", "transmission_mi", "transmission", "Mapped line distance; utility capacity unknown"],
    ["Substations", "substation_mi", "substation", "OSM inventory; equipment roles and coverage vary"],
    ["Fiber", "fiber_source_url", null, "No joined enterprise serviceability inventory"],
    ["Water gages", "water_gage_mi", null, "Monitoring context; source connection and supply unknown"],
    ["Reported land", null, null, "Site/parcel area; usable footprint and availability unknown"],
    ["Road", "highway_mi", "highway", "Mapped route; physical access unknown"],
    ["Rail", "rail_mi", "rail", "Mapped route; spur and service unknown"]
  ];
  const rows=descriptors.map(([label,field,layer,limit])=>{
    const count=pool.filter(s=>field ? s[field]!=null : s.acreage!=null || s.parcel_acreage!=null).length;
    const source=layer ? meta[layer] || {} : {};
    const date=source.source_snapshot_at || (field === "water_gage_mi" ? (waterSourceMetadata.source_retrieved_at_range || []).map(x=>x.slice(0,10)).join(" – ") || "Unknown" : "Unknown / record-specific");
    return `<tr><th scope="row">${label}</th><td>${count.toLocaleString()} / ${pool.length.toLocaleString()}</td><td>${escapeHtml(date)}${source.source_url ? ` · <a href="${escapeAttr(source.source_url)}" target="_blank" rel="noopener">Source</a>` : ""}</td><td>${limit}</td></tr>`;
  }).join("");
  host.innerHTML=`<h3>Coverage of loaded programs</h3><p>Counts mean a field is present, not verified service. ${lazyLoadsSettled ? "Core loading complete." : "Loading; counts are provisional."}</p><div class="source-coverage-wrap"><table class="source-coverage-table"><caption class="sr-only">Infrastructure observations and source snapshots</caption><thead><tr><th scope="col">Category</th><th scope="col">Records</th><th scope="col">Snapshot</th><th scope="col">Limit</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function mountAboutView() {
  if (aboutMounted) return;
  const tpl = el("about-template");
  const view = el("view-about");
  if (!tpl || !view || !tpl.content) return;
  aboutMounted = true;
  view.appendChild(tpl.content.cloneNode(true));
}

// Same lazy-mount mechanism for the Coal Reinvestment and Retired Sites view
// skeletons — their interiors live in <template> until first activation, so
// hidden tabs cost ~2 nodes each at first paint. Mount BEFORE any code that
// queries elements inside the view (buildCoalView / buildRetiredView run
// after their mount call in setView).
let coalViewMounted = false;
function mountCoalView() {
  if (coalViewMounted) return;
  const tpl = el("coal-template");
  const view = el("view-coal");
  if (!tpl || !view || !tpl.content) return;
  coalViewMounted = true;
  view.appendChild(tpl.content.cloneNode(true));
}

let retiredViewMounted = false;
function mountRetiredView() {
  if (retiredViewMounted) return;
  const tpl = el("retired-template");
  const view = el("view-retired");
  if (!tpl || !view || !tpl.content) return;
  retiredViewMounted = true;
  view.appendChild(tpl.content.cloneNode(true));
}

let nickelViewMounted = false;
function mountNickelView() {
  if (nickelViewMounted) return;
  const tpl = el("nickel-template");
  const view = el("view-nickel");
  if (!tpl || !view || !tpl.content) return;
  nickelViewMounted = true;
  view.appendChild(tpl.content.cloneNode(true));
  // Lens buttons live inside the template — wire after the clone, never at
  // boot (mountCoalView / mountMaritimeView record the same lesson).
  wireNickelFilters();
}

let maritimeViewMounted = false;
function mountMaritimeView() {
  if (maritimeViewMounted) return;
  const tpl = el("maritime-template");
  const view = el("view-maritime");
  if (!tpl || !view || !tpl.content) return;
  maritimeViewMounted = true;
  view.appendChild(tpl.content.cloneNode(true));
  // The lens toggle buttons live inside the template, so they don't exist
  // in the live DOM until this clone runs — wire them here, not at boot
  // (same lazy-mount lesson as coalFiltersBound / mountCoalView).
  wireMaritimeFilters();
}

// ----- Coal Reinvestment View (Spec 04) -----
let coalFiltersBound = false;

// Status labels for the coal catalog's actual value domain. Keep in sync with
// schema.py CoalConversionAsset.status — the filter <option>s are generated
// from the loaded data (drift-safe iteration, the PROGRAM_LEGEND/UAT-007
// rule), so a new status only needs a label here to render nicely.
const COAL_STATUS_LABELS = {
  operating: "Operating",
  planned_retirement: "Retiring soon",
  retired: "Retired",
  converted_gas: "Converted to gas",
};

// Rebuild a coal filter <select>'s options from the values present in the
// data, preserving the current selection when still valid.
function populateCoalFilterOptions(selectId, values, labelFor) {
  const sel = el(selectId);
  if (!sel) return;
  const prev = sel.value;
  const allLabel = sel.options.length ? sel.options[0].textContent : "All";
  const allOpt = document.createElement("option");
  allOpt.value = "all";
  allOpt.textContent = allLabel;
  const opts = [allOpt];
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = labelFor ? (labelFor(v) || v) : v;
    opts.push(opt);
  }
  sel.replaceChildren(...opts);
  sel.value = opts.some((o) => o.value === prev) ? prev : "all";
}

function buildCoalView() {
  const container = el("coal-table-container");
  if (!container) return;
  if (!coalConversionAssets || coalConversionAssets.length === 0) {
    // Three distinct states, never a forever-"Loading…" (Codex review P2,
    // same contract as the nuclear overlay): failed → retryable error;
    // settled-but-empty → explicit empty (a successful empty is NOT
    // retryable); otherwise genuinely still loading.
    if (coalConversionsLoadFailed) {
      container.replaceChildren();
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "Coal conversion assets failed to load. ";
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "coal-btn";
      retry.textContent = "Retry";
      retry.addEventListener("click", () => {
        container.innerHTML = '<p class="muted">Loading coal conversion assets…</p>';
        ensureCoalConversionsLoaded().then(() => buildCoalView());
      });
      p.appendChild(retry);
      container.appendChild(p);
    } else if (coalConversionsSettled) {
      container.innerHTML = '<p class="muted">No coal conversion assets in this build.</p>';
    } else {
      container.innerHTML = '<p class="muted">Loading coal conversion assets…</p>';
    }
    return;
  }

  // Filter options come from the dataset's actual value domain — hardcoded
  // lists are how the v1 "retiring"/"SERC" dead options shipped.
  const statuses = [...new Set(coalConversionAssets.map((a) => a.status).filter(Boolean))].sort();
  const isos = [...new Set(coalConversionAssets.map((a) => a.iso_rto).filter(Boolean))].sort();
  populateCoalFilterOptions("coal-status-filter", statuses, (v) => COAL_STATUS_LABELS[v]);
  populateCoalFilterOptions("coal-iso-filter", isos, null);
  const suits = [...new Set(coalConversionAssets.map((a) => a.conversion_suitability).filter(Boolean))].sort();
  populateCoalFilterOptions("coal-suitability-filter", suits, (v) => ({
    nuclear_preferred: "Nuclear Preferred",
    datacenter_preferred: "Data Center Preferred",
    dual_feasible: "Dual Feasible",
  })[v]);

  // Update headline KPI counters
  const totalMw = coalConversionAssets.reduce((sum, a) => sum + (a.nameplate_coal_mw || 0), 0);
  const totalVal = coalConversionAssets.reduce((sum, a) => sum + (a.est_stranded_asset_value_usd || 0), 0);
  const totalQueue = coalConversionAssets.filter((a) => a.queue_transfer_eligible).length;

  const countEl = el("coal-kpi-count");
  const mwEl = el("coal-kpi-mw");
  const valEl = el("coal-kpi-val");
  const queueEl = el("coal-kpi-queue");
  if (countEl) countEl.textContent = coalConversionAssets.length;
  if (mwEl) mwEl.textContent = `${(totalMw / 1000).toFixed(1)} GW`;
  if (valEl) valEl.textContent = `$${(totalVal / 1_000_000_000).toFixed(2)}B`;
  if (queueEl) queueEl.textContent = `${Math.round((totalQueue / coalConversionAssets.length) * 100)}%`;

  if (!coalFiltersBound) {
    coalFiltersBound = true;
    const sFilter = el("coal-status-filter");
    const iFilter = el("coal-iso-filter");
    const uFilter = el("coal-suitability-filter");
    if (sFilter) sFilter.addEventListener("change", renderCoalTable);
    if (iFilter) iFilter.addEventListener("change", renderCoalTable);
    if (uFilter) uFilter.addEventListener("change", renderCoalTable);
    const closeBtn = el("coal-drawer-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        const drawer = el("coal-site-drawer");
        if (drawer) drawer.hidden = true;
      });
    }
    const exportBtn = el("coal-export-csv");
    if (exportBtn) exportBtn.addEventListener("click", downloadCoalCsv);
    // Delegated row actions — the listener lives on the container so it
    // survives every innerHTML rebuild, and the plant name travels via the
    // row's data-plant attribute (dataset decodes entities), never via
    // string-interpolated inline onclick (code review 2026-08-23 #1).
    container.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-act]");
      if (!btn || !container.contains(btn)) return;
      const row = btn.closest(".coal-row");
      const plant = row && coalConversionAssets.find((a) => a.plant_name === row.dataset.plant);
      if (!plant) return;
      if (btn.dataset.act === "map") {
        window.__focusCoalPlantOnMap(plant.latitude, plant.longitude, plant.plant_name);
      } else if (btn.dataset.act === "inspect") {
        window.__inspectCoalPlant(plant.plant_name);
      }
    });
  }

  renderCoalTable();
}

// The single filter predicate shared by the table renderer and the CSV
// export, so "Export CSV" can never disagree with the rows on screen.
function getFilteredCoalAssets() {
  const statusFilter = (el("coal-status-filter") && el("coal-status-filter").value) || "all";
  const isoFilter = (el("coal-iso-filter") && el("coal-iso-filter").value) || "all";
  const suitFilter = (el("coal-suitability-filter") && el("coal-suitability-filter").value) || "all";
  return coalConversionAssets.filter((a) => {
    if (statusFilter !== "all" && a.status !== statusFilter) return false;
    if (isoFilter !== "all" && a.iso_rto !== isoFilter) return false;
    if (suitFilter !== "all" && a.conversion_suitability !== suitFilter) return false;
    return true;
  });
}

// Coal-tab CSV export (the ap1000-export-csv pattern) — the GLOBAL topbar
// export always serves the brownfield corpus, so this tab ships its own
// button for the coal catalog (Codex review 2026-08-23 round 2).
function buildCoalCsv() {
  const cols = [
    ["plant_name", (a) => a.plant_name],
    ["utility_operator", (a) => a.utility_operator],
    ["state", (a) => a.state],
    ["county", (a) => a.county],
    ["status", (a) => a.status],
    ["retired_year", (a) => a.retired_year ?? ""],
    ["planned_retirement_year", (a) => a.planned_retirement_year ?? ""],
    ["nameplate_coal_mw", (a) => a.nameplate_coal_mw],
    ["switchyard_kv", (a) => a.switchyard_kv],
    ["has_rail", (a) => a.has_rail],
    ["has_water_intake", (a) => a.has_water_intake],
    ["poi_occupied", (a) => a.poi_occupied ?? false],
    ["iso_rto", (a) => a.iso_rto],
    ["queue_transfer_eligible", (a) => a.queue_transfer_eligible],
    ["modeled_stranded_value_usd", (a) => a.est_stranded_asset_value_usd],
    ["conversion_suitability", (a) => a.conversion_suitability],
    ["site_acreage", (a) => a.site_acreage ?? ""],
    ["note", (a) => a.note ?? ""],
    ["source_url", (a) => a.source_url],
    ["verified_at", (a) => a.verified_at],
  ];
  const esc = (v) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rows = [cols.map(([label]) => label)];
  for (const a of getFilteredCoalAssets()) {
    rows.push(cols.map(([, get]) => get(a)));
  }
  return rows.map((r) => r.map(esc).join(",")).join("\n");
}

function downloadCoalCsv() {
  const csv = buildCoalCsv();
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `coal-conversions-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
window.__buildCoalCsv = buildCoalCsv; // e2e hook, like __buildAp1000Csv

function renderCoalTable() {
  const container = el("coal-table-container");
  if (!container) return;

  const filtered = getFilteredCoalAssets();

  if (filtered.length === 0) {
    container.innerHTML = '<p class="muted" style="padding:20px;">No coal conversion assets match the selected filters.</p>';
    return;
  }

  // Sort descending by MW
  const sorted = [...filtered].sort((a, b) => (b.nameplate_coal_mw || 0) - (a.nameplate_coal_mw || 0));

  let html = `
    <table class="coal-table">
      <thead>
        <tr>
          <th>Plant &amp; Operator</th>
          <th>Location</th>
          <th class="num">Coal Capacity</th>
          <th class="num">Switchyard</th>
          <th>Water &amp; Rail Assets</th>
          <th class="num">Stranded Value</th>
          <th>Reported reuse focus &amp; ISO</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
  `;

  for (const plant of sorted) {
    const valM = (plant.est_stranded_asset_value_usd / 1_000_000).toFixed(1);
    const suitLabel = plant.conversion_suitability === "nuclear_preferred"
      ? '<span class="coal-tag nuclear">Nuclear focus</span>'
      : plant.conversion_suitability === "datacenter_preferred"
      ? '<span class="coal-tag dc">Data-center focus</span>'
      : '<span class="coal-tag dual">Dual-use focus</span>';

    const statusBadge = `<span class="coal-status-pill ${escapeAttr(plant.status)}">${escapeHtml(COAL_STATUS_LABELS[plant.status] || plant.status)}</span>`;

    html += `
      <tr class="coal-row" data-plant="${escapeAttr(plant.plant_name)}">
        <td>
          <strong>${escapeHtml(plant.plant_name)}</strong>
          <span class="coal-op">${escapeHtml(plant.utility_operator || "")} ${statusBadge}</span>
        </td>
        <td>${escapeHtml(plant.county || "")} Co, ${escapeHtml(plant.state || "")}</td>
        <td class="num font-num"><strong>${Math.round(plant.nameplate_coal_mw).toLocaleString()} MW</strong></td>
        <td class="num font-num">${plant.switchyard_kv ? `${plant.switchyard_kv} kV` : "—"}</td>
        <td>
          <div class="coal-infra-badges">
            ${plant.has_water_intake ? `<span class="coal-badge water" title="Water intake on-site${plant.intake_flow_gpm ? ` · ${plant.intake_flow_gpm.toLocaleString()} GPM` : ''}">💧 Water intake</span>` : '<span class="coal-badge muted">Intake unconfirmed</span>'}
            ${plant.has_rail ? '<span class="coal-badge rail" title="On-site rail siding / loop">🚂 Rail siding</span>' : '<span class="coal-badge muted">Rail unconfirmed</span>'}
            ${plant.queue_transfer_eligible ? '<span class="coal-badge queue" title="Retired or retiring connection: utility and operator review required; rights and capacity unverified">Interconnection review needed</span>' : ''}
          </div>
        </td>
        <td class="num font-num"><strong>~$${valM}M</strong></td>
        <td>
          ${suitLabel}
          <span class="coal-iso">${escapeHtml(plant.iso_rto || "")}</span>
        </td>
        <td>
          <div class="coal-action-btns">
            <button type="button" class="coal-btn map-btn" data-act="map">Map ↗</button>
            <button type="button" class="coal-btn inspect-btn" data-act="inspect">Details ↓</button>
          </div>
        </td>
      </tr>
    `;
  }

  html += `</tbody></table>`;
  container.innerHTML = html;
}

window.__openCoalTabForPlant = function(plantName) {
  if (typeof window.__setView === "function") {
    window.__setView("coal");
  }
  // Chain on the loader, not a fixed timer — if the catalog fetch failed at
  // boot (loader nulls its promise for retry), setView('coal') retries it and
  // this resolves once the data is actually there (code review 2026-08-23 #13).
  ensureCoalConversionsLoaded().then(() => window.__inspectCoalPlant(plantName));
};

window.__focusCoalPlantOnMap = function(lat, lon, plantName) {
  if (typeof window.__setView === "function") {
    window.__setView("map");
  }
  setTimeout(() => {
    if (map) {
      map.setView([lat, lon], 12);
      const marker = coalMarkersByName.get(plantName);
      if (marker) marker.openPopup();
    }
  }, 150);
};

// Per-plant NEPA permitting screens (docs/data/coal-nepa.json, built by
// scripts/build_coal_nepa.py on nepa-mcp). Drawer-only evidence, so it loads
// lazily on first drawer open and deliberately does NOT call
// recordRefreshDate — same rule as reference-campuses.json: a file whose
// loader may never run must not be allowed to drive the displayed
// refresh date (it would understate freshness whenever nobody opened a
// drawer). Keep it OUT of test_refresh_date_reflects_freshest_data_file's
// file list for the same reason.
function ensureCoalNepaLoaded() {
  if (coalNepaLoadingPromise) return coalNepaLoadingPromise;
  coalNepaLoadFailed = false;
  coalNepaLoadingPromise = fetch(COAL_NEPA_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { plants: [] }; // screen not generated yet
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      coalNepaByPlant = new Map();
      for (const row of payload.plants || []) coalNepaByPlant.set(row.plant_name, row);
    })
    .catch((err) => {
      console.error("Coal NEPA screen load failed:", err);
      coalNepaLoadFailed = true;
      coalNepaLoadingPromise = null; // nulled so the next drawer open retries
    });
  return coalNepaLoadingPromise;
}

// Compact permitting-screen section for the coal drawer. Distinguishes the
// three states honestly: still loading, failed (retryable), and loaded —
// where "loaded but no row" means the screen has not been generated for
// this plant, never that the plant screens clean.
function _coalNepaSectionHtml(plantName) {
  if (coalNepaLoadFailed) {
    return `<div class="coal-nepa-section"><h4>Permitting screen</h4>` +
      `<p class="muted">Screen data failed to load. <button type="button" class="coal-btn coal-nepa-retry">Retry</button></p></div>`;
  }
  if (coalNepaByPlant === null) {
    return `<div class="coal-nepa-section"><h4>Permitting screen</h4>` +
      `<p class="muted">Loading NEPA screening evidence…</p></div>`;
  }
  const row = coalNepaByPlant.get(plantName);
  if (!row) {
    return `<div class="coal-nepa-section"><h4>Permitting screen</h4>` +
      `<p class="muted">No nepa-mcp screen generated for this plant yet.</p></div>`;
  }
  const s = row.screening || {};
  const ipac = s.ipac || {};
  const counts = ipac.counts || {};
  const flood = s.fema_nfhl || {};
  const districts = ((s.usace || {}).districts || [])
    .map((d) => d.district_abbreviation || d.district_name).filter(Boolean);
  const chip = (label, section, text, title) =>
    `<span class="coal-nepa-chip${section && section.status === "ok" ? "" : " unavailable"}"` +
    `${title ? ` title="${escapeAttr(title)}"` : ""}>` +
    `<span class="coal-nepa-k">${escapeHtml(label)}</span> ` +
    `${section && section.status === "ok" ? text : "Unavailable"}</span>`;
  const chips = [
    chip("ESA", ipac, `${counts.listed_species || 0} species · ${counts.critical_habitat || 0} crit. habitat`,
      "USFWS IPaC listed species and critical-habitat records intersecting the 5-mi screen"),
    chip("Tribal", s.tribal, `${(s.tribal || {}).count || 0} mapped`,
      "Census AIANNHA geographies in 5 mi — consultation context, never a conclusion"),
    chip("Historic", s.nrhp, `${(s.nrhp || {}).count || 0} NRHP`,
      "Listed properties only; eligible-but-unlisted resources are not in this layer"),
    chip("Protected", s.padus, `${(s.padus || {}).count || 0} PAD-US`,
      "Protected-area records at the plant point (0.1-mi context)"),
    chip("USACE", s.usace, districts.length ? escapeHtml(districts.join(" · ")) : "No district returned",
      "Regulatory district — not wetland presence or a CWA jurisdictional determination"),
    chip("Flood", flood, flood.count
        ? `${flood.count} zones · ${flood.sfha_count || 0} SFHA in 2 mi`
        : "No mapped zones in 2 mi",
      "Riverine coal plants sit next to water by design — nearby mapped zones are expected context, not a disqualifier"),
  ].join("");
  const assist = s.nepa_assist || {};
  const reportLink = assist.status === "ok" && assist.report_url
    ? ` · <a href="${escapeAttr(assist.report_url)}" target="_blank" rel="noopener noreferrer">EPA NEPAssist report ↗</a>`
    : "";
  const retrieved = (ipac.retrieved_at || "").slice(0, 10);
  return `<div class="coal-nepa-section">` +
    `<h4>Permitting screen <span class="coal-nepa-note">(PNNL nepa-mcp · 5-mi context · screening evidence, not a determination)</span></h4>` +
    `<div class="coal-nepa-chips">${chips}</div>` +
    `<p class="coal-nepa-note">Counts mean features intersect the screening buffer rather than the plant parcel itself. Unavailable means the source did not respond, which is different from a result of zero.` +
    `${retrieved ? ` Retrieved ${escapeHtml(retrieved)}.` : ""}${reportLink}</p>` +
    `</div>`;
}

window.__inspectCoalPlant = function(plantName) {
  const plant = coalConversionAssets.find((a) => a.plant_name === plantName);
  if (!plant) return;

  // Kick the lazy screen load on first open; when it settles, re-render the
  // drawer if it is still showing this plant. `hadSettled` prevents the
  // resolved-promise microtask from re-invoking this function forever.
  if (coalProxMatches === null && !coalProxLoadFailed) {
    ensureCoalConversionsProxLoaded().then(() => {
      const drawer=el("coal-site-drawer");
      if(drawer && !drawer.hidden && drawer.dataset.plant===plantName) window.__inspectCoalPlant(plantName);
    });
  }
  const hadSettled = coalNepaByPlant !== null || coalNepaLoadFailed;
  if (!hadSettled) {
    ensureCoalNepaLoaded().then(() => {
      const d = el("coal-site-drawer");
      if (d && !d.hidden && d.dataset.plant === plantName) {
        window.__inspectCoalPlant(plantName);
      }
    });
  }

  const drawer = el("coal-site-drawer");
  const title = el("coal-drawer-title");
  const body = el("coal-drawer-body");
  if (!drawer || !body || !title) return;

  // Find nearby brownfields in sitesById within 10 mi
  const nearby = [];
  for (const s of sitesById.values()) {
    if (s.coal_conversion_plant_name === plant.plant_name) {
      nearby.push(s);
    }
  }
  // ?? not || — a legitimate 0.0-mi ("Adjacent") distance is falsy and would
  // sort last under || (code review 2026-08-23 #9).
  nearby.sort((a, b) => (a.coal_conversion_plant_mi ?? 999) - (b.coal_conversion_plant_mi ?? 999));

  title.textContent = `${plant.plant_name} — Conversion Profile`;
  const valM = (plant.est_stranded_asset_value_usd / 1_000_000).toFixed(1);

  let nearbyHtml = '';
  if (nearby.length > 0) {
    nearbyHtml = `
      <div class="coal-nearby-section">
        <h4>Tracked Brownfields &amp; Superfund Sites Nearby (${nearby.length} within 10 mi)</h4>
        <div class="coal-nearby-list">
          ${nearby.slice(0, 15).map((s) => `
            <button type="button" class="coal-nearby-item" data-site-id="${escapeAttr(s.id)}">
              <div class="coal-nearby-head">
                <strong>${escapeHtml(s.name)}</strong>
                <span class="coal-nearby-dist">${fmt.miles(s.coal_conversion_plant_mi)}</span>
              </div>
              <div class="coal-nearby-sub">
                ${escapeHtml(s.program.toUpperCase())} · ${s.acreage ? `${Math.round(s.acreage)} ac · ` : ''}${escapeHtml(s.city || s.county || '')}, ${escapeHtml(s.state)}
                ${s.coal_conversion_queue_fasttrack ? '<span class="coal-fast-badge">Within 1.5 mi of cataloged plant · connection unverified</span>' : ''}
              </div>
            </button>
          `).join('')}
          ${nearby.length > 15 ? `<p class="muted" style="margin-top:8px;">+ ${nearby.length - 15} more sites nearby</p>` : ''}
        </div>
      </div>
    `;
  } else if (coalProxLoadFailed) {
    // A failed proximity load is UNKNOWN, never a negative claim — the
    // "absence means unknown" doctrine (Codex review round 4).
    nearbyHtml = `<p class="muted" style="margin-top:12px;">Nearby-sites data failed to load. <button type="button" class="coal-btn coal-nearby-retry">Retry</button></p>`;
  } else if (coalProxMatches === null) {
    nearbyHtml = `<p class="muted" style="margin-top:12px;">Loading nearby tracked sites…</p>`;
  } else {
    nearbyHtml = `<p class="muted" style="margin-top:12px;">No tracked brownfield sites recorded within 10 miles in the current filtered program set.</p>`;
  }

  body.innerHTML = `
    <div class="coal-profile-grid">
      <div class="coal-profile-card">
        <h4>⚡ Electrical &amp; Grid POI</h4>
        <dl class="coal-dl">
          <dt>Nameplate Capacity</dt><dd><strong>${Math.round(plant.nameplate_coal_mw).toLocaleString()} MW</strong></dd>
          <dt>Switchyard Voltage</dt><dd>${plant.switchyard_kv} kV High Voltage</dd>
          <dt>Grid Region / RTO</dt><dd>${escapeHtml(plant.iso_rto)}</dd>
          <dt>Status</dt><dd>${escapeHtml(COAL_STATUS_LABELS[plant.status] || plant.status)}${plant.retired_year ? ` (${plant.retired_year})` : plant.planned_retirement_year ? ` (${plant.planned_retirement_year})` : ''}</dd>
          <dt>Interconnection evidence</dt><dd>${plant.queue_transfer_eligible ? 'Retired or retiring connection: eligibility, rights and capacity require utility/operator review' : (plant.poi_occupied || plant.status === 'converted_gas') ? 'Connection occupied by successor units; spare capacity unassessed' : 'Operating connection; transfer rights and available capacity unassessed'}</dd>
        </dl>
      </div>
      <div class="coal-profile-card">
        <h4>💧 Water, Rail &amp; Land Assets</h4>
        <dl class="coal-dl">
          <dt>Water Intake</dt><dd>${plant.has_water_intake ? `Intake on-site${plant.intake_flow_gpm ? ` (${plant.intake_flow_gpm.toLocaleString()} GPM)` : ''}` : 'Not confirmed'}</dd>
          <dt>NPDES Permit</dt><dd>${plant.npdes_permit_id ? escapeHtml(plant.npdes_permit_id) : 'Not verified — check EPA ECHO'}</dd>
          <dt>Rail Access</dt><dd>${plant.has_rail ? 'Rail loop / siding on-site' : 'Not confirmed'}</dd>
          <dt>Site Acreage</dt><dd>${plant.site_acreage ? `${plant.site_acreage.toLocaleString()} Acres` : 'N/A'}</dd>
        </dl>
      </div>
      <div class="coal-profile-card valuation-card">
        <h4>💰 Modeled Stranded-Asset Value</h4>
        <div class="coal-val-big">~$${valM} Million</div>
        <p class="coal-val-desc">Screening estimate, not an appraisal: $180k/MW grid interconnect + $25M water + $12M rail + $8M civil, distance-decayed — anchored to the DOE/INL coal-to-nuclear 15–35% savings range. Gross of ash/CCR-closure and demolition liabilities.</p>
        <button type="button" class="coal-jump-map-btn">View on Map ↗</button>
      </div>
    </div>
    ${plant.note ? `<p class="coal-plant-note">${escapeHtml(plant.note)}</p>` : ''}
    ${plant.source_url ? `<p class="coal-plant-cite muted">Source: <a href="${escapeAttr(plant.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(plant.source_url.replace(/^https?:\/\//, ""))}</a>${plant.verified_at ? ` · verified ${escapeHtml(plant.verified_at)}` : ''}</p>` : ''}
    ${_coalNepaSectionHtml(plant.plant_name)}
    ${nearbyHtml}
  `;

  // Bind drawer actions with closures — no string-interpolated inline
  // handlers (code review 2026-08-23 #1/#8). Nearby items are real <button>s
  // so keyboard/AT users can open them.
  const jumpBtn = body.querySelector(".coal-jump-map-btn");
  if (jumpBtn) {
    jumpBtn.addEventListener("click", () =>
      window.__focusCoalPlantOnMap(plant.latitude, plant.longitude, plant.plant_name));
  }
  for (const item of body.querySelectorAll(".coal-nearby-item[data-site-id]")) {
    item.addEventListener("click", () => window.__selectAndOpenSite(item.dataset.siteId));
  }
  const proxRetry = body.querySelector(".coal-nearby-retry");
  if (proxRetry) {
    proxRetry.addEventListener("click", () => {
      ensureCoalConversionsProxLoaded().then(() => window.__inspectCoalPlant(plant.plant_name));
    });
  }
  const nepaRetry = body.querySelector(".coal-nepa-retry");
  if (nepaRetry) {
    nepaRetry.addEventListener("click", () => {
      ensureCoalNepaLoaded().then(() => window.__inspectCoalPlant(plant.plant_name));
    });
  }

  drawer.dataset.plant = plant.plant_name; // lets the lazy NEPA load re-render the right plant
  drawer.hidden = false;
  drawer.scrollIntoView({ behavior: "smooth", block: "nearest" });
};

window.__selectAndOpenSite = function(id) {
  if (typeof window.__setView === "function") {
    window.__setView("map");
  }
  setTimeout(() => {
    if (typeof selectSite === "function") {
      selectSite(id);
    }
  }, 150);
};

// ----- AP1000 reactor-siting view -----
// Self-contained card view over docs/data/ap1000-sites.json (a curated
// overlay, NOT SiteRecords) scored by ap1000-score.js. Lazy-loaded on first
// tab activation; no map markers (these are off the main brownfield corpus).
function ensureAp1000Loaded() {
  if (ap1000LoadingPromise) return ap1000LoadingPromise;
  ap1000LoadingPromise = fetch(AP1000_SITES_URL, { priority: "low" })
    .then((r) => {
      if (r.status === 404) return { sites: [] };
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      ap1000Sites = payload.sites || [];
      for(const site of ap1000Sites) site._infraSourceMetadata = payload.source_metadata?.infra || {};
      maybeRefreshAp1000();
      return ap1000Sites;
    })
    .catch((err) => {
      console.error("AP1000 load failed", err);
      ap1000LoadingPromise = null; // allow retry
      return [];
    });
  return ap1000LoadingPromise;
}

function maybeRefreshAp1000() {
  const v = el("view-ap1000");
  if (v && v.classList.contains("active")) buildAp1000View();
}

// Ordered for the breakdown bar + chips; keys match computeAp1000Breakdown.
const AP1000_FACTORS = [
  { key: "water",        label: "Water" },
  { key: "transmission", label: "Transmission" },
  { key: "substation",   label: "Substation" },
  { key: "workforce",    label: "Workforce" },
  { key: "fiber",        label: "Fiber" },
];
const AP1000_WATER_CLASS = { abundant: "ok", adequate: "ok", marginal: "warn", poor: "bad", severe: "bad" };
const AP1000_FIBER_CLASS = { excellent: "ok", good: "ok", moderate: "warn", limited: "bad" };
const AP1000_WORKFORCE_CLASS = { strong: "ok", good: "ok", moderate: "warn", limited: "bad" };
const AP1000_FLAG_CLASS = { none: "ok", low: "ok", moderate: "warn", elevated: "warn", high: "bad" };

// Matches the radius used in build_ap1000_sites.py.
const RETIRED_PLANT_RADIUS_MI_LABEL = "25 mi";

// EIA-860M fuel code → short display label (for retired plant).
const _EIA_FUEL = {
  BIT: "coal", SUB: "coal", LIG: "coal", WC: "waste coal",
  NG:  "natural gas", DFO: "fuel oil", RFO: "fuel oil", OIL: "petroleum",
  NUC: "nuclear", PC: "pet. coke", RC: "refined coal", SC: "syngas",
};
// HIFLD active-plant text fuel → short label.
function _ap1000ActiveFuelLabel(f) {
  if (!f) return "—";
  const fl = f.toLowerCase();
  if (fl.includes("coal")) return "coal";
  if (fl.includes("gas"))  return "gas";
  if (fl.includes("nuclear")) return "nuclear";
  if (fl.includes("hydro"))   return "hydro";
  if (fl.includes("solar"))   return "solar";
  if (fl.includes("wind"))    return "wind";
  if (fl.includes("pet") || fl.includes("oil")) return "petroleum";
  if (fl.includes("batter"))  return "battery";
  return f;
}



const _ap1000Src = (url, label) =>
  url ? ` <a href="${escapeHtml(url)}" target="_blank" rel="noopener">${label} ↗</a>` : "";
const _AP1000_SCORE_SOURCE = "https://pranava0x0.github.io/brownfield-opportunities/siting-context.js";
const _AP1000_DATA_SOURCE = "https://github.com/pranava0x0/brownfield-opportunities/blob/main/docs/data/ap1000-sites.json";
const _AP1000_INFRA_SOURCE = "https://pranava0x0.github.io/brownfield-opportunities/data/infra-proximity.json";
const _AP1000_TRANSMISSION_SOURCE = "https://hifld-geoplatform.opendata.arcgis.com/datasets/geoplatform::electric-power-transmission-lines/about";
const _AP1000_SUBSTATION_SOURCE = "https://overpass-turbo.eu/";
const _AP1000_GEOHAZARD_SOURCE = "https://www.fema.gov/flood-maps/tools-resources/flood-map-products/national-flood-hazard-layer";

function _ap1000CellSrc(url, ariaLabel) {
  if (!url) return "";
  // Per-factor accessible name so a screen-reader link list reads "Water source",
  // "Acreage source", … instead of nine identical "source" links per row.
  const al = ariaLabel ? ` aria-label="${escapeHtml(ariaLabel)} source"` : "";
  return ` <a class="ap1000-cell-src" href="${escapeHtml(url)}" target="_blank" rel="noopener"${al}>source</a>`;
}

const _AP1000_HIFLD_PLANT_SOURCE = "https://hifld-geoplatform.opendata.arcgis.com/datasets/geoplatform::power-plants/about";
const _AP1000_EIA_RETIRED_SOURCE = "https://www.eia.gov/electricity/data/eia860m/";
const _EIA_ISO_RTO_SOURCE = "https://www.eia.gov/electricity/wholesale/";
const _AP1000_USGS_SEISMIC_SOURCE = "https://earthquake.usgs.gov/ws/designmaps/asce7-22.json";

function _ap1000SourceFor(s, field) {
  if (!s) return "";
  if (field === "score") return _AP1000_SCORE_SOURCE;
  if (field === "water") return s.water_source_url || "";
  if (field === "acreage") return s.acreage_source || "";
  if (field === "transmission") return _AP1000_TRANSMISSION_SOURCE;
  if (field === "substation") return _AP1000_SUBSTATION_SOURCE;
  if (field === "workforce") return s.workforce_source_url || s.acreage_source || "";
  if (field === "fiber") return s.fiber_source_url || "";
  if (field === "flags") return s.geohazard_source_url || _AP1000_GEOHAZARD_SOURCE;
  if (field === "active_plant") return _AP1000_HIFLD_PLANT_SOURCE;
  if (field === "retired_plant") return _AP1000_EIA_RETIRED_SOURCE;
  if (field === "grid_operator") return s.iso_rto_source_url || _EIA_ISO_RTO_SOURCE;
  if (field === "seismic_usgs") return s.usgs_api_source || _AP1000_USGS_SEISMIC_SOURCE;
  if (field === "rank" || field === "installation") return _AP1000_DATA_SOURCE;
  return "";
}
const _ap1000KvMi = (mi, kv) =>
  `${fmt.miles(mi)} · ${kv != null ? kv + " kV" : "kV N/A"}`;

// Concise, sortable-feeling table; each row expands to a detail row with the
// full per-factor breakdown, analyst notes, sources, and unscored geohazard
// flags. Built once on tab activation (the dataset is a static 14 rows).
function buildAp1000View() {
  const host = el("ap1000-cards");
  if (!host) return;
  if (!ap1000Sites.length) { host.innerHTML = '<p class="muted">Nuclear site evidence unavailable or loading.</p>'; return; }
  const classes = window.REACTOR_CLASSES || {};
  const selected = classes[ap1000State.cls] || {};
  const buttons = Object.entries(classes).map(([key, c]) => `<button type="button" data-reactor-class="${escapeHtml(key)}" aria-pressed="${key === ap1000State.cls}">${escapeHtml(c.label || c.name || key)}</button>`).join("");
  const rows = ap1000ScoredRows().map(({s}, i) => {
    const assessment = SiteEvidence.assessSite(s, "nuclear");
    const landMet = window.ap1000MeetsAcreageThreshold?.(s, ap1000State.cls);
    const flags = [s.seismic_flag ? `Seismic context: ${s.seismic_flag}` : null, s.flood_flag ? `Flood context: ${s.flood_flag}` : null].filter(Boolean).join(" · ");
    return `<tr class="ap1000-row" data-id="${escapeHtml(s.id || s.name)}"><td><button class="ap1000-expand" aria-expanded="false" aria-controls="nuclear-evidence-${i}">${escapeHtml(s.name)}</button><small>${escapeHtml(s.state || "")} ${s.janus_site ? "· Janus shortlist" : ""}</small>${s.af_rflp_site ? '<span class="ap1000-rflp">AF RFLP</span>' : ""}</td>` +
      SiteEvidence.PRIMARY.map(k => `<td data-label="${SiteEvidence.LABELS[k]}" data-category="${k}">${evidenceCell(assessment[k])}</td>`).join("") + `</tr>` +
      `<tr class="ap1000-detail" id="nuclear-evidence-${i}" hidden><td colspan="6"><p>Reported land threshold: ${landMet === true ? "met" : landMet === false ? "below threshold" : "unknown"}. This does not establish a usable nuclear footprint.</p>${evidenceDetails(s,"nuclear")}<p class="ap1000-flags-cell">${escapeHtml(flags)}${s.usgs_pgam != null ? ` · USGS PGA ${Number(s.usgs_pgam).toFixed(2)}g · SDC ${escapeHtml(s.usgs_sdc || "unknown")}. Building-code context; nuclear site-specific analysis required.${_ap1000CellSrc(s.usgs_api_source,"USGS seismic API")}` : ""}</p>${s.af_rflp_site ? `<p class="ap1000-rflp-detail">Air Force lease solicitation: ${Number(s.af_rflp_acres).toLocaleString()} offered acres, distinct from installation area. Solicitation does not establish an award.${_ap1000CellSrc(s.af_rflp_source_url,"Air Force lease solicitation")}</p>` : ""}<p>${escapeHtml(s.developable_basis || "")}${_ap1000CellSrc(s.acreage_source,"Land")}</p><p>${escapeHtml(s.water_note || "")}${_ap1000CellSrc(s.water_source_url,"Water")}</p></td></tr>`;
  }).join("");
  host.innerHTML = `<div class="ap1000-class-switch">${buttons}</div><p class="muted">${escapeHtml(selected.label || selected.name || ap1000State.cls)} · ${selected.min_acres || 500} acres: planning threshold. Sites listed alphabetically; confidence describes evidence.</p><details class="ap1000-class-context"><summary>Reactor assumptions and sources</summary><p>${escapeHtml(selected.water_basis || "Water demand unassessed.")}${_ap1000CellSrc(selected.spec_source,"Reactor specification")}${_ap1000CellSrc(selected.water_source,"Water demand basis")}</p></details><div class="ap1000-table-wrap"><table class="ap1000-table evidence-table"><caption class="sr-only">Nuclear installation evidence, listed alphabetically</caption><thead><tr><th scope="col">Installation</th>${SiteEvidence.PRIMARY.map(k=>`<th scope="col">${SiteEvidence.LABELS[k]}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;
  host.querySelectorAll("[data-reactor-class]").forEach(btn => btn.addEventListener("click", () => { ap1000State.cls=btn.dataset.reactorClass; buildAp1000View(); }));
  host.querySelectorAll(".ap1000-expand").forEach(btn => btn.addEventListener("click", () => { const detail=el(btn.getAttribute("aria-controls")); detail.hidden=!detail.hidden; btn.setAttribute("aria-expanded", String(!detail.hidden)); }));
}

// ----- Civilian nuclear pipeline (Nuclear Siting tab, below the military
// screen) -----
//
// Built lazily on tab activation (and again when the overlay data lands) so
// it costs nothing at first paint — the same skeleton pattern the AP1000 and
// Rankings tables use. Lists only the promising INL tiers; the remaining
// yellow / red rows stay in the data file.
function maybeRefreshNuclearCivilian() {
  const v = el("view-ap1000");
  if (v && v.classList.contains("active")) buildNuclearCivilianView();
}

function nuclearSortedPromisingSites() {
  return nuclearCivilianSites
    .filter(nuclearIsMapped)
    .slice()
    .sort((a, b) => {
      const oa = NUCLEAR_CATEGORIES[a.inl_category].order;
      const ob = NUCLEAR_CATEGORIES[b.inl_category].order;
      if (oa !== ob) return oa - ob;
      return String(a.name).localeCompare(String(b.name));
    });
}

function buildNuclearCivilianView() {
  const host = el("nuclear-civilian");
  if (!host) return;
  if (!nuclearCivilianSites.length) {
    host.replaceChildren();
    if (nuclearSitesLoadSettled && !nuclearSitesLoadFailed) {
      // Loaded successfully but genuinely empty — an explicit empty state,
      // not eternal "Loading…" (can only happen on a broken regeneration of
      // the data file; a successful empty is not retryable).
      host.insertAdjacentHTML(
        "beforeend",
        '<p class="muted">No civilian nuclear pipeline data available.</p>'
      );
      return;
    }
    if (nuclearSitesLoadFailed) {
      host.insertAdjacentHTML(
        "beforeend",
        '<p class="muted">Couldn’t load the civilian nuclear pipeline data. ' +
          '<button type="button" id="nuke-civ-retry" class="text-btn">Retry</button></p>'
      );
      const retry = el("nuke-civ-retry");
      if (retry) {
        retry.addEventListener("click", () => {
          host.replaceChildren();
          host.insertAdjacentHTML("beforeend", '<p class="muted">Loading civilian nuclear pipeline…</p>');
          ensureNuclearSitesLoaded(); // promise was reset on failure — this refetches
        });
      }
    } else {
      host.insertAdjacentHTML("beforeend", '<p class="muted">Loading civilian nuclear pipeline…</p>');
    }
    return;
  }
  const promising = nuclearSortedPromisingSites();
  const total = nuclearCivilianSites.length;
  const remainder = total - promising.length;

  // Every interpolated value is escaped; the rest of the string is static.
  const rows = promising
    .map((s) => {
      const cat = NUCLEAR_CATEGORIES[s.inl_category];
      const capacity = nuclearCapacityText(s);
      return (
        `<tr data-nuke-id="${escapeAttr(s.id)}">` +
        `<td><span class="nuke-civ-name">${escapeHtml(s.name)}</span></td>` +
        `<td>${escapeHtml(s.state || "—")}</td>` +
        `<td><span class="nuke-civ-cat ${cat.chip}">${escapeHtml(cat.label)}</span></td>` +
        `<td>${escapeHtml(nuclearLabel(s.status))}</td>` +
        `<td>${escapeHtml(nuclearLabel(s.col_status))}</td>` +
        `<td class="nuke-civ-owner">${escapeHtml(s.owner_operator || "—")}</td>` +
        `<td class="num">${escapeHtml(capacity || "—")}</td>` +
        `<td>${escapeHtml(s.iso_rto || "—")}</td>` +
        `<td>` +
          (s.lat != null && s.lon != null
            ? `<button type="button" class="nuke-civ-map" data-nuke-map="${escapeAttr(s.id)}" aria-label="Show ${escapeAttr(s.name)} on the map">map →</button>`
            : '<span class="muted-cell">—</span>') +
        `</td>` +
        `</tr>`
      );
    })
    .join("");

  host.replaceChildren();
  host.insertAdjacentHTML(
    "beforeend",
    `<h3>Civilian nuclear pipeline — ${total.toLocaleString()} tracked sites</h3>` +
    `<p class="nuke-civ-lead">Base list from Idaho National Laboratory's August 2024 study ` +
      `<a href="data/references/INL-AP1000-Opportunities-Sort128167.pdf" target="_blank" rel="noopener"><em>Opportunities for AP1000 Deployment at Existing and Planned Nuclear Sites</em></a> ` +
      `(INL/MIS-24-80216), which screened existing and planned civilian nuclear sites and sorted them into readiness tiers — ` +
      `extended here with announced restarts and post-study entrants (2025–26 NRC filings). ` +
      `The ${promising.length.toLocaleString()} sites in the promising tiers are listed below and carry a ⚛ marker on the Map; ` +
      `each marker's popup also lists the tracked Superfund sites within 50 mi.</p>` +
    `<div class="nuke-civ-table-wrap"><table class="nuke-civ-table">` +
      `<caption class="sr-only">Civilian nuclear sites in the promising INL readiness tiers, grouped by tier then name.</caption>` +
      `<thead><tr>` +
        `<th scope="col">Site</th><th scope="col">ST</th><th scope="col">Tier</th>` +
        `<th scope="col">Status</th><th scope="col">COL status</th>` +
        `<th scope="col">Owner / operator</th><th class="num" scope="col">Units × MWe</th>` +
        `<th scope="col">ISO/RTO</th><th scope="col"><span class="sr-only">Map</span></th>` +
      `</tr></thead>` +
      `<tbody>${rows}</tbody>` +
    `</table></div>` +
    `<p class="nuke-civ-foot">${remainder.toLocaleString()} further sites tracked in the source data ` +
      `(yellow / red tiers) — present in ` +
      `<a href="data/nuclear-civilian-sites.json" target="_blank" rel="noopener">nuclear-civilian-sites.json</a>, ` +
      `not shown in this table or on the map.</p>`
  );

  if (!host._nukeWired) {
    host._nukeWired = true;
    host.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-nuke-map]");
      if (btn) focusNuclearSiteOnMap(btn.dataset.nukeMap);
    });
  }
}

// Jump from a civilian-pipeline row to its ⚛ marker. Routes through the real
// Map tab button so tab state, hash, and invalidateSize all follow the one
// existing code path.
function focusNuclearSiteOnMap(id) {
  const s = nuclearCivilianSites.find((x) => x.id === id);
  if (!s || s.lat == null || s.lon == null) return;
  const mapTab = el("tab-map");
  if (mapTab) mapTab.click();
  // The Map tab defers invalidateSize() by 50 ms; recenter after that so the
  // view math runs against the real container size.
  setTimeout(() => {
    if (!map) return;
    map.setView([s.lat, s.lon], 9);
    const marker = nuclearMarkersById.get(id);
    if (marker) marker.openPopup();
  }, 80);
}

const AP1000_CSV_COLUMNS = [
  { label: "installation", value: (r) => r.s.name, source: (r) => _ap1000SourceFor(r.s, "installation") },
  { label: "state", value: (r) => r.s.state, source: (r) => _ap1000SourceFor(r.s, "installation") },
  { label: "water", value: (r) => r.s.water_adequacy, source: (r) => _ap1000SourceFor(r.s, "water") },
  { label: "water_context_note", value: (r) => r.s.water_note, source: (r) => _ap1000SourceFor(r.s, "water") },
  { label: "water_source", value: (r) => r.s.water_source, source: (r) => _ap1000SourceFor(r.s, "water") },
  { label: "water_rights_class", value: (r) => r.s.water_rights_class, source: (r) => r.s.water_rights_source_url },
  { label: "water_rights_regime", value: (r) => r.s.water_rights_regime, source: (r) => r.s.water_rights_source_url },
  { label: "water_rights_context_note", value: (r) => r.s.water_rights_note, source: (r) => r.s.water_rights_source_url },
  { label: "water_low_flow_cfs", value: (r) => r.s.water_low_flow_cfs, source: (r) => _ap1000SourceFor(r.s, "water") },
  { label: "reactor_class", value: () => ap1000State.cls, source: (r) => _ap1000SourceFor(r.s, "score") },
  { label: "acreage_threshold_acres", value: () => ((window.REACTOR_CLASSES || {})[ap1000State.cls] || {}).min_acres ?? (window.AP1000_MIN_DEVELOPABLE_ACRES || 500), source: (r) => _ap1000SourceFor(r.s, "acreage") },
  { label: "acreage_threshold_met", value: (r) => window.ap1000MeetsAcreageThreshold ? window.ap1000MeetsAcreageThreshold(r.s, ap1000State.cls) : "", source: (r) => _ap1000SourceFor(r.s, "acreage") },
  { label: "developable_acreage", value: (r) => r.s.developable_acreage, source: (r) => _ap1000SourceFor(r.s, "acreage") },
  { label: "developable_acreage_reason", value: (r) => r.s.developable_basis, source: (r) => _ap1000SourceFor(r.s, "acreage") },
  { label: "installation_acreage", value: (r) => r.s.installation_acreage, source: (r) => _ap1000SourceFor(r.s, "acreage") },
  { label: "transmission_mi", value: (r) => r.s.transmission_mi, source: (r) => _ap1000SourceFor(r.s, "transmission") },
  { label: "transmission_kv", value: (r) => r.s.transmission_kv, source: (r) => _ap1000SourceFor(r.s, "transmission") },
  { label: "substation_mi", value: (r) => r.s.substation_mi, source: (r) => _ap1000SourceFor(r.s, "substation") },
  { label: "substation_kv", value: (r) => r.s.substation_kv, source: (r) => _ap1000SourceFor(r.s, "substation") },
  { label: "workforce", value: (r) => r.s.workforce, source: (r) => _ap1000SourceFor(r.s, "workforce") },
  { label: "workforce_reason", value: (r) => r.s.workforce_note, source: (r) => _ap1000SourceFor(r.s, "workforce") },
  { label: "workforce_metro", value: (r) => r.s.workforce_metro, source: (r) => _ap1000SourceFor(r.s, "workforce") },
  { label: "fiber", value: (r) => r.s.fiber, source: (r) => _ap1000SourceFor(r.s, "fiber") },
  { label: "fiber_context_note", value: (r) => r.s.fiber_note, source: (r) => _ap1000SourceFor(r.s, "fiber") },
  { label: "seismic_flag", value: (r) => r.s.seismic_flag, source: (r) => _ap1000SourceFor(r.s, "flags") },
  { label: "usgs_pgam_g", value: (r) => r.s.usgs_pgam, source: (r) => _ap1000SourceFor(r.s, "seismic_usgs") },
  { label: "usgs_ss_g", value: (r) => r.s.usgs_ss, source: (r) => _ap1000SourceFor(r.s, "seismic_usgs") },
  { label: "usgs_sdc", value: (r) => r.s.usgs_sdc, source: (r) => _ap1000SourceFor(r.s, "seismic_usgs") },
  { label: "usgs_exceeds_sse_0.30g", value: (r) => r.s.usgs_exceeds_sse, source: (r) => _ap1000SourceFor(r.s, "seismic_usgs") },
  { label: "flood_flag", value: (r) => r.s.flood_flag, source: (r) => _ap1000SourceFor(r.s, "flags") },
  { label: "janus_site", value: (r) => r.s.janus_site, source: (r) => r.s.janus_source_url || _ap1000SourceFor(r.s, "installation") },
  { label: "af_rflp_site", value: (r) => r.s.af_rflp_site, source: (r) => r.s.af_rflp_source_url || "" },
  { label: "af_rflp_acres", value: (r) => r.s.af_rflp_acres, source: (r) => r.s.af_rflp_source_url || "" },
  { label: "iso_rto", value: (r) => r.s.iso_rto, source: (r) => _ap1000SourceFor(r.s, "grid_operator") },
  { label: "iso_rto_note", value: (r) => r.s.iso_rto_note, source: (r) => _ap1000SourceFor(r.s, "grid_operator") },
  { label: "power_plant_mi", value: (r) => r.s.power_plant_mi, source: (r) => _ap1000SourceFor(r.s, "active_plant") },
  { label: "power_plant_mw", value: (r) => r.s.power_plant_mw, source: (r) => _ap1000SourceFor(r.s, "active_plant") },
  { label: "power_plant_fuel", value: (r) => r.s.power_plant_fuel, source: (r) => _ap1000SourceFor(r.s, "active_plant") },
  { label: "retired_plant_mi", value: (r) => r.s.retired_plant_mi, source: (r) => _ap1000SourceFor(r.s, "retired_plant") },
  { label: "retired_plant_mw", value: (r) => r.s.retired_plant_mw, source: (r) => _ap1000SourceFor(r.s, "retired_plant") },
  { label: "retired_plant_fuel", value: (r) => r.s.retired_plant_fuel, source: (r) => _ap1000SourceFor(r.s, "retired_plant") },
  { label: "retired_plant_year", value: (r) => r.s.retired_plant_year, source: (r) => _ap1000SourceFor(r.s, "retired_plant") },
  { label: "retired_plant_name", value: (r) => r.s.retired_plant_name, source: (r) => _ap1000SourceFor(r.s, "retired_plant") },
];

// Reactor class selected in the Nuclear Siting tab. AP1000 / APR1400 are
// large Gen III+ PWRs — a different CATEGORY from SMRs and microreactors
// (see REACTOR_CLASSES in ap1000-score.js); the selector regroups the same
// 14 sites under each class's water demand / acreage threshold / voltage
// expectations. Default stays "ap1000" so deep links and tests are stable.
const ap1000State = { cls: "ap1000" };

function ap1000ScoredRows() {
  return ap1000Sites.slice().sort(evidenceNameOrder).map(s => ({s}));
}

function buildAp1000Csv() {
  const headers = [];
  for (const c of AP1000_CSV_COLUMNS) {
    headers.push(c.label, `${c.label}_source_url`);
  }
  const categoryColumns = evidenceCsvColumns(r => r.s);
  headers.push(...categoryColumns.map(c => c.label));
  const rows = [headers];
  for (const r of ap1000ScoredRows()) {
    const row = [];
    const assessment = SiteEvidence.assessSite(r.s);
    for (const c of AP1000_CSV_COLUMNS) {
      const v = c.value(r);
      const src = c.source(r);
      row.push(v == null ? "" : v, src || "");
    }
    row.push(...categoryColumns.map(c => c.compute(r,assessment)));
    rows.push(row);
  }
  return rows.map(csvRow).join("\n");
}

function downloadAp1000Csv() {
  const csv = buildAp1000Csv();
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ap1000-siting-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function wireAp1000ExportCsv() {
  const btn = el("ap1000-export-csv");
  if (!btn) return;
  btn.addEventListener("click", () => {
    ensureAp1000Loaded().then(() => downloadAp1000Csv());
  });
  window.__buildAp1000Csv = buildAp1000Csv;
}


// ===== Microreactors view =====
//
// Three surfaces on one tab, because they only make sense together:
//
//   1. THE FLEET — the 11 designs in the 1–20 MWe band plus one labelled
//      adjacency, each carrying the evidence band its strongest documented
//      state supports.
//   2. THE COMMITMENTS — 32 named pairings of a buyer, a programme, or a
//      site to capacity. 24 carry coordinates and render as ⬣ markers on the
//      map; the Army Janus nine take their coordinates from the same
//      ap1000-sites.json the Nuclear Siting tab uses, so the two nuclear
//      surfaces can never disagree about where Fort Wainwright is.
//   3. THE SITING SCREEN — the whole corpus ranked by computeMicroreactorScore
//      (microreactor-score.js), which inverts the grid signal every other lens
//      in this app uses.
//
// Data: docs/data/microreactor-fleet.json, built by
// scripts/build_microreactor_fleet.py from two sibling research projects.
//
// The view is built ENTIRELY in JS on first tab activation. index.html ships
// only a four-node skeleton because the first-paint DOM budget is 5,000 nodes
// with roughly 60 to spare — see CLAUDE.md, "Paginated table".

const MICRO_RANK_LIMIT = 100;
const MICRO_SCORE_SOURCE = "https://github.com/pranava0x0/brownfield-opportunities/blob/main/docs/microreactor-score.js";
const MICRO_DATA_SOURCE = "https://github.com/pranava0x0/brownfield-opportunities/blob/main/docs/data/microreactor-fleet.json";

const microState = {
  ranked: [],
  offGridOnly: false,   // hard-islanded sites only (no transmission within 100 mi)
  janusSelectedId: null,
  built: false,
};

function ensureMicroFleetLoaded() {
  if (microFleetLoadingPromise) return microFleetLoadingPromise;
  microFleetLoadFailed = false;
  microFleetLoadingPromise = fetch(MICRO_FLEET_URL, { priority: "low" })
    .then((r) => {
      // A 404 is a failure, not an empty fleet. Rendering "0 designs" when
      // the file simply didn't deploy would be a false negative about the
      // industry, which is exactly the trap the nuclear overlay documents.
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, MICRO_FLEET_URL);
      microFleet = payload;
      addMicroCommitmentMarkers();
      maybeRefreshMicro();
      return payload;
    })
    .catch((err) => {
      console.error("Microreactor fleet load failed:", err);
      microFleetLoadingPromise = null;   // allow retry
      microFleetLoadFailed = true;
      maybeRefreshMicro();
      return null;
    });
  return microFleetLoadingPromise;
}

function ensureJanusNepaLoaded() {
  if (janusNepaLoadingPromise) return janusNepaLoadingPromise;
  janusNepaLoadFailed = false;
  janusNepaLoadingPromise = fetch(JANUS_NEPA_URL, { priority: "low" })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at, JANUS_NEPA_URL);
      janusNepa = payload;
      const requested = new URLSearchParams(location.search).get("janus");
      if (requested && (payload.sites || []).some((site) => site.id === requested)) {
        microState.janusSelectedId = requested;
      }
      maybeRefreshMicro();
      return payload;
    })
    .catch((err) => {
      console.error("Janus NEPA screening load failed:", err);
      janusNepaLoadingPromise = null;
      janusNepaLoadFailed = true;
      maybeRefreshMicro();
      return null;
    });
  return janusNepaLoadingPromise;
}

function microCommitmentPopupHtml(c) {
  const band = (microFleet?.evidence_bands || []).find((b) => b.band === c.band);
  const srcs = (c.sources || []).slice(0, 2).map(
    (s) => `<a href="${escapeAttr(s.url)}" target="_blank" rel="noopener" class="ref-campus-link">${escapeHtml(s.label)} ↗</a>`
  ).join("");
  return (
    `<div class="ref-campus-popup">` +
    `<strong>${escapeHtml(c.name)}</strong>` +
    `<div class="micro-pop-band band-${escapeAttr(c.band)}">${escapeHtml(band ? band.label : c.band)}</div>` +
    (c.location ? `<div class="ref-campus-company">${escapeHtml(c.location)}` +
      (c._inset ? ` <span class="micro-note">· shown in the ${escapeHtml(c._inset)} inset ` +
        `(${c.lat_real.toFixed(3)}, ${c.lon_real.toFixed(3)})</span>` : "") +
      `</div>` : "") +
    `<div class="ref-campus-meta">` +
      `<span>${escapeHtml(c.vendor_name || "Vendor not assigned")}</span>` +
      `<span>${escapeHtml(c.power_label || "Output not specified")}</span>` +
    `</div>` +
    `<div class="ref-campus-prev">${escapeHtml(c.owner)}</div>` +
    `<div class="ref-campus-prev" style="font-style:normal">${escapeHtml(c.instrument)}</div>` +
    ((c.gaps || []).length
      ? `<div class="micro-pop-gap"><strong>Gap:</strong> ${escapeHtml(c.gaps[0])}</div>` : "") +
    (c.janus && c.ap1000_ref
      ? `<a href="?janus=${encodeURIComponent(c.ap1000_ref)}#micro" class="ref-campus-link">Open environmental screen →</a>`
      : "") +
    srcs +
    `</div>`
  );
}

function addMicroCommitmentMarkers() {
  if (!microCommitmentLayer || !microFleet) return;   // map not yet initialized
  if (microCommitmentLayer.getLayers().length) return; // already populated
  for (const c of microFleet.commitments || []) {
    if (c.lat == null || c.lon == null) continue;
    // Alaska is the whole point of two of these rows — Eielson AFB and the
    // Fort Wainwright Janus installation — and their real coordinates sit
    // outside US_BOUNDS, so a raw marker would be unreachable behind
    // maxBoundsViscosity. Remap into the ALASKA inset box the same way
    // ingestSites() does for the corpus. Mutating in place is safe: the
    // tables render `location` text, never coordinates, and applyInsetRemap
    // preserves the originals on lat_real / lon_real.
    applyInsetRemap(c);
    const icon = L.divIcon({
      // Glyph straight in the icon div — no inner <span>. Copies the pattern
      // the ⚛ nuclear overlay uses to halve per-marker DOM cost.
      className: "micro-commit-icon band-" + c.band,
      html: "⬣",
      iconSize: [20, 20],
      iconAnchor: [10, 10],
      popupAnchor: [0, -11],
    });
    const marker = L.marker([c.lat, c.lon], { icon, zIndexOffset: 460 });
    marker.bindPopup(microCommitmentPopupHtml(c), { maxWidth: 300 });
    microCommitmentLayer.addLayer(marker);
  }
  rerenderLegend();
}

function maybeRefreshMicro() {
  const v = el("view-micro");
  if (v && v.classList.contains("active")) buildMicroView();
}

// Ordered for the breakdown chips; keys match computeMicroreactorBreakdown.
const MICRO_FACTORS = [
  { key: "licensing_path", label: "Licensing path" },
  { key: "grid_isolation", label: "Grid isolation" },
  { key: "anchor_load",    label: "Anchor load" },
  { key: "deliverability", label: "Deliverability" },
  { key: "readiness",      label: "Readiness" },
];

// Tier breaks are anchored to THIS lens's own distribution, not copied from
// the data-center lens's 75/50/25. The microreactor lens has a lower practical
// ceiling by construction: grid isolation pulls against deliverability and
// readiness, so no real site can max both halves of the rubric. Observed over
// the 46,759-site corpus the scores run min 0 / median 37 / p90 50 / p99 61 /
// max 73, so these breaks land at roughly the top 0.5%, top 5% and top 25%.
// Reusing 75/50/25 here would paint the entire corpus one colour and the tier
// would carry no information at all. Re-measure on a refresh that materially
// shifts the distribution — computeMicroreactorScore over window.__sites is
// the whole measurement.
const MICRO_TIER_BREAKS = Object.freeze({ strong: 64, moderate: 55, marginal: 44 });



// Rank the globally-filtered set. Sourcing from `tableState.filtered` — not
// from `sites` — is what makes the search / state / program / acreage filters
// carry onto this tab, the same unification the Rankings tab got in v1.21.
function microRankedSites() {
  return tableState.filtered.filter(s => microreactorMeetsAcreageThreshold(s) !== false
    && (!microState.offGridOnly || (s.transmission_mi == null && s.substation_mi == null)))
    .slice().sort(evidenceNameOrder).map(site => ({site}));
}

function _microFleetRows() {
  const bands = new Map((microFleet.evidence_bands || []).map((b) => [b.band, b]));
  return (microFleet.vendors || []).map((v) => {
    const band = bands.get(v.band);
    const specs = [
      v.coolant, v.fuel,
      v.refuel_years ? `${v.refuel_years}-yr refuelling` : null,
      v.footprint_acres ? `${v.footprint_acres} ac footprint` : null,
      v.mass_tonnes ? `${v.mass_tonnes} t` : null,
      v.transport,
    ].filter(Boolean);
    const srcs = (v.sources || []).map(
      (s) => `<a href="${escapeAttr(s.url)}" target="_blank" rel="noopener" title="${escapeAttr(s.label)}">↗</a>`
    ).join(" ");
    return (
      `<tr${v.adjacent ? ' class="micro-adjacent"' : ""}>` +
      `<td><strong>${escapeHtml(v.design)}</strong>` +
        `<div class="micro-sub">${escapeHtml(v.name)}${v.ticker ? ` · ${escapeHtml(v.ticker)}` : ""}</div>` +
        (v.adjacent ? `<div class="micro-note">Adjacency — ${escapeHtml(v.adjacent_note)}</div>` : "") +
      `</td>` +
      `<td class="micro-mwe">${escapeHtml(v.mwe_label || "—")}</td>` +
      `<td class="micro-specs">${specs.length ? escapeHtml(specs.join(" · ")) : '<span class="muted-cell">Not published</span>'}</td>` +
      `<td><span class="micro-band band-${escapeAttr(v.band)}">${escapeHtml(band ? band.label : v.band)}</span>` +
        `<div class="micro-note">${escapeHtml(v.band_basis)}</div></td>` +
      `<td class="micro-src">${srcs}</td>` +
      `</tr>`
    );
  }).join("");
}

const MICRO_TRACK_LABEL = {
  "us-gov": "U.S. Government",
  "us-commercial": "U.S. Commercial",
  "intl": "International",
};

function _microCommitmentRows() {
  const bands = new Map((microFleet.evidence_bands || []).map((b) => [b.band, b]));
  const order = ["us-gov", "us-commercial", "intl"];
  const byTrack = new Map(order.map((t) => [t, []]));
  for (const c of microFleet.commitments || []) {
    (byTrack.get(c.track) || byTrack.get("us-commercial")).push(c);
  }
  let html = "";
  for (const track of order) {
    const rows = byTrack.get(track) || [];
    if (!rows.length) continue;
    html += `<tr class="micro-track-row"><th colspan="6" scope="colgroup">` +
            `${escapeHtml(MICRO_TRACK_LABEL[track])} <span class="micro-note">${rows.length}</span></th></tr>`;
    for (const c of rows) {
      const band = bands.get(c.band);
      const srcs = (c.sources || []).map(
        (s) => `<a href="${escapeAttr(s.url)}" target="_blank" rel="noopener" title="${escapeAttr(s.label)}">↗</a>`
      ).join(" ");
      html +=
        `<tr>` +
        `<td><strong>${escapeHtml(c.name)}</strong>` +
          `<div class="micro-sub">${escapeHtml(c.owner)}</div>` +
          ((c.gaps || []).length ? `<div class="micro-note micro-gap">Gap: ${escapeHtml(c.gaps[0])}</div>` : "") +
        `</td>` +
        `<td>${escapeHtml(c.vendor_name || "—")}</td>` +
        `<td>${escapeHtml(c.location || "—")}` +
          (c.lat != null ? ` <span class="micro-mapped" title="Shown on the map">⬣</span>` : "") +
        `</td>` +
        `<td class="micro-mwe">${escapeHtml(c.power_label || "—")}</td>` +
        `<td><span class="micro-band band-${escapeAttr(c.band)}">${escapeHtml(band ? band.label : c.band)}</span>` +
          `<div class="micro-note">${escapeHtml(c.status)}</div></td>` +
        `<td class="micro-src">${srcs}</td>` +
        `</tr>`;
    }
  }
  return html;
}

function _janusStatus(section, content) {
  if (!section || section.status !== "ok") {
    return '<span class="janus-unavailable">Unavailable</span>';
  }
  return content || '<span class="muted-cell">None returned</span>';
}

function _janusMatrixHtml() {
  if (janusNepaLoadFailed) {
    return '<p class="muted">Janus environmental screen could not be loaded. ' +
      '<button type="button" id="janus-retry" class="text-btn">Retry</button></p>';
  }
  if (!janusNepa) return '<p class="muted">Loading Janus environmental evidence…</p>';

  const rows = (janusNepa.sites || []).map((site) => {
    const s = site.screening || {};
    const ipac = s.ipac || {};
    const ipacCounts = ipac.counts || {};
    const wildlife = _janusStatus(ipac,
      `<strong>${ipacCounts.listed_species || 0}</strong> ESA species` +
      `<div class="micro-sub">${ipacCounts.critical_habitat || 0} critical-habitat records · ` +
      `${ipacCounts.migratory_birds || 0} migratory birds</div>`);
    const water = _janusStatus(ipac,
      `<strong>${ipacCounts.wetland_types || 0}</strong> wetland types` +
      '<div class="micro-sub">10-mi context; field delineation still required</div>');
    const cultural = _janusStatus(s.nrhp,
      `<strong>${s.nrhp.count || 0}</strong> NRHP records`) +
      `<div class="micro-sub">${_janusStatus(s.tribal, `${s.tribal.count || 0} mapped tribal geographies`)}</div>`;
    const protectedLand = _janusStatus(s.padus,
      `<strong>${s.padus.count || 0}</strong> PAD-US records` +
      '<div class="micro-sub">0.1-mi point context only</div>');
    const districts = (s.usace?.districts || []).map((d) => d.district_abbreviation || d.district_name);
    const agency = _janusStatus(s.usace,
      districts.length ? escapeHtml(districts.join(" · ")) : '<span class="muted-cell">No district returned</span>');
    const map = site.map_summary || {};
    const mapText = map.feature_count == null
      ? '<span class="janus-unavailable">Unavailable</span>'
      : `<strong>${map.feature_count.toLocaleString()}</strong> features` +
        `<div class="micro-sub">${map.layers_failed || 0} failed layer${map.layers_failed === 1 ? "" : "s"}</div>`;
    const selected = microState.janusSelectedId === site.id;
    return `<tr class="janus-row${selected ? " selected" : ""}">` +
      `<td><button type="button" class="janus-site-button" data-janus="${escapeAttr(site.id)}" ` +
        `aria-expanded="${selected}"><strong>${escapeHtml(site.name)}</strong>` +
        `<span>${escapeHtml(site.location || site.state)}</span></button></td>` +
      `<td>${wildlife}</td><td>${water}</td><td>${cultural}</td>` +
      `<td>${protectedLand}</td><td>${agency}</td><td>${mapText}</td></tr>`;
  }).join("");

  return `<div class="micro-table-wrap"><table class="micro-table janus-table">` +
    `<thead><tr><th scope="col">Installation</th><th scope="col">ESA / wildlife</th>` +
    `<th scope="col">Water context</th><th scope="col">Cultural / tribal</th>` +
    `<th scope="col">Protected land</th><th scope="col">USACE path</th>` +
    `<th scope="col">Map package</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function _janusNames(items, keys, limit = 8) {
  const names = (items || []).map((item) => {
    for (const key of keys) if (item?.[key]) return item[key];
    return null;
  }).filter(Boolean);
  if (!names.length) return "None returned";
  return names.slice(0, limit).join(" · ") + (names.length > limit ? ` · +${names.length - limit} more` : "");
}

function _janusDetailHtml() {
  if (!janusNepa || !microState.janusSelectedId) {
    return '<p class="janus-prompt">Choose an installation to inspect records, source links, limitations, and its map package.</p>';
  }
  const site = (janusNepa.sites || []).find((row) => row.id === microState.janusSelectedId);
  if (!site) return "";
  const s = site.screening || {};
  const source = janusNepa.sources || {};
  const pathway = janusNepa.deployment_pathway || {};
  const cards = [
    ["ipac", "Species and habitat", _janusNames(s.ipac?.species, ["common_name", "scientific_name"])],
    ["tribal", "Mapped tribal geographies", _janusNames(s.tribal?.tribal_lands, ["name", "namelsad"])],
    ["nrhp", "Listed historic properties", _janusNames(s.nrhp?.properties, ["property_name", "name"])],
    ["padus", "Protected-land point context", _janusNames(s.padus?.largest_records, ["unit_name", "name"])],
    ["usace", "Regulatory district and wetland method", _janusNames(s.usace?.districts, ["district_name"])],
    ["nepa_assist", "EPA NEPAssist", s.nepa_assist?.status === "ok" ? "Interactive screening report available" : "Source unavailable"],
  ].map(([key, heading, text]) => {
    const section = s[key] || {};
    const meta = source[key] || {};
    const reportUrl = key === "nepa_assist" ? section.report_url : null;
    return `<article class="janus-source-card">` +
      `<div class="janus-card-head"><h4>${escapeHtml(heading)}</h4>` +
      `<span class="janus-source-status status-${escapeAttr(section.status || "unavailable")}">` +
        `${escapeHtml(section.status === "ok" ? "Available" : "Unavailable")}</span></div>` +
      `<p>${escapeHtml(text)}</p>` +
      `<p class="micro-note">${escapeHtml(meta.covers || "Coverage not documented")}</p>` +
      `<div class="janus-card-links">` +
        (meta.url ? `<a href="${escapeAttr(meta.url)}" target="_blank" rel="noopener">Source ↗</a>` : "") +
        (reportUrl ? `<a href="${escapeAttr(reportUrl)}" target="_blank" rel="noopener">Open report ↗</a>` : "") +
        (section.retrieved_at ? `<span>Retrieved ${escapeHtml(section.retrieved_at.slice(0, 10))}</span>` : "") +
      `</div>` +
      (section.error ? `<p class="janus-error">${escapeHtml(section.error)}</p>` : "") +
      `</article>`;
  }).join("");
  const pathwayLinks = (pathway.sources || []).map((item) =>
    `<a href="${escapeAttr(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.label)} ↗</a>`
  ).join("");
  return `<div id="janus-detail" class="janus-detail" tabindex="-1">` +
    `<div class="janus-detail-head"><div><p class="eyebrow">Installation context</p>` +
      `<h3>${escapeHtml(site.name)}</h3><p>${escapeHtml(site.location)} · ` +
      `${janusNepa.screening_buffer_miles}-mile screen around a reference point</p></div>` +
      `<button type="button" class="ap1000-export janus-map-button" data-janus-map="${escapeAttr(site.id)}">` +
      `Show ${site.map_summary?.feature_count?.toLocaleString() || "available"} features on map</button></div>` +
    `<div class="janus-limit"><strong>Screening, not siting:</strong> installation point only; parcel unknown. ` +
      `No count here is a permit, an agency decision, a wetland-jurisdiction call, or a suitability conclusion. A source recorded as unavailable is different from a result of zero.</div>` +
    `<article class="janus-pathway"><div><p class="eyebrow">Announced deployment pathway</p>` +
      `<h4>${escapeHtml(pathway.reactor_regulator || "Authorization path not published")}</h4>` +
      `<p>${escapeHtml(pathway.acquisition || "Acquisition details unavailable")}</p>` +
      `<p class="micro-note">${escapeHtml(pathway.nepa_status || "Project-specific NEPA pathway not published.")}</p>` +
      `<p class="micro-note">${escapeHtml(pathway.limitations || "Confirm in award documents.")}</p></div>` +
      `<div class="janus-card-links">${pathwayLinks}</div></article>` +
    `<div class="janus-source-grid">${cards}</div></div>`;
}

function _remapJanusGeoJson(geojson, state) {
  const inset = INSET_BY_STATE[state];
  if (!inset) return geojson;
  const copy = JSON.parse(JSON.stringify(geojson));
  const remap = (coords) => {
    if (typeof coords?.[0] === "number") {
      const lon = Math.max(inset.src.west, Math.min(inset.src.east, coords[0]));
      const lat = Math.max(inset.src.south, Math.min(inset.src.north, coords[1]));
      const fLon = (lon - inset.src.west) / (inset.src.east - inset.src.west);
      const fLat = (lat - inset.src.south) / (inset.src.north - inset.src.south);
      coords[0] = inset.dst.west + fLon * (inset.dst.east - inset.dst.west);
      coords[1] = inset.dst.south + fLat * (inset.dst.north - inset.dst.south);
      return;
    }
    for (const child of coords || []) remap(child);
  };
  for (const feature of copy.features || []) remap(feature.geometry?.coordinates);
  return copy;
}

function _janusLayerColor(layer) {
  if (/nhd_|wetland/.test(layer)) return cssColor("--janus-water");
  if (/critical_habitat|wildlife|tribal/.test(layer)) return cssColor("--janus-ecology");
  if (/federal|nps|fire/.test(layer)) return cssColor("--janus-land");
  return cssColor("--janus-context");
}

// Fit target for a screening map package: the ROI buffer feature, never the
// union of every layer's geometry — USACE districts and wetland delineation
// regions are multi-state polygons, so a union fit zooms out to half the
// country (the Hanford package fit to zoom 4 before this). Falls back to
// the full layer bounds only when the package carries no ROI feature.
function _screeningFitBounds(payload, renderedLayer) {
  const roiFeatures = (payload.features || []).filter((f) => {
    const t = f.properties?.type;
    return t === "Region of Interest" || t === "Project Location";
  });
  if (roiFeatures.length) {
    const b = L.geoJSON({ type: "FeatureCollection", features: roiFeatures }).getBounds();
    if (b.isValid()) return b;
  }
  const b = renderedLayer.getBounds();
  return b.isValid() ? b : null;
}

function showJanusMap(siteId) {
  const site = (janusNepa?.sites || []).find((row) => row.id === siteId);
  if (!site?.geojson_url) return;
  const button = document.querySelector(`[data-janus-map="${CSS.escape(siteId)}"]`);
  if (button) { button.disabled = true; button.textContent = "Loading map…"; }
  fetch(site.geojson_url)
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((payload) => {
      if (janusNepaLayer) map.removeLayer(janusNepaLayer);
      // One screening overlay at a time — clear a lingering Hanford package
      // too (the Hanford flow clears this one; keep the symmetry).
      if (hanfordNepaLayer) { map.removeLayer(hanfordNepaLayer); hanfordNepaLayer = null; }
      const displayPayload = _remapJanusGeoJson(payload, site.state);
      janusNepaLayer = L.geoJSON(displayPayload, {
        style: (feature) => ({
          color: _janusLayerColor(feature.properties?.layer || feature.properties?.type || "context"),
          weight: feature.properties?.type === "Region of Interest" ? 2 : 1,
          opacity: 0.8,
          fillOpacity: feature.properties?.type === "Region of Interest" ? 0.03 : 0.12,
        }),
        pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
          radius: feature.properties?.type === "Project Location" ? 6 : 3,
          color: _janusLayerColor(feature.properties?.layer || "context"),
          fillOpacity: 0.75,
        }),
        onEachFeature: (feature, layer) => {
          const props = feature.properties || {};
          const label = props.name || props.common_name || props.type || props.layer || "Mapped feature";
          layer.bindPopup(`<strong>${escapeHtml(label)}</strong><br>` +
            `<span class="micro-note">${escapeHtml(props.layer || "screening area")}</span>`);
        },
      }).addTo(map);
      el("tab-map")?.click();
      const bounds = _screeningFitBounds(displayPayload, janusNepaLayer);
      if (bounds) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 11 });
      const failedLayers = site.map_summary?.layers_failed || 0;
      showToast(
        `${site.name}: NEPA screening layers shown. Not a project footprint.` +
        (failedLayers > 0 ? ` ${failedLayers} layer${failedLayers === 1 ? "" : "s"} unavailable — not a no-hit.` : "")
      );
    })
    .catch((err) => {
      console.error("Janus GeoJSON load failed:", err);
      showToast(`${site.name}: map package unavailable.`);
    })
    .finally(() => {
      if (button) { button.disabled = false; button.textContent = "Show features on map"; }
    });
}

// ----- DOE site dossiers (federal sites, screened end-to-end) -----
// Data: docs/data/<site>-e2e.json from scripts/build_hanford_e2e.py (Hanford)
// and scripts/build_doe_sites_e2e.py (SRS / Portsmouth / Paducah / WIPP) —
// curated parcel ground truth + a nepa-mcp screen + corpus joins. The tab
// interior mounts lazily from <template id="hanford-template"> (ids keep
// their historical hanford- names for test/CSS continuity — the naming-vs-
// identifier split rule); only Hanford loads eagerly (its generated_at
// drives the refresh date), the other sites lazy-load on pill selection and
// therefore deliberately do NOT call recordRefreshDate (reference-campuses
// rule: a file whose loader may never run must not drive the displayed date).

// Site registry — drift-safe iteration rule (UAT-007): pills, loaders, and
// markers all derive from this list; never hardcode the site set elsewhere.
const DOE_SITES = [
  { id: "hanford", label: "Hanford", state: "WA", url: HANFORD_E2E_URL },
  { id: "srs", label: "Savannah River", state: "SC", url: "data/srs-e2e.json" },
  { id: "portsmouth", label: "Portsmouth", state: "OH", url: "data/portsmouth-e2e.json" },
  { id: "paducah", label: "Paducah", state: "KY", url: "data/paducah-e2e.json" },
  { id: "wipp", label: "WIPP", state: "NM", url: "data/wipp-e2e.json" },
];

let doeActiveSite = "hanford";
let doeUrlSiteApplied = false;        // one-shot ?doe= param read
const doeSiteData = {};               // site id -> dossier payload
const doeSitePromises = {};           // site id -> in-flight fetch promise
const doeSiteFailed = {};             // site id -> last load failed
const doeSelectedParcel = {};         // site id -> parcel id open in the drawer

const HANFORD_KIND_LABEL = {
  cleanup_area: "Cleanup area",
  cleanup_core: "Cleanup core",
  transferred: "Transferred",
  leased_energy: "Leased for energy",
  leased_industrial: "Leased for industry",
  conservation: "Conservation",
  cultural: "Historic",
  context_campus: "Context",
  operating_mission: "Operating mission",
};

const HANFORD_FIT_LABEL = {
  anchored: "Anchored",
  strong: "Strong",
  conditional: "Conditional",
  precluded: "Precluded",
};

// Binding-constraint chip labels for facility-fit cells (schema
// HanfordFacilityFit.constraint) — WHY a cell is what it is, at a glance.
const DOE_CONSTRAINT_LABEL = {
  mission: "mission occupies land",
  land: "land status / designation",
  licensing: "licensing path",
  power: "speed to power",
  water: "water",
  gas: "gas supply",
  workforce: "workforce",
  security: "security perimeter",
};

// Facility-fit summary vocabulary — a dedicated data-center-vs-reactor-class
// comparison, distinct from the general `opportunities` list (which has a
// single combined "advanced_nuclear" kind). Order matters: it's the column
// order in the top-of-page summary table AND the row order in each parcel's
// mini-list, smallest-footprint reactor class last.
const HANFORD_FACILITY_ORDER = ["data_center", "lwr_pwr", "smr", "microreactor"];
const HANFORD_FACILITY_SHORT_LABEL = {
  data_center: "Data center",
  lwr_pwr: "Large reactor",
  smr: "SMR",
  microreactor: "Microreactor",
};

// The seven-category infrastructure vocabulary (schema DoeInfrastructureRow).
const DOE_INFRA_LABEL = {
  power_td: "Power — transmission & distribution",
  natural_gas: "Natural gas",
  water: "Water",
  rail: "Rail",
  road: "Road",
  fiber: "Fiber",
  workforce: "Workforce",
};
const DOE_INFRA_ORDER = ["power_td", "natural_gas", "water", "rail", "road", "fiber", "workforce"];

function _doeAddParcelMarkers(site, payload) {
  if (!hanfordParcelLayer) return;
  for (const p of payload.parcels || []) {
    if (p.lat == null || p.lon == null) continue;
    // Overlay markers need the inset remap whenever a row could sit outside
    // US_BOUNDS (the microreactor/Eielson lesson) — all five DOE sites are
    // CONUS today, but the call is cheap and future rows stay reachable.
    // applyInsetRemap keys off `.state`, so pass the site's state code.
    const pos = { lat: p.lat, lon: p.lon, state: (payload.site_overview || {}).state };
    applyInsetRemap(pos);
    // Glyph directly in the icon div (no inner span) — the divIcon
    // DOM-cost rule every overlay follows.
    const icon = L.divIcon({
      className: "hanford-parcel-icon",
      html: "▣",
      iconSize: [18, 18],
      iconAnchor: [9, 9],
      popupAnchor: [0, -10],
    });
    const marker = L.marker([pos.lat, pos.lon], { icon, zIndexOffset: 420 });
    const kindLabel = HANFORD_KIND_LABEL[p.kind] || p.kind;
    marker.bindPopup(
      `<div class="ref-campus-popup">` +
      `<strong>${escapeHtml(p.name)}</strong>` +
      `<div class="ref-campus-company">${escapeHtml(site.label)} · ${escapeHtml(kindLabel)} · ${_doeAcres(p)}</div>` +
      `<div class="ref-campus-prev">${escapeHtml(p.availability)}</div>` +
      `<button type="button" class="hanford-popup-btn">Open ${escapeHtml(site.label)} dossier &rarr;</button>` +
      `</div>`,
      { maxWidth: 290 }
    );
    // Closure-bound on popupopen — never string-interpolated inline
    // handlers (code review 2026-08-23 #1).
    marker.on("popupopen", (ev) => {
      const btn = ev.popup.getElement()?.querySelector(".hanford-popup-btn");
      if (btn) btn.addEventListener("click", () => window.__openDoeParcel(site.id, p.id), { once: true });
    });
    hanfordParcelLayer.addLayer(marker);
  }
  rerenderLegend();
}

function ensureDoeSiteLoaded(siteId) {
  const site = DOE_SITES.find((s) => s.id === siteId);
  if (!site) return Promise.resolve(null);
  if (doeSitePromises[siteId]) return doeSitePromises[siteId];
  doeSiteFailed[siteId] = false;
  doeSitePromises[siteId] = fetch(site.url, { priority: "low" })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      // Only the eager Hanford artifact drives the displayed refresh date —
      // the other four load on demand, and a loader that may never run must
      // not feed recordRefreshDate (reference-campuses rule).
      if (siteId === "hanford") {
        recordRefreshDate(payload.generated_at, HANFORD_E2E_URL);
        hanfordData = payload;
        window.__hanford = payload; // e2e hook, like __sites / __coalAssets
      }
      doeSiteData[siteId] = payload;
      window.__doeSites = doeSiteData; // e2e hook for the multi-site tab
      _doeAddParcelMarkers(site, payload);
      // If the user is already sitting on the tab, upgrade the loading state.
      const view = el("view-hanford");
      if (view && view.classList.contains("active")) buildHanfordView();
    })
    .catch((err) => {
      console.error(`DOE dossier load failed (${siteId}):`, err);
      doeSiteFailed[siteId] = true;
      doeSitePromises[siteId] = null; // nulled so the next call retries
      if (siteId === "hanford") hanfordLoadFailed = true;
      const view = el("view-hanford");
      if (view && view.classList.contains("active")) buildHanfordView();
    });
  return doeSitePromises[siteId];
}

function ensureHanfordLoaded() {
  // Boot fan-out entry point (eager — the artifact drives the refresh date).
  hanfordLoadingPromise = ensureDoeSiteLoaded("hanford");
  return hanfordLoadingPromise;
}

let hanfordViewMounted = false;
function mountHanfordView() {
  if (hanfordViewMounted) return;
  const tpl = el("hanford-template");
  const view = el("view-hanford");
  if (!tpl || !view || !tpl.content) return;
  hanfordViewMounted = true;
  view.appendChild(tpl.content.cloneNode(true));
}

// Jump from a map popup into the dossier with the unit drawer open.
window.__openDoeParcel = function (siteId, parcelId) {
  if (typeof window.__setView === "function") window.__setView("hanford");
  if (DOE_SITES.some((s) => s.id === siteId)) doeActiveSite = siteId;
  doeSelectedParcel[siteId] = parcelId;
  // A marker for a sibling site stays in the shared map layer after that
  // site's dossier loads, so this can change the active site without going
  // through the pill handler — sync the URL here too, or a copied/refreshed
  // link reopens the wrong (or no) dossier (Codex PR #24 finding).
  syncUrl();
  buildHanfordView();
  ensureDoeSiteLoaded(siteId);
  const drawer = document.getElementById("doe-drawer");
  if (drawer && !drawer.hidden) drawer.scrollIntoView({ behavior: "smooth", block: "start" });
};

// Back-compat alias (older popups/tests) — Hanford-scoped.
window.__openHanfordParcel = function (parcelId) {
  window.__openDoeParcel("hanford", parcelId);
};

// Compressed per-source headline for one parcel's screening record. Reuses
// the Janus status helper so "Unavailable is never a no-hit" renders the
// same way on both surfaces. Rows are emitted only for sources the site's
// dossier actually declares (payload.sources) — the four non-Pacific DOE
// sites run an 8-source matrix (no NOAA West Coast CH / salmon EFH), and a
// hardcoded ten-row table would render misleading "Unavailable" rows for
// tools that were never applicable there.
function _doeScreenRows(payload, s) {
  const ipac = s.ipac || {};
  const counts = ipac.counts || {};
  const noaa = s.noaa || {};
  const efh = s.efh_salmon || {};
  const nrhp = s.nrhp || {};
  const tribal = s.tribal || {};
  const padus = s.padus || {};
  const usace = s.usace || {};
  const flood = s.fema_nfhl || {};
  const gbif = s.gbif || {};
  const assist = s.nepa_assist || {};
  const districts = (usace.districts || []).map((d) => d.district_abbreviation || d.district_name).filter(Boolean);
  const noaaNames = (noaa.habitats || []).slice(0, 2).map((h) => h.listed_entity || h.common_name).filter(Boolean);
  const floodNote = escapeHtml(payload.flood_unmapped_note || "unmapped in NFHL is not flood-free");
  const rows = [
    ["ipac", "USFWS IPaC", _janusStatus(ipac,
      `<strong>${counts.listed_species || 0}</strong> listed species · ${counts.critical_habitat || 0} critical-habitat records`), ipac],
    ["noaa", "NOAA critical habitat", _janusStatus(noaa,
      `<strong>${noaa.count || 0}</strong> NMFS designations` +
      (noaaNames.length ? `<div class="micro-sub">${escapeHtml(noaaNames.join(" · "))}</div>` : "")), noaa],
    ["efh_salmon", "Salmon EFH", _janusStatus(efh,
      `<strong>${efh.count || 0}</strong> HUC-8 watersheds with mapped EFH`), efh],
    ["tribal", "Tribal geography", _janusStatus(tribal,
      `<strong>${tribal.count || 0}</strong> mapped geographies` +
      '<div class="micro-sub">consultation context, not a conclusion</div>'), tribal],
    ["nrhp", "Historic (NRHP)", _janusStatus(nrhp,
      `<strong>${nrhp.count || 0}</strong> listed properties · ${nrhp.national_historic_landmarks || 0} NHL`), nrhp],
    ["padus", "Protected land", _janusStatus(padus,
      `<strong>${padus.count || 0}</strong> PAD-US records` +
      '<div class="micro-sub">0.1-mi point context</div>'), padus],
    ["usace", "USACE district", _janusStatus(usace,
      districts.length ? escapeHtml(districts.join(" · ")) : '<span class="muted-cell">No district returned</span>'), usace],
    ["fema_nfhl", "Flood (NFHL)", _janusStatus(flood,
      flood.count
        ? `<strong>${flood.count}</strong> mapped zones in 2 mi · ${flood.sfha_count || 0} SFHA`
        : `No mapped zones in 2 mi<div class="micro-sub">${floodNote}</div>`), flood],
    ["gbif", "Biodiversity (GBIF)", _janusStatus(gbif,
      `<strong>${(gbif.occurrence_count || 0).toLocaleString()}</strong> threatened-species records · ${gbif.species_count || 0} species since 2000`), gbif],
    ["nepa_assist", "EPA NEPAssist", _janusStatus(assist,
      assist.report_url
        ? `<a href="${escapeAttr(assist.report_url)}" target="_blank" rel="noopener">Screening report ↗</a>`
        : "Screen returned"), assist],
  ];
  const declared = payload.sources || {};
  return rows
    .filter(([key]) => declared[key])
    .map(([key, label, html, section]) => [label, html, section, (declared[key] || {}).url]);
}

// One parcel's corpus-join readout (the dashboard's own enrichments).
function _hanfordCorpusHtml(p) {
  const c = p.corpus_record;
  if (!c) return "";
  const rows = [
    ["Transmission", c.transmission_mi != null ? `${fmt.miles(c.transmission_mi)}${c.transmission_kv ? ` · ${c.transmission_kv} kV` : ""}` : null],
    ["Substation", c.substation_mi != null ? `${fmt.miles(c.substation_mi)}${c.substation_kv ? ` · ${c.substation_kv} kV` : ""}` : null],
    ["Rail", c.rail_mi != null ? fmt.miles(c.rail_mi) : null],
    ["Highway", c.highway_mi != null ? fmt.miles(c.highway_mi) : null],
    ["Gas pipeline", c.gas_pipeline_mi != null ? fmt.miles(c.gas_pipeline_mi) : null],
    ["Nearest plant", c.power_plant_mi != null ? `${fmt.miles(c.power_plant_mi)} · ${Math.round(c.power_plant_mw || 0).toLocaleString()} MW ${escapeHtml(c.power_plant_fuel || "")}` : null],
    ["NPL status", c.npl_status ? escapeHtml(c.npl_status) : null],
  ].filter(([, v]) => v != null);
  if (!rows.length) return "";
  return (
    `<div class="hanford-corpus">` +
    `<h5>From this dashboard's enrichments <span class="micro-note">(infra-proximity joins on the NPL record)</span></h5>` +
    `<dl class="hanford-kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>` +
    (p.corpus_site_id
      ? `<a href="?site=${encodeURIComponent(p.corpus_site_id)}" class="hanford-site-link" data-site="${escapeAttr(p.corpus_site_id)}">Open the tracked site record →</a>`
      : "") +
    `</div>`
  );
}

// Acreage renderer that never invents a number — None/undefined means the
// source publishes no figure (e.g. the Centrus ACP footprint).
function _doeAcres(p, suffix) {
  if (p.approx_acres == null) return "size not published";
  return `~${Math.round(p.approx_acres).toLocaleString()} ${suffix || "ac"}`;
}

const HANFORD_FIT_RANK = { anchored: 4, strong: 3, conditional: 2, precluded: 1 };

// Best-fit ranking for one parcel's facility_fit set. 2026-08-24 fix: a
// parcel whose every type is "precluded" must say "None", never list all
// four types as ties (the old top-rank tie-listing read an all-precluded
// row as fit-for-everything — the exact opposite of the data). Only
// conditional-or-better ranks count as a fit.
function doeBestFit(byType) {
  let bestRank = 0;
  for (const t of HANFORD_FACILITY_ORDER) {
    const r = HANFORD_FIT_RANK[byType[t]?.fit] || 0;
    if (r > bestRank) bestRank = r;
  }
  if (bestRank === 0) return { label: "Not assessed", none: true };
  if (bestRank <= HANFORD_FIT_RANK.precluded) return { label: "None", none: true };
  const types = HANFORD_FACILITY_ORDER.filter((t) => HANFORD_FIT_RANK[byType[t]?.fit] === bestRank);
  return { label: types.map((t) => HANFORD_FACILITY_SHORT_LABEL[t]).join(" / "), none: false };
}

// One facility-fit cell's expanded reasoning block: fit chip + binding
// constraint + full rationale + its citations (per-cell sources when the
// rationale asserts an external fact, plus the parcel's own primary source).
function _doeFitReasonHtml(p, t) {
  const ff = (p.facility_fit || []).find((row) => row.type === t);
  if (!ff) return "";
  const cites = [
    ...(ff.sources || []).map((sr) =>
      `<a href="${escapeAttr(sr.url)}" target="_blank" rel="noopener">${escapeHtml(sr.label)} ↗</a>`),
    `<a href="${escapeAttr(p.source_url)}" target="_blank" rel="noopener">Unit primary source ↗</a>`,
  ].join(" ");
  const why = ff.constraint
    ? `<span class="hp-constraint" title="Binding factor">${escapeHtml(DOE_CONSTRAINT_LABEL[ff.constraint] || ff.constraint)}</span>`
    : "";
  return (
    `<div class="doe-fit-reason" data-type="${escapeAttr(t)}">` +
    `<div class="doe-fit-reason-head"><strong>${escapeHtml(HANFORD_FACILITY_SHORT_LABEL[t] || t)}</strong>` +
    `<span class="hp-fit hp-fit-${escapeAttr(ff.fit)}">${escapeHtml(HANFORD_FIT_LABEL[ff.fit] || ff.fit)}</span>${why}</div>` +
    `<p>${escapeHtml(ff.rationale)}</p>` +
    `<div class="doe-fit-cites">${cites} <span class="micro-note">Verified ${escapeHtml(p.verified_at)}</span></div>` +
    `</div>`
  );
}

// The answer surface: parcel × facility-type matrix, open by default at the
// top of the tab. The per-cell fit VALUES are curated (facility_fit on each
// parcel); only the best-fit ranking is computed client-side. Every cell is
// a real <button> — clicking it expands a full-width reasoning row with the
// rationale, binding constraint, and citations (never tooltip-only: the old
// title-attribute pattern was invisible on touch and to assistive tech).
function _doeFitMatrixHtml(payload) {
  const parcels = payload.parcels || [];
  const facilityTypes = payload.facility_types || {};
  if (!parcels.length) return "";
  const considerationRows = HANFORD_FACILITY_ORDER.map((t) => {
    const meta = facilityTypes[t] || {};
    const src = meta.source_url
      ? ` <a href="${escapeAttr(meta.source_url)}" target="_blank" rel="noopener" class="micro-note">Source ↗</a>`
      : "";
    return `<tr><th scope="row">${escapeHtml(meta.label || HANFORD_FACILITY_SHORT_LABEL[t] || t)}</th>` +
      `<td>${escapeHtml(meta.considerations || "")}${src}</td></tr>`;
  }).join("");
  const bodyRows = parcels.map((p) => {
    const byType = {};
    for (const ff of p.facility_fit || []) byType[ff.type] = ff;
    const best = doeBestFit(byType);
    const cells = HANFORD_FACILITY_ORDER.map((t) => {
      const ff = byType[t];
      if (!ff) return `<td class="hanford-fit-cell">—</td>`;
      const why = ff.constraint ? `<span class="hp-cell-why">${escapeHtml(ff.constraint)}</span>` : "";
      return `<td class="hanford-fit-cell">` +
        `<button type="button" class="doe-fit-cell-btn" data-parcel="${escapeAttr(p.id)}" data-type="${escapeAttr(t)}"` +
        ` aria-expanded="false" aria-label="${escapeAttr(`${p.name} — ${HANFORD_FACILITY_SHORT_LABEL[t]}: ${HANFORD_FIT_LABEL[ff.fit]}. Show reasoning.`)}">` +
        `<span class="hp-fit hp-fit-${escapeAttr(ff.fit)}">${escapeHtml(HANFORD_FIT_LABEL[ff.fit] || ff.fit)}</span>${why}</button></td>`;
    }).join("");
    const reasonBlocks = HANFORD_FACILITY_ORDER.map((t) => _doeFitReasonHtml(p, t)).join("");
    return `<tr class="doe-fit-row" data-parcel="${escapeAttr(p.id)}">` +
      `<th scope="row"><button type="button" class="doe-open-parcel text-btn" data-parcel="${escapeAttr(p.id)}">${escapeHtml(p.name)}</button>` +
      ` <span class="micro-note">${_doeAcres(p)}</span></th>` +
      cells +
      `<td class="hanford-best-fit${best.none ? " doe-best-none" : ""}">${escapeHtml(best.label)}</td></tr>` +
      `<tr class="doe-fit-detail" data-parcel="${escapeAttr(p.id)}" hidden><td colspan="${HANFORD_FACILITY_ORDER.length + 2}">` +
      `<div class="doe-fit-reasons">${reasonBlocks}</div></td></tr>`;
  }).join("");
  return (
    `<section class="doe-fit-section" id="doe-fit">` +
    `<h3 class="hanford-section-title">What fits where</h3>` +
    `<p class="hanford-summary">Every land unit is rated against the same four facility types. These are source-backed editorial judgements — <strong>click any cell</strong> for the reasoning, its binding constraint, and sources. "Best fit" is the highest rating in the row.</p>` +
    `<div class="micro-table-wrap"><table class="micro-table hanford-pathway-table hanford-facility-matrix">` +
    `<thead><tr><th scope="col">Land unit</th>${HANFORD_FACILITY_ORDER.map((t) => `<th scope="col">${escapeHtml(HANFORD_FACILITY_SHORT_LABEL[t])}</th>`).join("")}<th scope="col">Best fit</th></tr></thead>` +
    `<tbody>${bodyRows}</tbody></table></div>` +
    `<details class="hanford-pathways hanford-facility-summary"><summary><strong>What each facility type needs</strong> <span class="micro-note">(the assessment criteria, with sources)</span></summary>` +
    `<div class="micro-table-wrap"><table class="micro-table hanford-pathway-table hanford-facility-considerations">` +
    `<thead><tr><th scope="col">Facility type</th><th scope="col">What it needs</th></tr></thead>` +
    `<tbody>${considerationRows}</tbody></table></div>` +
    `</details>` +
    `</section>`
  );
}

// Compact land-unit card for the explorer grid. Clicking opens the drawer —
// the tab renders ONE unit's full dossier at a time instead of nine stacked
// open accordions (the 2026-08-24 too-much-scrolling finding).
function _doeParcelCardHtml(p, isOpen) {
  const kindLabel = HANFORD_KIND_LABEL[p.kind] || p.kind;
  const availability = String(p.availability || "");
  const firstSentence = availability.split(/(?<=\.)\s/)[0] || availability;
  const byType = {};
  for (const ff of p.facility_fit || []) byType[ff.type] = ff;
  const best = doeBestFit(byType);
  return (
    `<button type="button" class="doe-parcel-card${isOpen ? " doe-card-open" : ""}" data-parcel="${escapeAttr(p.id)}" aria-expanded="${isOpen ? "true" : "false"}">` +
    `<span class="doe-card-head"><strong>${escapeHtml(p.name)}</strong>` +
    `<span class="hanford-kind hanford-kind-${escapeAttr(p.kind)}">${escapeHtml(kindLabel)}</span></span>` +
    `<span class="doe-card-meta">${_doeAcres(p)} · Best fit: <strong>${escapeHtml(best.label)}</strong></span>` +
    `<span class="doe-card-avail">${escapeHtml(firstSentence)}</span>` +
    `<span class="doe-card-cta">${isOpen ? "Open below ↓" : "Open unit dossier →"}</span>` +
    `</button>`
  );
}

// Prior federal decision documents (CERCLA RODs, Five-Year Reviews …) for
// units that ARE NPL sub-areas — reuses the epa-superfund-docs join already
// loaded for the corpus (the 2026-08-24 backlog quick win). Client-side
// only: no new fetch, the documents live on the corpus record in sitesById.
function _doeDecisionDocsHtml(p) {
  if (!p.corpus_site_id || typeof sitesById === "undefined") return "";
  const rec = sitesById.get(p.corpus_site_id);
  const docs = (rec && rec.documents) || [];
  if (!docs.length) return "";
  const items = docs.slice(0, 5).map((d) =>
    `<li><a href="${escapeAttr(d.url)}" target="_blank" rel="noopener">${escapeHtml(d.title)}</a>` +
    ` <span class="micro-note">${escapeHtml([d.date ? d.date.slice(0, 4) : null, d.category].filter(Boolean).join(" · "))}</span></li>`
  ).join("");
  return (
    `<h5>Prior federal decision documents <span class="micro-note">(EPA Superfund record for ${escapeHtml(p.corpus_site_id)} — CERCLA response-action history)</span></h5>` +
    `<ul class="hanford-nearby doe-docs">${items}</ul>` +
    (docs.length > 5 ? `<p class="micro-note">${docs.length - 5} more on the tracked site record below.</p>` : "")
  );
}

// The full single-unit dossier, rendered into #doe-drawer for the selected
// unit only. Every prose block carries its citation adjacent to the claim.
function _doeDrawerHtml(payload, p) {
  const kindLabel = HANFORD_KIND_LABEL[p.kind] || p.kind;
  const screenRows = _doeScreenRows(payload, p.screening || {}).map(([label, html, section, srcUrl]) =>
    `<tr><th scope="row">${srcUrl ? `<a href="${escapeAttr(srcUrl)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>` : escapeHtml(label)}</th><td>${html}</td>` +
    `<td class="hanford-retrieved">${section && section.retrieved_at ? escapeHtml(section.retrieved_at.slice(0, 10)) : "—"}</td></tr>`
  ).join("");
  const hasScreen = Object.keys(p.screening || {}).length > 0;
  const opps = (p.opportunities || []).map((o) =>
    `<li class="hp-opp"><span class="hp-fit hp-fit-${escapeAttr(o.fit)}">${escapeHtml(HANFORD_FIT_LABEL[o.fit] || o.fit)}</span>` +
    `<div><strong>${escapeHtml((payload.opportunity_kinds || {})[o.kind] || o.kind)}</strong>` +
    `<p>${escapeHtml(o.rationale)}</p></div></li>`
  ).join("");
  const fitReasons = HANFORD_FACILITY_ORDER.map((t) => _doeFitReasonHtml(p, t)).join("");
  const nearby = (p.nearby_tracked || []).map((n) =>
    `<li><a href="?site=${encodeURIComponent(n.id)}" class="hanford-site-link" data-site="${escapeAttr(n.id)}">${escapeHtml(prettyName(n.name) || n.id)}</a>` +
    ` <span class="micro-note">${escapeHtml((n.program || "").toUpperCase())} · ${fmt.miles(n.distance_mi)}</span></li>`
  ).join("");
  const extraSources = (p.extra_sources || []).map((sr) =>
    `<a href="${escapeAttr(sr.url)}" target="_blank" rel="noopener">${escapeHtml(sr.label)} ↗</a>`
  ).join("");
  const featureCount = p.map_summary?.feature_count;
  // A partial package (some layers timed out) must not read as a pure
  // success — an omitted layer is not a no-hit (Codex PR #22 round 2).
  const failedLayers = p.map_summary?.layers_failed || 0;
  const totalLayers = failedLayers + (p.map_summary?.layers_ok || 0) + (p.map_summary?.layers_partial || 0);
  const mapWarn = failedLayers > 0
    ? `<span class="hanford-map-warn">${failedLayers} of ${totalLayers} map layers unavailable — not a no-hit</span>`
    : "";
  const mapBtn = p.geojson_url
    ? `<button type="button" class="ap1000-export hanford-map-btn" data-hanford-map="${escapeAttr(p.id)}"` +
      `${failedLayers > 0 ? ` title="${failedLayers} of ${totalLayers} layers failed to collect — their absence from the map is coverage, not clearance"` : ""}>` +
      `Show ${featureCount != null ? featureCount.toLocaleString() + " " : ""}features on map</button>${mapWarn}`
    : `<button type="button" class="ap1000-export" disabled title="Map package not generated for this parcel yet">Map package pending</button>`;
  const cite = `<a href="${escapeAttr(p.source_url)}" target="_blank" rel="noopener" class="doe-inline-cite" title="Primary source for this unit's status and availability">[source ↗]</a>`;
  return (
    `<div class="coal-drawer-head"><h3 id="hp-${escapeAttr(p.id)}">${escapeHtml(p.name)} ` +
    `<span class="hanford-kind hanford-kind-${escapeAttr(p.kind)}">${escapeHtml(kindLabel)}</span></h3>` +
    `<button type="button" class="text-btn" id="doe-drawer-close" aria-label="Close unit dossier">✕ Close</button></div>` +
    `<p class="hanford-status"><strong>Status.</strong> ${escapeHtml(p.status)} ${cite}</p>` +
    `<p class="hanford-status"><strong>Availability.</strong> ${escapeHtml(p.availability)} ${cite}</p>` +
    `<dl class="hanford-kv hanford-kv-top">` +
    `<dt>Land-use plan</dt><dd>${p.clup_designation ? `<strong>${escapeHtml(p.clup_designation)}</strong> — ` : ""}${escapeHtml(p.clup_note)}</dd>` +
    `<dt>Size</dt><dd>${_doeAcres(p, "acres")}</dd>` +
    `<dt>Coordinates</dt><dd>${p.lat.toFixed(4)}, ${p.lon.toFixed(4)} <span class="micro-note">${escapeHtml(p.coord_note)}</span></dd>` +
    `</dl>` +
    `<h5>Facility fit — the reasoning</h5>` +
    `<div class="doe-fit-reasons">${fitReasons || '<p class="micro-note">None assessed.</p>'}</div>` +
    `<h5>Opportunities</h5><ul class="hp-opps">${opps || '<li class="micro-note">None assessed.</li>'}</ul>` +
    `<h5>Environmental screen <span class="micro-note">(${escapeHtml(String(payload.screening_buffer_miles || 5))}-mile context; unavailable ≠ no-hit)</span></h5>` +
    (hasScreen
      ? `<div class="micro-table-wrap"><table class="micro-table hanford-screen-table">` +
        `<thead><tr><th scope="col">Source</th><th scope="col">Finding</th><th scope="col">Retrieved</th></tr></thead>` +
        `<tbody>${screenRows}</tbody></table></div>`
      : `<p class="micro-note">Environmental screen not yet run for this unit — evidence pending, which is not a no-hit.</p>`) +
    _hanfordCorpusHtml(p) +
    _doeDecisionDocsHtml(p) +
    (nearby ? `<h5>Nearby tracked records</h5><ul class="hanford-nearby">${nearby}</ul>` : "") +
    `<div class="janus-card-links hanford-cites">` +
    `<a href="${escapeAttr(p.source_url)}" target="_blank" rel="noopener">Primary source ↗</a>` +
    extraSources +
    `<span>Verified ${escapeHtml(p.verified_at)}</span>` +
    `${mapBtn}` +
    `</div>`
  );
}

function _doeSitePillsHtml() {
  return DOE_SITES.map((s) => {
    const active = s.id === doeActiveSite;
    return `<button type="button" class="doe-pill${active ? " doe-pill-active" : ""}" data-doe-site="${escapeAttr(s.id)}"` +
      ` role="tab" aria-selected="${active ? "true" : "false"}">` +
      `${escapeHtml(s.label)} <span class="doe-pill-state">${escapeHtml(s.state)}</span></button>`;
  }).join("");
}

// At-a-glance header: the answer a developer or practitioner came for,
// before any scrolling — who runs the site, how big, how many units are
// live vs. gated vs. off the table — plus jump links and the AI-narrative
// disclosure (every AI-drafted surface says so and cites its inputs).
// All interpolations pass through escapeHtml/escapeAttr (house pattern).
function _doeGlanceHtml(payload) {
  const ov = payload.site_overview || {};
  const parcels = payload.parcels || [];
  let viable = 0, precluded = 0;
  for (const p of parcels) {
    const byType = {};
    for (const ff of p.facility_fit || []) byType[ff.type] = ff;
    if (doeBestFit(byType).none) precluded += 1; else viable += 1;
  }
  const landlord = (ov.managers || [])[0];
  const lup = ov.land_use_plan || {};
  const jump = [
    ["#doe-fit", "What fits where"],
    ["#doe-units", "Land units"],
    ["#doe-infra", "Infrastructure"],
    ["#doe-permitting", "Permitting"],
    ["#doe-sources", "Sources & method"],
  ].map(([href, label]) => `<a href="${href}" class="doe-jump">${escapeHtml(label)}</a>`).join("");
  return (
    `<section class="doe-glance">` +
    `<div class="doe-glance-head"><h3 class="hanford-section-title">${escapeHtml(ov.name || payload.site_label || "")}` +
    `<span class="micro-note"> ${escapeHtml(ov.county || "")}${ov.county ? " County, " : ""}${escapeHtml(ov.state || "")}</span></h3></div>` +
    `<div class="doe-stats">` +
    `<span class="doe-stat"><strong>${ov.size_sq_mi ? escapeHtml(String(ov.size_sq_mi)) : "—"}</strong> sq mi</span>` +
    `<span class="doe-stat"><strong>${parcels.length}</strong> land units</span>` +
    `<span class="doe-stat doe-stat-viable"><strong>${viable}</strong> with a viable fit</span>` +
    `<span class="doe-stat doe-stat-off"><strong>${precluded}</strong> precluded</span>` +
    (landlord ? `<span class="doe-stat">Landlord: <a href="${escapeAttr(landlord.url)}" target="_blank" rel="noopener">${escapeHtml((landlord.who || "").split("—")[0].trim())}</a></span>` : "") +
    `</div>` +
    `<p class="hanford-summary">${escapeHtml(ov.summary || "")}` +
    (lup.url ? ` <a href="${escapeAttr(lup.url)}" target="_blank" rel="noopener" class="doe-inline-cite" title="${escapeAttr(lup.label || "Land-use plan")}">[land-use plan ↗]</a>` : "") +
    `</p>` +
    (payload.narrative_note ? `<p class="doe-ai-note">⚠ ${escapeHtml(payload.narrative_note)}</p>` : "") +
    `<nav class="doe-jumps" aria-label="Dossier sections">${jump}</nav>` +
    `</section>`
  );
}

function _doeInfraHtml(payload) {
  const rows = payload.infrastructure || [];
  if (!rows.length) return "";
  const byCat = {};
  for (const r of rows) (byCat[r.category] = byCat[r.category] || []).push(r);
  const items = DOE_INFRA_ORDER.filter((c) => byCat[c]).map((c) => {
    const entries = byCat[c].map((r) => {
      const extra = (r.extra_sources || []).map((sr) =>
        ` · <a href="${escapeAttr(sr.url)}" target="_blank" rel="noopener">${escapeHtml(sr.label)} ↗</a>`).join("");
      return `<p>${escapeHtml(r.summary)} <a href="${escapeAttr(r.source_url)}" target="_blank" rel="noopener" class="doe-inline-cite">[${escapeHtml(r.source_label)} ↗]</a>${extra}</p>`;
    }).join("");
    return `<div class="doe-infra-row"><h4>${escapeHtml(DOE_INFRA_LABEL[c] || c)}</h4>${entries}</div>`;
  }).join("");
  return (
    `<section class="doe-infra" id="doe-infra">` +
    `<h3 class="hanford-section-title">Site infrastructure</h3>` +
    `<p class="hanford-summary micro-note">What the site as a whole has to work with. Distances from any one land unit are in that unit's dossier.</p>` +
    `<div class="doe-infra-grid">${items}</div>` +
    `</section>`
  );
}

function buildHanfordView() {
  const host = el("hanford-content");
  if (!host) return;
  // One-shot ?doe= deep-link read (parsed here, not at top level — the
  // candidatesState ?lens= TDZ lesson).
  if (!doeUrlSiteApplied) {
    doeUrlSiteApplied = true;
    const want = new URLSearchParams(location.search).get("doe");
    if (want && DOE_SITES.some((s) => s.id === want)) doeActiveSite = want;
  }
  const site = DOE_SITES.find((s) => s.id === doeActiveSite) || DOE_SITES[0];
  const payload = doeSiteData[site.id];
  const pills = `<nav class="doe-pills" role="tablist" aria-label="DOE site selector">${_doeSitePillsHtml()}</nav>`;

  if (!payload && doeSiteFailed[site.id]) {
    host.innerHTML = pills +
      `<p class="muted">${escapeHtml(site.label)} dossier could not be loaded. ` +
      '<button type="button" id="hanford-retry" class="text-btn">Retry</button></p>';
    _wireDoePills(host);
    const retry = el("hanford-retry");
    if (retry) retry.addEventListener("click", () => {
      doeSiteFailed[site.id] = false;
      if (site.id === "hanford") hanfordLoadFailed = false;
      buildHanfordView();
      ensureDoeSiteLoaded(site.id);
    });
    return;
  }
  if (!payload) {
    ensureDoeSiteLoaded(site.id);
    host.innerHTML = pills + `<p class="muted">Loading ${escapeHtml(site.label)} dossier…</p>`;
    _wireDoePills(host);
    return;
  }

  const ov = payload.site_overview || {};
  const managers = (ov.managers || []).map((m) =>
    `<div class="hanford-mgr"><span class="hanford-mgr-role">${escapeHtml(m.role)}</span>` +
    `<p>${escapeHtml(m.who)}</p>` +
    `<a href="${escapeAttr(m.url)}" target="_blank" rel="noopener">Source ↗</a></div>`
  ).join("");
  const pathways = (payload.permitting_pathways || []).map((pw) =>
    `<tr><th scope="row">${escapeHtml(pw.regime)}</th>` +
    `<td>${escapeHtml(pw.applies)}</td>` +
    `<td>${escapeHtml(pw.authority)} <a href="${escapeAttr(pw.url)}" target="_blank" rel="noopener">↗</a></td></tr>`
  ).join("");
  const limits = (payload.limitations || []).map((l) => escapeHtml(l)).join(" · ");
  const selectedId = doeSelectedParcel[site.id];
  const selected = (payload.parcels || []).find((p) => p.id === selectedId) || null;
  const cards = (payload.parcels || []).map((p) => _doeParcelCardHtml(p, selected && p.id === selected.id)).join("");
  const lup = ov.land_use_plan || {};
  const sourceRows = Object.values(payload.sources || {}).map((s) =>
    `<tr><th scope="row">${s.url ? `<a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.label)} ↗</a>` : escapeHtml(s.label)}</th>` +
    `<td>${escapeHtml(s.covers || "")}</td></tr>`
  ).join("");

  host.innerHTML =
    pills +
    _doeGlanceHtml(payload) +
    _doeFitMatrixHtml(payload) +
    `<section class="hanford-parcels" id="doe-units"><h3 class="hanford-section-title">The land, unit by unit</h3>` +
    `<p class="hanford-summary micro-note">Click a unit for its full dossier — status, environmental screen, corpus joins, and citations. One unit opens at a time.</p>` +
    `<div class="doe-parcel-grid">${cards}</div>` +
    `<div class="coal-drawer doe-drawer" id="doe-drawer"${selected ? "" : " hidden"}>${selected ? _doeDrawerHtml(payload, selected) : ""}</div>` +
    `</section>` +
    _doeInfraHtml(payload) +
    `<details class="hanford-pathways" id="doe-permitting"><summary><strong>Permitting &amp; licensing pathways</strong> <span class="micro-note">(what applies and who decides)</span></summary>` +
    `<div class="micro-table-wrap"><table class="micro-table hanford-pathway-table">` +
    `<thead><tr><th scope="col">Regime</th><th scope="col">When it applies at ${escapeHtml(site.label)}</th><th scope="col">Authority</th></tr></thead>` +
    `<tbody>${pathways}</tbody></table></div></details>` +
    `<details class="hanford-pathways"><summary><strong>Who manages this land</strong> <span class="micro-note">(landlord, regulators, and every overlapping jurisdiction)</span></summary>` +
    `<div class="hanford-mgrs">${managers}</div>` +
    (lup.label
      ? `<p class="hanford-lup micro-note">${escapeHtml(lup.note || "")} <a href="${escapeAttr(lup.url)}" target="_blank" rel="noopener">${escapeHtml(lup.label)} ↗</a></p>`
      : "") +
    `</details>` +
    `<details class="hanford-pathways hanford-sources" id="doe-sources"><summary><strong>Sources &amp; methodology</strong> <span class="micro-note">(where every finding on this page comes from, and how it was pulled)</span></summary>` +
    `<div class="janus-limit"><strong>Screening, not siting:</strong> ${limits}</div>` +
    `<p class="hanford-summary">The environmental screen comes from <a href="https://github.com/pnnl/nepa-mcp" target="_blank" rel="noopener">PNNL's nepa-mcp</a>, an open-source toolkit (BSD-3) that wraps live federal GIS and regulatory APIs behind one interface. For each land unit, this dossier calls one tool per source listed below within ${escapeHtml(String(payload.screening_buffer_miles || 5))} miles of a representative point, caches the response, and normalizes it into the Finding column. A source that times out or errors is marked <strong>unavailable</strong>, which is different from a result of zero. The Map Composer layers behind "Show features on map" come from the same calls, returned as GeoJSON instead of counts. Site history, ownership, and land-use facts are drafted from the public sources linked in each row.</p>` +
    `<div class="micro-table-wrap"><table class="micro-table hanford-pathway-table">` +
    `<thead><tr><th scope="col">Source (nepa-mcp tool)</th><th scope="col">What it actually covers</th></tr></thead>` +
    `<tbody>${sourceRows}</tbody></table></div></details>` +
    `<p class="micro-note hanford-method">${escapeHtml(payload.method || "")} nepa-mcp ${escapeHtml(payload.nepa_mcp_version || "")} · generated ${escapeHtml((payload.generated_at || "").slice(0, 10))}</p>`;

  _wireDoePills(host);
  // Delegated bindings — no string-interpolated inline handlers.
  host.querySelectorAll("a.hanford-site-link").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      selectSite(a.dataset.site);
    });
  });
  host.querySelectorAll(".hanford-map-btn").forEach((btn) => {
    btn.addEventListener("click", () => showHanfordScreeningMap(btn.dataset.hanfordMap));
  });
  // Fit-matrix cell buttons toggle the full-width reasoning row.
  host.querySelectorAll(".doe-fit-cell-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.dataset.parcel;
      const detail = host.querySelector(`tr.doe-fit-detail[data-parcel="${CSS.escape(pid)}"]`);
      if (!detail) return;
      const opening = detail.hidden;
      detail.hidden = !opening;
      host.querySelectorAll(`.doe-fit-cell-btn[data-parcel="${CSS.escape(pid)}"]`)
        .forEach((b) => b.setAttribute("aria-expanded", opening ? "true" : "false"));
      if (opening) {
        detail.querySelectorAll(".doe-fit-reason").forEach((r) =>
          r.classList.toggle("doe-reason-hot", r.dataset.type === btn.dataset.type));
      }
    });
  });
  // Parcel-name buttons in the matrix + unit cards open the drawer.
  const openDrawer = (pid) => {
    doeSelectedParcel[site.id] = pid;
    buildHanfordView();
    const drawer = el("doe-drawer");
    if (drawer) drawer.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  host.querySelectorAll(".doe-open-parcel, .doe-parcel-card").forEach((btn) => {
    btn.addEventListener("click", () => openDrawer(btn.dataset.parcel));
  });
  const closeBtn = el("doe-drawer-close");
  if (closeBtn) closeBtn.addEventListener("click", () => {
    delete doeSelectedParcel[site.id];
    buildHanfordView();
  });
}

function _wireDoePills(host) {
  host.querySelectorAll(".doe-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.doeSite;
      if (!id || id === doeActiveSite) return;
      doeActiveSite = id;
      syncUrl();
      buildHanfordView();
      ensureDoeSiteLoaded(id);
    });
  });
}

// Load one parcel's Map Composer GeoJSON package onto the main map. Mirrors
// showJanusMap; WA is CONUS so the inset remap is a structural no-op but is
// kept for symmetry (every overlay repeats the AK-rows lesson eventually).
function showHanfordScreeningMap(parcelId) {
  const sitePayload = doeSiteData[doeActiveSite] || hanfordData;
  const parcel = (sitePayload?.parcels || []).find((row) => row.id === parcelId);
  if (!parcel?.geojson_url) return;
  const stateCode = (sitePayload?.site_overview || {}).state || "WA";
  const button = document.querySelector(`[data-hanford-map="${CSS.escape(parcelId)}"]`);
  if (button) { button.disabled = true; button.textContent = "Loading map…"; }
  fetch(parcel.geojson_url)
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((payload) => {
      if (hanfordNepaLayer) map.removeLayer(hanfordNepaLayer);
      if (janusNepaLayer) { map.removeLayer(janusNepaLayer); janusNepaLayer = null; }
      const displayPayload = _remapJanusGeoJson(payload, stateCode);
      hanfordNepaLayer = L.geoJSON(displayPayload, {
        style: (feature) => ({
          color: _janusLayerColor(feature.properties?.layer || feature.properties?.type || "context"),
          weight: feature.properties?.type === "Region of Interest" ? 2 : 1,
          opacity: 0.8,
          fillOpacity: feature.properties?.type === "Region of Interest" ? 0.03 : 0.12,
        }),
        pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
          radius: feature.properties?.type === "Project Location" ? 6 : 3,
          color: _janusLayerColor(feature.properties?.layer || "context"),
          fillOpacity: 0.75,
        }),
        onEachFeature: (feature, layer) => {
          const props = feature.properties || {};
          const label = props.name || props.common_name || props.type || props.layer || "Mapped feature";
          layer.bindPopup(`<strong>${escapeHtml(label)}</strong><br>` +
            `<span class="micro-note">${escapeHtml(props.layer || "screening area")}</span>`);
        },
      }).addTo(map);
      el("tab-map")?.click();
      const bounds = _screeningFitBounds(displayPayload, hanfordNepaLayer);
      if (bounds) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 11 });
      const failed = parcel.map_summary?.layers_failed || 0;
      showToast(
        `${parcel.name}: NEPA screening layers shown. Not a project footprint.` +
        (failed > 0 ? ` ${failed} layer${failed === 1 ? "" : "s"} unavailable — not a no-hit.` : "")
      );
    })
    .catch((err) => {
      console.error("Hanford GeoJSON load failed:", err);
      showToast(`${parcel.name}: map package unavailable.`);
    })
    .finally(() => {
      if (button) { button.disabled = false; button.textContent = "Show features on map"; }
    });
}

function _microSectorHtml() {
  return (microFleet.sectors || []).map((sec) => {
    const full = sec.loads.filter((l) => l.fit === "full").length;
    const items = sec.loads.map(
      (l) =>
        `<li class="fit-${escapeAttr(l.fit)}"><span class="micro-load">${escapeHtml(l.label)}</span>` +
        `<span class="micro-band-mw">${escapeHtml(l.band)}</span></li>`
    ).join("");
    return (
      `<div class="micro-sector">` +
      `<h4>${escapeHtml(sec.sector)} <span class="micro-note">${full}/${sec.loads.length} fully served</span></h4>` +
      `<ul class="micro-loads">${items}</ul>` +
      `</div>`
    );
  }).join("");
}

function _microRankRows(rows) {
  return rows.slice(0,MICRO_RANK_LIMIT).map(({site:s}) => {
    const a=SiteEvidence.assessSite(s,"micro");
    return `<tr data-id="${escapeAttr(s.id)}"><td><a class="micro-site-link" data-site="${escapeAttr(s.id)}" href="?site=${encodeURIComponent(s.id)}">${escapeHtml(s.name || s.id)}</a><span class="micro-sub">${escapeHtml(s.state || "")}</span></td>`
      + SiteEvidence.PRIMARY.map(k => `<td data-category="${k}" data-label="${SiteEvidence.LABELS[k]}">${evidenceCell(a[k])}</td>`).join("")+"</tr>";
  }).join("");
}

// Acreage display that keeps the parcel fallback and the structural gap
// visible. `null` here is a source-side absence, never a filtered-out site.
function _microEffectiveAcreageDisplay(s) {
  if (s.acreage != null) return fmt.acres(s.acreage);
  if (s.parcel_acreage != null) return fmt.acres(s.parcel_acreage) + " (parcel)";
  return "Not reported";
}

function buildMicroView() {
  const host = el("micro-content");
  if (!host) return;
  if (microFleetLoadFailed) {
    host.innerHTML =
      '<p class="muted">Microreactor fleet data could not be loaded. ' +
      '<button type="button" id="micro-retry" class="text-btn">Retry</button></p>';
    const retry = el("micro-retry");
    if (retry) {
      retry.addEventListener("click", () => {
        // Clear the failure and re-render BEFORE kicking off the fetch, so the
        // click has immediate feedback. Without this the error text sits there
        // unchanged for the whole round-trip and the button reads as dead.
        microFleetLoadFailed = false;
        buildMicroView();
        ensureMicroFleetLoaded();
      });
    }
    return;
  }
  if (!microFleet) {
    host.innerHTML = '<p class="muted">Loading microreactor fleet…</p>';
    return;
  }

  // Idempotent — covers the case where the fleet resolved before initMap()
  // had created the layer (the loader's own call would have no-oped).
  addMicroCommitmentMarkers();

  const ranked = microRankedSites();
  microState.ranked = ranked;
  const counts = microFleet.counts || {};
  const mwe = microFleet.committed_mwe_by_band || {};
  const bandStrip = (microFleet.evidence_bands || [])
    .filter((b) => mwe[b.band] != null)
    .map(
      (b) =>
        `<div class="micro-band-cell band-${escapeAttr(b.band)}" title="${escapeAttr(b.rule)}">` +
        `<span class="micro-band-mwe">${mwe[b.band].toLocaleString()} MWe</span>` +
        `<span class="micro-band-label">${escapeHtml(b.label)}</span>` +
        `<span class="micro-band-auth">${escapeHtml(b.authority)}</span></div>`
    ).join("");

  const filtered = (typeof filtersActive === "function" && filtersActive()) || filterState.q;
  const scorable = ranked.length;
  // Derived, never hardcoded — the same rule PROGRAM_LEGEND and the nuclear
  // overlay counts follow. These move on every data refresh.
  let federalCount = 0, fedSuperfundCount = 0;
  for (const s of sites) {
    if (s.program === "fuds" || s.program === "brac") federalCount++;
    else if (s.program === "superfund" && s.federal_facility_code === "Y") fedSuperfundCount++;
  }

  host.innerHTML =
    `<div class="micro-lead"><h2>Microreactors</h2><p>Compare site evidence, then review designs and documented commitments. Grid absence and former military use establish neither isolation nor licensing eligibility.</p>` +
    `<button id="micro-export-csv" type="button" class="ap1000-export">Download evidence CSV</button></div>` +
    `<section class="micro-section">` +
      `<h3>The fleet — ${counts.vendors_microreactor_band || 0} designs in the 1–20&nbsp;MWe band` +
        `<span class="micro-note"> · plus 1 labelled adjacency</span></h3>` +
      `<div class="micro-bandstrip">${bandStrip}` +
        `<p class="micro-note micro-bandstrip-foot">Committed MWe, summed <strong>only within a band</strong>. ` +
        `An announced MOU and an executed contract are never added together.</p></div>` +
      `<div class="micro-table-wrap"><table class="micro-table"><thead><tr>` +
        `<th scope="col">Design</th><th scope="col">Output</th><th scope="col">Specification</th>` +
        `<th scope="col">Strongest documented state</th><th scope="col">Src</th>` +
      `</tr></thead><tbody>${_microFleetRows()}</tbody></table></div>` +
    `</section>` +

    `<section class="micro-section">` +
      `<h3>Named commitments — ${counts.commitments || 0}` +
        `<span class="micro-note"> · ${counts.commitments_mapped || 0} carry coordinates and appear as ⬣ on the map</span></h3>` +
      `<div class="micro-table-wrap"><table class="micro-table"><thead><tr>` +
        `<th scope="col">Commitment</th><th scope="col">Vendor</th><th scope="col">Location</th>` +
        `<th scope="col">Power</th><th scope="col">Evidence</th><th scope="col">Src</th>` +
      `</tr></thead><tbody>${_microCommitmentRows()}</tbody></table></div>` +
    `</section>` +

    `<section class="micro-section janus-section" id="janus-screen">` +
      `<div class="janus-section-head"><div><p class="eyebrow">Army Janus · NEPA MCP 0.1.1</p>` +
      `<h3>Environmental and regulatory screen — 9 candidate installations</h3></div>` +
      `<span class="micro-note">Federal evidence; no composite risk score</span></div>` +
      `<p class="micro-note janus-intro">Click an installation for traceable ESA, water, historic, tribal, ` +
      `protected-land, USACE, EPA, and geospatial evidence. Counts describe a 10-mile installation context, ` +
      `except PAD-US at the reference point. They do not describe a proposed reactor footprint.</p>` +
      `${_janusMatrixHtml()}${_janusDetailHtml()}` +
    `</section>` +

    `<details class="ap1000-help micro-demand">` +
      `<summary>Demand ladder — ${counts.sector_loads || 0} load classes across ${counts.sectors || 0} sectors ` +
      `(${counts.sector_loads_full_fit || 0} fully served by a single ≤20&nbsp;MWe unit)</summary>` +
      `<div class="ap1000-help-body">` +
        `<p class="micro-note">Annual-average electrical demand planning bands. ` +
        `<span class="fit-key fit-full">Filled</span> = one unit covers the whole load; ` +
        `<span class="fit-key fit-block">Outlined</span> = the load exceeds the band, so a unit serves a ` +
        `dedicated block inside a larger campus. These are planning bands, not guaranteed averages — ` +
        `final sizing needs at least a year of hourly site-load data.</p>` +
        `<div class="micro-sectors">${_microSectorHtml()}</div>` +
      `</div>` +
    `</details>` +

    `<section class="micro-section"><h3>Site evidence · ${scorable.toLocaleString()} matches</h3>` +
    `<div class="micro-controls"><button type="button" id="micro-offgrid-toggle" class="cand-filter" aria-pressed="${microState.offGridOnly}">Missing grid evidence</button><span class="micro-note">${MICRO_MIN_ACRES}+ reported acres or unknown. Missing grid data does not mean off-grid.</span></div>` +
    (scorable ? `<div class="micro-table-wrap"><table class="micro-table micro-rank-table evidence-table"><thead><tr><th>Site</th>${SiteEvidence.PRIMARY.map(k=>`<th>${SiteEvidence.LABELS[k]}</th>`).join("")}</tr></thead><tbody>${_microRankRows(ranked)}</tbody></table></div>` : `<p>No sites match these filters.</p>`) + `</section>`;

  microState.built = true;
  wireMicroControls();
}

// e2e hooks, mirroring window.__buildAp1000Csv / __sites / __tableState. They
// let a test target the ranking and the fleet without depending on scroll
// position, table paging, or marker decimation.
function exposeMicroTestHooks() {
  window.__buildMicroCsv = buildMicroCsv;
  window.__microRankedCount = () => microRankedSites().length;
  window.__microFleet = () => microFleet;
  window.__janusNepa = () => janusNepa;
  window.__showJanusMap = showJanusMap;
  window.__janusMapFeatureCount = () => janusNepaLayer?.getLayers().length || 0;
  window.__fmtMiles = fmt.miles;
}

function wireMicroControls() {
  exposeMicroTestHooks();
  const toggle = el("micro-offgrid-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      microState.offGridOnly = !microState.offGridOnly;
      buildMicroView();
    });
  }
  const csv = el("micro-export-csv");
  if (csv) csv.addEventListener("click", downloadMicroCsv);
  const janusRetry = el("janus-retry");
  if (janusRetry) {
    janusRetry.addEventListener("click", () => {
      janusNepaLoadFailed = false;
      buildMicroView();
      ensureJanusNepaLoaded();
    });
  }
  // Site links open the detail panel in place rather than reloading the page
  // with ?site= — same affordance the Rankings table gives.
  const host = el("micro-content");
  if (host) {
    host.querySelectorAll("button.janus-site-button").forEach((button) => {
      button.addEventListener("click", () => {
        microState.janusSelectedId = button.dataset.janus;
        const url = new URL(location.href);
        url.searchParams.set("janus", button.dataset.janus);
        url.hash = "micro";
        history.replaceState(null, "", url.pathname + url.search + url.hash);
        buildMicroView();
        requestAnimationFrame(() => el("janus-detail")?.focus());
      });
    });
    host.querySelectorAll("button.janus-map-button").forEach((button) => {
      button.addEventListener("click", () => showJanusMap(button.dataset.janusMap));
    });
    host.querySelectorAll("a.micro-site-link").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        selectSite(a.dataset.site);
      });
    });
  }
}

const MICRO_CSV_COLS = [
  ["id", (r) => r.site.id],
  ["name", (r) => prettyName(r.site.name) || ""],
  ["program", (r) => r.site.program],
  ["state", (r) => r.site.state || ""],
  ["acreage", (r) => r.site.acreage ?? ""],
  ["parcel_acreage", (r) => r.site.parcel_acreage ?? ""],
  ["transmission_mi", (r) => r.site.transmission_mi ?? ""],
  ["grid_access_mi", (r) => microreactorGridAccessMi(r.site) ?? ""],
  ["substation_mi", (r) => r.site.substation_mi ?? ""],
  ["highway_mi", (r) => r.site.highway_mi ?? ""],
  ["rail_mi", (r) => r.site.rail_mi ?? ""],
  ["power_plant_mi", (r) => r.site.power_plant_mi ?? ""],
  ["power_plant_mw", (r) => r.site.power_plant_mw ?? ""],
  ["power_plant_fuel", (r) => r.site.power_plant_fuel ?? ""],
  ["in_sfha", (r) => (r.site.in_sfha == null ? "" : r.site.in_sfha)],
  ["nri_wildfire_rating", (r) => r.site.nri_wildfire_rating ?? ""],
];

function buildMicroCsv() {
  const cols=evidenceCsvColumns(r=>r.site);
  return [csvRow(MICRO_CSV_COLS.map(c=>c[0]).concat(cols.map(c=>c.label))),
    ...microRankedSites().map(r=>{const a=SiteEvidence.assessSite(r.site); return csvRow(MICRO_CSV_COLS.map(c=>c[1](r)).concat(cols.map(c=>c.compute(r,a))));})].join("\n");
}

function downloadMicroCsv() {
  const blob = new Blob([buildMicroCsv()], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `microreactor-siting-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ----- DC Candidates view -----
//
// A ranked, pre-sorted table of every site with a suitability score, showing
// the key signals that explain the score side-by-side: voltage class,
// substation proximity, nearest plant (capacity + fuel), gas pipeline,
// and readiness/risk badges (OZ, Cleanup, Flood, etc.).
//
// Sources from `tableState.filtered` — the SAME globally-filtered set the
// map and table show — so search / state / program / acreage / persona /
// OZ filters carry across tabs. (Pre-unification the tab silently ignored
// them and duplicated tier + readiness as unsynced parallel controls —
// see the 2026-06-10 tab-UX findings in backlog.md.) The only view-local
// state is the scoring lens, round-tripped through the URL as `?lens=gen`.
//
// The view is rebuilt on tab activation, on every applyFilter(), and after
// relevant lazy loads settle (evidence becomes available as sources arrive).
const CANDIDATES_PAGE = 50;
const candidatesState = {
  sorted:   [],
  rendered: 0,
  lens:     "dc",   // "dc" | "gen" | "mfg" — URL state ?lens=
};
let _candidatesObserver = null;



// EPA Sitewide Ready for Anticipated Use (SWRAU) — true only for the two
// affirmative values. "Does Not Meet the Measure", its "(Retracted)" variant,
// and null all return false (a retracted determination is not a ready signal).
function _meetsRau(rauStatus) {
  return typeof rauStatus === "string" && /^Meets the Measure/i.test(rauStatus);
}

function makeCandidateRow(s) { return evidenceRow(s,candidatesState.lens); }

function siteMatchesEvidenceFilters(s) {
  sanitizeGeographicEvidence(s);
  const key = el("evidence-category-filter")?.value || "grid";
  const status = el("evidence-status-filter")?.value || "";
  const confidence = el("evidence-confidence-filter")?.value || "";
  if (!status && !confidence) return true;
  const e = SiteEvidence.assessSite(s,candidatesState.lens)[key];
  return (!status || e.status === status) && (!confidence || e.confidence === confidence);
}
function buildCandidatesView() {
  candidatesState.sorted = tableState.filtered.filter(siteMatchesEvidenceFilters).slice().sort(evidenceNameOrder);
  updateFilterChip(); syncUrl();
  const stats = el("candidates-stats");
  if (stats) stats.textContent = `${candidatesState.sorted.length.toLocaleString()} sites · alphabetical · confidence describes evidence, not suitability`;
  const tbody = document.querySelector("#candidates-table tbody"); if (!tbody) return;
  tbody.replaceChildren(); candidatesState.rendered=0; _appendCandidatesPage(tbody); _setupCandidatesScroll();
  ["evidence-category-filter","evidence-status-filter","evidence-confidence-filter"].forEach(id => {
    const node=el(id); if(node && !node._evidenceWired) {node._evidenceWired=true; node.addEventListener("change",buildCandidatesView);}
  });
}

function _appendCandidatesPage(tbody) {
  const start = candidatesState.rendered;
  const end   = Math.min(start + CANDIDATES_PAGE, candidatesState.sorted.length);
  const frag  = document.createDocumentFragment();
  for (let i = start; i < end; i++) {
    frag.appendChild(makeCandidateRow(candidatesState.sorted[i], i + 1));
  }
  tbody.appendChild(frag);
  candidatesState.rendered = end;
}

function _setupCandidatesScroll() {
  const wrap = el("candidates-wrap");
  if (!wrap) return;
  if (_candidatesObserver) _candidatesObserver.disconnect();
  let sentinel = wrap.querySelector(".cand-sentinel");
  if (!sentinel) {
    sentinel = document.createElement("div");
    sentinel.className = "cand-sentinel";
    sentinel.setAttribute("aria-hidden", "true");
    wrap.appendChild(sentinel);
  }
  _candidatesObserver = new IntersectionObserver(
    (entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      const candidatesView = el("view-candidates");
      if (!candidatesView?.classList.contains("active") || wrap.clientHeight <= 0) {
        return;
      }
      // Same scroll-position guard as the main table (UAT-2026-05-11):
      // don't prefetch during tab-transition layout thrash.
      const remaining = wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight;
      if (remaining > 400) return;
      const tbody = document.querySelector("#candidates-table tbody");
      if (tbody && candidatesState.rendered < candidatesState.sorted.length) {
        _appendCandidatesPage(tbody);
      }
    },
    { root: wrap, rootMargin: "300px" }
  );
  _candidatesObserver.observe(sentinel);
}

// Reflect candidatesState.lens onto the lens buttons — called at wire time
// and again after URL-state parsing so a `?lens=gen` deep-link lands with
// the right button lit.
function refreshCandLensButtons() {
  document.querySelectorAll("[data-cand-lens]").forEach((b) =>
    b.classList.toggle("active", b.dataset.candLens === candidatesState.lens));
}

function wireCandidatesFilters() {
  // `?lens=` is parsed here, NOT in loadInitialFiltersFromUrl() — that
  // runs at top level before `const candidatesState` initializes (TDZ).
  // wireCandidatesFilters runs from the boot .then(), safely after.
  const urlLens = new URLSearchParams(location.search).get("lens");
  if (urlLens === "gen" || urlLens === "mfg") {
    candidatesState.lens = urlLens;
  }
  document.querySelectorAll("[data-cand-lens]").forEach((btn) => {
    btn.addEventListener("click", () => {
      candidatesState.lens = btn.dataset.candLens;
      refreshCandLensButtons();
      syncUrl();
      if (el("view-candidates").classList.contains("active")) buildCandidatesView();
    });
  });
  refreshCandLensButtons();
}

function maybeRefreshCandidates() {
  const view = el("view-candidates");
  if (view && view.classList.contains("active")) buildCandidatesView();
}

// ----- Maritime Siting view -----
// Ranks the whole corpus (sourced from tableState.filtered, same global-
// filter contract as Rankings/Microreactors) for two lenses defined in
// maritime-score.js: floating/offshore nuclear, and coastal on-site
// generation/data centers. Simpler than Rankings' infinite-scroll table —
// capped at the top MARITIME_PAGE sites, no pagination, since both lenses
// gate on port_mi != null and only a fraction of the corpus is coastal.
const MARITIME_PAGE = 150;
const maritimeState = {
  lens: "offshore", // "offshore" | "coastal" — URL state ?mlens=
};



function makeMaritimeRow(s) { return evidenceRow(s,"maritime"); }

function buildMaritimeView() {
  const eligible = maritimeState.lens === "coastal" ? s => s.port_mi != null : s => s.port_mi != null || s.shipyard_mi != null;
  const sorted = tableState.filtered.filter(eligible).slice().sort(evidenceNameOrder);
  const stats=el("maritime-stats"); if(stats) stats.textContent=`${sorted.length.toLocaleString()} sites with mapped port or shipyard context · alphabetical · showing ${Math.min(sorted.length,MARITIME_PAGE)}`;
  const tbody=document.querySelector("#maritime-table tbody"); if(!tbody)return;
  tbody.replaceChildren(...sorted.slice(0,MARITIME_PAGE).map(s => makeMaritimeRow(s)));
}

function refreshMaritimeLensButtons() {
  document.querySelectorAll("[data-maritime-lens]").forEach((b) =>
    b.classList.toggle("active", b.dataset.maritimeLens === maritimeState.lens));
}

function wireMaritimeFilters() {
  // `?mlens=` is parsed here, not at top level — same TDZ lesson as
  // wireCandidatesFilters()'s `?lens=` parsing.
  const urlLens = new URLSearchParams(location.search).get("mlens");
  if (urlLens === "coastal") maritimeState.lens = urlLens;
  document.querySelectorAll("[data-maritime-lens]").forEach((btn) => {
    btn.addEventListener("click", () => {
      maritimeState.lens = btn.dataset.maritimeLens;
      refreshMaritimeLensButtons();
      syncUrl();
      if (el("view-maritime")?.classList.contains("active")) buildMaritimeView();
    });
  });
  refreshMaritimeLensButtons();
}

// ----- Nickel Refining view -----
// Ranks the corpus (sourced from tableState.filtered, the same global-filter
// contract as Rankings / Microreactors / Maritime) under the two feed models
// defined in nickel-score.js.
const NICKEL_PAGE = 150;
const nickelState = {
  lens: "import",        // "import" | "domestic" — URL state ?nlens=
  // Land basis. Defaults to CONFIRMED, and that default is the difference
  // between a useful screen and a misleading one: 95% of otherwise-eligible
  // sites have no published acreage, they are mostly small urban parcels, and
  // because every scored component is a distance that is near zero downtown
  // they dominated the ranking outright — 0 of the top 150 had confirmed land
  // before this. Showing them by default answers "which brownfield sits in
  // the densest infrastructure", which is not the question this tab asks.
  // "confirmed" (refinery, 300 ac) | "recycling" (100 ac) | "any"
  // URL state ?land=recycling / ?land=any
  landBasis: "confirmed",
};



function _nickelWaterCell(s) {
  // Three distinct states, and collapsing any two of them would mislead:
  // the join has not run; it ran and found nothing in range; it found a gage.
  if (!s._waterChecked) return '<span class="muted-cell">—</span>';
  if (s.water_flow_cfs == null) return '<span class="muted-cell">Supply unassessed</span>';
  return `${Math.round(s.water_flow_cfs).toLocaleString()} cfs` +
    `<div class="micro-sub">${escapeHtml(s.water_gage_name || "")} · ${fmt.miles(s.water_gage_mi)}</div>`;
}

// Land is a threshold, and the null case is the one that matters: EPA
// publishes no acreage at all for its ~36k brownfield properties, so "unknown"
// is the honest answer for most rows and must not read as "too small".
function _nickelLandCell(s, minAcres = NICKEL_MIN_ACRES) {
  const status = nickelAcreageStatus(s, minAcres);
  if (status === null) return '<span class="muted-cell">Unknown</span>';
  const ac = s.acreage ?? s.parcel_acreage;
  return status
    ? `<span class="nickel-land ok">${fmt.acres(ac)}</span>`
    : `<span class="nickel-land under">${fmt.acres(ac)}</span>`;
}

function makeNickelRow(s) { return evidenceRow(s,"nickel"); }

function buildNickelView() {
  const minAcres=nickelState.landBasis === "recycling" ? NICKEL_MIN_ACRES_RECYCLING : NICKEL_MIN_ACRES;
  const sorted=tableState.filtered.filter(s => {
    const land=nickelAcreageStatus(s,minAcres);
    return (land === true || (land === null && nickelState.landBasis === "any"))
      && (nickelState.lens === "domestic" ? s.rail_mi != null : s.port_mi != null);
  }).slice().sort(evidenceNameOrder);
  const stats=el("nickel-stats");
  const errors=[...nickelDataErrors].filter(key => !(key === "port" && nickelState.lens === "domestic"));
  const pending=!lazyLoadsSettled || (!nickelAnchorRecords && !errors.includes("supply chain")) || (nickelState.lens === "import" && !portProximityRecords && !errors.includes("port"));
  if(stats) stats.textContent=errors.length ? `Some evidence unavailable: ${errors.join(", ")}. Reopen this tab to retry; missing data is unassessed.` : sorted.length ? `${sorted.length.toLocaleString()} sites · reported land ${minAcres}+ acres${nickelState.landBasis === "any" ? " or unknown" : ""} · alphabetical · showing ${Math.min(sorted.length,NICKEL_PAGE)}`
    : pending ? "Loading site evidence…" : "No sites match these filters. Try including unknown acreage.";
  const tbody=document.querySelector("#nickel-table tbody");if(!tbody)return;
  tbody.replaceChildren(...sorted.slice(0,NICKEL_PAGE).map(s => makeNickelRow(s)));
}

function refreshNickelLensButtons() {
  document.querySelectorAll("[data-nickel-lens]").forEach((b) =>
    b.classList.toggle("active", b.dataset.nickelLens === nickelState.lens));
  document.querySelectorAll("[data-nickel-land]").forEach((b) =>
    b.classList.toggle("active", b.dataset.nickelLand === nickelState.landBasis));
}

function wireNickelFilters() {
  // `?nlens=` parsed here, not at top level — the same TDZ lesson as
  // wireCandidatesFilters()'s `?lens=`.
  const params = new URLSearchParams(location.search);
  const urlLens = params.get("nlens");
  if (urlLens === "domestic") nickelState.lens = urlLens;
  const urlLand = params.get("land");
  if (urlLand === "any" || urlLand === "recycling") nickelState.landBasis = urlLand;
  document.querySelectorAll("[data-nickel-land]").forEach((btn) => {
    btn.addEventListener("click", () => {
      nickelState.landBasis = btn.dataset.nickelLand;
      refreshNickelLensButtons();
      syncUrl();
      if (el("view-nickel")?.classList.contains("active")) buildNickelView();
    });
  });
  document.querySelectorAll("[data-nickel-lens]").forEach((btn) => {
    btn.addEventListener("click", () => {
      nickelState.lens = btn.dataset.nickelLens;
      refreshNickelLensButtons();
      syncUrl();
      if (el("view-nickel")?.classList.contains("active")) buildNickelView();
    });
  });
  refreshNickelLensButtons();
}

function maybeRefreshNickel() {
  const view = el("view-nickel");
  if (view && view.classList.contains("active") && nickelViewMounted) buildNickelView();
}

function maybeRefreshMaritime() {
  const view = el("view-maritime");
  if (view && view.classList.contains("active") && maritimeViewMounted) buildMaritimeView();
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
// Selecting a new site preserves the LAST tab the user clicked within the
// session, so an analyst reading AI summaries across multiple sites
// doesn't have to re-click "Summary" on every selection. Resets to
// "overview" on page reload. URL/localStorage intentionally NOT used —
// the preference is ephemeral.
let _lastDetailTab = "overview";
function wireDetailTabs() {
  const tabs = [
    { id: "overview", btn: el("dtab-overview"), pane: el("dpane-overview") },
    { id: "summary",  btn: el("dtab-summary"),  pane: el("dpane-summary") },
  ];
  for (const t of tabs) {
    if (!t.btn || !t.pane) continue;
    t.btn.addEventListener("click", () => {
      _lastDetailTab = t.id;
      if (t.id === "summary") ensureSummariesLoaded();
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
  const summaryActive = _lastDetailTab === "summary";
  if (ov) { ov.classList.toggle("active", !summaryActive); ov.setAttribute("aria-selected", String(!summaryActive)); }
  if (sm) { sm.classList.toggle("active", summaryActive); sm.setAttribute("aria-selected", String(summaryActive)); }
  if (ovp) ovp.hidden = summaryActive;
  if (smp) smp.hidden = !summaryActive;
}


// Location-confidence note under the coordinate row.
//
// Every marker looks equally authoritative, but the corpus audit found 118
// sites plotted outside their own state, 17 on typed-in whole degrees, and
// 3,728 sharing a coordinate with two or more others (a geocoder falling
// back to a city centroid). Saying so is the honest alternative to silently
// correcting coordinates we have no better source for.
//
// Flags come from the `coord-quality` connector; the field is absent on
// records with no known problem, so most sites show nothing at all.
const COORD_FLAG_NOTES = {
  outside_us: () => "Source coordinate falls outside the United States.",
  state_mismatch: (s) => {
    const where = s.coord_actual_state ? ` in ${s.coord_actual_state}` : "";
    const gap = s.coord_state_gap_mi != null
      ? ` (${fmt.miles(s.coord_state_gap_mi)} outside ${s.state})` : "";
    return `Source places this${where}${gap}, not in ${s.state || "the listed state"}.`;
  },
  placeholder: () => "Coordinate looks like a placeholder, not a survey.",
  shared_point: (s) =>
    `Shares this exact coordinate with ${(s.coord_shared_count || 1) - 1} other `
    + `site${(s.coord_shared_count || 2) - 1 === 1 ? "" : "s"} — likely a city centroid.`,
  low_precision: () => "Low precision — about 1 km or coarser.",
};

// Most-severe first: a site outside its state is a bigger caveat than a
// coarse decimal count, and we only show one line.
const COORD_FLAG_ORDER = [
  "outside_us", "state_mismatch", "placeholder", "shared_point", "low_precision",
];

function setCoordQualityNote(s) {
  const note = el("d-coord-note");
  if (!note) return;
  const flags = Array.isArray(s.coord_flags) ? s.coord_flags : [];
  const top = COORD_FLAG_ORDER.find((f) => flags.includes(f));
  if (!top) {
    note.hidden = true;
    note.textContent = "";
    return;
  }
  note.textContent = COORD_FLAG_NOTES[top](s);
  note.hidden = false;
}

// ---- Sources & evidence -----------------------------------------------
//
// Renders one row per claim on the record: publisher, dataset + layer, how
// the value was derived, when that file was last refreshed, and a link that
// resolves to THIS site at the source wherever the upstream service allows
// it. The registry lives in provenance.js.
//
// Built LAZILY on first expand. The panel is in the DOM at first paint, and
// a full evidence table for a well-enriched site is ~150 nodes — enough to
// matter against the 5,000-node first-paint budget if it were eager. The
// `_evidenceRenderedFor` guard also stops a re-render on every toggle.
let _evidenceRenderedFor = null;

function renderEvidence(site) {
  const block = el("d-evidence-block");
  if (!block) return;
  const body = el("d-evidence-body");
  const countEl = el("d-evidence-count");
  if (typeof window.buildEvidence !== "function") {
    block.hidden = true;
    return;
  }
  const rows = window.buildEvidence(site);
  block.hidden = rows.length === 0;
  if (countEl) countEl.textContent = rows.length ? `· ${rows.length} fields` : "";
  // Collapse on site change so the next site starts closed and unbuilt.
  if (_evidenceRenderedFor !== site.id) {
    block.open = false;
    body.textContent = "";
    _evidenceRenderedFor = null;
  }
  if (block.open) buildEvidenceBody(site);
}

function buildEvidenceBody(site) {
  if (_evidenceRenderedFor === site.id) return;
  const body = el("d-evidence-body");
  const rows = window.buildEvidence(site);
  body.textContent = "";

  const groups = [];
  for (const r of rows) {
    let g = groups.find((x) => x.name === r.group);
    if (!g) { g = { name: r.group, rows: [] }; groups.push(g); }
    g.rows.push(r);
  }

  for (const group of groups) {
    const h = document.createElement("h4");
    h.className = "evidence-group";
    h.textContent = group.name;
    body.appendChild(h);

    for (const r of group.rows) {
      const item = document.createElement("div");
      item.className = "evidence-row";

      const label = document.createElement("div");
      label.className = "evidence-label";
      label.textContent = r.label;
      item.appendChild(label);

      const meta = document.createElement("div");
      meta.className = "evidence-meta";

      const pub = document.createElement("div");
      pub.className = "evidence-source";
      pub.textContent = r.dataset ? `${r.publisher} — ${r.dataset}` : r.publisher;
      meta.appendChild(pub);

      if (r.layer) {
        const layer = document.createElement("div");
        layer.className = "evidence-layer";
        layer.textContent = r.layer;
        meta.appendChild(layer);
      }

      if (r.derivation) {
        const how = document.createElement("div");
        how.className = "evidence-derivation";
        how.textContent = r.derivation;
        meta.appendChild(how);
      }

      const foot = document.createElement("div");
      foot.className = "evidence-foot";
      if (r.asOf) {
        const asOf = document.createElement("span");
        asOf.className = "evidence-asof";
        asOf.textContent = `As of ${r.asOf}`;
        foot.appendChild(asOf);
      }
      if (r.verifyUrl) {
        const a = document.createElement("a");
        a.href = r.verifyUrl;
        a.target = "_blank";
        a.rel = "noopener";
        a.className = "evidence-verify";
        a.textContent = r.verifyLabel + " \u2197";
        foot.appendChild(a);
      }
      if (r.code) {
        const code = document.createElement("span");
        code.className = "evidence-code";
        code.textContent = r.code;
        foot.appendChild(code);
      }
      if (foot.childNodes.length) meta.appendChild(foot);

      item.appendChild(meta);
      body.appendChild(item);
    }
  }
  _evidenceRenderedFor = site.id;
}

function wireEvidenceDisclosure() {
  const block = el("d-evidence-block");
  if (!block) return;
  block.addEventListener("toggle", () => {
    if (!block.open) return;
    const site = selectedId ? sitesById.get(selectedId) : null;
    if (site) buildEvidenceBody(site);
  });
}


// Nonessential catalogs load when their map surface is requested. Existing
// per-loader promises deduplicate concurrent view and map requests.
function ensureMapOverlayData() {
  return Promise.allSettled([
    ensureReferenceCampusesLoaded(), ensureRetiredIndustrialLoaded(),
    ensurePlannedRetirementsLoaded(), ensureCoalConversionsLoaded(),
    ensureFederalCleanEnergyLoaded(), ensureNuclearSitesLoaded(),
    ensureMicroFleetLoaded(), ensureHanfordLoaded(), ensurePortsLoaded(),
    ensureShipyardsLoaded(), ensureNickelAnchorsLoaded(),
  ]);
}

// Separate detail work from the initial category-screen readiness signal.
// Keep the settled promise to avoid selectSite -> loader -> selectSite loops.
let detailEvidencePromise = null;
function ensureDetailEvidenceLoaded() {
  if (detailEvidencePromise) return detailEvidencePromise;
  detailEvidencePromise = Promise.allSettled([
    ensureSuperfundDocsLoaded(), ensureEchoLoaded(), ensureTribalAreasLoaded(),
    ensureIraEnergyCommunityLoaded(), ensureFemaNriLoaded(), ensureClimateZoneLoaded(),
    ensureRetiredPlantsLoaded(), ensurePlannedRetireProxLoaded(),
    ensureCoalConversionsProxLoaded(), ensurePortProximityLoaded(),
  ]).then(() => {
    if (selectedId && sitesById.has(selectedId)) selectSite(selectedId);
  });
  return detailEvidencePromise;
}

function selectSite(id, { fromMap = false, fromTable = false } = {}) {
  const s = sitesById.get(id);
  if (!s) return;
  sanitizeGeographicEvidence(s);
  if (selectedId && tableRowsById.has(selectedId)) {
    tableRowsById.get(selectedId).classList.remove("selected");
  }
  selectedId = id;
  ensureDetailEvidenceLoaded();
  if (_lastDetailTab === "summary") ensureSummariesLoaded();
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
  // "Land Ready" — EPA Sitewide Ready for Anticipated Use (SWRAU). The single
  // best public per-site land-availability signal: EPA's own answer to "is
  // ALL of this site's land ready for its anticipated use." Only the two
  // affirmative values count; the "(Retracted)" / "Does Not Meet" values don't.
  const landReadyPill = _meetsRau(s.rau_status)
    ? ` <span class="pill reuse-pill" title="EPA Sitewide Ready for Anticipated Use (SWRAU): all of this site's land is ready for its anticipated use">Land Ready</span>`
    : "";
  // Opportunity Zone pill — financial signal, not technical. 30% capital
  // gains deferral on 5+yr holds inside a Treasury-designated QOZ. Rural
  // OZs are a meaningful subset (~700 / 8,765 tracts) so we label them.
  const ozPill = s.in_opportunity_zone === true
    ? ` <span class="pill oz-pill" title="Site is inside a Treasury Qualified Opportunity Zone — capital gains deferral applies to 5+yr holds (QOF investment)${s.oz_rural ? ' · Rural OZ designation' : ''}">${s.oz_rural ? 'OZ \xb7 Rural' : 'OZ'}</span>`
    : "";
  // IRA energy community pill — financial signal that stacks with OZ. A
  // clean-energy build here earns a +10pp ITC/PTC bonus. Coal-closure
  // communities are the higher-confidence (tract-level) signal.
  const iraPill = s.in_energy_community === true
    ? ` <span class="pill ira-pill" title="IRA energy community (${escapeAttr(s.energy_community_type === "coal_closure" ? "coal closure" : "fossil-fuel employment")}${s.energy_community_detail ? " · " + escapeAttr(s.energy_community_detail) : ""}) — clean-energy projects earn a +10 percentage-point ITC/PTC bonus">${s.energy_community_type === "coal_closure" ? "IRA \xb7 Coal" : "IRA"}</span>`
    : "";
  const tribalPill = s.in_aiannha_area === true
    ? ` <span class="pill tribal-pill" title="Inside ${s.aiannha_area_count || 1} Census TIGERweb AIANNHA mapped area(s): ${escapeAttr((s.aiannha_areas || []).map((area) => area.name).join(" · "))}. Screening context only; not title or a consultation determination.">Tribal area context</span>`
    : "";
  // EO 14318 "Federal Fast Lane" — policy signal. Meets EPA Jan 2026 criteria
  // for fast-tracked NEPA categorical exclusion + Army Corps Section 404 permits.
  const eo14318Pill = ""; // A spatial screen cannot establish a permitting entitlement.
  el("d-program").innerHTML = programPill + cleanupPill + reusePill + landReadyPill + dcPill + ozPill + iraPill + tribalPill + eo14318Pill;
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
  // Parcel area — the actual cadastral parcel size (parcel-owner connector).
  // Shown when known; it's the only land-size signal for ACRES sites, whose
  // program `acreage` is always null.
  const parcelRow = el("d-parcel-acreage-row");
  const parcelEl = el("d-parcel-acreage");
  if (parcelRow && parcelEl) {
    const has = s.parcel_acreage != null;
    parcelRow.hidden = !has;
    parcelEl.hidden = !has;
    if (has) {
      const src = s.current_owner_source ? ` · ${escapeHtml(s.current_owner_source)}` : "";
      const pid = s.parcel_id ? ` · parcel ${escapeHtml(String(s.parcel_id))}` : "";
      parcelEl.innerHTML = `${escapeHtml(fmt.acres(s.parcel_acreage))}<span class="muted-cell">${src}${pid}</span>`;
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
  // computed for every program against HIFLD + Census TIGER). Out-of-CONUS
  // sites (AK / HI / PR / VI / Pacific) are intentionally absent from
  // `infra-proximity.json` because the connector's MAX_DISTANCE_MI=100mi
  // window doesn't extend that far — surface a placeholder so the rows
  // don't read as missing/uncomputed data.
  const offConus = !!s._inset;
  setMileCell("d-transmission-mi", s.transmission_mi, { offConus });
  // Append the line voltage when known so users can see whether the
  // nearest line is hyperscale-grade (≥230 kV) at a glance. The kV chip
  // is a child span so subsequent calls to setMileCell don't clobber it.
  setKvSuffix("d-transmission-mi", s.transmission_kv);
  setMileCell("d-substation-mi", s.substation_mi, { offConus });
  // Substation kV uses the same chip pattern as transmission. A 500 kV
  // substation 0.3 mi away is the most actionable signal for a hyperscale
  // siting evaluation — pairs with the transmission line distance above.
  setKvSuffix("d-substation-mi", s.substation_kv);
  setMileCell("d-power-plant-mi", s.power_plant_mi, { offConus });
  // Append MW + fuel suffix to the power-plant row so users see "2.5 mi · 450 MW · natural gas".
  setPowerPlantSuffix("d-power-plant-mi", s.power_plant_mw, s.power_plant_fuel);
  // Retired plant row (EIA-860M). Shown when within MAX_DISTANCE_MI (5 mi).
  setRetiredPlantCell("d-retired-plant-mi", s);
  // Planned-retirement plant row — an operating plant with an announced
  // shutdown date (the interconnect frees on a known future date).
  setPlannedRetireCell("d-planned-retire-mi", s);
  // Coal conversion asset row — evaluated stranded switchyard/water/rail value.
  setCoalRepowerCell("d-coal-repower-mi", s);
  setMileCell("d-rail-mi", s.rail_mi, { offConus });
  setMileCell("d-highway-mi", s.highway_mi, { offConus });
  setMileCell("d-gas-pipeline-mi", s.gas_pipeline_mi, { offConus });
  // Port / shipyard proximity (port-proximity enrichment) — Maritime Siting.
  setPortCell("d-port-mi", s);
  setWaterCell("d-water-flow", s);
  setShipyardCell("d-shipyard-mi", s);
  // Flood zone is a string code, not a mile-distance, so it gets its own
  // renderer. Critical permitting signal: a site in an SFHA effectively
  // can't be permitted as critical infrastructure (DC, energy plant) without
  // expensive elevation / flood-proofing work.
  setFloodZoneCell("d-flood-zone", s.flood_zone, s.in_sfha);
  setTextCell("d-iso-rto", s.iso_rto ? (ISO_RTO_LABELS[s.iso_rto] || s.iso_rto) : null);
  setTextCell("d-climate-zone", s.climate_zone);
  // Opportunity Zone — financial signal for buyers, surfaced as a cell in
  // the infra section. Yes/No based on the universal HUD layer; legacy
  // string-valued `in_opp_zone` (EPA RE-Powering, Superfund-only) is a
  // fallback when the universal enrichment hasn't loaded yet.
  setOpportunityZoneCell("d-opp-zone", s);
  setEnergyCommunityCell("d-energy-community", s);
  setRauStatusCell("d-rau-status", s);
  setNriCell("d-nri-risk", s);
  // State data-center tax incentive chip (Tier 1/2/3) — uses the static
  // STATE_DC_INCENTIVES lookup, no fetch.
  renderStateIncentive(s);
  // Shared category findings, evidence confidence and remaining checks.
  renderSuitability(s);
  // EPA RE-Powering service-area indicators (Superfund-only).
  el("d-near-water").textContent = fmt.text(s.near_water_supply);
  el("d-near-ww").textContent = fmt.text(s.near_wastewater);
  el("d-pop-density").textContent = fmt.text(s.pop_density);
  // The DC candidate `<dd>` carries an inline criteria `<span>` that surfaces
  // the EPA RE-Powering reasoning when the boolean is true. Same text-node
  // pattern as the FUDS acreage note — rewrite firstChild only so the span
  // survives subsequent renders.
  const dcEl = el("d-dc-candidate");
  const dcCriteria = el("d-dc-criteria");
  const dcText = s.data_center_reuse_candidate === true ? "Yes"
    : s.data_center_reuse_candidate === false ? "No"
    : "—";
  dcEl.firstChild && dcEl.firstChild.nodeType === Node.TEXT_NODE
    ? (dcEl.firstChild.nodeValue = dcText)
    : dcEl.insertBefore(document.createTextNode(dcText), dcCriteria || null);
  if (dcCriteria) {
    if (s.data_center_reuse_candidate === true) {
      dcCriteria.textContent = "≥50 acres · electric transmission · water service area";
      dcCriteria.hidden = false;
    } else {
      dcCriteria.textContent = "";
      dcCriteria.hidden = true;
    }
  }

  el("d-region").textContent = s.region != null ? `Region ${s.region}` : "—";
  el("d-addr").textContent = [s.address, s.city, s.state, s.zip].filter(Boolean).join(", ") || "—";
  // Show real coordinates in the detail panel — `s.lat`/`s.lon` may be the
  // remapped inset display coords for AK/HI/PR/Pacific records.
  const realLat = s.lat_real ?? s.lat;
  const realLon = s.lon_real ?? s.lon;
  // Rewrite ONLY the leading text node — `#d-coord-note` is a sibling inside
  // the same <dd>, and textContent= would delete it (the same trap the FUDS
  // acreage note documents).
  const coordCell = el("d-coord");
  const coordText =
    realLat != null && realLon != null ? `${realLat.toFixed(4)}, ${realLon.toFixed(4)}` : "—";
  if (coordCell.firstChild && coordCell.firstChild.nodeType === 3) {
    coordCell.firstChild.nodeValue = coordText;
  } else {
    coordCell.insertBefore(document.createTextNode(coordText), coordCell.firstChild);
  }
  setCoordQualityNote(s);
  renderEvidence(s);

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
  renderGrants(s);
  renderSummary(s);
  renderNearbySites(s);
  resetDetailTabs();
  // After all section content updates, re-apply the accordion defaults so a
  // newly-shown section (e.g. ECHO block transitioning from hidden→visible)
  // picks up either the user's recorded preference or the viewport default.
  applyDetailSectionDefaults();

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
  // NPDES permit flag — water-access proxy (CWA/NPDES = legacy industrial water infrastructure)
  const npdesNode = el("d-echo-npdes");
  if (npdesNode) {
    if (enf.has_npdes_permit === true) {
      npdesNode.textContent = "Yes — CWA/NPDES permit on file";
      npdesNode.className = "ready";
    } else if (enf.has_npdes_permit === false) {
      npdesNode.textContent = "No";
      npdesNode.className = "muted-cell";
    } else {
      npdesNode.textContent = "Not available";
      npdesNode.className = "muted-cell";
    }
  }
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
  sanitizeGeographicEvidence(s);
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

// Render the "Nearby sites" block — up to 5 other sites within
// EPA ACRES cleanup status + brownfield grant history. Shown for brownfield
// records only; hidden for all other programs. Populates from the
// acres-cleanup enrichment connector lazy-loaded via ensureAcresCleanupLoaded().
function renderGrants(s) {
  const block = el("d-grants-block");
  if (!block) return;
  if (s.program !== "brownfield" || (!s.cleanup_status && s.grant_total_usd == null)) {
    block.hidden = true;
    return;
  }
  block.hidden = false;

  const statusEl = el("d-cleanup-status");
  if (statusEl) {
    if (s.cleanup_status) {
      statusEl.textContent = s.cleanup_status;
      statusEl.className = s.cleanup_status === "Completed" ? "ready" : "";
    } else {
      statusEl.textContent = "Not available";
      statusEl.className = "muted-cell";
    }
  }

  const dateEl = el("d-cleanup-date");
  if (dateEl) {
    if (s.cleanup_complete_date) {
      dateEl.textContent = s.cleanup_complete_date;
      dateEl.className = "";
    } else {
      dateEl.textContent = "Not available";
      dateEl.className = "muted-cell";
    }
  }

  const totalEl = el("d-grant-total");
  if (totalEl) {
    if (s.grant_total_usd != null) {
      totalEl.textContent = "$" + s.grant_total_usd.toLocaleString();
      totalEl.className = "";
    } else {
      totalEl.textContent = "Not available";
      totalEl.className = "muted-cell";
    }
  }

  const typesEl = el("d-grant-types");
  if (typesEl) {
    if (s.grant_types && s.grant_types.length) {
      typesEl.textContent = s.grant_types.join(", ");
      typesEl.className = "";
    } else {
      typesEl.textContent = "Not available";
      typesEl.className = "muted-cell";
    }
  }

  const countEl = el("d-grants-count");
  if (countEl && s.grant_count != null) countEl.textContent = `(${s.grant_count})`;
  else if (countEl) countEl.textContent = "";
}

// NEARBY_RADIUS_MI of the selected site (Haversine on `lat_real`/`lon_real`
// so inset-remapped coords don't pollute distance). Clicking a result
// calls `selectSite(id)`. Block is hidden when the selected site has no
// real coords or when no neighbours fall within the radius.
const NEARBY_RADIUS_MI = 25;
const NEARBY_MAX_RESULTS = 5;
function renderNearbySites(s) {
  const block = el("d-nearby-block");
  const list = el("d-nearby-list");
  const countEl = el("d-nearby-count");
  if (!block || !list) return;
  const lat = s.lat_real ?? s.lat;
  const lon = s.lon_real ?? s.lon;
  if (lat == null || lon == null) {
    block.hidden = true;
    list.innerHTML = "";
    return;
  }
  // Linear scan of in-memory sites. Pre-filter via cheap lat-window check
  // (~0.4° box, ~28 mi at the equator) before Haversine to skip ~99% of
  // the corpus in O(n).
  const latDelta = NEARBY_RADIUS_MI / 69; // ~mi per degree of latitude
  const lonDelta = NEARBY_RADIUS_MI / (69 * Math.cos((lat * Math.PI) / 180));
  const candidates = [];
  for (const other of sites) {
    if (other.id === s.id) continue;
    const olat = other.lat_real ?? other.lat;
    const olon = other.lon_real ?? other.lon;
    if (olat == null || olon == null) continue;
    if (Math.abs(olat - lat) > latDelta) continue;
    if (Math.abs(olon - lon) > lonDelta) continue;
    const dist = haversineMi(lat, lon, olat, olon);
    if (dist <= NEARBY_RADIUS_MI) candidates.push({ s: other, dist });
  }
  candidates.sort((a, b) => a.dist - b.dist);
  const top = candidates.slice(0, NEARBY_MAX_RESULTS);
  if (!top.length) {
    block.hidden = true;
    list.innerHTML = "";
    return;
  }
  list.innerHTML = top.map(({ s: o, dist }) => {
    const programLabel = PROGRAM_LABEL[o.program] || o.program;
    const place = [o.city, o.state].filter(Boolean).join(", ");
    return `<li>` +
      `<button type="button" class="nearby-link" data-id="${escapeAttr(o.id)}">` +
      `<span class="nearby-name">${escapeHtml(o.name || o.id)}</span>` +
      `<span class="nearby-meta">${escapeHtml(programLabel)}${place ? " · " + escapeHtml(place) : ""}</span>` +
      `<span class="nearby-dist">${dist.toFixed(1)} mi</span>` +
      `</button></li>`;
  }).join("");
  if (countEl) countEl.textContent = `(${top.length}${candidates.length > top.length ? ` of ${candidates.length}` : ""} within ${NEARBY_RADIUS_MI} mi)`;
  block.hidden = false;
}

// Haversine distance in miles between two lat/lon points. Used by the
// nearby-sites renderer where precise great-circle distance matters
// across the full ~3,000-mile US span; the local-equirectangular
// approximation in `connectors/spatial.py` would understate distance
// by up to ~3% near the corners of CONUS.
function haversineMi(lat1, lon1, lat2, lon2) {
  const R = 3958.8; // Earth radius in miles
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
    Math.cos((lat2 * Math.PI) / 180) *
    Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

// Delegated click handler for nearby-site links — wired once at init.
function wireNearbyClicks() {
  const list = el("d-nearby-list");
  if (!list) return;
  list.addEventListener("click", (e) => {
    const btn = e.target.closest(".nearby-link");
    if (!btn) return;
    const id = btn.dataset.id;
    if (id) selectSite(id);
  });
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
  { key: "parcel_acreage", label: "parcel_acreage" },
  { key: "parcel_id", label: "parcel_id" },
  // Universal infra-proximity (v1.10 + v1.13 gas pipelines + v1.13.3 substation/power-plant/flood)
  { key: "transmission_mi", label: "transmission_mi" },
  { key: "transmission_kv", label: "transmission_kv" },
  { key: "substation_mi", label: "substation_mi" },
  { key: "substation_kv", label: "substation_kv" },
  { key: "power_plant_mi", label: "power_plant_mi" },
  { key: "power_plant_mw", label: "power_plant_mw" },
  { key: "power_plant_fuel", label: "power_plant_fuel" },
  { key: "rail_mi", label: "rail_mi" },
  { key: "highway_mi", label: "highway_mi" },
  { key: "gas_pipeline_mi", label: "gas_pipeline_mi" },
  { key: "flood_zone", label: "flood_zone" },
  { key: "in_sfha", label: "in_sfha" },
  { key: "iso_rto", label: "iso_rto" },
  { key: "climate_zone", label: "climate_zone" },
  // Water proximity (v1.23 streamgages / USGS)
  { key: "water_gage_mi", label: "water_gage_mi" },
  { key: "water_flow_cfs", label: "water_flow_cfs" },
  { key: "water_gage_name", label: "water_gage_name" },
  { key: "water_gage_id", label: "water_gage_id" },
  // FEMA National Risk Index (v1.19) — climate / natural-hazard risk
  { key: "nri_risk_score", label: "nri_risk_score" },
  { key: "nri_risk_rating", label: "nri_risk_rating" },
  { key: "nri_wildfire_rating", label: "nri_wildfire_rating" },
  { key: "nri_drought_rating", label: "nri_drought_rating" },
  // IRA energy community (v1.18) — financial signal (+10pp ITC/PTC bonus)
  { key: "in_energy_community", label: "in_energy_community" },
  { key: "energy_community_type", label: "energy_community_type" },
  // Independent findings with confidence, reasons and source links.
  ...evidenceCsvColumns(),
  // EPA RE-Powering qualitative (Superfund-only, v1.7)
  { key: "near_electric_transmission", label: "near_electric_transmission" },
  { key: "near_water_supply", label: "near_water_supply" },
  { key: "near_wastewater", label: "near_wastewater" },
  { key: "pop_density", label: "pop_density" },
  { key: "data_center_reuse_candidate", label: "dc_reuse_candidate" },
  { key: "rau_status", label: "rau_status" },
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
    return Array.isArray(v) ? v.length : null;
  }
  if (!key.includes(".")) return obj == null ? null : obj[key];
  let cur = obj;
  for (const part of key.split(".")) {
    if (cur == null) return null;
    cur = cur[part];
  }
  return cur;
}

function csvCell(s, col, assessment) {
  sanitizeGeographicEvidence(s);
  // Computed columns (e.g. the suitability scores) derive their value from
  // a function rather than a stored field.
  if (typeof col.compute === "function") {
    const cv = col.compute(s,assessment);
    return cv == null ? "" : cv;
  }
  let v = pickCsvField(s, col.key);
  if ((v == null || v === "") && col.fallback) v = pickCsvField(s, col.fallback);
  if (v == null) return "";
  if (typeof v === "boolean") return v ? "true" : "false";
  return v;
}

function buildSiteCsv() {
  const rows = [CSV_COLUMNS.map(c=>c.label)];
  const useEvidenceFilters = el("view-candidates")?.classList.contains("active");
  for(const site of sites) {
    if(!siteMatchesFilters(site) || (useEvidenceFilters && !siteMatchesEvidenceFilters(site))) continue;
    const assessment = SiteEvidence.assessSite(site);
    rows.push(CSV_COLUMNS.map(c=>csvCell(site,c,assessment)));
  }
  return rows.map(csvRow).join("\n");
}
function wireExportCsv() {
  el("export-csv").addEventListener("click", async () => {
    const button=el("export-csv"); button.disabled=true;
    try { await ensureDetailEvidenceLoaded(); } finally { button.disabled=false; }
    const csv = buildSiteCsv();
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
  for(const [param,id] of [["evidence","evidence-category-filter"],["finding","evidence-status-filter"],["confidence","evidence-confidence-filter"]]) {
    const node=el(id); const value=p.get(param);
    if(node && value != null && [...node.options].some(o=>o.value===value)) node.value=value;
  }
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
  if (p.has("dc_tier")) {
    const t = p.get("dc_tier") || "";
    if (DC_TIERS.some(tier=>tier.id===t)) filterState.dcTier = t;
  }
  if (p.has("dc_candidate")) {
    const v = p.get("dc_candidate");
    if (v === "1" || v === "true") filterState.dcCandidate = true;
  }
  if (p.has("oz")) {
    const v = p.get("oz");
    if (v === "1" || v === "true") filterState.oppZone = true;
  }
  if (p.has("iso_rto")) {
    const v = p.get("iso_rto") || "";
    if (v) filterState.isoRto = v;
  }
  if (p.has("available")) {
    const v = p.get("available");
    if (v === "1" || v === "true") filterState.availableOnly = true;
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
    if (filterState.dcTier) p.set("dc_tier", filterState.dcTier);
    if (filterState.dcCandidate) p.set("dc_candidate", "1");
    if (filterState.oppZone) p.set("oz", "1");
    if (filterState.isoRto) p.set("iso_rto", filterState.isoRto);
    if (filterState.availableOnly) p.set("available", "1");
    const finding=el("evidence-status-filter")?.value, confidence=el("evidence-confidence-filter")?.value;
    if(finding || confidence) {
      p.set("evidence",el("evidence-category-filter").value);
      if(finding) p.set("finding",finding);
      if(confidence) p.set("confidence",confidence);
    }
    // Candidates-view lens — only encoded off-default ("dc").
    if (candidatesState.lens !== "dc") p.set("lens", candidatesState.lens);
    if (maritimeState.lens !== "offshore") p.set("mlens", maritimeState.lens);
    if (nickelState.lens !== "import") p.set("nlens", nickelState.lens);
    if (nickelState.landBasis !== "confirmed") p.set("land", nickelState.landBasis);
    // DOE-sites tab: active site — only encoded off-default ("hanford").
    if (doeActiveSite !== "hanford") p.set("doe", doeActiveSite);
    if (selectedId) p.set("site", selectedId);
    const qs = p.toString();
    const hash = location.hash; // preserve active-tab hash (e.g. "#ap1000")
    const newUrl = (qs ? `${location.pathname}?${qs}` : location.pathname) + hash;
    if (newUrl !== location.pathname + location.search + location.hash) {
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
// `offConus` (set when `s._inset` is truthy) swaps the placeholder for an
// explicit "Remote — outside continental US" so AK / HI / PR / Pacific sites
// don't read as missing data.
function setMileCell(id, value, opts = {}) {
  const node = el(id);
  if (!node) return;
  if (value == null) {
    node.textContent = opts.offConus ? "Remote — outside continental US" : "Not available";
    node.classList.add("muted-cell");
  } else {
    node.textContent = fmt.miles(value);
    node.classList.remove("muted-cell");
  }
}

// Append (or remove) a "138 kV" / "230 kV" / "500 kV" voltage chip to the
// end of a setMileCell-rendered <dd>. The chip is a span sibling so
// setMileCell's subsequent textContent rewrite would clobber it — we
// always re-append after setMileCell. Voltage is descriptive, not readiness.
function setKvSuffix(id, kv) {
  const node = el(id);
  if (!node) return;
  // Remove any prior kV span — setMileCell wiped textContent above so a
  // residual span is unlikely, but be defensive in case render order
  // changes later.
  for (const old of node.querySelectorAll(".kv-chip")) old.remove();
  if (kv == null) return;
  const span = document.createElement("span");
  span.className = "kv-chip";
  span.textContent = `${Math.round(kv).toLocaleString()} kV`;
  span.title = "Reported asset voltage; connection capacity is unverified.";
  node.appendChild(document.createTextNode(" "));
  node.appendChild(span);
}

// Append "450 MW · natural gas" to the end of the power-plant distance cell.
// Same chip pattern as setKvSuffix — used for the nearest-power-plant signal
// where the MW + fuel type matter as much as the distance (e.g. "450 MW
// natural gas at 2 mi" implies behind-the-meter PPA potential, while "20 MW
// solar at 1 mi" doesn't).
function setPowerPlantSuffix(id, mw, fuel) {
  const node = el(id);
  if (!node) return;
  for (const old of node.querySelectorAll(".pp-chip")) old.remove();
  if (mw == null && !fuel) return;
  const parts = [];
  if (mw != null) parts.push(`${Math.round(mw).toLocaleString()} MW`);
  if (fuel) parts.push(String(fuel));
  const span = document.createElement("span");
  // Highlight large dispatchable generation — these are the PPA / behind-the-
  // meter candidates. >100 MW nameplate is the rough threshold where
  // utility-scale generation can host a hyperscale DC's load behind the meter.
  span.className = "pp-chip" + (mw != null && mw >= 100 ? " ready" : "");
  span.textContent = parts.join(" · ");
  span.title = "Nearby generation; HIFLD capacity context is not spare capacity or a supply agreement.";
  node.appendChild(document.createTextNode(" "));
  node.appendChild(span);
}

// Retired-plant row — shows distance + name + MW + fuel + year, with a
// "Ret. Plant" badge tinted amber-brown to distinguish it from the active-
// plant row above.  Hidden when no large retired plant is within 5 mi.
function setRetiredPlantCell(id, s) {
  const node = el(id);
  if (!node) return;
  const row = node.closest("tr") || node.parentElement;
  if (s.retired_plant_mi == null) {
    if (row) row.hidden = true;
    node.textContent = "";
    return;
  }
  if (row) row.hidden = false;
  // Distance
  node.textContent = fmt.miles(s.retired_plant_mi);
  // Detail chip: name · MW · fuel · year
  const parts = [];
  if (s.retired_plant_name) parts.push(s.retired_plant_name);
  if (s.retired_plant_mw != null) parts.push(`${Math.round(s.retired_plant_mw).toLocaleString()} MW`);
  if (s.retired_plant_fuel) parts.push(s.retired_plant_fuel);
  if (s.retired_plant_year) parts.push(`ret. ${s.retired_plant_year}`);
  if (parts.length) {
    const span = document.createElement("span");
    span.className = "pp-chip sig-plant";
    span.textContent = parts.join(" · ");
    span.title = "Nearby retired generation. Connection availability and transferable rights are unverified.";
    node.appendChild(document.createTextNode(" "));
    node.appendChild(span);
  }
}

// Planned-retirement plant cell — an OPERATING plant with an announced
// shutdown date. Follows the safe setMileCell pattern ("Not available"
// muted when out of range, never touching the shared <dl>'s hidden attr),
// then appends a "name · MW · fuel · ret. YEAR" chip when in range.
function setPlannedRetireCell(id, s) {
  const node = el(id);
  if (!node) return;
  if (s.planned_retirement_mi == null) {
    node.textContent = "Not available";
    node.classList.add("muted-cell");
    return;
  }
  node.classList.remove("muted-cell");
  node.textContent = fmt.miles(s.planned_retirement_mi);
  const parts = [];
  if (s.planned_retirement_name) parts.push(s.planned_retirement_name);
  if (s.planned_retirement_mw != null) parts.push(`${Math.round(s.planned_retirement_mw).toLocaleString()} MW`);
  if (s.planned_retirement_fuel) parts.push(s.planned_retirement_fuel);
  if (s.planned_retirement_year) parts.push(`ret. ${s.planned_retirement_year}`);
  if (parts.length) {
    const span = document.createElement("span");
    span.className = "pp-chip sig-plant";
    span.textContent = parts.join(" · ");
    span.title = "Operating plant with an announced retirement — interconnect frees on a known date; replacement-generation/co-location deals close before shutdown (Homer City pattern)";
    node.appendChild(document.createTextNode(" "));
    node.appendChild(span);
  }
}

// Nearest principal port cell (port-proximity enrichment).
//
// `_portChecked` distinguishes two different null states that otherwise
// both read as "Not available": the join hasn't loaded yet (genuinely
// unknown), vs. the join HAS run and found nothing within 75 mi (a real
// negative result — the site is checked and landlocked). Rendering both the
// same way discards the distinction `_portChecked` exists to preserve
// (Codex round 2, this PR) — same principle as `offConus` in setMileCell.
function setPortCell(id, s) {
  const node = el(id);
  if (!node) return;
  if (s.port_mi == null) {
    node.textContent = s._portChecked ? "None within 75 mi" : "Not available";
    node.classList.add("muted-cell");
    return;
  }
  node.classList.remove("muted-cell");
  node.textContent = fmt.miles(s.port_mi);
  const parts = [];
  if (s.port_name) parts.push(s.port_name);
  if (s.port_type) parts.push(s.port_type);
  if (parts.length) {
    const span = document.createElement("span");
    span.className = "pp-chip";
    span.textContent = parts.join(" · ");
    node.appendChild(document.createTextNode(" "));
    node.appendChild(span);
  }
}

// Surface-water cell (water-proximity enrichment). Three states, same
// checked-vs-unchecked distinction as setPortCell — and a mandatory caveat.
//
// `water_flow_cfs` is the mean of a gage's ANNUAL mean discharges over its
// period of record. Withdrawal permits are written against LOW flow (7Q10),
// routinely an order of magnitude lower on a flashy river. So the cell states
// what the number is rather than letting a reader take it for available
// water. This is the same disclosure discipline the AP1000 tab applies to its
// analyst-researched water adequacy.
function setWaterCell(id, s) {
  const node = el(id);
  if (!node) return;
  while (node.firstChild) node.removeChild(node.firstChild);
  if (s.water_flow_cfs == null) {
    node.textContent = s.water_evidence_status === "unsupported_region" ? "Region outside assessed coverage; supply unknown" : s._waterChecked ? "No qualifying gage in this catalog; supply unassessed" : "Not available";
    node.classList.add("muted-cell");
    return;
  }
  node.classList.remove("muted-cell");
  node.appendChild(document.createTextNode(
    `${Math.round(s.water_flow_cfs).toLocaleString()} cfs mean of annual means`));
  const chip = document.createElement("span");
  chip.className = "pp-chip";
  chip.textContent = `${s.water_gage_name || "USGS gage"} · ${fmt.miles(s.water_gage_mi)}`;
  node.appendChild(document.createTextNode(" "));
  node.appendChild(chip);
  const note = document.createElement("span");
  note.className = "dd-criteria";
  note.textContent = `Record ${s.water_gage_record_start_year || "unknown"}–${s.water_gage_record_end_year || "unknown"}; ${s.water_gage_record_years || "unknown"} annual values. Supply and rights unassessed.`;
  node.appendChild(note);
}

// Nearest curated shipyard cell (port-proximity enrichment). Same
// checked-vs-unchecked distinction as setPortCell, at the 150-mi radius.
function setShipyardCell(id, s) {
  const node = el(id);
  if (!node) return;
  if (s.shipyard_mi == null) {
    node.textContent = s._portChecked ? "None within 150 mi" : "Not available";
    node.classList.add("muted-cell");
    return;
  }
  node.classList.remove("muted-cell");
  node.textContent = fmt.miles(s.shipyard_mi);
  const CAPABILITY_LABEL = {
    heavy_module: "heavy-module fabrication",
    large_hull: "large-hull construction",
    naval_repair: "naval repair",
  };
  const parts = [];
  if (s.shipyard_name) parts.push(s.shipyard_name);
  if (s.shipyard_capability) parts.push(CAPABILITY_LABEL[s.shipyard_capability] || s.shipyard_capability);
  if (parts.length) {
    const span = document.createElement("span");
    span.className = "pp-chip" + (s.shipyard_capability === "heavy_module" ? " ready" : "");
    span.textContent = parts.join(" · ");
    span.title = "heavy_module = offshore module/topsides fabrication — the capability most relevant to floating/offshore nuclear assembly";
    node.appendChild(document.createTextNode(" "));
    node.appendChild(span);
  }
}

// Coal conversion asset cell (Spec 04)
function setCoalRepowerCell(id, s) {
  const node = el(id);
  if (!node) return;
  if (s.coal_conversion_plant_mi == null) {
    node.textContent = "Not available";
    node.classList.add("muted-cell");
    return;
  }
  node.classList.remove("muted-cell");
  node.textContent = fmt.miles(s.coal_conversion_plant_mi);
  const parts = [];
  if (s.coal_conversion_plant_name) parts.push(s.coal_conversion_plant_name);
  if (s.coal_conversion_mw != null) parts.push(`${Math.round(s.coal_conversion_mw).toLocaleString()} MW coal`);
  if (s.coal_conversion_switchyard_kv != null) parts.push(`${s.coal_conversion_switchyard_kv} kV`);
  if (s.coal_conversion_stranded_val_usd != null) {
    const valM = (s.coal_conversion_stranded_val_usd / 1_000_000).toFixed(1);
    parts.push(`~$${valM}M modeled`);
  }
  if (s.coal_conversion_queue_fasttrack) parts.push("Nearby plant; connection unverified");
  if (parts.length) {
    const span = document.createElement("button");
    span.type = "button";
    span.className = "pp-chip sig-plant coal-clickable-chip";
    span.textContent = parts.join(" · ") + " →";
    span.title = "Click to explore this coal plant in the Coal Reinvestment tab (DOE/EIA data, stranded asset breakdown, nearby brownfield parcels)";
    span.addEventListener("click", (e) => {
      e.stopPropagation();
      if (s.coal_conversion_plant_name && window.__openCoalTabForPlant) {
        window.__openCoalTabForPlant(s.coal_conversion_plant_name);
      }
    });
    node.appendChild(document.createTextNode(" "));
    node.appendChild(span);
  }
}

function setTextCell(id, value, emptyText = "Not available") {
  const node = el(id);
  if (!node) return;
  if (value == null || value === "") {
    node.textContent = emptyText;
    node.classList.add("muted-cell");
  } else {
    node.textContent = String(value);
    node.classList.remove("muted-cell");
  }
}

// Render the Opportunity Zone cell. Three states:
//   - `in_opportunity_zone === true`: green "Yes" (or "Yes — Rural OZ") with
//     a deep-link to the HUD OZ tract page so users can pivot to canonical.
//   - `in_opportunity_zone === false`: muted "Outside any OZ".
//   - undefined: fall back to the legacy EPA RE-Powering string field for
//     Superfund sites (`in_opp_zone === "Yes"` or similar), or show "Not
//     available" if neither source has data.
function setOpportunityZoneCell(id, s) {
  const node = el(id);
  if (!node) return;
  const universal = s.in_opportunity_zone;
  if (universal === true) {
    const rural = s.oz_rural === true;
    const label = rural ? "Yes — Rural OZ" : "Yes";
    if (s.oz_tract_geoid) {
      // HUD's interactive OZ map deep-links by tract GEOID.
      const url = `https://opportunityzones.hud.gov/resources/map`;
      node.innerHTML = `<a href="${escapeAttr(url)}" target="_blank" rel="noopener" title="${escapeAttr(`Treasury-designated QOZ · Census tract ${s.oz_tract_geoid}${rural ? " · Rural OZ" : ""}`)}">${escapeHtml(label)} (tract ${s.oz_tract_geoid.slice(-6)})</a>`;
    } else {
      node.textContent = label;
    }
    node.classList.remove("muted-cell");
    node.classList.add("ready");
    return;
  }
  if (universal === false) {
    node.textContent = "Outside any OZ";
    node.classList.remove("ready", "muted-cell");
    return;
  }
  // Legacy fallback for Superfund sites enriched by the EPA RE-Powering layer.
  if (typeof s.in_opp_zone === "string" && s.in_opp_zone.trim()) {
    const legacy = s.in_opp_zone.trim();
    node.textContent = /^yes/i.test(legacy)
      ? "Yes (EPA RE-Powering)"
      : `${legacy} (EPA RE-Powering)`;
    node.classList.remove("muted-cell");
    if (/^yes/i.test(legacy)) node.classList.add("ready");
    return;
  }
  node.textContent = "Not available";
  node.classList.add("muted-cell");
  node.classList.remove("ready");
}

// Render the EPA SWRAU "Land readiness" cell. Four states:
//   - "Meets the Measure" (incl. "Formerly Retracted"): green affirmative.
//   - "Does Not Meet the Measure": plain text (not ready, not an error).
//   - "(Retracted)" variant: plain text with the retraction noted.
//   - null / unknown: muted "Not available" (only Superfund redev sites have it).
function setRauStatusCell(id, s) {
  const node = el(id);
  if (!node) return;
  const raw = typeof s.rau_status === "string" ? s.rau_status.trim() : "";
  if (!raw) {
    node.textContent = "Not available";
    node.classList.add("muted-cell");
    node.classList.remove("ready");
    return;
  }
  node.classList.remove("muted-cell");
  if (_meetsRau(raw)) {
    node.textContent = "All land ready (SWRAU)";
    node.title = "EPA Sitewide Ready for Anticipated Use: all of this site's land is ready for its anticipated use" + (/Formerly Retracted/i.test(raw) ? " (formerly retracted)" : "");
    node.classList.add("ready");
  } else {
    node.textContent = /Retracted/i.test(raw) ? "Not ready (determination retracted)" : "Not all land ready";
    node.title = "EPA Sitewide Ready for Anticipated Use: " + raw;
    node.classList.remove("ready");
  }
}

// Render the IRA energy community cell. Three states:
//   - `in_energy_community === true`: green label with the category + the
//     human-readable reason (coal mine/generator closure, adjacency, or the
//     fossil-fuel-employment statistical-area name) and a deep-link to the
//     DOE energy-communities map. The +10pp ITC/PTC bonus is the headline.
//   - `in_energy_community === false`: muted "Not an energy community".
//   - undefined: muted "Not available" (enrichment not loaded yet).
function setEnergyCommunityCell(id, s) {
  const node = el(id);
  if (!node) return;
  const v = s.in_energy_community;
  if (v === true) {
    const type = s.energy_community_type;
    const typeLabel = type === "coal_closure" ? "Coal closure"
      : type === "fossil_fuel_employment" ? "Fossil-fuel employment"
      : "Energy community";
    const detail = s.energy_community_detail ? ` — ${s.energy_community_detail}` : "";
    const url = "https://energycommunities.gov/energy-community-tax-credit-bonus/";
    const title = `IRA energy community (${typeLabel}${detail}) — clean-energy projects here earn a +10 percentage-point ITC/PTC bonus under IRA §45/48`;
    node.innerHTML = `<a href="${escapeAttr(url)}" target="_blank" rel="noopener" title="${escapeAttr(title)}">Yes · ${escapeHtml(typeLabel)}${escapeHtml(detail)}</a>`;
    node.classList.remove("muted-cell");
    node.classList.add("ready");
    return;
  }
  if (v === false) {
    node.textContent = "Not an energy community";
    node.classList.remove("ready", "muted-cell");
    return;
  }
  node.textContent = "Not available";
  node.classList.add("muted-cell");
  node.classList.remove("ready");
}

// FEMA NRI risk rating → red/amber/green tinting. The composite rating is
// the headline; wildfire / drought / heat-wave append as a per-hazard line
// when any reaches a notable tier. "Very High" / "Relatively High" are the
// risk tiers; everything else (incl. "Insufficient Data") renders neutral.
const _NRI_RISK_CLASS = {
  "Very High": "violation",
  "Relatively High": "violation",
};
function setNriCell(id, s) {
  const node = el(id);
  if (!node) return;
  const rating = s.nri_risk_rating;
  if (!rating) {
    node.textContent = "Not available";
    node.classList.add("muted-cell");
    node.classList.remove("violation", "ready");
    return;
  }
  // Per-hazard suffix for the DC-relevant hazards when elevated.
  const hz = [];
  if (s.nri_wildfire_rating) hz.push(`wildfire ${s.nri_wildfire_rating}`);
  if (s.nri_drought_rating) hz.push(`drought ${s.nri_drought_rating}`);
  if (s.nri_heatwave_rating) hz.push(`heat ${s.nri_heatwave_rating}`);
  const score = s.nri_risk_score != null ? ` (${s.nri_risk_score})` : "";
  const suffix = hz.length ? ` — ${hz.join(", ")}` : "";
  node.textContent = `${rating}${score}${suffix}`;
  node.title = `FEMA National Risk Index composite${score} for the county. `
    + `County context only; a site-specific hazard assessment is still needed.`;
  node.classList.remove("muted-cell", "violation", "ready");
  const cls = _NRI_RISK_CLASS[rating];
  if (cls) node.classList.add(cls);
  else if (rating === "Very Low" || rating === "Relatively Low") node.classList.add("ready");
}

// FEMA flood-zone codes the dashboard can encounter. The map keeps the
// labels short for the detail panel; the title attribute carries the full
// description so users can hover for context.
const FLOOD_ZONE_LABELS = {
  A: { short: "Zone A · 100-yr floodplain", title: "1% annual chance of flooding — no Base Flood Elevation determined" },
  AE: { short: "Zone AE · 100-yr w/ BFE", title: "1% annual chance of flooding — Base Flood Elevation determined" },
  AH: { short: "Zone AH · 100-yr ponding", title: "1% annual chance of shallow ponding (1-3 ft)" },
  AO: { short: "Zone AO · 100-yr sheet flow", title: "1% annual chance of sheet flow flooding (1-3 ft)" },
  V: { short: "Zone V · coastal high-hazard", title: "Coastal 1% annual chance with velocity hazard (wave action)" },
  VE: { short: "Zone VE · coastal w/ BFE", title: "Coastal 1% annual chance with velocity hazard — BFE determined" },
  X: { short: "Zone X · minimal hazard", title: "Outside 1% and 0.2% annual chance floodplains" },
  D: { short: "Zone D · undetermined", title: "Possible but undetermined flood hazards" },
};

// Render the flood-zone cell. Critical permitting signal: a site in an SFHA
// effectively can't be permitted as critical infrastructure (data center,
// energy plant) without expensive elevation / flood-proofing work — so SFHA
// gets a red "violation"-style tint to read at a glance.
function setFloodZoneCell(id, zone, inSfha) {
  const node = el(id);
  if (!node) return;
  if (zone == null) {
    node.textContent = "Not available";
    node.classList.add("muted-cell");
    node.classList.remove("violation", "ready");
    node.title = "";
    return;
  }
  const info = FLOOD_ZONE_LABELS[zone] || { short: `Zone ${zone}`, title: "" };
  node.textContent = info.short;
  node.classList.remove("muted-cell");
  // Red for SFHA (permitting risk); green for Zone X (minimal hazard).
  node.classList.toggle("violation", inSfha === true);
  node.classList.toggle("ready", inSfha === false && (zone === "X" || zone === "X500"));
  node.title = info.title + (inSfha === true
    ? " — Special Flood Hazard Area (SFHA)"
    : inSfha === false
    ? " — outside SFHA"
    : "");
}

// ----- Siting suitability block -----
// Shared evidence categories in the detail drawer.
function renderSuitability(s) {
  const node=el("d-suit-dc"); if(node) node.innerHTML=evidenceDetails(s, el("view-micro")?.classList.contains("active") ? "micro" : el("view-nickel")?.classList.contains("active") ? "nickel" : "dc");
  for(const id of ["d-suit-gen","d-suit-nickel-import","d-suit-nickel-domestic","d-suit-nickel-land"]) {const n=el(id);if(n){n.replaceChildren();n.hidden=true;}}
}

// Render the State DC tax incentive chip in the detail panel. Looks up
// `STATE_DC_INCENTIVES[s.state]` and surfaces tier + program name + status
// note. Hidden when the state is unknown (territories, missing data).
function renderStateIncentive(s) {
  const node = el("d-tax-incentive");
  if (!node) return;
  const inc = s && s.state ? STATE_DC_INCENTIVES[s.state] : null;
  if (!inc) {
    node.hidden = true;
    return;
  }
  node.hidden = false;
  const tierClass = inc.tier === 1 ? "tax-tier-1"
    : inc.tier === 2 ? "tax-tier-2"
    : "tax-tier-3";
  const stateName = STATE_NAMES[s.state] || s.state;
  const tierText = TAX_TIER_LABEL[inc.tier] || "—";
  const note = TAX_STATUS_NOTE[inc.status] || "";
  // Build chip + meta line. Anchor the chip to the source URL so users can
  // verify the program details upstream.
  const chipHtml = `<a class="tax-chip ${tierClass}" href="${escapeAttr(inc.url || "#")}" target="_blank" rel="noopener" title="${escapeAttr(tierText + note)}">${escapeHtml(stateName)} · Tier ${inc.tier}</a>`;
  let metaText;
  if (inc.tier === 3) {
    // Prefer a row-specific program string when set (post-2026-05-08 rows
    // for CA / NJ / NM / DC carry a "None enacted (…)" explanation that's
    // more informative than the status-derived fallback). Status-specific
    // copy still overrides for the no-sales-tax + repeal + pending cases.
    metaText = inc.status === "no_state_sales_tax"
      ? "No state sales tax — neutral"
      : inc.status === "partially_repealed"
      ? "Electricity sales-tax exemption repealed (2025)"
      : inc.status === "pending_legislation"
      ? "DC tax incentive bill pending in legislature"
      : inc.program
      ? inc.program
      : inc.status === "restrictive"
      ? "Restrictive policy or active anti-DC sentiment"
      : "No dedicated data-center tax incentive";
  } else if (inc.program) {
    const parts = [inc.program];
    if (inc.min_investment_usd) {
      parts.push(`min $${(inc.min_investment_usd / 1_000_000).toLocaleString()}M`);
    }
    if (inc.sunset) parts.push(`sunset ${inc.sunset}`);
    if (inc.status && inc.status !== "active") {
      const noteTrim = (TAX_STATUS_NOTE[inc.status] || "").replace(/^\s*·\s*/, "");
      if (noteTrim) parts.push(noteTrim);
    }
    metaText = parts.join(" · ");
  } else {
    metaText = "—";
  }
  node.innerHTML = `${chipHtml}<p class="tax-meta muted-cell">${escapeHtml(metaText)}</p>`;
}
