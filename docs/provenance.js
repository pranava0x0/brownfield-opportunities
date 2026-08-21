// Chain of evidence — where every claim on a site record came from.
//
// This dashboard synthesizes ~20 federal and state datasets into one record
// per site. That synthesis is only trustworthy if a reader can walk any
// single number back to the agency that published it. This module is the
// registry that makes that possible: for each field it records the
// publisher, the exact dataset and layer, the source field name, how the
// value was derived (copied / computed / spatially joined), and — where the
// upstream service supports it — a URL that returns THAT SITE'S row.
//
// Design rules:
//
//   1. Verification links are per-site wherever the source allows it. A link
//      to "the HIFLD transmission layer" is documentation; a link to the
//      features within 5 miles of THIS site is evidence. Prefer the latter.
//   2. Derivation is stated plainly. `transmission_mi` is not "from HIFLD" —
//      it is "shortest distance from this site's coordinate to any polyline
//      in HIFLD's layer, computed locally". A reader who doesn't know that
//      can't judge the number.
//   3. Nothing here is per-site data. The registry is static, so it costs
//      one small file rather than inflating 46,759 records with repeated
//      source strings.
//   4. As-of dates come from `window.__sourceDates`, keyed by data file, so
//      each row reports when ITS file was refreshed. Files run on different
//      cadences; a single global date would misdate most rows.
//
// Exposed on window: FIELD_PROVENANCE, buildEvidence(site).

