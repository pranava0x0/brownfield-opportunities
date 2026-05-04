# Brownfield Opportunities

Static dashboard of EPA Superfund + ACRES brownfield + USACE FUDS + DOD BRAC sites — map and table view with filters, site-level detail, CSV export, and shareable URL state. Designed to live on GitHub Pages and refresh via a one-command CLI.

**Live:** https://pranava0x0.github.io/brownfield-opportunities/

## What's in v1.9 (federal acreage / ownership / documents enrichment)

Two new federal data paths land per-site acreage, current owner, and related documents that were previously gaps:

- **FUDS polygon acreage.** `connectors/dod_fuds.py` now joins layer 1 (points, ~10k properties) with layer 4 (polygons, ~3k boundaries) of the USACE FUDS FeatureServer, computing acreage from the polygon geometry via Shoelace + cos(latitude). ~3k previously-null FUDS records gain accurate acreage; affected records also get a polygon-centroid lat/lon (more accurate than the point representation for properties spanning miles).
- **Per-site owner provenance.** Schema gains `current_owner_source` so the detail panel can cite where the owner came from (today: "USACE FUDS"; future: ACRES PPF, Regrid, etc.). FUDS records that already carried a `CURRENTOWNER` value now also carry the citation label.
- **EPA Superfund federal documents.** New `connectors/epa_superfund_docs.py` enrichment connector walks three hops to assemble a per-site list of curated public documents (RODs, ESDs, Five Year Reviews, fact sheets, technical reports) from EPA's SEMS infrastructure: (1) EPA pretty page → SF_SITE_ID, (2) cumulis docdata → collection IDs, (3) `semspub.epa.gov/src/cachejson/...` → document records. Output writes to `docs/data/epa-superfund-docs.json`; the frontend lazy-loads and joins by EPA_ID.
- **Detail panel: Federal documents block.** When a Superfund site has been enriched, the detail panel renders a "Federal documents" section with title + date + collection category + size + page count, plus an "All site documents on EPA →" deep-link to the canonical SEMS docdata page for full coverage.
- **Resumable batched coverage.** The Superfund docs connector defaults to `--docs-limit 100` (largest Final/Deleted-NPL sites first). Re-runs are cheap (everything cached); future batches use `--docs-skip 100 --docs-limit 100` to stripe coverage across the ~1,800-site Final/Deleted-NPL universe without re-fetching.

## What's in v1.6 (UAT 2026-04-29 fixes)

- **Cold-load freeze fixed.** ACRES marker hydration is now chunked via `requestIdleCallback` (800 markers per tick), so DOM-interactive lands in ~30 ms even with both programs on. Previously the main thread froze for 30+ s.
- **Paginated table.** The table paginates at 250 rows with an IntersectionObserver-driven sentinel that auto-appends the next page on scroll. Total DOM nodes dropped from ~265k to ~2,700.
- **Auto-fit map on filter narrow.** Searching a single site or filtering a single state now zooms the map to the visible bbox instead of leaving the lower-48 view active.
- **NPL Status checkboxes** (replaces the trap-door `<select multiple>`) and **state dropdown with full names** (sorted by full name, territories grouped under `<optgroup label="Territories">`).
- **Acreage slider with tick labels** (1 / 10 / 100 / 1k / 10k / 100k / 1M).
- **Toast for unknown `?site=<id>`** instead of silently opening an empty detail panel.
- **Cleaner copy** in the detail panel — no more "N/A — see backlog" or "Code Not a Federal Facility".
- **A11y additions** — skip-to-content link, toolbar `<nav>` landmark, `<main id="main">` skip target, detail panel `aria-hidden` synced to its `hidden` attr.
- **Detail panel actually hides on close** (was leaving a sliver of stale text on the right edge from a CSS specificity bug).
- **Non-CONUS state polygons masked** — Alaska / Hawaii / Puerto Rico no longer render at their real coords while their markers sit in the inset boxes.
- **Counties auto-load** on direct deep-zoom entry (via `?site=` or marker auto-zoom), not just on user-initiated zoom-in past 7.
- **Programmatic ready signal.** `window.__APP_READY__ = true` and `brownfield:ready` event fire after both programs hydrate — automation no longer has to poll header text or network status.

## What's in v1.4

- **Continental-US-focused map.** `maxBounds` and `minZoom` are tightened so the lower 48 dominates the basemap — no more Canada/Mexico filling the screen at first paint. The map fits to bounds at init so the view adapts to viewport size.
- **Cartographic insets for AK / HI / PR / VI / Pacific territories.** Records from those states/territories are linearly remapped into labeled boxes along the bottom of the map (classic US-map-with-insets layout: ALASKA, HAWAII, PR / USVI, GU / MP / AS). The detail panel and CSV export still show the real geographic coordinates — only the marker placement is remapped. Adding a new state/territory to an inset is one edit in `INSETS` in `docs/app.js`.

