# Infrastructure accuracy review — 2026-09-08

Asked of the nickel-refinery candidate sites specifically, but the answer is
corpus-wide. Three separate questions get three different answers, and they are
worth keeping apart:

1. Are the infrastructure distances we already publish **correct**?
2. What is **missing** that a metallurgical siting screen needs?
3. Which gaps are **fixable** and which are source-side dead ends?

---

## 1. What we publish is correct: 96 of 96 re-measurements reproduce

`scripts/validate_against_sources.py --only infra` does not trust our spatial
index. For each sampled site it asks the **source layer** for the features
inside a bounding box around the site and recomputes the minimum distance
locally. It is the only check that can falsify `transmission_mi` and friends.

Run over 24 Michigan and Maine sites that pass a rail-and-transmission
pre-screen — 4 fields each, 96 checks:

| Field | Source re-queried | Result |
|---|---|---|
| `transmission_mi` | HIFLD Electric Power Transmission Lines | 24/24 OK |
| `highway_mi` | Census TIGERweb primary roads (MTFCC S1100) | 24/24 OK |
| `rail_mi` | Census TIGERweb railroads | 24/24 OK |
| `gas_pipeline_mi` | HIFLD natural gas pipelines | 24/24 OK |

**Every delta was ≤ 0.05 mi**, which is the rounding floor: the stored value is
rounded to 0.1 mi, so 0.04 is agreement, not error. Examples:
`ACRES-215841` (the Bucksport Verso mill) stored transmission 0.0 against a
re-measured 0.04 from 9 source features; `ACRES-129141` stored rail 0.0 against
0.01 from 456 features.

A second pass over the **32 top-ranked nickel candidates** in both states ran
both families:

* **Attribute round-trip: 32/32 OK.** Name, state, coordinates and acreage
  re-queried from each site's owning FeatureServer all match what we shipped.
* **Infra re-measurement: 119/128 OK, 0 failures, 9 skipped.** The nine skips
  are the validator's own guard, not a disagreement — eight Upper Peninsula
  sites store a highway distance of 53–56 miles, and one stores 27.7 miles to
  a gas pipeline, which need a bounding box larger than the tool will fetch.
  Those are genuinely remote sites; the stored values are plausible and simply
  were not independently confirmed.

**So the answer on power, rail, road and gas is: verified, not assumed.** The
weakness is not in the four fields anyone would suspect.

## 2. Coverage, which is a different question from correctness

Percentage of sites carrying a non-null value:

| Field | Nationwide | Michigan | Maine |
|---|---|---|---|
| `transmission_mi` | 98.8% | 100% | 99.4% |
| `substation_mi` | 99.1% | 100% | 100% |
| `rail_mi` | 98.3% | 100% | 100% |
| `highway_mi` | 97.1% | 98.7% | 100% |
| `gas_pipeline_mi` | 96.2% | 100% | 92.9% |
| `power_plant_mi` | 99.4% | 100% | 100% |
| `flood_zone` | 91.1% | 92.7% | 81.7% |
| **`water_flow_cfs`** | **98.3% (was 0%)** | **100%** | **100%** |
| **`acreage`** | **10.4%** | **4.3%** | **8.4%** |
| **`parcel_acreage`** | 9.9% | **0%** | **0%** |

The infrastructure layers are near-complete. The two rows in bold are the
story.

## 3. Water was never collected. It is now.

Every layer this project had collected moved electrons, freight or fuel. There
was no water layer at all. The only water fields on a record were
`near_water_supply` and `near_water_body` — qualitative EPA RE-Powering strings
("Yes - 1 mile") covering ~1,905 Superfund sites, **4% of the corpus and none
of the brownfields**.

That is a real hole for this project's own purposes, not just for nickel: the
Nuclear Siting tab weights water **40 of 100** and meets it with analyst
research over 14 curated installations, because no national layer answered the
question.

**Closed this pass** — `scripts/build_streamgages_overlay.py` →
`connectors/water_proximity.py`: active USGS streamgages carrying a published
mean annual discharge, joined to every site within 50 miles.

