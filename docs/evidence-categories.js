// Shared evidence findings. Confidence applies to the claim, never site suitability.
// No composite total, implicit ranking, or credit for missing observations.
(function (root) {
  "use strict";
  const VERSION = "categories-1";
  const MAX_CONTEXT_AGE_DAYS = 730;
  const LABELS = Object.freeze({grid: "Grid", grid_capacity: "Grid capacity", fiber: "Fiber",
    water: "Water", water_reliability: "Water reliability", water_rights: "Water entitlement",
    land: "Land", logistics: "Logistics", hazards: "Hazards", demand: "Demand",
    feedstock: "Feedstock", regulatory: "Regulatory pathway"});
  const PRIMARY = Object.freeze(["grid", "fiber", "water", "land", "logistics"]);
  const SOURCES = Object.freeze({
    transmission: "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer/0",
    substation: "https://www.openstreetmap.org/", water: "https://waterdata.usgs.gov/",
    highway: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer/2",
    rail: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer/9"});
  const valid = v => typeof v === "number" && Number.isFinite(v) && v >= 0;
  const url = v => typeof v === "string" && /^https:\/\//.test(v) ? v : null;
  const distance = n => n === 0 ? "<0.1 mi" : `${n.toFixed(1)} mi`;
  const result = (key, finding, status, confidence, reason, sources = []) => ({
    key, label: LABELS[key], finding, status, confidence, reason,
    sources: [...new Set(sources.filter(url))]});
  const unknown = (key, reason) => result(key, "Unknown", "unknown", null, reason);
  function metadata(s, layer) {
    const source = s._infraSourceMetadata?.[layer] || {};
    return {...source, ...(source.assets_by_id?.[s[`${layer}_asset_id`]] || {}), ...(s.infra_evidence?.[layer] || {})};
  }
  function contextConfidence(meta, today, proxy) {
    if (meta.status && meta.status !== "matched_context") return "Low";
    const date = meta.source_snapshot_at || meta.source_date || meta.data_last_edit || meta.snapshot_at || meta.fetched_at;
    const age = (Date.parse(today) - Date.parse(date)) / 86400000;
    return !proxy && Number.isFinite(age) && age >= 0 && age <= MAX_CONTEXT_AGE_DAYS ? "Medium" : "Low";
  }
  function assessSite(input, lens = "dc", today = new Date().toISOString().slice(0, 10)) {
    const s = input || {};
    const a = {};
    const proxy = !!s.infra_source_id || !!s.coord_quality_flag || !!s.coord_quality_flags?.length || !!s.coord_flags?.length;
    const geometry = s.infra_source_id ? "Distances use a cleanup-site reference point, not a proposed parcel. "
      : "Distances use the reported site point, not a surveyed connection route. ";
    const coordinateNote = s.coord_flags?.length ? "Coordinate quality flags: " + s.coord_flags.join(", ") + ". " : "";
    let layer = null;
    if (valid(s.substation_mi) && (!valid(s.transmission_mi) || s.substation_mi < s.transmission_mi)) layer = "substation";
    else if (valid(s.transmission_mi)) layer = "transmission";
    if (layer) {
      const m = metadata(s, layer);
      const role = layer === "substation" ? s.substation_role || m.role || m.asset_role : null;
      const label = layer === "substation" ? `Substation${role ? ` (${role})` : " (role unknown)"}` : "Mapped line";
      const kv = s[`${layer}_kv`];
      a.grid = result("grid", `${label} · ${distance(s[`${layer}_mi`])}${valid(kv) ? ` · ${kv} kV` : " · voltage unknown"}`,
        "context", contextConfidence(m, today, proxy), geometry + coordinateNote +
        `Source snapshot: ${m.source_snapshot_at || m.snapshot_at || "unknown"}. ${m.voltage_basis ? "Voltage basis: " + m.voltage_basis + ". " : ""}${m.voltage_class ? "Published class: " + m.voltage_class + ". " : ""} ${m.status && m.status !== "matched_context" ? "Retained or incomplete evidence. " : ""}` +
        "Mapped proximity only. Equipment role, connection route and available capacity need utility confirmation.",
        [m.source_url || SOURCES[layer]]);
    } else a.grid = unknown("grid", "No usable mapped match. Coverage gaps and incomplete searches cannot establish off-grid status.");
    a.grid_capacity = unknown("grid_capacity", "No utility service commitment or interconnection study is attached to this site.");
    // A source URL for acreage or an analyst adjective cannot support a fiber claim.
    const regionalFiber = s.fiber_regional_evidence;
    a.fiber = regionalFiber?.status === "regional_context" && url(regionalFiber.source_url)
      ? result("fiber", `${regionalFiber.network} · regional footprint`, "context", "Medium",
        `${regionalFiber.footprint}. ${regionalFiber.lifecycle}. Evidence scope: ${regionalFiber.evidence_scope}. ` +
        `This does not establish service at the parcel. Unresolved: ${regionalFiber.unresolved}`,
        [regionalFiber.source_url])
      : url(s.fiber_source_url) && s.fiber && s.fiber !== "unknown"
      ? result("fiber", "Reported fiber context", "context", "Low",
        "Confirm parcel service, carrier, capacity and independent routes. " + (s.fiber_note || ""), [s.fiber_source_url])
      : unknown("fiber", "No site-specific fiber evidence. Regional networks and broadband availability do not establish enterprise service.");
    const networkWater = s.water_network_evidence;
    a.water = networkWater?.status === "network_context" && url(networkWater.source_url)
      ? result("water", `Network-linked reach · ${networkWater.huc12_name}`, "context", "Medium",
        `${networkWater.connection_method}; ${distance(networkWater.snap_distance_mi)} to NHD flowline ${networkWater.feature_id}. ` +
        `HUC12 ${networkWater.huc12}. Network identity is not supply. Unresolved: ${networkWater.unresolved}`,
        [networkWater.source_url, networkWater.basin_source_url])
      : valid(s.water_gage_mi) && valid(s.water_flow_cfs)
      ? result("water", `Gage ${distance(s.water_gage_mi)} · supply unknown`, "context", "Low",
        `${s.water_flow_cfs.toLocaleString()} cfs ${s.water_statistic === "mean_of_annual_means" ? "mean of annual means" : "reported mean flow"} at ${s.water_gage_name || "a monitoring gage"}. ` +
        (s.water_gage_record_start_year ? `Record: ${s.water_gage_record_start_year}–${s.water_gage_record_end_year || "unknown"}, ${s.water_gage_record_years || "unknown"} annual values. ` : "Record period unknown. ") +
        "Gage distance is not distance to water; catchment, intake, low flow and allocation are unassessed.",
        [s.water_gage_source_url || (s.water_gage_id ? `https://waterdata.usgs.gov/monitoring-location/USGS-${String(s.water_gage_id).replace(/^USGS-/, "")}/` : SOURCES.water)])
      : url(s.water_source_url) && s.water_source
        ? result("water", "Reported water source", "context", "Low", s.water_note || "Supply is unassessed.", [s.water_source_url])
        : unknown("water", "No assessed water supply. A missing qualifying gage does not establish absence of water.");
    a.water_reliability = unknown("water_reliability", "No source-matched low-flow or firm-yield assessment against project demand.");
    a.water_rights = unknown("water_rights", "No project allocation or supply contract. Discharge permits do not establish withdrawal rights.");
    const acres = valid(s.acreage) ? s.acreage : valid(s.developable_acreage) ? s.developable_acreage
      : valid(s.parcel_acreage) ? s.parcel_acreage : null;
    const landSource = valid(s.acreage)
      ? [s.acreage_source, s.profile_url, s._coreSourceUrl].find(url)
      : valid(s.developable_acreage) ? url(s.acreage_source) : url(s.current_owner_source);
    a.land = acres !== null ? result("land", `${acres.toLocaleString()} acres reported`, "context",
      valid(s.acreage) && landSource ? "Medium" : "Low", "Reported area may cover a site or matched parcel. Ownership, usable footprint and availability require verification.",
      [landSource])
      : unknown("land", "Acreage not reported. Unknown area is not evidence of a small or available parcel.");
    const routes = ["highway", "rail"].filter(k => valid(s[`${k}_mi`]));
    a.logistics = routes.length ? result("logistics", routes.map(k => `${k === "highway" ? "Road" : "Rail"} ${distance(s[`${k}_mi`])}`).join(" · "),
      "context", routes.every(k => contextConfidence(metadata(s,k),today,proxy) === "Medium") ? "Medium" : "Low",
      geometry + "Mapped routes do not establish a driveway, rail spur, load limits or a freight agreement.", routes.map(k => metadata(s,k).source_url || SOURCES[k]))
      : unknown("logistics", "No usable mapped route evidence; delivery feasibility is unassessed.");
    a.hazards = s.in_sfha === true ? result("hazards", "Mapped flood hazard", "constraint", contextConfidence(metadata(s,"flood_zone"),today,proxy),
      "FEMA maps a Special Flood Hazard Area at the reference point. Confirm current mapping and the proposed footprint.",
      ["https://msc.fema.gov/portal/home"])
      : unknown("hazards", "No complete site-specific hazard assessment. An absent hazard flag is not clearance.");
    a.demand = unknown("demand", "Nearby generation does not establish an operating customer load or energy contract.");
    a.regulatory = unknown("regulatory", "Program membership and former military use do not establish current federal ownership or an authorized project pathway.");
    a.feedstock = valid(s.nickel_feedstock_mi) ? result("feedstock", "Supply-chain location mapped", "context", "Low",
      `${Math.round(s.nickel_feedstock_mi)} miles to ${s.nickel_feedstock_name || "a cataloged anchor"}. Production, available material, route and supply agreement require confirmation.`,
      [s.nickel_feedstock_source_url]) : unknown("feedstock", "No site-specific feedstock agreement is recorded.");
    return a;
  }
  const api = Object.freeze({VERSION, LABELS, PRIMARY, assessSite});
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.SiteEvidence = api;
})(typeof window !== "undefined" ? window : null);
