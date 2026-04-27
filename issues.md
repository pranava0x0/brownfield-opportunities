# Issues

| Date | Area | Description | Root cause | Status |
|------|------|-------------|------------|--------|
| 2026-04-27 | refresh.py | EPA Envirofacts SEMS tables (`SEMS_ACTIVE_SITES`, `SEMS_NPL`) return "table not available". | EPA data source path: switched to the EPA-hosted ArcGIS FeatureServer (`FAC_Superfund_Site_Boundaries_EPA_Public`) instead. | Fixed |
| 2026-04-27 | data | ~Some Superfund features carry `GIS_AREA_UNITS` of `Miles` (linear features) or `null`. | Source data quality. | Open — currently filtered out; backlog item to surface them with "N/A" acreage. |
| 2026-04-27 | frontend | Local preview blocked by sandbox (`docs/serve.py` not permitted to run). | Sandbox permission. | Open — does not affect production; verified on GH Pages. |
| 2026-04-27 | deploy | `gh` token lacks `workflow` OAuth scope — `.github/workflows/deploy.yml` and `refresh.yml` exist locally but are not committed/pushed. Pages currently deploys via legacy `main:/docs` source instead of the deploy Action; `refresh.py` cron is not running. | Auth scope. | Open — run `gh auth refresh -h github.com -s workflow` then push the staged workflow files. |
| 2026-04-27 | frontend | Site never opened in a real browser during the build (sandbox blocked local server, Pages live URL not visually inspected). Tabs, markers, and side-panel interactions are unverified. | Tooling. | Open — needs a manual smoke test or a Playwright UAT pass. Mobile bottom-sheet detail panel and CARTO dark tile swap (2026-04-27) also unverified in a real browser. |
| 2026-04-27 | frontend | `app.js` had a `let map` (Leaflet) shadowed by `const map = el("tab-map")` inside `wireTabs()` — caught and fixed during the build, no test covers it. | Code bug. | Fixed — backlog item: regression test. |
| 2026-04-27 | frontend | `docs/serve.py` (local dev shim) ships to GitHub Pages because the deploy source is the entire `docs/` directory. It's never referenced from `index.html` so it's harmless dead weight, but violates "never ship dev files to production." | Build hygiene. | Open — move to repo root or exclude from deploy. |
