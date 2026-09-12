# Grid source rebuild and validation — 2026-09-12

Infrastructure was recalculated against the refreshed core site coordinates. Existing raw infrastructure snapshots were reused; this is not a fresh nationwide infrastructure survey. All 46,759 site IDs remain covered by an observation record.

| Observation | Before | After | Newly available matches |
|---|---:|---:|---|
| Transmission distance | 46,211 | 46,237 | 26 Alaska sites |
| Transmission voltage | 46,211 | 46,237 | Reported numeric voltage only |
| Substation distance | 46,328 | 46,349 | 21 Alaska sites |
| Substation voltage | 34,042 | 34,048 | 12,301 matched substations still lack voltage |
| Power plant distance | 46,496 | 46,514 | 14 Alaska, 4 Montana sites |
| Power plant summer capacity | 46,492 | 46,510 | Not available connection capacity |

The physical search radius is now 100 miles at every latitude. Antimeridian queries wrap correctly; crossing polylines are split instead of creating a line across the world. The cache rebuild processes one layer at a time and optionally uses installed NumPy. Independent brute-force comparisons, high-latitude fixtures, long segments, exact-radius boundaries and antimeridian cases verify the accelerated calculation. Pure Python remains available.

## Source completeness and provenance

Cached feature inventories: 52,244 transmission lines; 17,612 primary-road features; 111,627 rail features; 32,892 gas-pipeline features; 13,446 plant points. Transmission and plant counts matched live service counts during the audit. Matching counts do not certify identical feature membership: legacy geometry-only caches lack original feature IDs. Their IDs explicitly say `local:` and their provenance says `local_geometry_fingerprint`.

The OSM snapshot is **2026-05-17T21:31:28Z** at its oldest regional cut. Its 77,967 elements contain two repeated IDs. After deduplication and excluding 90 gas/valve/compression/other plainly unrelated tags, 77,875 points remain. Matched roles include 3,509 transmission, 17,558 distribution, 2,865 minor distribution, 488 traction and 18,048 unspecified. These roles are not interchangeable evidence of interconnection suitability. Cached queries cover nodes and ways; relations and GU/MP/AS coverage remain incomplete. Unsupported point locations have an explicit status.

Exact live service metadata reports transmission data last edited **2023-09-05** and plant data last edited **2025-07-01**. These are service metadata dates, not recovered acquisition timestamps for our historical caches. Unknown cache retrieval dates remain unknown in the shipped metadata. `generated_at` records recalculation time. Full fresh ArcGIS pulls check source counts, stable object IDs, repeated pages, transfer-limit continuation and error bodies. Legacy cached pulls remain marked `count_reconciled: false`.

FEMA values were retained as historical observations with unknown acquisition dates. They were not refreshed; the coordinate-invalidation manifest separately clears observations affected by moved points. Future flood seeding requires matching coordinates and an observation no older than 365 days. Missing or incomplete coverage never establishes off-grid status or hazard clearance.

## EIA update

Both retired and planned-retirement producers now use the actual published **July 2026** workbook, released August 26. The shared cache key includes its URL, preventing April bytes from receiving July labels. Discovery reads EIA's published links rather than guessing archive paths.

- Retired plants qualifying for this screen: 466 → 468; nearby site joins: 7,620 → 7,622.
- Planned overlay: 90 → 94 plants; 75,573 → 76,545 MW of announced retiring units.
- Planned-retirement site joins: 614 → 677.

These are preliminary inventory and announcement data, not transferable interconnection rights or capacity commitments.

## Bounded live checks

[Machine-readable results](infra-live-validation-2026-09-12.json) record **8/8 PASS**: six independent live transmission-distance comparisons, including three newly recovered Alaska matches at 97.5, 94.5 and 88.4 miles; and two live OSM role checks confirming minor-distribution and traction equipment. All six distance errors were below 0.05 mile. This sample does not certify nationwide completeness or independently validate every plant point.

The final infrastructure file is **28,614,426 bytes raw / 2,498,819 bytes gzip**. Asset metadata and plant names are shared in envelope lookup maps. Per-site asset IDs, equipment roles, exception statuses and assessed coordinates remain available.

## Primary references

- [Transmission service](https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer/0)
- [Plant service and capacity definitions](https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Power_Plants_in_the_US/FeatureServer/0)
- [OSM substation roles](https://wiki.openstreetmap.org/wiki/Key:substation)
- [EIA-860M inventory and preliminary-data limits](https://www.eia.gov/electricity/data/eia860m/)
