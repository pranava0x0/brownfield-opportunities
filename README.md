# Brownfield Opportunities

Static dashboard of EPA Superfund sites — map and table view with site-level detail. Designed to live on GitHub Pages and refresh via a one-command CLI.

**Live:** https://pranava0x0.github.io/brownfield-opportunities/

## What's in v1.1

- **All 1,908 unique NPL Superfund sites** (was top-100 by acreage). Multi-polygon sites merged by EPA_ID; ~200 sites with non-areal geometry surfaced in an "N/A acreage" bucket rather than dropped.
- **Map view (default)** with Canvas-rendered markers on CARTO light tiles; markers sized by acreage (log scale) and colored by NPL status, with an in-map legend.
- **US-only.** `maxBounds` and `minZoom` constrain the map to the contiguous US plus Alaska and Puerto Rico.
- **Table view** with sortable columns.
- **Search** — free-text filter on site name / city / county / state. Filters both the table and the map markers.
- **Mobile-friendly:** detail panel becomes a bottom sheet on phones; tap targets sized for touch; tiles preconnected and `sites.json` preloaded for fast first paint.
- **Side panel** on click: name, NPL status, acreage, EPA ID, full address, coordinates, link to EPA site profile (with EPA_ID-based fallback URL when source links are missing).
- **Dynamic code labels.** Both NPL status and federal-facility codes are decoded from the layer's coded-value domain at refresh time — no risk of going stale.
- **Source:** [EPA NPL Superfund Site Boundaries (Public)](https://hub.arcgis.com/datasets/EPA::npl-superfund-site-boundaries-epa-public-2022/about) ArcGIS FeatureServer.

Owner / encumbrance / infrastructure-proximity data and the broader Brownfields/ACRES universe are deferred. See [`backlog.md`](backlog.md) for the data-center-opportunity pivot and the data sources that would feed it.

## Refresh the data

```bash
pip install -r requirements.txt
python refresh.py --list-sources                   # show registered connectors
python refresh.py                                  # default: all NPL sites
python refresh.py --source superfund-npl --limit 200
python refresh.py --source superfund-npl --no-cache
python refresh.py --source superfund-npl --dry-run # use only cached responses
```

Output: `docs/data/sites.json` (committed, served by Pages) + `data/changes.md` (diff vs prior run).

The script is idempotent: re-runs hit a local cache (`data/cache/`) until you pass `--no-cache`.

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

pytest tests/ --ignore=tests/e2e          # unit tests (~50 tests, <1s)
pytest tests/e2e --browser chromium       # Playwright smoke tests
```

Run on every PR by `.github/workflows/test.yml`.

## Deploy

Three GitHub Actions workflows:

- **`deploy.yml`** — every push to `main` publishes `docs/` to GitHub Pages.
- **`refresh.yml`** — weekly cron (Mon 07:00 UTC) re-runs `refresh.py`. Commits if `sites.json` changed; commit message includes the diff summary (`+N −N ~N sites`). Manually triggerable with a `--limit` override.
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
│   └── superfund_npl.py        # EPA NPL FeatureServer
├── tests/
│   ├── test_normalize.py       # Unit tests
│   ├── test_envelope.py
│   ├── test_fetch.py
│   ├── test_schema.py
│   ├── test_dedupe.py
│   ├── test_merge_by_epa_id.py
│   ├── test_diff.py
│   └── e2e/
│       └── test_smoke.py       # Playwright smoke test for the frontend
├── scripts/
│   └── serve.py                # local dev server (chdirs to docs/)
├── docs/                       # static site (deployed by Pages)
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── data/sites.json         # committed; regenerated by refresh.py
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