(function () {
  "use strict";

  const D = {
    SITES: "data/sites.json",
    ACRES: "data/epa-acres.json",
    FUDS: "data/dod-fuds.json",
    BRAC: "data/dod-brac.json",
    REDEV: "data/epa-redev.json",
    DOCS: "data/epa-superfund-docs.json",
    INFRA: "data/infra-proximity.json",
    OZ: "data/opportunity-zone.json",
    IRA: "data/ira-energy-community.json",
    NRI: "data/fema-nri.json",
    CLIMATE: "data/climate-zone.json",
    ISO: "data/iso-rto.json",
    ECHO: "data/epa-echo.json",
    PARCEL: "data/parcel-owner.json",
    SUMMARY: "data/ai-summary.json",
    CLEANUP: "data/acres-cleanup.json",
    RETIRED: "data/eia-retired-plants.json",
    PLANNED: "data/planned-retirements-proximity.json",
    COORD: "data/coord-quality.json",
    TRIBAL: "data/tribal-areas.json",
    WORKFORCE: "data/census-workforce.json",
  };

  // ---- per-site verification link builders --------------------------------
  //
  // Each returns a URL that resolves to the specific record, or null when the
  // upstream service has no addressable per-record view (in which case the
  // row still cites the dataset, it just can't deep-link).

  const ARC = {
    superfund:
      "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/" +
      "FAC_Superfund_Site_Boundaries_EPA_Public/FeatureServer/0/query",
    acres:
      "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/" +
      "All%20ACRES%20Properties%208_30_2021/FeatureServer/0/query",
    fuds:
      "https://services7.arcgis.com/n1YM8pTrFmm7L4hs/arcgis/rest/services/" +
      "fuds/FeatureServer/1/query",
    brac:
      "https://services.arcgis.com/hRUr1F8lE8Jq2uJo/arcgis/rest/services/" +
      "milbases/FeatureServer/0/query",
    transmission:
      "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/" +
      "Electric_Power_Transmission_Lines/FeatureServer/0/query",
    powerPlant:
      "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/" +
      "Power_Plants_in_the_US/FeatureServer/0/query",
    gas:
      "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/" +
      "Natural_Gas_Interstate_and_Intrastate_Pipelines_1/FeatureServer/0/query",
    rail:
      "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/" +
      "Transportation/MapServer/9/query",
    highway:
      "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/" +
      "Transportation/MapServer/2/query",
    nfhl:
      "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query",
    nri:
      "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/" +
      "National_Risk_Index_Counties/FeatureServer/0/query",
    coalClosure:
      "https://arcgis.netl.doe.gov/server/rest/services/Hosted/" +
      "2024_Coal_Closure_Energy_Communities/FeatureServer/0/query",
    ffeArea:
      "https://arcgis.netl.doe.gov/server/rest/services/Hosted/" +
      "2024_MSAs_NonMSAs_that_are_Energy_Communities/FeatureServer/0/query",
  };

  // Point-containment query — returns the polygon this site actually falls
  // in. Strictly better evidence than an agency landing page: it is the same
  // question the connector asked, and it is verifiable rather than merely
  // reachable. (Landing pages also rot: energycommunities.gov stopped
  // resolving and hazards.fema.gov/nri now redirects into RAPT.)
  function pointQuery(base, site, extra) {
    if (site.lat == null || site.lon == null) return null;
    const lat = site.lat_real != null ? site.lat_real : site.lat;
    const lon = site.lon_real != null ? site.lon_real : site.lon;
    return q(base, Object.assign({
      geometry: `${lon.toFixed(5)},${lat.toFixed(5)}`,
      geometryType: "esriGeometryPoint",
      inSR: "4326",
      spatialRel: "esriSpatialRelIntersects",
      outFields: "*",
      returnGeometry: "false",
      f: "json",
    }, extra || {}));
  }

  function q(base, params) {
    const usp = new URLSearchParams(params);
    return `${base}?${usp.toString()}`;
  }

  // "Show me the source features near this site" — the query the connector
  // itself effectively ran, in a form a browser will render as JSON.
  //
  // The radius is derived from the site's OWN stored distance so the box is
  // always guaranteed to contain the feature the number refers to. A fixed
  // radius silently breaks this: a 10-mile box around a site whose nearest
  // gas pipeline is 14.5 mi returns zero features, and the "evidence" then
  // reads as a contradiction of the claim it is supposed to support.
  // Distances are capped at 100 mi upstream, so `needed` tops out around
  // 152 — the ceiling here exists only to bound a pathological input, never
  // to clip a real claim. An earlier 60 mi cap silently produced empty
  // results for the handful of sites 60-100 mi from their nearest feature
  // (BRAC-487's highway is 90.1 mi out), which made the evidence look like
  // it disproved the number.
  function radiusFor(site, key, floorMi) {
    const v = site[key];
    const needed = v == null ? 0 : v * 1.5 + 2;
    return Math.min(160, Math.max(floorMi, needed));
  }

  function bboxQuery(base, site, radiusMi, extra) {
    if (site.lat == null || site.lon == null) return null;
    const lat = site.lat_real != null ? site.lat_real : site.lat;
    const lon = site.lon_real != null ? site.lon_real : site.lon;
    const dLat = radiusMi / 69;
    const dLon = radiusMi / (69 * Math.max(Math.cos((lat * Math.PI) / 180), 0.05));
    return q(base, Object.assign({
      geometry: `${(lon - dLon).toFixed(5)},${(lat - dLat).toFixed(5)},` +
                `${(lon + dLon).toFixed(5)},${(lat + dLat).toFixed(5)}`,
      geometryType: "esriGeometryEnvelope",
      inSR: "4326",
      spatialRel: "esriSpatialRelIntersects",
      outFields: "*",
      returnGeometry: "false",
      f: "json",
    }, extra || {}));
  }

  function recordQuery(site) {
    if (site.program === "superfund" && site.epa_id) {
      return q(ARC.superfund, {
        where: `EPA_ID='${site.epa_id}'`, outFields: "*",
        returnGeometry: "true", outSR: "4326", f: "json",
      });
    }
    if (site.program === "brownfield") {
      const pid = String(site.id).replace(/^ACRES-/, "");
      return q(ARC.acres, {
        where: `PROPERTY_ID=${pid}`, outFields: "*",
        returnGeometry: "false", f: "json",
      });
    }
    if (site.program === "fuds") {
      const pid = String(site.id).replace(/^FUDS-/, "");
      return q(ARC.fuds, {
        where: `DODFUDSPROPERTYIDPK='${pid}'`, outFields: "*",
        returnGeometry: "true", outSR: "4326", f: "json",
      });
    }
    if (site.program === "brac") {
      const oid = String(site.id).replace(/^BRAC-/, "");
      return q(ARC.brac, {
        where: `OBJECTID=${oid}`, outFields: "*",
        returnGeometry: "true", outSR: "4326", f: "json",
      });
    }
    return null;
  }

  const PROGRAM_SOURCE = {
    superfund: {
      publisher: "US EPA",
      dataset: "NPL Superfund Site Boundaries (Public)",
      layer: "FAC_Superfund_Site_Boundaries_EPA_Public / FeatureServer / 0",
      file: D.SITES,
    },
    brownfield: {
      publisher: "US EPA",
      dataset: "All ACRES Properties",
      layer: "All ACRES Properties 8_30_2021 / FeatureServer / 0",
      file: D.ACRES,
    },
    fuds: {
      publisher: "US Army Corps of Engineers",
      dataset: "Formerly Used Defense Sites (FUDS) FY24",
      layer: "fuds / FeatureServer / 1 (points) + 4 (polygons)",
      file: D.FUDS,
    },
    brac: {
      publisher: "US Department of Defense",
      dataset: "Military Installations (BRAC_SITE='YES')",
      layer: "milbases / FeatureServer / 0",
      file: D.BRAC,
    },
  };

  // ---- the registry -------------------------------------------------------
  //
  // `derivation` is the sentence that lets a reader judge the number. Keep it
  // specific about WHAT was measured and HOW.

  const FIELD_PROVENANCE = {
    // --- identity & location, straight from the owning program ---
    name: {
      group: "Identity", label: "Site name", byProgram: true,
      derivation: "Copied from the source record, then title-cased for display "
        + "(the original is kept on name_raw).",
    },
    state: {
      group: "Identity", label: "State", byProgram: true,
      derivation: "Copied from the source record's state attribute. Populated "
        + "independently of the geometry — see the coordinate row when the two "
        + "disagree.",
    },
    city: {
      group: "Identity", label: "City / county / address", byProgram: true,
      derivation: "Copied from the source record; placeholder strings such as "
        + "\"NO CITY\" are collapsed to blank rather than displayed.",
    },
    lat: {
      group: "Location", label: "Coordinates", byProgram: true,
      derivationByProgram: {
        superfund: "Midpoint of the bounding box of the site's boundary "
          + "polygon(s) from EPA's layer. Sites split across multiple polygons "
          + "are merged by EPA_ID first.",
        brownfield: "LATITUDE_MEASURE / LONGITUDE_MEASURE copied directly from "
          + "the ACRES point record. Many are address geocodes, not surveys.",
        fuds: "Centroid of the USACE layer-4 boundary polygon where one has "
          + "been digitized; otherwise the layer-1 property point.",
        brac: "Midpoint of the bounding box of the installation polygon.",
      },
    },
    coord_flags: {
      group: "Location", label: "Location confidence", file: D.COORD,
      publisher: "This project (derived)",
      dataset: "coord-quality — computed, not sourced",
      derivation: "Point-in-polygon test against the same us-states.json this "
        + "map draws, plus checks for placeholder coordinates and shared "
        + "points. Reports only; never alters a coordinate.",
      code: "connectors/coord_quality.py",
    },
    acreage: {
      group: "Location", label: "Acreage", byProgram: true,
      derivationByProgram: {
        superfund: "GIS_AREA when EPA tags it in acres or square miles; "
          + "otherwise computed from the boundary polygon (Shoelace with a "
          + "cos-latitude correction).",
        brownfield: "Not published — the ACRES layer has no acreage column. "
          + "Any value shown comes from the matched cadastral parcel instead.",
        fuds: "Computed from the USACE layer-4 boundary polygon. Absent for "
          + "the ~66% of properties USACE has not digitized.",
        brac: "Computed from the installation polygon.",
      },
    },

    // --- infrastructure proximity: all locally computed distances ---
    transmission_mi: {
      group: "Infrastructure", label: "Transmission line",
      publisher: "HIFLD (Homeland Infrastructure Foundation-Level Data)",
      dataset: "Electric Power Transmission Lines",
      file: D.INFRA, code: "connectors/infra_proximity.py",
      derivation: "Shortest distance from this site's coordinate to any "
        + "polyline in the HIFLD layer, computed locally with a grid index "
        + "(no service call per site). Rounded to 0.1 mi; dropped beyond "
        + "100 mi. Voltage is the VOLTAGE field of the winning segment.",
      verify: (s) => bboxQuery(ARC.transmission, s, radiusFor(s, "transmission_mi", 6)),
      verifyLabel: "HIFLD transmission lines near this site",
    },
    substation_mi: {
      group: "Infrastructure", label: "Substation",
      publisher: "OpenStreetMap contributors",
      dataset: "power=substation (via Overpass API)",
      file: D.INFRA, code: "connectors/infra_proximity.py",
      derivation: "Nearest OSM substation node/way centroid. Voltage is the "
        + "OSM `voltage` tag converted from volts; values under 1 kV are "
        + "withheld as distribution gear. HIFLD's substation layer went "
        + "private in 2025, so OSM is the remaining public national source.",
      verify: (s) => (s.lat == null ? null :
        `https://www.openstreetmap.org/#map=13/${(s.lat_real ?? s.lat).toFixed(5)}/${(s.lon_real ?? s.lon).toFixed(5)}`),
      verifyLabel: "OpenStreetMap at this location",
    },
    power_plant_mi: {
      group: "Infrastructure", label: "Power plant",
      publisher: "HIFLD (EIA-860 sourced)",
      dataset: "Power Plants in the US",
      file: D.INFRA, code: "connectors/infra_proximity.py",
      derivation: "Nearest ACTIVE generating plant. HIFLD's layer contains no "
        + "retired plants — those come from EIA-860M separately.",
      verify: (s) => bboxQuery(ARC.powerPlant, s, radiusFor(s, "power_plant_mi", 8)),
      verifyLabel: "HIFLD power plants near this site",
    },
    gas_pipeline_mi: {
      group: "Infrastructure", label: "Gas pipeline",
      publisher: "HIFLD (EIA sourced)",
      dataset: "Natural Gas Interstate and Intrastate Pipelines",
      file: D.INFRA, code: "connectors/infra_proximity.py",
      derivation: "Nearest methane pipeline. Excludes the separate NGL "
        + "(propane/ethane) layer, which is irrelevant to turbine fuel.",
      verify: (s) => bboxQuery(ARC.gas, s, radiusFor(s, "gas_pipeline_mi", 8)),
      verifyLabel: "HIFLD gas pipelines near this site",
    },
    rail_mi: {
      group: "Infrastructure", label: "Rail",
      publisher: "US Census Bureau",
      dataset: "TIGERweb Railroads",
      file: D.INFRA, code: "connectors/infra_proximity.py",
      derivation: "Nearest rail polyline. Includes spurs and yard track, not "
        + "just mainline.",
      verify: (s) => bboxQuery(ARC.rail, s, radiusFor(s, "rail_mi", 6)),
      verifyLabel: "TIGER rail lines near this site",
    },
    highway_mi: {
      group: "Infrastructure", label: "Highway",
      publisher: "US Census Bureau",
      dataset: "TIGERweb Primary Roads (MTFCC S1100)",
      file: D.INFRA, code: "connectors/infra_proximity.py",
      derivation: "Nearest primary road — Interstates plus major US/state "
        + "routes. Secondary roads are deliberately excluded.",
      verify: (s) => bboxQuery(ARC.highway, s, radiusFor(s, "highway_mi", 8), { where: "MTFCC='S1100'" }),
      verifyLabel: "TIGER primary roads near this site",
    },
    flood_zone: {
      group: "Infrastructure", label: "Flood zone",
      publisher: "FEMA",
      dataset: "National Flood Hazard Layer, Flood Hazard Zones (layer 28)",
      file: D.INFRA, code: "connectors/infra_proximity.py",
      derivation: "Point-in-polygon queried per site against FEMA's live "
        + "service. Absent means the site lies outside any mapped FEMA study "
        + "area — which is not the same as 'no flood risk'.",
      verify: (s) => bboxQuery(ARC.nfhl, s, 1),
      verifyLabel: "FEMA NFHL zones at this location",
      // A site outside every mapped FEMA study area correctly returns none.
      expectsFeatures: (s) => s.flood_zone != null,
    },
    retired_plant_mi: {
      group: "Infrastructure", label: "Retired plant",
      publisher: "US Energy Information Administration",
      dataset: "Form EIA-860M, Retired sheet",
      file: D.RETIRED, code: "connectors/eia_retired_plants.py",
      derivation: "Nearest retired plant of at least 100 MW on a dispatchable "
        + "fuel, within 5 mi. MW is summed across the plant's retired units.",
      url: "https://www.eia.gov/electricity/data/eia860m/",
      verifyLabel: "EIA-860M monthly inventory",
    },
    planned_retirement_mi: {
      group: "Infrastructure", label: "Retiring plant",
      publisher: "US Energy Information Administration",
      dataset: "Form EIA-860M, Operating sheet (Planned Retirement Year)",
      file: D.PLANNED, code: "connectors/planned_retirements.py",
      derivation: "Nearest operating plant of at least 100 MW with an "
        + "announced retirement date, within 5 mi. Announced dates slip.",
      url: "https://www.eia.gov/electricity/data/eia860m/",
      verifyLabel: "EIA-860M monthly inventory",
    },

    // --- programmatic / financial overlays ---
    in_opportunity_zone: {
      group: "Incentives", label: "Opportunity Zone",
      publisher: "US Department of Housing and Urban Development",
      dataset: "Qualified Opportunity Zones (8,765 tracts)",
      file: D.OZ, code: "connectors/opportunity_zone.py",
      derivation: "Point-in-polygon against the designated QOZ census tracts.",
      expectsFeatures: (s) => s.in_opportunity_zone === true,
      verify: (s) => (s.oz_tract_geoid
        ? `https://www.arcgis.com/apps/mapviewer/index.html?layers=f4cd55044b924fed9bc8b64022966097#tract=${s.oz_tract_geoid}`
        : null),
      verifyLabel: "HUD Opportunity Zone map",
    },
    in_energy_community: {
      group: "Incentives", label: "IRA energy community",
      publisher: "US DOE / NETL",
      dataset: "2024 Coal Closure + MSA/non-MSA Energy Communities",
      file: D.IRA, code: "connectors/ira_energy_community.py",
      derivation: "Point-in-polygon against the coal-closure tract layer "
        + "(tract level, takes precedence) and the fossil-fuel-employment "
        + "area layer (county level). The statutory brownfield category is "
        + "deliberately NOT asserted.",
      verify: (s) => pointQuery(
        s.energy_community_type === "fossil_fuel_employment" ? ARC.ffeArea : ARC.coalClosure,
        s),
      verifyLabel: "DOE NETL energy-community polygon at this point",
      expectsFeatures: (s) => s.in_energy_community === true,
    },
    in_aiannha_area: {
      group: "Environmental", label: "Tribal-area context",
      publisher: "US Census Bureau",
      dataset: "TIGERweb American Indian, Alaska Native, and Native Hawaiian Areas",
      file: D.TRIBAL, code: "connectors/tribal_areas.py",
      derivation: "Point-in-polygon against six TIGERweb AIANNHA layers. "
        + "This is mapped consultation-planning context, not land title and "
        + "not a determination of which governments an agency must consult.",
      url: "https://tigerweb.geo.census.gov/tigerwebmain/TIGERweb_restmapservice.html",
      verifyLabel: "Census TIGERweb AIANNHA service",
    },
    county_construction_employment: {
      group: "Community", label: "County workforce context",
      publisher: "US Census Bureau",
      dataset: "2024 ACS 5-Year Selected Economic Characteristics (DP03)",
      file: D.WORKFORCE, code: "connectors/census_workforce.py",
      derivation: "County civilian labor force (DP03_0003E), construction-industry "
        + "employment (DP03_0034E), and median household income (DP03_0062E) "
        + "joined by normalized state and county. County context is not a "
        + "project labor-availability study.",
      url: "https://www.census.gov/data/developers/data-sets/acs-5year.html",
      verifyLabel: "Census ACS 5-Year API documentation",
    },
    nri_risk_rating: {
      group: "Risk", label: "Natural-hazard risk",
      publisher: "FEMA",
      dataset: "National Risk Index (county level)",
      file: D.NRI, code: "connectors/fema_nri.py",
      derivation: "County-level composite and per-hazard ratings joined by "
        + "point-in-polygon. Ratings are FEMA's own national-percentile "
        + "buckets, carried verbatim rather than re-derived.",
      verify: (s) => pointQuery(ARC.nri, s),
      verifyLabel: "FEMA NRI county record for this point",
    },
    iso_rto: {
      group: "Risk", label: "ISO / RTO",
      publisher: "EIA / HIFLD",
      dataset: "Regional transmission organization boundaries",
      file: D.ISO, code: "connectors/iso_rto.py",
      derivation: "Point-in-polygon against RTO service-territory polygons.",
    },
    climate_zone: {
      group: "Risk", label: "Climate zone",
      publisher: "US DOE / PNNL",
      dataset: "Building America IECC climate zones by county",
      file: D.CLIMATE, code: "connectors/climate_zone.py",
      derivation: "County-level IECC/ASHRAE zone joined by point-in-polygon.",
    },

    // --- status, ownership, documents ---
    current_owner: {
      group: "Ownership", label: "Current owner",
      publisher: "Varies — see the owner-source row on the record",
      dataset: "USACE FUDS attribute, or a statewide cadastral parcel layer",
      file: D.PARCEL, code: "connectors/parcel_owner.py",
      derivation: "FUDS publishes an owner category directly. For other "
        + "programs the site's coordinate is matched into a statewide parcel "
        + "polygon (11 states so far) and the assessor's owner name is used. "
        + "Never overwrites an owner the program itself supplied.",
    },
    enforcement: {
      group: "Status", label: "Enforcement history",
      publisher: "US EPA",
      dataset: "ECHO (Enforcement & Compliance History Online)",
      file: D.ECHO, code: "connectors/epa_echo.py",
      derivation: "Facility summary retrieved by EPA program ID: inspections, "
        + "formal and informal actions, and penalties over the trailing "
        + "5 years. Zero is a real value, not a gap.",
      verify: (s) => (s.enforcement && s.enforcement.dfr_url) || null,
      verifyLabel: "ECHO Detailed Facility Report",
    },
    documents: {
      group: "Status", label: "Federal documents",
      publisher: "US EPA",
      dataset: "SEMS / CUMULIS public document collections",
      file: D.DOCS, code: "connectors/epa_superfund_docs.py",
      derivation: "Curated public collections (EPA doctype SC) for the site. "
        + "Administrative-record dockets (type AR) are excluded as high "
        + "volume and low signal. Each document links to its own PDF.",
      verify: (s) => (s.profile_url || null),
      verifyLabel: "EPA site profile",
    },
    cleanup_status: {
      group: "Status", label: "Cleanup status",
      publisher: "US EPA",
      dataset: "ACRES cleanup + grant history",
      file: D.CLEANUP, code: "connectors/epa_acres_cleanup.py",
      derivation: "Cleanup activity status and EPA brownfield grant awards. "
        + "Coverage is very sparse — the public ACRES cleanup layer holds "
        + "only ~110 of 36,003 properties.",
    },
    data_center_reuse_candidate: {
      group: "Status", label: "EPA reuse screening",
      publisher: "US EPA",
      dataset: "Superfund Redevelopment (RE-Powering) site points",
      file: D.REDEV, code: "connectors/epa_redev.py",
      derivation: "EPA's own qualitative proximity flags. The data-center "
        + "candidate flag is computed from them: near electric transmission, "
        + "inside a water service area, and at least 50 acres.",
      verify: (s) => (s.profile_url || null),
      verifyLabel: "EPA site profile",
    },
    summary: {
      group: "Status", label: "Plain-English summary",
      publisher: "This project (generated)",
      dataset: "ai-summary — composed from the fields above",
      file: D.SUMMARY, code: "connectors/ai_summary.py",
      derivation: "Assembled deterministically from the structured fields "
        + "already on this record. It introduces no facts of its own; every "
        + "claim in it traces to a row in this table.",
    },
  };

  // ---- assembly -----------------------------------------------------------

  function asOf(file) {
    // Resolve the global lazily: in the browser this is `window`, under node
    // (tests, the link checker) there is none and every row simply has no
    // as-of date, which is correct — nothing has been fetched there.
    const g = typeof window !== "undefined" ? window : globalThis;
    const dates = (g && g.__sourceDates) || {};
    return (file && dates[file]) || null;
  }

  function hasValue(site, key) {
    if (key === "lat") return site.lat != null;
    if (key === "city") return !!(site.city || site.county || site.address);
    if (key === "coord_flags") return Array.isArray(site.coord_flags) && site.coord_flags.length > 0;
    const v = site[key];
    if (v == null) return false;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === "object") return Object.keys(v).length > 0;
    return true;
  }

  /**
   * Evidence rows for one site — only for fields the site actually carries,
   * so the panel never cites a source for a value that isn't shown.
   */
  function buildEvidence(site) {
    if (!site) return [];
    const rows = [];
    for (const [key, spec] of Object.entries(FIELD_PROVENANCE)) {
      if (!hasValue(site, key)) continue;

      let publisher = spec.publisher;
      let dataset = spec.dataset;
      let layer = spec.layer;
      let file = spec.file;
      let derivation = spec.derivation;
      let verifyUrl = null;
      let verifyLabel = spec.verifyLabel;

      if (spec.byProgram) {
        const ps = PROGRAM_SOURCE[site.program];
        if (ps) {
          publisher = ps.publisher;
          dataset = ps.dataset;
          layer = ps.layer;
          file = ps.file;
        }
        verifyUrl = recordQuery(site);
        verifyLabel = "This record in the source service";
        if (spec.derivationByProgram) {
          derivation = spec.derivationByProgram[site.program] || derivation;
        }
      } else if (typeof spec.verify === "function") {
        try { verifyUrl = spec.verify(site); } catch { verifyUrl = null; }
      } else if (spec.url) {
        verifyUrl = spec.url;
      }

      rows.push({
        key,
        // Whether the verification link SHOULD return data. A negative claim
        // ("not in an Opportunity Zone") is evidenced by an empty result, so
        // a link checker must not read that as a dead citation.
        expectsFeatures: typeof spec.expectsFeatures === "function"
          ? !!spec.expectsFeatures(site)
          : true,
        group: spec.group,
        label: spec.label,
        publisher,
        dataset,
        layer: layer || null,
        derivation,
        file: file || null,
        asOf: asOf(file),
        code: spec.code || null,
        verifyUrl,
        verifyLabel: verifyUrl ? (verifyLabel || "Verify at source") : null,
      });
    }
    return rows;
  }

  // Browser: attach to window, which is what app.js reads. Node: export
  // normally so tests and the link checker can `require()` this file instead
  // of eval-ing its source — a validation tool should not need `new
  // Function` to read the module it is validating.
  const root = typeof window !== "undefined" ? window : globalThis;
  root.FIELD_PROVENANCE = FIELD_PROVENANCE;
  root.buildEvidence = buildEvidence;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { FIELD_PROVENANCE, buildEvidence };
  }
})();
