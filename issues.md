# Issues

| Date | Area | Description | Root cause | Status |
|------|------|-------------|------------|--------|
| 2026-04-27 | refresh.py | EPA Envirofacts SEMS tables (`SEMS_ACTIVE_SITES`, `SEMS_NPL`) return "table not available". | EPA data source path: switched to the EPA-hosted ArcGIS FeatureServer (`FAC_Superfund_Site_Boundaries_EPA_Public`) instead. | Fixed |
| 2026-04-27 | data | ~Some Superfund features carry `GIS_AREA_UNITS` of `Miles` (linear features) or `null`. | Source data quality. | Open — currently filtered out; backlog item to surface them with "N/A" acreage. |
| 2026-04-27 | frontend | Local preview blocked by sandbox (`docs/serve.py` not permitted to run). | Sandbox permission. | Open — does not affect production; verified on GH Pages. |