Two caveats that belong on every surface rendering it, and are:

* **`water_flow_cfs` is a long-run annual mean, not a permittable low flow.**
  A withdrawal permit is written against a 7Q10 drought statistic, routinely an
  order of magnitude lower on a flashy river. The number screens a candidate
  and never clears one.
* **`water_gage_mi` is distance to a gage, not to water.** Gages sit tens of
  miles apart on a large river, so a bank-side site can read several miles out,
  and a Great Lakes shoreline site with no nearby gage reads as nothing in
  range. Fixing that needs a waterbody layer, which is in the backlog with the
  feature counts already probed.

## 4. Acreage is the weakest field, and it blocks a land threshold

A nickel refinery needs roughly 300–500 acres. Michigan has acreage on **153 of
3,571 sites** and Maine on **75 of 898** — and neither state is in the parcel
registry, so `parcel_acreage` is **zero** in both. The Nickel Refining tab's
land test therefore reads "Unknown" for nearly every Michigan and Maine row.

That is disclosed rather than papered over: `nickelAcreageStatus()` is
tri-state, and a null renders as "Unknown", never as a failed threshold.
Reading null as "too small" would silently delete most of the corpus from the
lens; reading it as "big enough" would invent a fact.

**Partly fixable.** Maine publishes a statewide parcel layer — MEGIS
`Maine_Parcels_Organized_Towns`, 708,382 polygons, no token — with **no owner
field** but a `Shape__Area` in real metres that converts cleanly to acres.
Maine is the mirror image of the Iowa owner-only exception: an *acreage-only*
state, which `connectors/parcel_owner.py`'s registry has no path for today.
Filed in the backlog. Michigan stays blocked — no statewide parcel layer
exists at all.

## 5. Fiber: not a gap we can close

No public source ships fiber backbone as polylines. HIFLD's `Long_Haul_Fiber`
layer went private in the 2025 reorganization; the FCC National Broadband Map
gives binary "fiber served at this address" at ~80 GB bulk; OSM's `cable=fiber`
covers under 10% of the US backbone. This was investigated in v1.13.3 and the
conclusion has not changed. It is disclosed as unassessed, the same treatment
bathymetry gets on the Maritime tab and seismic gets on the microreactor lens.

## 6. Known upstream problems, unchanged

`scripts/validate_data.py` reports these as WARN rather than FAIL because EPA
and USACE control the data, not us:

* **118 sites sit more than a mile outside their own `state` polygon**, 13 of
  them by more than 25 miles. The `coord-quality` connector labels these rather
  than correcting them — the state attribute and the geometry come from
  independent paths inside the source, and we have no better third source.
* **3,728 sites share a coordinate with another site**, mostly address-level
  geocodes that collapsed to a municipal centroid.
* **6,222 sites report a substation closer than their nearest transmission
  line**, which is impossible. That is HIFLD's public feed being patchy on
  sub-transmission, and all three existing lenses plus both nickel lenses
  correct for it by letting the substation stand in as the interconnect point.

None of these is new, and none is introduced by this pass.

## 7. One defect found in this pass's own new code

The nickel-anchor join initially reused `connectors.spatial.PointIndex`, as
every other proximity connector does. A brute-force haversine cross-check
found two problems that only appear at continental range:

* **Up to 18.9 miles of projection error.** `PointIndex` measures with the
  local-equirectangular projection whose "better than 1% in CONUS" bound was
  written for the sub-100-mile queries it was built for. One percent of 900
  miles is nine miles.
* **False nulls at the cap.** Ring expansion gave up before reaching an anchor
  992 miles away and emitted "nothing within 1,000 miles".

With sixteen anchors an index buys nothing: 46,759 x 16 haversine evaluations
run in about a second and are exact. After the switch, the largest deviation
across 200 samples is 0.050 miles — the rounding floor — and there are no
false nulls in 40 sampled. Worth stating because the instinct to reuse the
existing index was the wrong one, and only a check outside the index could
show it.
