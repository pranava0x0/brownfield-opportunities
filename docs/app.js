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
const CLIMATE_ZONE_URL = "data/climate-zone.json";
const ISO_RTO_URL = "data/iso-rto.json";
const ECHO_DATA_URL = "data/epa-echo.json";
const PARCEL_OWNER_URL = "data/parcel-owner.json";
const AI_SUMMARY_URL = "data/ai-summary.json";
const ACRES_CLEANUP_URL = "data/acres-cleanup.json";
const RETIRED_PLANTS_URL = "data/eia-retired-plants.json";
const REFERENCE_CAMPUSES_URL = "data/reference-campuses.json";
const RETIRED_INDUSTRIAL_URL = "data/retired-industrial.json";
const IRA_EC_URL = "data/ira-energy-community.json";
const AP1000_SITES_URL = "data/ap1000-sites.json";
const FEMA_NRI_URL = "data/fema-nri.json";
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
  { id: "mega",       label: "AI mega (500 MW+)", minAcres: 500, maxTxMi: 1.0, minKv: 500, color: "var(--readiness-ready)" },
  { id: "hyperscale", label: "Hyperscale (100 MW+)", minAcres: 100, maxTxMi: 1.0, minKv: 230, color: "var(--readiness-ready)" },
  { id: "colo",       label: "Colocation (general)", minAcres: 25, maxTxMi: 1.0, minKv: 138, color: "var(--accent)" },
  { id: "edge",       label: "Edge / inference", minAcres: 5, maxTxMi: 1.0, minKv: 0, color: "var(--accent)" },
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
  AZ: { tier: 1, program: "Computer Data Center Program (A.R.S. § 41-1519)", min_investment_usd: 25_000_000, min_jobs: null, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://www.azleg.gov/ars/41/01519.htm" },
  NV: { tier: 1, program: "Data Center Abatement (10yr / 20yr tiers, NRS § 360.754)", min_investment_usd: 25_000_000, min_jobs: 10, sunset: 2056, status: "active", verified_at: "2026-05-08", url: "https://law.justia.com/codes/nevada/chapter-360/statute-360-754/" },
  NC: { tier: 1, program: "Qualifying Data Center Sales Tax Exemption", min_investment_usd: 75_000_000, min_jobs: null, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://edpnc.com/incentives/data-centers-sales-use-tax-exemptions/" },
  TN: { tier: 1, program: "Qualified Data Center Sales Tax Exemption (Tenn. Code § 67-6-206(c))", min_investment_usd: 100_000_000, min_jobs: 15, sunset: null, status: "active", verified_at: "2026-05-08", url: "https://www.tn.gov/content/dam/tn/revenue/documents/forms/sales/f1325001.pdf" },

  // Tier 2 — moderate
  IL: { tier: 2, program: "Data Center Investment Program (20yr cert + 5yr renewals)", min_investment_usd: 250_000_000, min_jobs: 20, sunset: 2056, status: "active", verified_at: "2026-05-08", url: "https://dceo.illinois.gov/expandrelocate/incentives/datacenters.html" },
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
  VA: { climate: "restrictive", note: "Loudoun County repealed by-right data-center zoning (Mar 2025); all new projects require public hearings, and the state is debating sunsetting the DC tax exemption.", verified_at: "2026-06-19", url: "https://www.multistate.us/resources/state-data-center-policy-101" },
  OK: { climate: "restrictive", note: "SB 1488 (moratorium on new data-center construction to Nov 2029) advancing; HB 2992 imposes data-center cost-allocation / ratepayer-protection rules.", verified_at: "2026-06-19", url: "https://goodjobsfirst.org/data-center-moratorium-bills-are-spreading-in-2026/" },
  VT: { climate: "cautionary", note: "S.205 would pause data-center facilities above 10 MW until July 2030 (advancing, not enacted).", verified_at: "2026-06-19", url: "https://goodjobsfirst.org/data-center-moratorium-bills-are-spreading-in-2026/" },
  FL: { climate: "cautionary", note: "SB 484 bars utilities from passing data-center costs onto residential / small-business ratepayers — a cost-allocation friction (state is otherwise pro-DC).", verified_at: "2026-06-19", url: "https://www.multistate.us/resources/state-data-center-policy-101" },
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
  none: "",
  no_state_sales_tax: " · no state sales tax (neutral)",
};

// ----- State -----
let sites = [];
let map, markerLayer, referenceCampusLayer, retiredIndustrialLayer;
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
let climateZoneLoadingPromise = null;
let isoRtoLoadingPromise = null;
let echoLoadingPromise = null;
let parcelOwnerLoadingPromise = null;
let summariesLoadingPromise = null;
let acresCleanupLoadingPromise = null;
let retiredPlantsLoadingPromise = null;
let referenceCampusesLoadingPromise = null;
let retiredIndustrialLoadingPromise = null;
let retiredIndustrialSites = []; // raw payload, for the Retired Sites stats tab
let ap1000LoadingPromise = null;
let ap1000Sites = []; // raw payload, for the AP1000 siting tab
let iraEcLoadingPromise = null;
let femaNriLoadingPromise = null;

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
function recordRefreshDate(generatedAt) {
  if (!generatedAt) return;
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
  let hyperCount = 0;
  let genCount = 0;
  const programSet = new Set();
  for (const s of sites) {
    if (typeof s.acreage === "number") {
      acreSum += s.acreage;
      acreCount++;
    }
    if (s.data_center_reuse_candidate === true) dcCount++;
    const tier = computeDcScore(s);
    if (tier === "hyperscale" || tier === "mega") hyperCount++;
    const genScore = computeGenerationScore(s);
    if (genScore != null && genScore >= 75) genCount++;
    if (s.program) programSet.add(s.program);
  }
  const set = (id, value) => {
    const node = el(id);
    if (node) node.textContent = value;
  };
  // Also set `title` on every KPI subtext so the unclipped string is
  // available on hover — `text-overflow: ellipsis` truncates these on
  // narrow desktop columns (e.g. "4.9K sites with rep…"). The static
  // strings in HTML (DC/hyperscale criteria, states subtext) get their
  // title applied at init via setKpiSubTitles().
  const setSub = (id, value) => {
    const node = el(id);
    if (!node) return;
    node.textContent = value;
    node.title = value;
  };
  set("kpi-total", fmt.compact(total));
  setSub("kpi-total-sub", `across ${programSet.size} program${programSet.size === 1 ? "" : "s"}`);
  set("kpi-acres", fmt.compact(acreSum));
  setSub("kpi-acres-sub", `${fmt.compact(acreCount)} sites with reported area`);
  set("kpi-dc", fmt.compact(dcCount));
  set("kpi-hyperscale", fmt.compact(hyperCount));
  set("kpi-generation", fmt.compact(genCount));
  // Mobile disclosure strip — the two highest-signal numbers (total +
  // DC candidates) live in the always-visible summary line; expanding the
  // <details> reveals the full carousel.
  set("kpi-summary-total", fmt.compact(total));
  set("kpi-summary-dc", fmt.compact(dcCount));
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
    active.push("Available sites only");
  }
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
    recordRefreshDate(payload.generated_at);
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
    wireCandidatesFilters();
    wireDetailPanel();
    wireSearch();
    wireFilters();
    wirePersonaButtons();
    wireKpiClicks();
    wireNearbyClicks();
    wireExportCsv();
    wireAp1000ExportCsv();
    wireShareLink();
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
    lazyLoads.push(ensureOppZoneLoaded());
    lazyLoads.push(ensureIraEnergyCommunityLoaded());
    lazyLoads.push(ensureFemaNriLoaded());
    lazyLoads.push(ensureClimateZoneLoaded());
    lazyLoads.push(ensureIsoRtoLoaded());
    lazyLoads.push(ensureEchoLoaded());
    lazyLoads.push(ensureParcelOwnerLoaded());
    lazyLoads.push(ensureSummariesLoaded());
    lazyLoads.push(ensureAcresCleanupLoaded());
    lazyLoads.push(ensureRetiredPlantsLoaded());
    lazyLoads.push(ensureReferenceCampusesLoaded());
    lazyLoads.push(ensureRetiredIndustrialLoaded());
    applyUrlSelection();
    if (lazyLoads.length === 0) {
      markAppReady();
      maybeRefreshCandidates();
    } else {
      Promise.allSettled(lazyLoads).then(() => { markAppReady(); maybeRefreshCandidates(); });
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
      recordRefreshDate(payload.generated_at);
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
  if (loadedPrograms.has("fuds")) return Promise.resolve();
  fudsLoadingPromise = fetch(FUDS_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at);
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
  if (loadedPrograms.has("brac")) return Promise.resolve();
  bracLoadingPromise = fetch(BRAC_DATA_URL)
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at);
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
  redevLoadingPromise = fetch(REDEV_DATA_URL, { priority: "low" })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((payload) => {
      recordRefreshDate(payload.generated_at);
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
      recordRefreshDate(payload.generated_at);
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
      recordRefreshDate(payload.generated_at);
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
    .then((payload) => {
      recordRefreshDate(payload.generated_at);
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing || !rec.current_owner) continue;
        if (existing.current_owner) continue; // don't overwrite a source-provided owner
        existing.current_owner = rec.current_owner;
        existing.current_owner_source = rec.current_owner_source || "Public parcel records";
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
      recordRefreshDate(payload.generated_at);
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
    .then((payload) => {
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
    .then((payload) => {
      recordRefreshDate(payload.generated_at);
      for (const rec of payload.sites || []) {
        const existing = sitesById.get(rec.id);
        if (!existing) continue;
        const patch = {};
        if (rec.transmission_mi != null) patch.transmission_mi = rec.transmission_mi;
        if (rec.transmission_kv != null) patch.transmission_kv = rec.transmission_kv;
        if (rec.rail_mi != null) patch.rail_mi = rec.rail_mi;
        if (rec.highway_mi != null) patch.highway_mi = rec.highway_mi;
        if (rec.gas_pipeline_mi != null) patch.gas_pipeline_mi = rec.gas_pipeline_mi;
        if (rec.substation_mi != null) patch.substation_mi = rec.substation_mi;
        if (rec.substation_kv != null) patch.substation_kv = rec.substation_kv;
        if (rec.power_plant_mi != null) patch.power_plant_mi = rec.power_plant_mi;
        if (rec.power_plant_mw != null) patch.power_plant_mw = rec.power_plant_mw;
        if (rec.power_plant_fuel != null) patch.power_plant_fuel = rec.power_plant_fuel;
        if (rec.flood_zone != null) patch.flood_zone = rec.flood_zone;
        if (rec.in_sfha != null) patch.in_sfha = rec.in_sfha;
        Object.assign(existing, patch);
      }
      // Re-run KPI deck (hyperscale-ready count depends on transmission_kv)
      // and re-render an open detail panel so the new pill / chip lights up
      // without requiring the user to reselect the site.
      updateKpiDeck();
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
    .then((payload) => {
      recordRefreshDate(payload.generated_at);
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
    .then((payload) => {
      recordRefreshDate(payload.generated_at);
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
    .then((payload) => {
      recordRefreshDate(payload.generated_at);
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
    .then((payload) => {
      recordRefreshDate(payload.generated_at);
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
    .then((payload) => {
      recordRefreshDate(payload.generated_at);
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
    .then((payload) => {
      recordRefreshDate(payload.generated_at);
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
      recordRefreshDate(payload.generated_at); // this can be the freshest artifact in a GHGRP refresh
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
        marker.bindPopup(
          `<div class="ref-campus-popup">` +
          `<strong>${escapeHtml(s.name)}</strong>` +
          `<div class="ref-campus-company">${escapeHtml(s.sector)}</div>` +
          (place ? `<div class="ref-campus-prev">${escapeHtml(place)}</div>` : "") +
          `<div class="ref-campus-meta">` +
            (s.last_report_year ? `<span>Last reported ${escapeHtml(String(s.last_report_year))}</span>` : "") +
            (s.parent_company ? `<span>${escapeHtml(s.parent_company)}</span>` : "") +
          `</div>` +
          `<div class="ref-campus-prev" style="margin-top:6px">Screening signal — ${escapeHtml(reason)}. A former large-load facility may retain reusable grid infrastructure worth diligence; not a confirmed-available or still-connected site.</div>` +
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

  fitUsBoundsSafely();

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
  if (mapEl && mapEl.getBoundingClientRect().width > 0 && tryFit()) return;
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
    div.innerHTML =
      `<div class="legend-title"><span>Program</span></div>${rows}${refRow}${retRow}` +
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

// Tier ordering for the dcTier filter — higher rank = stricter tier.
// "any matched tier ≥ rank(filterState.dcTier)" is the inclusion test, so
// picking "colo" includes colo + hyperscale + mega; "hyperscale" includes
// hyperscale + mega; "mega" is the strictest.
const DC_TIER_RANK = { edge: 1, colo: 2, hyperscale: 3, mega: 4 };

function siteMatchesFilters(s, opts = {}) {
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
  // The candidates view sources from tableState.filtered — rebuild it when
  // it's the active tab so global filter changes apply live there too.
  maybeRefreshCandidates();
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

// Open the KPI disclosure by default on desktop so the carousel renders as
// a static panel. On phones we leave it closed (the slim summary strip is
// the always-visible signal). A matchMedia listener keeps the state in
// sync when the user resizes or rotates a tablet.
function wireKpiDisclosure() {
  const disc = el("kpi-disclosure");
  if (!disc) return;
  const mq = window.matchMedia("(max-width: 640px)");
  const sync = (mobileMode) => {
    // Don't fight the user — only auto-toggle if the user hasn't manually
    // interacted in this session. After first toggle the mode flips and we
    // respect the user's choice.
    if (disc.dataset.userToggled === "true") return;
    disc.open = !mobileMode;
  };
  sync(mq.matches);
  // Modern browsers: addEventListener; Safari <14 fallback: addListener.
  if (mq.addEventListener) mq.addEventListener("change", (ev) => sync(ev.matches));
  else if (mq.addListener) mq.addListener((ev) => sync(ev.matches));
  disc.addEventListener("toggle", () => {
    disc.dataset.userToggled = "true";
  });
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
  const deck = el("kpi-deck");
  if (!deck) return;
  const ACTIONABLE = { hyperscale: "tier", dc: "candidate" };
  for (const cell of deck.querySelectorAll("[data-kpi]")) {
    const kpi = cell.dataset.kpi;
    if (!ACTIONABLE[kpi]) continue;
    cell.classList.add("kpi-actionable");
    cell.setAttribute("role", "button");
    cell.setAttribute("tabindex", "0");
    const labelText = cell.querySelector(".kpi-label")?.textContent?.trim();
    cell.setAttribute("aria-label", labelText
      ? `Filter to ${labelText}`
      : `Toggle ${kpi} filter`);
    const handler = () => toggleKpiFilter(kpi);
    cell.addEventListener("click", handler);
    cell.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handler();
      }
    });
  }
  refreshKpiActiveStates();
}

function toggleKpiFilter(kpi) {
  if (kpi === "hyperscale") {
    filterState.dcTier = filterState.dcTier === "hyperscale" ? "" : "hyperscale";
    refreshPersonaButtons();
  } else if (kpi === "dc") {
    filterState.dcCandidate = !filterState.dcCandidate;
  } else {
    return;
  }
  refreshKpiActiveStates();
  applyFilter();
  refitMapToFilters();
}

function refreshKpiActiveStates() {
  const deck = el("kpi-deck");
  if (!deck) return;
  for (const cell of deck.querySelectorAll("[data-kpi]")) {
    let active = false;
    if (cell.dataset.kpi === "hyperscale") active = filterState.dcTier === "hyperscale";
    else if (cell.dataset.kpi === "dc") active = filterState.dcCandidate;
    cell.classList.toggle("kpi-active", active);
    cell.setAttribute("aria-pressed", String(active));
  }
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
  let statusHtml;
  if (s.npl_status_code) {
    statusHtml = `<span class="pill" data-status="${escapeAttr(s.npl_status_code)}">${escapeHtml(s.npl_status || "Unknown")}</span>`;
  } else if (s.program === "fuds" && s.eligibility) {
    statusHtml = escapeHtml(s.eligibility);
  } else if (s.program === "brownfield" && s.cleanup_status) {
    const cls = s.cleanup_status === "Completed" ? " ready" : "";
    statusHtml = `<span class="cleanup-status${cls}">${escapeHtml(s.cleanup_status)}</span>`;
  } else {
    statusHtml = '<span class="muted-cell">—</span>';
  }
  const dcScore = computeDcCompositeScore(s);
  const dcScoreHtml = dcScore == null
    ? '<span class="muted-cell">—</span>'
    : String(dcScore);
  tr.innerHTML = `
    <td>${escapeHtml(s.name || "—")}</td>
    <td><span class="pill" data-program="${escapeAttr(s.program)}">${escapeHtml(programLabel)}</span></td>
    <td>${escapeHtml(s.state || "—")}</td>
    <td class="num">${fmt.acres(s.acreage)}</td>
    <td>${statusHtml}</td>
    <td>${escapeHtml(s.city || "—")}</td>
    <td>${escapeHtml(s.county || "—")}</td>
    <td class="num">${dcScoreHtml}</td>
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
      if (!entries.some((e) => e.isIntersecting)) return;
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
  if (key === "dc_score") {
    return (a, b) => {
      const av = computeDcCompositeScore(a);
      const bv = computeDcCompositeScore(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return (av - bv) * mul;
    };
  }
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

// Single source of truth for the DC-score column tooltip lives in
// dc-score.js so the formula text doesn't drift between the score
// implementation and the user-facing explanation.
const _dcScoreTh = document.getElementById("th-dc-score");
if (_dcScoreTh && typeof DC_SCORE_TOOLTIP === "string") {
  _dcScoreTh.setAttribute("title", DC_SCORE_TOOLTIP);
  _dcScoreTh.setAttribute("aria-label", `DC score. ${DC_SCORE_TOOLTIP}`);
}

// ----- Tabs -----
function wireTabs() {
  const mapTab = el("tab-map");
  const tableTab = el("tab-table");
  const candidatesTab = el("tab-candidates");
  const retiredTab = el("tab-retired");
  const ap1000Tab = el("tab-ap1000");
  const aboutTab = el("tab-about");
  const setView = (which) => {
    const onMap = which === "map";
    const onTable = which === "table";
    const onCandidates = which === "candidates";
    const onRetired = which === "retired";
    const onAp1000 = which === "ap1000";
    const onAbout = which === "about";
    for (const [tab, active] of [
      [mapTab, onMap], [tableTab, onTable],
      [candidatesTab, onCandidates], [retiredTab, onRetired],
      [ap1000Tab, onAp1000], [aboutTab, onAbout],
    ]) {
      if (!tab) continue;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    }
    const mapView = el("view-map");
    const tableView = el("view-table");
    const candidatesView = el("view-candidates");
    const retiredView = el("view-retired");
    const ap1000View = el("view-ap1000");
    const aboutView = el("view-about");
    if (mapView)        { mapView.classList.toggle("active", onMap);               mapView.hidden = !onMap; }
    if (tableView)      { tableView.classList.toggle("active", onTable);           tableView.hidden = !onTable; }
    if (candidatesView) { candidatesView.classList.toggle("active", onCandidates); candidatesView.hidden = !onCandidates; }
    if (retiredView)    { retiredView.classList.toggle("active", onRetired);       retiredView.hidden = !onRetired; }
    if (ap1000View)     { ap1000View.classList.toggle("active", onAp1000);         ap1000View.hidden = !onAp1000; }
    if (aboutView)      { aboutView.classList.toggle("active", onAbout);           aboutView.hidden = !onAbout; }
    const globalExportCsv = el("export-csv");
    if (globalExportCsv) globalExportCsv.hidden = onAp1000;
    if (onMap) setTimeout(() => map.invalidateSize(), 50);
    if (onCandidates) buildCandidatesView();
    if (onRetired) { ensureRetiredIndustrialLoaded(); buildRetiredView(); }
    if (onAp1000) { ensureAp1000Loaded(); buildAp1000View(); }
    if (onAbout) {
      const d = el("about-refresh-date");
      if (d && window.__refreshedAt) d.textContent = window.__refreshedAt;
    }
    // Update URL hash so the active tab can be bookmarked / shared.
    // Map is the default; omit its hash to keep URLs clean.
    const newHash = which === "map" ? "" : "#" + which;
    history.replaceState(null, "", location.pathname + location.search + newHash);
  };
  mapTab.addEventListener("click", () => setView("map"));
  tableTab.addEventListener("click", () => setView("table"));
  if (candidatesTab) candidatesTab.addEventListener("click", () => setView("candidates"));
  if (retiredTab) retiredTab.addEventListener("click", () => setView("retired"));
  if (ap1000Tab) ap1000Tab.addEventListener("click", () => setView("ap1000"));
  if (aboutTab) aboutTab.addEventListener("click", () => setView("about"));

  // Honor hash on initial load (e.g. shared URL with #ap1000).
  const VALID_TABS = new Set(["map", "table", "candidates", "retired", "ap1000", "about"]);
  const initialHash = location.hash.replace(/^#/, "").toLowerCase();
  if (VALID_TABS.has(initialHash)) setView(initialHash);

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
    + `<p class="retired-foot muted">Source: EPA GHGRP facilities that ceased reporting (closed, idled, or below threshold). This is a screening signal for reusable grid infrastructure — verify ownership, interconnection, and closure before treating any site as available. Use the rust ◆ markers on the Map to locate them.</p>`;
}

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

function _ap1000ScoreTier(score) {
  if (score == null) return { label: "—", cls: "weak" };
  if (score >= 75) return { label: "Strong", cls: "strong" };
  if (score >= 60) return { label: "Moderate", cls: "moderate" };
  if (score >= 45) return { label: "Marginal", cls: "marginal" };
  return { label: "Weak", cls: "weak" };
}

const _ap1000Src = (url, label) =>
  url ? ` <a href="${escapeHtml(url)}" target="_blank" rel="noopener">${label} ↗</a>` : "";
const _AP1000_SCORE_SOURCE = "https://github.com/pranava0x0/brownfield-opportunities/blob/main/docs/ap1000-score.js";
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
  if (field === "fiber") return s.fiber_source_url || s.acreage_source || "";
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
  if (!ap1000Sites.length) {
    host.innerHTML = '<p class="muted">Loading AP1000 siting data…</p>';
    return;
  }
  const W = window.AP1000_WEIGHTS || {};
  const scored = ap1000ScoredRows();

  const rows = scored.map((row, i) => {
    const { s, score, bd } = row;
    const tier = _ap1000ScoreTier(score);
    const rank = i + 1;

    const waterCls = AP1000_WATER_CLASS[(s.water_adequacy || "").toLowerCase()] || "warn";
    const fiberCls = AP1000_FIBER_CLASS[(s.fiber || "").toLowerCase()] || "warn";
    const wfCls = AP1000_WORKFORCE_CLASS[(s.workforce || "").toLowerCase()] || "warn";

    const janus = s.janus_site
      ? `<span class="ap1000-janus" title="On the U.S. Army Janus microreactor shortlist (Nov 2025)">★ Janus</span>` : "";
    const afRflp = s.af_rflp_site
      ? `<span class="ap1000-rflp" title="Named in the Air Force AFCEC-26-R-0002 AI data-center lease solicitation">AF RFLP</span>` : "";

    // Unscored geohazard flags — only surface the notable ones.
    const flags = [];
    if (s.usgs_pgam != null) {
      // Quantitative USGS ASCE 7-22 seismic hazard replaces the qualitative flag.
      const pgam = s.usgs_pgam;
      const exceedsCls = pgam > 0.30 ? "bad" : pgam >= 0.15 ? "warn" : "ok";
      const exceedsTip = pgam > 0.30
        ? ` — exceeds AP1000 SSE threshold (0.30g); site-specific seismic analysis required`
        : "";
      const seismicLabel = `PGA ${pgam.toFixed(2)}g · SDC ${escapeHtml(s.usgs_sdc || "?")}`;
      flags.push(
        `<span class="ap1000-flag ${exceedsCls}" title="USGS ASCE 7-22 seismic hazard (Risk Cat. IV, Site Class C)${exceedsTip}">` +
        `⚠ Seismic ${seismicLabel}</span>` +
        _ap1000CellSrc(_ap1000SourceFor(s, "seismic_usgs"), "USGS seismic API")
      );
    } else if (s.seismic_flag && s.seismic_flag !== "low" && s.seismic_flag !== "none") {
      flags.push(`<span class="ap1000-flag ${AP1000_FLAG_CLASS[s.seismic_flag] || "warn"}" title="Seismic risk (not scored)">⚠ Seismic ${escapeHtml(s.seismic_flag)}</span>`);
    }
    if (s.flood_flag && s.flood_flag !== "low" && s.flood_flag !== "none")
      flags.push(`<span class="ap1000-flag ${AP1000_FLAG_CLASS[s.flood_flag] || "warn"}" title="Flood exposure (not scored)">⚠ Flood ${escapeHtml(s.flood_flag)}</span>`);
    const flagCell = flags.length ? flags.join(" ") : '<span class="muted-cell">—</span>';

    // Grid context badges — notable active or retired plant signals for the
    // Installation cell meta line (informational, not scored).
    const gridBadges = [];
    if (s.power_plant_mw != null && s.power_plant_mw >= 500) {
      const fuel = _ap1000ActiveFuelLabel(s.power_plant_fuel);
      gridBadges.push(
        `<span class="ap1000-grid-badge active" title="${Math.round(s.power_plant_mw).toLocaleString()} MW ${escapeHtml(s.power_plant_fuel || "—")} plant ${fmt.miles(s.power_plant_mi)} away (HIFLD active generators)">⚡ ${Math.round(s.power_plant_mw).toLocaleString()} MW ${escapeHtml(fuel)}</span>`
      );
    }
    if (s.retired_plant_mw != null && s.retired_plant_mi <= 15) {
      const rFuel = _EIA_FUEL[s.retired_plant_fuel] || (s.retired_plant_fuel || "").toLowerCase();
      gridBadges.push(
        `<span class="ap1000-grid-badge retired" title="${Math.round(s.retired_plant_mw).toLocaleString()} MW retired ${escapeHtml(rFuel)} — ${escapeHtml(s.retired_plant_name || "")} (${s.retired_plant_year || "—"}) ${fmt.miles(s.retired_plant_mi)} away (EIA-860M)">♻ ${Math.round(s.retired_plant_mw).toLocaleString()} MW ${escapeHtml(rFuel)} retired</span>`
      );
    }
    const gridBadgeHtml = gridBadges.join("");

    // Expandable detail: per-factor breakdown bar + chips + notes + sources.
    const seg = AP1000_FACTORS.map((f) =>
      `<span class="ap1000-seg ap1000-seg-${f.key}" style="flex:${bd[f.key] || 0} 0 0" title="${f.label}: ${bd[f.key] || 0}/${W[f.key] || 0}"></span>`
    ).join("") + `<span class="ap1000-seg ap1000-seg-rest" style="flex:${Math.max(0, 100 - score)} 0 0"></span>`;
    const chips = AP1000_FACTORS.map((f) =>
      `<span class="ap1000-chip"><span class="ap1000-chip-k">${f.label}</span><span class="ap1000-chip-v">${bd[f.key] || 0}<span class="ap1000-chip-cap">/${W[f.key] || 0}</span></span></span>`
    ).join("");

    const dataRow =
      `<tr class="ap1000-row" data-ap1000-row="${rank}">` +
        `<td class="num ap1000-rank-cell"><button type="button" class="ap1000-expand" aria-expanded="false" aria-controls="ap1000-detail-${rank}" aria-label="Toggle siting detail for ${escapeHtml(s.name)}"><span class="ap1000-rank-num">${rank}</span><span class="ap1000-caret" aria-hidden="true">▸</span></button></td>` +
        `<td class="ap1000-name-cell"><span class="ap1000-name">${escapeHtml(s.name)}</span><span class="ap1000-meta">${escapeHtml(s.branch || "")} · ${escapeHtml(s.state || "")}${janus}${afRflp}${gridBadgeHtml}</span>${_ap1000CellSrc(_ap1000SourceFor(s, "installation"), "Installation data")}</td>` +
        `<td class="num ap1000-score-cell"><span class="ap1000-score-chip ap1000-tier-${tier.cls}">${score == null ? "—" : score}</span>${_ap1000CellSrc(_ap1000SourceFor(s, "score"), "Score methodology")}</td>` +
        `<td><span class="ap1000-tag ${waterCls}">${escapeHtml(s.water_adequacy || "—")}</span>${_ap1000CellSrc(_ap1000SourceFor(s, "water"), "Water")}</td>` +
        `<td class="num" title="${escapeHtml(s.developable_basis || "")}">${s.developable_acreage != null ? s.developable_acreage.toLocaleString() : "—"}${_ap1000CellSrc(_ap1000SourceFor(s, "acreage"), "Acreage")}</td>` +
        `<td class="num ap1000-kvmi">${_ap1000KvMi(s.transmission_mi, s.transmission_kv)}${_ap1000CellSrc(_ap1000SourceFor(s, "transmission"), "Transmission")}</td>` +
        `<td class="num ap1000-kvmi">${_ap1000KvMi(s.substation_mi, s.substation_kv)}${_ap1000CellSrc(_ap1000SourceFor(s, "substation"), "Substation")}</td>` +
        `<td class="ap1000-workforce-cell"><span class="ap1000-tag ${wfCls}">${escapeHtml(s.workforce || "—")}</span><span class="ap1000-workforce-area">${escapeHtml(s.workforce_metro || "Area TBD")}</span>${_ap1000CellSrc(_ap1000SourceFor(s, "workforce"), "Workforce")}</td>` +
        `<td><span class="ap1000-tag ${fiberCls}">${escapeHtml(s.fiber || "—")}</span>${_ap1000CellSrc(_ap1000SourceFor(s, "fiber"), "Fiber")}</td>` +
        `<td class="ap1000-flags-cell">${flagCell}${_ap1000CellSrc(_ap1000SourceFor(s, "flags"), "Geohazard data")}</td>` +
      `</tr>`;

    // Grid context block — active + retired plant details (informational, not scored).
    const activeBlock = s.power_plant_mw != null
      ? `<div><dt>Nearest active generating plant${_ap1000CellSrc(_ap1000SourceFor(s, "active_plant"), "HIFLD active plants source")}</dt><dd>` +
          `<strong>${Math.round(s.power_plant_mw).toLocaleString()} MW</strong> ${escapeHtml(_ap1000ActiveFuelLabel(s.power_plant_fuel))} · ${fmt.miles(s.power_plant_mi)} away` +
          `<p class="ap1000-note muted">Source: HIFLD Power_Plants_in_the_US (active generators only). Large active plants indicate existing grid load served by nearby transmission, but do not imply stranded interconnect.</p></dd></div>`
      : `<div><dt>Nearest active generating plant</dt><dd><span class="muted-cell">None found in range</span></dd></div>`;

    const retiredBlock = s.retired_plant_mw != null
      ? `<div><dt>Nearest large retired plant (≥100 MW dispatchable)${_ap1000CellSrc(_ap1000SourceFor(s, "retired_plant"), "EIA-860M retired plants source")}</dt><dd>` +
          `<strong>${Math.round(s.retired_plant_mw).toLocaleString()} MW</strong> ` +
          `${escapeHtml(_EIA_FUEL[s.retired_plant_fuel] || (s.retired_plant_fuel || "").toLowerCase())} · ` +
          `${escapeHtml(s.retired_plant_name || "—")} · retired ${s.retired_plant_year || "—"} · ${fmt.miles(s.retired_plant_mi)} away` +
          `<p class="ap1000-note">Retired plants often leave stranded high-voltage interconnects, industrial-grade cooling infrastructure, and brownfield zoning — the Conesville / Widows Creek / Susquehanna pattern for large campus energy deals. Verify interconnect status and site availability independently.</p></dd></div>`
      : `<div><dt>Nearest large retired plant (≥100 MW dispatchable)${_ap1000CellSrc(_ap1000SourceFor(s, "retired_plant"), "EIA-860M retired plants source")}</dt><dd>` +
          `<span class="muted-cell">None found within ${RETIRED_PLANT_RADIUS_MI_LABEL}</span></dd></div>`;

    const detailRow =
      `<tr class="ap1000-detail" id="ap1000-detail-${rank}" hidden><td colspan="10">` +
        `<div class="ap1000-bar" role="img" aria-label="Score ${score} of 100">${seg}</div>` +
        `<div class="ap1000-chips">${chips}</div>` +
        `<dl class="ap1000-facts">` +
          `<div><dt>Cooling water</dt><dd><span class="ap1000-tag ${waterCls}">${escapeHtml(s.water_adequacy || "—")}</span> ${escapeHtml(s.water_source || "")}${_ap1000Src(s.water_source_url, "source")}<p class="ap1000-note">${escapeHtml(s.water_note || "")}</p></dd></div>` +
          `<div><dt>Developable acreage</dt><dd><strong>${fmt.acres(s.developable_acreage)}</strong> <span class="muted">of ${fmt.acres(s.installation_acreage)} installation</span>${_ap1000Src(s.acreage_source, "source")}<p class="ap1000-note">${escapeHtml(s.developable_basis || "")}</p></dd></div>` +
          `<div><dt>Construction workforce</dt><dd><span class="ap1000-tag ${wfCls}">${escapeHtml(s.workforce || "—")}</span> ${escapeHtml(s.workforce_metro || "")}${_ap1000Src(s.workforce_source_url, "source")}<p class="ap1000-note">${escapeHtml(s.workforce_note || "")}</p></dd></div>` +
          `<div><dt>Fiber</dt><dd><span class="ap1000-tag ${fiberCls}">${escapeHtml(s.fiber || "—")}</span><p class="ap1000-note">${escapeHtml(s.fiber_note || "")}</p></dd></div>` +
        `</dl>` +
        `<details class="ap1000-grid-ctx" open><summary class="ap1000-grid-summary">Grid context <span class="ap1000-grid-note">(informational — not scored)</span></summary>` +
          `<dl class="ap1000-facts ap1000-grid-facts">` +
            (s.iso_rto ? `<div><dt>Grid operator (ISO/RTO)${_ap1000CellSrc(_ap1000SourceFor(s, "grid_operator"), "ISO/RTO source")}</dt><dd><strong>${escapeHtml(s.iso_rto)}</strong><p class="ap1000-note">${escapeHtml(s.iso_rto_note || "")}</p></dd></div>` : "") +
            activeBlock + retiredBlock +
          `</dl>` +
        `</details>` +
        (s.siting_note ? `<p class="ap1000-siting"><span class="ap1000-siting-label">Siting note (geohazards not scored):</span> ${escapeHtml(s.siting_note)}</p>` : "") +
        (s.af_rflp_site ? `<p class="ap1000-nuke muted"><strong>Air Force AI data-center RFLP:</strong> ${fmt.acres(s.af_rflp_acres)} offered as underutilized land (${escapeHtml(s.af_rflp_detail || "")}). This is shown as provenance for active-base energy/data-center siting interest, not substituted for total developable acreage. ${_ap1000Src(s.af_rflp_source_url, "SAM.gov")} ${_ap1000Src(s.af_rflp_article_url, "public Q&A")}</p>` : "") +
        (s.nuclear_notes ? `<p class="ap1000-nuke muted">${escapeHtml(s.nuclear_notes)}</p>` : "") +
      `</td></tr>`;

    return dataRow + detailRow;
  }).join("");

  host.innerHTML =
    `<div class="ap1000-table-wrap"><table class="ap1000-table">` +
      `<caption class="sr-only">AP1000 reactor-siting suitability for 14 named U.S. military installations, ranked best-first. Use each row's expand button for the full per-factor breakdown, sources, and unscored geohazard flags.</caption>` +
      `<thead><tr>` +
        `<th class="num" scope="col">#</th><th scope="col">Installation</th>` +
        `<th class="num" scope="col" title="${escapeHtml(window.AP1000_SCORE_TOOLTIP || "AP1000 suitability 0–100")}">Score</th>` +
        `<th scope="col">Water</th><th class="num" scope="col">Dev. acres</th>` +
        `<th class="num" scope="col">Transmission</th><th class="num" scope="col">Substation</th>` +
        `<th scope="col">Workforce</th><th scope="col">Fiber</th><th scope="col">Flags (not scored)</th>` +
      `</tr></thead>` +
      `<tbody>${rows}</tbody>` +
    `</table></div>`;

  // Expand/collapse. The focusable control is the per-row <button> in the rank
  // cell (it carries aria-expanded / aria-controls and handles Enter/Space
  // natively); a click anywhere else on the row is a mouse-only convenience.
  const tbody = host.querySelector(".ap1000-table tbody");
  if (tbody && !tbody._ap1000Wired) {
    tbody._ap1000Wired = true;
    const toggle = (rowEl) => {
      const detail = rowEl.nextElementSibling;
      if (!detail || !detail.classList.contains("ap1000-detail")) return;
      const open = detail.hidden;
      detail.hidden = !open;
      const btn = rowEl.querySelector(".ap1000-expand");
      if (btn) btn.setAttribute("aria-expanded", String(open));
      rowEl.classList.toggle("ap1000-open", open);
    };
    tbody.addEventListener("click", (e) => {
      const rowEl = e.target.closest(".ap1000-row");
      // Ignore clicks on the source links; the expand button (not an <a>) and
      // bare-cell clicks both bubble here and toggle once.
      if (rowEl && !e.target.closest("a")) toggle(rowEl);
    });
  }
}

const AP1000_CSV_COLUMNS = [
  { label: "rank", value: (r) => r.rank, source: (r) => _ap1000SourceFor(r.s, "rank") },
  { label: "installation", value: (r) => r.s.name, source: (r) => _ap1000SourceFor(r.s, "installation") },
  { label: "state", value: (r) => r.s.state, source: (r) => _ap1000SourceFor(r.s, "installation") },
  { label: "score", value: (r) => r.score, source: (r) => _ap1000SourceFor(r.s, "score") },
  { label: "score_water_points", value: (r) => r.bd.water, source: (r) => _ap1000SourceFor(r.s, "score") },
  { label: "score_transmission_points", value: (r) => r.bd.transmission, source: (r) => _ap1000SourceFor(r.s, "score") },
  { label: "score_substation_points", value: (r) => r.bd.substation, source: (r) => _ap1000SourceFor(r.s, "score") },
  { label: "score_workforce_points", value: (r) => r.bd.workforce, source: (r) => _ap1000SourceFor(r.s, "score") },
  { label: "score_fiber_points", value: (r) => r.bd.fiber, source: (r) => _ap1000SourceFor(r.s, "score") },
  { label: "water", value: (r) => r.s.water_adequacy, source: (r) => _ap1000SourceFor(r.s, "water") },
  { label: "water_reason", value: (r) => r.s.water_note, source: (r) => _ap1000SourceFor(r.s, "water") },
  { label: "water_source", value: (r) => r.s.water_source, source: (r) => _ap1000SourceFor(r.s, "water") },
  { label: "acreage_threshold_acres", value: () => window.AP1000_MIN_DEVELOPABLE_ACRES || 500, source: (r) => _ap1000SourceFor(r.s, "acreage") },
  { label: "acreage_threshold_met", value: (r) => window.ap1000MeetsAcreageThreshold ? window.ap1000MeetsAcreageThreshold(r.s) : "", source: (r) => _ap1000SourceFor(r.s, "acreage") },
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
  { label: "fiber_reason", value: (r) => r.s.fiber_note, source: (r) => _ap1000SourceFor(r.s, "fiber") },
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

function ap1000ScoredRows() {
  return ap1000Sites
    .map((s) => ({ s, score: window.computeAp1000Score(s), bd: window.computeAp1000Breakdown(s) }))
    .sort((a, b) => (b.score ?? -1) - (a.score ?? -1))
    .map((r, i) => ({ ...r, rank: i + 1 }));
}

function buildAp1000Csv() {
  const headers = [];
  for (const c of AP1000_CSV_COLUMNS) {
    headers.push(c.label, `${c.label}_source_url`);
  }
  const rows = [headers];
  for (const r of ap1000ScoredRows()) {
    const row = [];
    for (const c of AP1000_CSV_COLUMNS) {
      const v = c.value(r);
      const src = c.source(r);
      row.push(v == null ? "" : v, src || "");
    }
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
// all lazy-loads settle (scores improve as enrichment data arrives).
const CANDIDATES_PAGE = 200;
const candidatesState = {
  sorted:   [],
  rendered: 0,
  lens:     "dc",   // "dc" | "gen" — URL state ?lens=
};
let _candidatesObserver = null;

function _candidateScoreFn() {
  return candidatesState.lens === "gen" ? computeGenerationScore : computeDcCompositeScore;
}

// Returns true when the site has a large dispatchable plant nearby that
// could indicate an inheritable grid interconnection (the "Homer City /
// Widows Creek" pattern: coal/gas plants ≥500 MW within 1 mi).
function _hasGridInheritance(s) {
  return s.power_plant_mw != null && s.power_plant_mw >= 500
    && s.power_plant_mi != null && s.power_plant_mi <= 1
    && s.power_plant_fuel != null
    && /coal|natural gas/i.test(s.power_plant_fuel);
}

// Confirmed-retired plant within 1 mi — the Conesville / Widows Creek pattern:
// inherited transmission connection without competing for the active plant's
// capacity.  Source: EIA-860M `retired_plant_*` fields (eia-retired-plants
// enrichment connector).  Lower MW floor (≥100 MW) — even a retired 200 MW
// peaker leaves behind a 138+ kV interconnect.
function _hasRetiredPlant(s) {
  return s.retired_plant_mi != null && s.retired_plant_mi <= 1
    && s.retired_plant_mw != null && s.retired_plant_mw >= 100;
}

// Operating nuclear plant ≥500 MW within 5 mi — the AWS/Talen Susquehanna
// pattern: 24/7 carbon-free baseload accessed via PPA. Wider radius than
// coal/gas (5 mi vs 1) because nuclear connects high in the transmission
// hierarchy and DCs reach it via PPA, not direct co-location. Mirrors the
// nuclear pathway in dc-score.js:_scoreGridInheritance.
function _hasNuclearAdjacency(s) {
  return s.power_plant_mi != null && s.power_plant_mi <= 5
    && s.power_plant_mw != null && s.power_plant_mw >= 500
    && s.power_plant_fuel != null && /nuclear/i.test(s.power_plant_fuel);
}

// Returns true when the site meets the EPA's stated EO 14318 / January 2026
// guidance criteria for fast-tracked brownfield/Superfund data center permits:
// program is superfund or brownfield, ≥100 ac, grid ≤2 mi, outside SFHA.
function _hasEO14318(s) {
  return (s.program === "superfund" || s.program === "brownfield")
    && s.acreage != null && s.acreage >= 100
    && s.transmission_mi != null && s.transmission_mi <= 2
    && s.in_sfha !== true;
}

// EPA Sitewide Ready for Anticipated Use (SWRAU) — true only for the two
// affirmative values. "Does Not Meet the Measure", its "(Retracted)" variant,
// and null all return false (a retracted determination is not a ready signal).
function _meetsRau(rauStatus) {
  return typeof rauStatus === "string" && /^Meets the Measure/i.test(rauStatus);
}

function makeCandidateRow(s, rank) {
  const tr = document.createElement("tr");
  tr.dataset.id = s.id;

  const scoreFn = _candidateScoreFn();
  const score   = scoreFn(s);
  const tier    = computeDcScore(s);

  // Score cell — reuse existing .suit-score[data-tier] coloring
  const scoreTier = score == null ? null
    : score >= 75 ? "strong" : score >= 50 ? "moderate"
    : score >= 25 ? "marginal" : "weak";
  const scoreHtml = score == null
    ? '<span class="muted-cell">—</span>'
    : `<span class="suit-score" data-tier="${escapeAttr(scoreTier)}">${score}</span>`;

  // Tier pill — reuse .dc-tier-pill
  const tierHtml = tier
    ? `<span class="pill dc-tier-pill${tier === "hyperscale" || tier === "mega" ? " ready" : ""}">${escapeHtml(DC_TIER_LABEL[tier] || tier)}</span>`
    : '<span class="muted-cell">—</span>';

  // kV
  const kvHtml = s.transmission_kv != null
    ? `${Math.round(s.transmission_kv).toLocaleString()} kV`
    : '<span class="muted-cell">—</span>';

  // Substation distance
  const subHtml = s.substation_mi != null
    ? fmt.miles(s.substation_mi)
    : '<span class="muted-cell">—</span>';

  // Power plant — distance, MW, abbreviated fuel
  let plantHtml = '<span class="muted-cell">—</span>';
  if (s.power_plant_mw != null || s.power_plant_fuel) {
    const parts = [];
    if (s.power_plant_mi != null) parts.push(fmt.miles(s.power_plant_mi));
    if (s.power_plant_mw != null) parts.push(`${Math.round(s.power_plant_mw).toLocaleString()} MW`);
    if (s.power_plant_fuel) {
      // Shorten verbose EIA-860 fuel names
      const fuel = String(s.power_plant_fuel)
        .replace(/Conventional/gi, "").replace(/Photovoltaic/gi, "").trim();
      parts.push(fuel);
    }
    const isLarge = s.power_plant_mw != null && s.power_plant_mw >= 100;
    const cls = isLarge ? "pp-chip ready" : "pp-chip";
    plantHtml = `<span class="${cls}">${escapeHtml(parts.join(" · "))}</span>`;
  }

  // Gas pipeline distance
  const gasHtml = s.gas_pipeline_mi != null
    ? fmt.miles(s.gas_pipeline_mi)
    : '<span class="muted-cell">—</span>';

  // Signal badges — readiness green / risk red / financial blue
  const badges = [];
  if (_meetsRau(s.rau_status)) {
    badges.push('<span class="sig-badge sig-land" title="EPA Sitewide Ready for Anticipated Use (SWRAU): all of this site\'s land is ready for its anticipated use — the strongest public land-availability signal">Land Ready</span>');
  }
  if (s.in_opportunity_zone) {
    const lbl = s.oz_rural ? "OZ Rural" : "OZ";
    badges.push(`<span class="sig-badge sig-oz" title="${s.oz_rural ? "Rural Qualified Opportunity Zone — 30% basis step-up" : "Qualified Opportunity Zone"}">${escapeHtml(lbl)}</span>`);
  }
  if (s.in_energy_community) {
    const lbl = s.energy_community_type === "coal_closure" ? "IRA Coal" : "IRA";
    badges.push(`<span class="sig-badge sig-ira" title="IRA energy community${s.energy_community_detail ? " — " + escapeAttr(s.energy_community_detail) : ""} — +10pp ITC/PTC bonus for clean-energy builds">${escapeHtml(lbl)}</span>`);
  }
  if (s.npl_status_code === "D") {
    badges.push('<span class="sig-badge sig-ready" title="Deleted from NPL — cleanup complete">Clean</span>');
  }
  if (/^yes/i.test(s.in_reuse || "")) {
    badges.push('<span class="sig-badge sig-ready" title="Active reuse underway">Reuse</span>');
  }
  if (s.data_center_reuse_candidate) {
    badges.push('<span class="sig-badge sig-dc" title="EPA RE-Powering data-center reuse candidate">EPA DC</span>');
  }
  if (_hasRetiredPlant(s)) {
    badges.push('<span class="sig-badge sig-plant" title="Retired power plant ≤1 mi — inherited transmission connection and stranded interconnection agreement (Conesville / Widows Creek pattern)">Ret. Plant</span>');
  } else if (_hasGridInheritance(s)) {
    badges.push('<span class="sig-badge sig-grid" title="Large coal/gas plant ≤1 mi — potential inherited grid interconnection">Grid Inherit</span>');
  } else if (_hasNuclearAdjacency(s)) {
    badges.push('<span class="sig-badge sig-grid" title="Operating nuclear ≥500 MW within 5 mi — 24/7 carbon-free baseload via PPA (AWS/Talen Susquehanna pattern)">Nuclear</span>');
  }
  if (_hasEO14318(s)) {
    badges.push('<span class="sig-badge sig-fedfast" title="Meets EO 14318 / EPA Jan 2026 guidance: superfund/brownfield ≥100 ac, grid ≤2 mi, outside SFHA — qualifies for fast-tracked NEPA categorical exclusion">Fed Fast Lane</span>');
  }
  if (s.in_sfha === true) {
    badges.push('<span class="sig-badge sig-flood" title="FEMA Special Flood Hazard Area — permitting challenge for critical infrastructure">Flood</span>');
  }
  // FEMA NRI wildfire/drought climate penalty — surface BOTH penalized tiers so
  // the ranking drag is visible (Very High = −10, Relatively High = −5), parallel
  // to Flood. Show the magnitude in the badge so a −5 site isn't invisible.
  const _climRank = (r) => r === "Very High" ? 2 : r === "Relatively High" ? 1 : 0;
  const _climWorst = Math.max(_climRank(s.nri_wildfire_rating), _climRank(s.nri_drought_rating));
  if (_climWorst > 0) {
    const _climPts = _climWorst === 2 ? 10 : 5;
    const _climTier = _climWorst === 2 ? "Very High" : "Relatively High";
    const _climHaz = _climRank(s.nri_wildfire_rating) >= _climRank(s.nri_drought_rating)
      ? "wildfire" : "drought";
    badges.push(`<span class="sig-badge sig-flood" title="FEMA National Risk Index: ${_climTier} ${_climHaz} risk — insurability / cooling-water constraint (−${_climPts} to the suitability score)">Climate −${_climPts}</span>`);
  }
  // State DC regulatory friction (DC-lens penalty). Names the policy so the
  // ranking drag is explained, not just flagged.
  if (s.dc_regulatory_climate) {
    const reg = STATE_DC_REGULATION[s.state];
    const pts = s.dc_regulatory_climate === "restrictive" ? "−8" : "−4";
    badges.push(`<span class="sig-badge sig-flood" title="${escapeAttr((reg && reg.note) || "State regulatory restriction")} (${pts} to the data-center score)">Zoning</span>`);
  }
  if (s.enforcement?.has_npdes_permit === true) {
    badges.push('<span class="sig-badge sig-water" title="Active CWA/NPDES permit — legacy industrial water discharge infrastructure (intake, treated effluent rights)">Water</span>');
  }

  const progLabel = PROGRAM_LABEL[s.program] || s.program;
  tr.innerHTML = `
    <td class="num cand-rank">${rank}</td>
    <td class="cand-name">${escapeHtml(s.name || "—")}<span class="cand-prog"><span class="pill" data-program="${escapeAttr(s.program)}">${escapeHtml(progLabel)}</span></span></td>
    <td>${escapeHtml(s.state || "—")}</td>
    <td class="num">${fmt.acres(s.acreage)}</td>
    <td class="num cand-score">${scoreHtml}</td>
    <td>${tierHtml}</td>
    <td class="num">${kvHtml}</td>
    <td class="num">${subHtml}</td>
    <td class="cand-plant">${plantHtml}</td>
    <td class="num">${gasHtml}</td>
    <td class="cand-signals">${badges.join("")}</td>
  `;
  tr.addEventListener("click", () => selectSite(s.id, { fromTable: true }));
  return tr;
}

function buildCandidatesView() {
  const scoreFn = _candidateScoreFn();
  candidatesState.sorted = tableState.filtered
    .filter((s) => scoreFn(s) != null)
    .sort((a, b) => (scoreFn(b) || 0) - (scoreFn(a) || 0));

  // Tier distribution for the stats line
  const counts = { mega: 0, hyperscale: 0, colo: 0, edge: 0 };
  for (const s of candidatesState.sorted) {
    const t = computeDcScore(s);
    if (t && t in counts) counts[t]++;
  }
  const total = candidatesState.sorted.length;
  const parts = [];
  if (counts.mega)       parts.push(`${counts.mega.toLocaleString()} Mega`);
  if (counts.hyperscale) parts.push(`${counts.hyperscale.toLocaleString()} Hyperscale`);
  if (counts.colo)       parts.push(`${counts.colo.toLocaleString()} Colo`);
  if (counts.edge)       parts.push(`${counts.edge.toLocaleString()} Edge`);
  const statsEl = el("candidates-stats");
  if (statsEl) {
    const filtered = filtersActive() || filterState.q !== "";
    statsEl.textContent = total > 0
      ? `${total.toLocaleString()} sites scored · ${parts.join(" · ")} · sorted by ${candidatesState.lens === "gen" ? "generation" : "data-center"} score${filtered ? " · global filters applied" : ""}`
      : (filtered ? "No scored sites match the current filters — adjust them via the ⚙ Filters strip." : "No candidates match current filters.");
  }

  const tbody = document.querySelector("#candidates-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  candidatesState.rendered = 0;
  _appendCandidatesPage(tbody);
  _setupCandidatesScroll();
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
  if (new URLSearchParams(location.search).get("lens") === "gen") {
    candidatesState.lens = "gen";
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
  // EO 14318 "Federal Fast Lane" — policy signal. Meets EPA Jan 2026 criteria
  // for fast-tracked NEPA categorical exclusion + Army Corps Section 404 permits.
  const eo14318Pill = _hasEO14318(s)
    ? ` <span class="pill eo14318-pill" title="Meets EO 14318 / EPA Jan 2026 guidance — fast-tracked NEPA categorical exclusion and Army Corps Section 404 permits apply (superfund/brownfield ≥100 ac, grid ≤2 mi, outside SFHA)">Fed Fast Lane</span>`
    : "";
  // DC suitability tier (Tier 0 score) — earns a green "Hyperscale-ready"
  // outline pill at hyperscale+, accent-colored at colo / edge. Title shows
  // the threshold met so the buyer sees *why*.
  const tier = computeDcScore(s);
  let tierPill = "";
  if (tier) {
    const tierMeta = DC_TIERS.find((t) => t.id === tier);
    const isReady = tier === "hyperscale" || tier === "mega";
    const cls = isReady ? "dc-tier-pill ready" : "dc-tier-pill";
    const titleParts = [`${tierMeta.minAcres.toLocaleString()}+ ac`];
    if (tierMeta.minKv > 0) titleParts.push(`≥${tierMeta.minKv} kV transmission ≤1 mi`);
    else titleParts.push("transmission ≤1 mi");
    tierPill = ` <span class="pill ${cls}" title="${escapeAttr(titleParts.join(" \xb7 "))}">${escapeHtml(DC_TIER_LABEL[tier])}</span>`;
  }
  el("d-program").innerHTML = programPill + cleanupPill + reusePill + landReadyPill + dcPill + ozPill + iraPill + eo14318Pill + tierPill;
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
  setMileCell("d-rail-mi", s.rail_mi, { offConus });
  setMileCell("d-highway-mi", s.highway_mi, { offConus });
  setMileCell("d-gas-pipeline-mi", s.gas_pipeline_mi, { offConus });
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
  // Siting suitability scores (data-center load + new generation), the
  // synthesis of the infra signals above. Reads dc-score.js — no fetch.
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
  // FEMA National Risk Index (v1.19) — climate / natural-hazard risk
  { key: "nri_risk_score", label: "nri_risk_score" },
  { key: "nri_risk_rating", label: "nri_risk_rating" },
  { key: "nri_wildfire_rating", label: "nri_wildfire_rating" },
  { key: "nri_drought_rating", label: "nri_drought_rating" },
  // IRA energy community (v1.18) — financial signal (+10pp ITC/PTC bonus)
  { key: "in_energy_community", label: "in_energy_community" },
  { key: "energy_community_type", label: "energy_community_type" },
  // Computed suitability scores (0–100, dc-score.js) — synthesis of the
  // infra signals above. Empty when transmission data is missing.
  { key: "dc_score", label: "dc_score", compute: (s) => computeDcCompositeScore(s) },
  { key: "generation_score", label: "generation_score", compute: (s) => computeGenerationScore(s) },
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
  // Computed columns (e.g. the suitability scores) derive their value from
  // a function rather than a stored field.
  if (typeof col.compute === "function") {
    const cv = col.compute(s);
    return cv == null ? "" : cv;
  }
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
// Copy the current page URL (with all filter state encoded by syncUrl)
// to the clipboard. Prefers the modern async Clipboard API; falls back
// to the legacy hidden-textarea + execCommand path for older browsers
// and for non-secure-context loads (Clipboard API requires HTTPS or
// localhost). Toast confirms the copy so users get feedback without an
// extra modal.
function wireShareLink() {
  const btn = el("share-link");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const url = window.location.href;
    let ok = false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(url);
        ok = true;
      } else {
        const ta = document.createElement("textarea");
        ta.value = url;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        ok = document.execCommand("copy");
        document.body.removeChild(ta);
      }
    } catch (_e) {
      ok = false;
    }
    showToast(ok ? "Link copied to clipboard" : "Couldn't copy link — long-press the address bar instead");
  });
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
  if (p.has("dc_tier")) {
    const t = p.get("dc_tier") || "";
    if (DC_TIER_RANK[t]) filterState.dcTier = t;
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
    // Candidates-view lens — only encoded off-default ("dc").
    if (candidatesState.lens !== "dc") p.set("lens", candidatesState.lens);
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
// always re-append after setMileCell. ≥230 kV gets a "ready" green tint
// to match the hyperscale-tier visual language.
function setKvSuffix(id, kv) {
  const node = el(id);
  if (!node) return;
  // Remove any prior kV span — setMileCell wiped textContent above so a
  // residual span is unlikely, but be defensive in case render order
  // changes later.
  for (const old of node.querySelectorAll(".kv-chip")) old.remove();
  if (kv == null) return;
  const span = document.createElement("span");
  span.className = "kv-chip" + (kv >= 230 ? " ready" : "");
  span.textContent = `${Math.round(kv).toLocaleString()} kV`;
  span.title = kv >= 500
    ? "≥500 kV — AI mega-campus tier"
    : kv >= 230
    ? "≥230 kV — hyperscale tier"
    : kv >= 138
    ? "≥138 kV — colocation tier"
    : "<138 kV — sub-transmission";
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
  span.title = mw != null && mw >= 100
    ? "≥100 MW — hyperscale-tier dispatchable generation nearby"
    : "Nearby generation — PPA / co-location candidate";
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
    span.title = "Retired plant — inherited transmission + stranded interconnect (Conesville/Widows Creek pattern)";
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
    + `Wildfire and drought at Relatively-High or Very-High apply a climate penalty to the siting scores.`;
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
// Group the per-component score breakdown into a few human-readable
// buckets so the detail panel shows *why* a site scores the way it does
// without a 9-row field dump. The keys match the breakdown objects
// returned by computeDcScoreBreakdown / computeGenerationScoreBreakdown
// in dc-score.js.
const _DC_SUIT_GROUPS = [
  { label: "Power access", cls: "suit-power",  keys: ["transmission_distance", "voltage", "substation", "grid_inheritance"] },
  { label: "Land",         cls: "suit-land",   keys: ["acreage"] },
  { label: "Gas",          cls: "suit-gas",    keys: ["gas_pipeline"] },
  { label: "Logistics",    cls: "suit-logi",   keys: ["logistics"] },
  { label: "Readiness",    cls: "suit-ready",  keys: ["readiness"] },
];
const _GEN_SUIT_GROUPS = [
  { label: "Land",         cls: "suit-land",   keys: ["acreage"] },
  { label: "Grid export",  cls: "suit-power",  keys: ["transmission_distance", "voltage", "substation", "grid_reuse"] },
  { label: "Gas",          cls: "suit-gas",    keys: ["gas_pipeline"] },
  { label: "Market",       cls: "suit-market", keys: ["iso_rto"] },
  { label: "Readiness",    cls: "suit-ready",  keys: ["readiness"] },
];

function _suitTier(score) {
  return score >= 75 ? "strong" : score >= 50 ? "moderate" : score >= 25 ? "marginal" : "weak";
}

function _suitLensHtml(title, score, breakdown, groups) {
  if (score == null) {
    return `<div class="suit-lens-head"><span class="suit-lens-name">${escapeHtml(title)}</span>`
      + `<span class="suit-score muted-cell">N/A</span></div>`
      + `<p class="suit-na">No transmission data — can't score power access.</p>`;
  }
  const chips = [];
  for (const g of groups) {
    const pts = g.keys.reduce((sum, k) => sum + (breakdown[k] || 0), 0);
    if (pts > 0) chips.push(`<span class="suit-chip ${g.cls}">${escapeHtml(g.label)} ${pts}</span>`);
  }
  const penalty = breakdown.flood_penalty || 0;
  if (penalty < 0) chips.push(`<span class="suit-chip suit-penalty">Flood ${penalty}</span>`);
  const climate = breakdown.climate_penalty || 0;
  if (climate < 0) chips.push(`<span class="suit-chip suit-penalty">Climate ${climate}</span>`);
  const reg = breakdown.regulatory_penalty || 0;
  if (reg < 0) chips.push(`<span class="suit-chip suit-penalty">Zoning ${reg}</span>`);
  const tier = _suitTier(score);
  return `<div class="suit-lens-head">`
    + `<span class="suit-lens-name">${escapeHtml(title)}</span>`
    + `<span class="suit-score" data-tier="${tier}">${score}<span class="suit-score-max">/100</span></span>`
    + `</div>`
    + `<div class="suit-track"><span class="suit-fill" data-tier="${tier}" style="width:${score}%"></span></div>`
    + `<div class="suit-chips">${chips.join("")}</div>`;
}

// Fill the detail-panel "Siting suitability" block with the two scoring
// lenses (data-center load vs. new power generation) plus an SFHA
// deal-blocker note. Both scores read from the same on-disk signals the
// infra-proximity section shows above — this is the synthesis layer.
function renderSuitability(s) {
  const dcEl = el("d-suit-dc");
  const genEl = el("d-suit-gen");
  if (!dcEl || !genEl) return;
  dcEl.innerHTML = _suitLensHtml(
    "Data center", computeDcCompositeScore(s), computeDcScoreBreakdown(s) || {}, _DC_SUIT_GROUPS);
  genEl.innerHTML = _suitLensHtml(
    "Power generation", computeGenerationScore(s), computeGenerationScoreBreakdown(s) || {}, _GEN_SUIT_GROUPS);
  const floodEl = el("d-suit-flood");
  if (floodEl) {
    const flooded = s.in_sfha === true;
    floodEl.hidden = !flooded;
    if (flooded) {
      floodEl.textContent = "⚑ In a FEMA Special Flood Hazard Area — permitting as critical "
        + "infrastructure requires elevation / flood-proofing. Both scores carry an 18-point penalty.";
    }
  }
  const climateEl = el("d-suit-climate");
  if (climateEl) {
    // Surface the worst of wildfire / drought when it reaches a penalized tier.
    const hazards = [];
    if (s.nri_wildfire_rating === "Very High" || s.nri_wildfire_rating === "Relatively High") {
      hazards.push(`wildfire (${s.nri_wildfire_rating})`);
    }
    if (s.nri_drought_rating === "Very High" || s.nri_drought_rating === "Relatively High") {
      hazards.push(`drought (${s.nri_drought_rating})`);
    }
    climateEl.hidden = hazards.length === 0;
    if (hazards.length) {
      const pts = (s.nri_wildfire_rating === "Very High" || s.nri_drought_rating === "Very High") ? 10 : 5;
      climateEl.textContent = `⚑ Elevated FEMA climate risk — ${hazards.join(" · ")}. `
        + `Both scores carry a ${pts}-point penalty.`;
    }
  }
  const regEl = el("d-suit-reg");
  if (regEl) {
    const reg = s.state && STATE_DC_REGULATION[s.state];
    regEl.hidden = !reg;
    if (reg) {
      const pts = reg.climate === "restrictive" ? 8 : 4;
      regEl.textContent = `⚑ ${reg.note} The data-center score carries a ${pts}-point penalty `
        + `(the generation score is unaffected — this restricts data centers, not power plants).`;
    }
  }
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