## What's in v1.2

- **All 1,908 unique NPL Superfund sites** (multi-polygon sites merged by EPA_ID; ~200 with non-areal geometry surfaced in an "N/A acreage" bucket).
- **36,003 EPA ACRES brownfield properties** loaded lazily — both programs are on by default, but Superfund paints first (~170KB gzipped) and brownfields stream in over the wire afterwards.
- **Map view (default)** with Canvas-rendered markers, sized by acreage (log scale), colored **by program** (Superfund vs. Brownfield). NPL-status detail lives in the table pill and detail panel.
- **Two-tier basemap.** At low zoom the map shows just landmasses + the US silhouette — labels (states / counties / cities) only render once the user zooms in past zoom 5, so the first view stays clean and US-focused.
- **Program-based legend.** The in-map legend has one row per program and only shows rows that exist in currently-loaded data (Superfund first paint → Brownfield row appears once the lazy fetch completes).
- **Table view** with sortable columns and a Program column.
- **Filters strip** (toggle from the toolbar): program (Superfund / Brownfield checkboxes — both on by default), state, NPL status (multi-select), minimum acreage (log slider). Plus the existing free-text search. All filters operate on both the table and the map markers.
- **Filtered summary.** Whenever a filter is active the search-count surface displays `N of M [in <state>] · X total ac` so you get a per-state (or per-filter) "# sites / total acres" roll-up at a glance.
- **URL state sharing.** `?site=<ID>` deep-links to a site; `?q=<text>`, `?state=NY`, `?status=F,P`, `?program=brownfield`, `?min_ac=2` round-trip via `history.replaceState`. Legacy `?epa_id=` still works.
- **CSV export** of the currently-filtered set (date-stamped filename).
- **Theme toggle** (light/dark) with `localStorage` persistence; honors `prefers-color-scheme` on first visit. Markers + legend re-stylize on swap.
- **Sub-site surfacing.** Status-A NPL sub-sites that get rolled up under a parent now appear as a "Sub-sites" list on the parent's detail panel.
- **US-only.** `maxBounds` and `minZoom` constrain the map to continental US; AK / HI / PR / VI / Pacific territories appear as inset boxes (see v1.4 above).
- **Marker decimation at low zoom.** At zoom ≤4 we render 1 in 8 markers, ≤5 keeps 1 in 4, ≤6 keeps 1 in 2, ≥7 shows all. Stable hash-based sampling so the visible subset doesn't flicker on zoom.
- **Mobile-friendly:** detail panel becomes a bottom sheet on phones; tap targets sized for touch; tiles preconnected and `sites.json` preloaded for fast first paint.
- **Dynamic code labels.** NPL status and federal-facility codes are decoded from the layer's coded-value domain at refresh time — no risk of going stale.
- **Sources:**
  - [EPA NPL Superfund Site Boundaries (Public)](https://hub.arcgis.com/datasets/EPA::npl-superfund-site-boundaries-epa-public-2022/about) ArcGIS FeatureServer.
  - [EPA ACRES Brownfield Properties](https://www.epa.gov/cleanups/assessment-cleanup-and-redevelopment-exchange-system-acres) (`All ACRES Properties 8_30_2021` ArcGIS FeatureServer).

Owner / encumbrance / infrastructure-proximity data is deferred. See [`backlog.md`](backlog.md) for the data-center-opportunity pivot and the data sources that would feed it.

## Refresh the data

```bash
pip install -r requirements.txt
python refresh.py --list-sources                   # show registered connectors
python refresh.py                                  # default: Superfund only → docs/data/sites.json
python refresh.py --source epa-acres               # ACRES → docs/data/epa-acres.json
python refresh.py --source dod-fuds                # FUDS (point + polygon join) → docs/data/dod-fuds.json
python refresh.py --source epa-superfund-docs --docs-limit 100  # docs enrichment, 100 sites/batch
python refresh.py --source epa-superfund-docs --docs-limit 100 --docs-skip 100  # next 100
python refresh.py --all                            # all connectors, plus mirror Superfund → sites.json
python refresh.py --all --combined                 # also write a single fat sites.json (~2MB gz)
python refresh.py --source superfund-npl --no-cache
python refresh.py --source superfund-npl --dry-run # use only cached responses
python refresh.py --pretty                         # pretty-printed JSON (default is minified)
```

Output:
- `docs/data/sites.json` — canonical fast-path file the frontend loads first (~170KB gzipped, Superfund only)
- `docs/data/superfund-npl.json` — same as `sites.json`, written by `--all`
- `docs/data/epa-acres.json` — ACRES brownfields, lazy-loaded by the frontend (~1.5MB gzipped)
- `docs/data/dod-fuds.json` — USACE FUDS (~8.8k records, ~4MB), 3k now carry polygon-derived acreage
- `docs/data/dod-brac.json` — DOD BRAC installations (27 records, polygon-derived acreage)
- `docs/data/epa-redev.json` — Superfund Redevelopment infrastructure-proximity enrichment
- `docs/data/epa-superfund-docs.json` — per-EPA_ID list of related federal documents (RODs, ESDs, etc.); merged client-side by `ensureSuperfundDocsLoaded()`
- `data/changes.md` — diff vs prior run (canonical file only)

The script is idempotent: re-runs hit a local cache (`data/cache/`) until you pass `--no-cache`. JSON is minified by default and skips null fields; `exclude_none=True` keeps the per-record overhead small.

### Adding a new data source

The fetch logic lives in `connectors/`. Each source is one file with a class that subclasses `Connector`:

```python
# connectors/my_source.py
from connectors.base import Connector

class MySource(Connector):
    slug = "my-source"
    source_label = "Human-readable label"
    source_url = "https://example.com/about"

    def fetch_records(self, args, use_cache):
        # call self.http_get_json(...) — caching + rate-limiting are handled
        # return list of dicts matching schema.SiteRecord
        # MUST set 'id' and 'program' on every record.
        ...
```

Then register it in `connectors/__init__.py`:

```python
from connectors.my_source import MySource
register("my-source", MySource)
```

Run with `python refresh.py --source my-source`.

## Local preview

```bash
python scripts/serve.py            # default 8765
python scripts/serve.py 8080       # custom port
# → http://127.0.0.1:8765
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium

pytest tests/ --ignore=tests/e2e          # unit tests (~69 tests, <1s)
pytest tests/e2e --browser chromium       # Playwright smoke tests (11 tests)
```

Run on every PR by `.github/workflows/test.yml`.

## Deploy

Three GitHub Actions workflows:

- **`deploy.yml`** — every push to `main` publishes `docs/` to GitHub Pages.
- **`refresh.yml`** — weekly cron (Mon 07:00 UTC) re-runs `refresh.py --all`. Commits if any output changed; commit message includes the diff summary (`+N −N ~N sites`). Manually triggerable with a `--limit` override.
- **`test.yml`** — pytest + Playwright on every PR.

Pages source: **Settings → Pages → Source: GitHub Actions** (or `gh api -X PUT repos/<owner>/<repo>/pages -f build_type=workflow`).

## Project structure

```
.
├── refresh.py                  # CLI driver — picks a connector, validates, writes JSON
├── schema.py                   # Pydantic schema (single source of truth for sites.json shape)
├── diff.py                     # Diff prior vs current sites.json → data/changes.md
├── connectors/
│   ├── __init__.py             # Connector registry
│   ├── base.py                 # Connector ABC + shared HTTP/cache infra
│   ├── superfund_npl.py        # EPA NPL FeatureServer
│   └── epa_acres.py            # EPA ACRES Brownfield Properties
├── tests/
│   ├── test_normalize.py       # Unit tests
│   ├── test_envelope.py
│   ├── test_fetch.py
│   ├── test_schema.py
│   ├── test_dedupe.py
│   ├── test_merge_by_epa_id.py
│   ├── test_diff.py
│   ├── test_acres.py           # ACRES connector
│   └── e2e/
│       └── test_smoke.py       # Playwright smoke test for the frontend
├── scripts/
│   └── serve.py                # local dev server (chdirs to docs/)
├── docs/                       # static site (deployed by Pages)
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── data/
│       ├── sites.json          # canonical fast-path (Superfund) — committed
│       ├── superfund-npl.json  # written by --all (mirror of sites.json)
│       └── epa-acres.json      # lazy-loaded by the frontend
├── data/
│   ├── cache/                  # raw API responses (gitignored)
│   └── changes.md              # diff log from last refresh
├── .github/workflows/
│   ├── deploy.yml
│   ├── refresh.yml
│   └── test.yml
├── requirements.txt            # runtime deps (requests, pydantic)
├── requirements-dev.txt        # +pytest, +playwright
├── backlog.md
├── issues.md
└── CLAUDE.md
```
