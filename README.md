# Brownfield Opportunities

Static dashboard of EPA Superfund + ACRES brownfield sites — map and table view with filters, site-level detail, CSV export, and shareable URL state. Designed to live on GitHub Pages and refresh via a one-command CLI.

**Live:** https://pranava0x0.github.io/brownfield-opportunities/

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
- **US-only.** `maxBounds` and `minZoom` constrain the map to the contiguous US plus Alaska and Puerto Rico.
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
python refresh.py --all                            # both, plus mirror Superfund → sites.json
python refresh.py --all --combined                 # also write a single fat sites.json (~2MB gz)
python refresh.py --source superfund-npl --no-cache
python refresh.py --source superfund-npl --dry-run # use only cached responses
python refresh.py --pretty                         # pretty-printed JSON (default is minified)
```

Output:
- `docs/data/sites.json` — canonical fast-path file the frontend loads first (~170KB gzipped, Superfund only)
- `docs/data/superfund-npl.json` — same as `sites.json`, written by `--all`
- `docs/data/epa-acres.json` — ACRES brownfields, lazy-loaded by the frontend (~1.5MB gzipped)
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
