# Brownfield Opportunities

Static dashboard of EPA Superfund + ACRES brownfield + USACE FUDS + DOD BRAC sites — map and table view with filters, site-level detail, infrastructure-proximity scoring, ECHO enforcement signals, AI-generated narrative summaries, CSV export, and shareable URL state. Designed to live on GitHub Pages and refresh via a one-command CLI.

**Live:** https://pranava0x0.github.io/brownfield-opportunities/

## Current capabilities (v1.11)

**Coverage** — ~46,800 federally-tracked contaminated sites across four programs:

- **EPA Superfund (NPL)** — 1,908 unique sites, multi-polygon Portland-Harbor-style fragments merged, NPL status decoded from the layer's live coded-value domain.
- **EPA ACRES brownfields** — 36,003 properties from the EPA-hosted ArcGIS service. Lazy-loaded after first paint, chunked-hydrated so the main thread never freezes.
- **USACE FUDS** — 8,822 Formerly Used Defense Sites with layer-1/layer-4 join; ~3k carry polygon-derived acreage. Owner labels normalized from raw USACE codes.
- **DOD BRAC** — 27 Base Realignment & Closure installations, polygon-derived acreage via Shoelace + cos(lat).

**Per-site enrichment** —

- **Universal infrastructure proximity** (v1.10) — distance in miles to nearest electric transmission line (HIFLD), primary road (Census TIGER), and rail (Census TIGER). Pure-Python spatial grid index, no shapely/rtree dependency. ~98% coverage on transmission alone.
- **EPA Redevelopment / data-center reuse flag** (v1.7) — qualitative power / water / wastewater / population-density signals from EPA's RE-Powering FeatureServer. 828 / 1,905 Superfund sites flagged as data-center reuse candidates (≥50 ac + power + water).
- **Federal documents** (v1.9) — RODs, ESDs, Five Year Reviews, fact sheets pulled from EPA SEMS via a three-hop walk (EPA pretty page → SF_SITE_ID → cumulis docdata → SEMS cachejson).
- **EPA ECHO enforcement summary** (v1.11) — 5-year inspections / formal & informal actions / penalties / current compliance / last violation date. Open enforcement gets red-highlighted styling in the detail panel.
- **AI-generated site summaries** (v1.11) — Claude Haiku synthesizes name + status + acreage + infra + documents + enforcement into a 3-paragraph buyer-oriented narrative. Cached by content-hash so re-runs only re-bill when underlying data changes. Surfaced as a "Summary" tab in the detail panel.

**Frontend** —

- Map (Leaflet + Canvas) and table views with sortable columns, free-text search, program / state / NPL-status / acreage filters, and shareable URL state (`?site=`, `?q=`, `?state=`, `?status=`, `?program=`, `?min_ac=`).
- US-only vector basemap (no raster tiles): states (filled GeoJSON polygons) + counties (lazy-loaded TopoJSON past zoom 7), CSS-var-driven so theme swaps repaint cleanly.
- Cartographic insets for AK / HI / PR / VI / Pacific territories — markers remap into labeled boxes along the bottom of the map; real coords preserved on `lat_real`/`lon_real`.
- Editorial type system (v1.8): system-serif display stack, hero strip + 4-cell KPI deck (`#kpi-total`, `#kpi-acres`, `#kpi-dc`, `#kpi-states`), footer with sources.
- Marker decimation at low zoom (1/8 at zoom ≤4 ramping up), paginated table (250 rows/page with IntersectionObserver auto-append), and chunked marker hydration via `requestIdleCallback`.
- Detail panel with Overview / Summary tab strip; FUDS, infrastructure, federal-documents, and ECHO enforcement sections render conditionally per program.
- Mobile-friendly: detail panel becomes a bottom sheet, KPI deck becomes a horizontal scroll-snap carousel.
- Theme toggle (light/dark) with `localStorage` persistence + `prefers-color-scheme` first-visit honor.
- A11y: skip-to-content link, toolbar `<nav>` landmark, `<main id="main">` skip target, detail panel `aria-hidden` synced.

See `issues.md` for the bug log and [`backlog.md`](backlog.md) for the data-center-opportunity pivot, the development-readiness signal taxonomy, and other data sources / UX patterns under consideration.

## Refresh the data

```bash
pip install -r requirements.txt
python refresh.py --list-sources                       # show registered connectors
python refresh.py                                      # default: Superfund only → docs/data/sites.json
python refresh.py --source epa-acres                   # ACRES → docs/data/epa-acres.json
python refresh.py --source dod-fuds                    # FUDS (point + polygon join) → docs/data/dod-fuds.json
python refresh.py --source dod-brac                    # BRAC → docs/data/dod-brac.json
python refresh.py --source epa-redev                   # Redevelopment infra enrichment (Superfund-only)
python refresh.py --source infra-proximity             # universal HIFLD + TIGER infra-proximity (~7 min)
python refresh.py --source epa-superfund-docs --docs-limit 100              # docs enrichment, 100 sites/batch
python refresh.py --source epa-superfund-docs --docs-limit 100 --docs-skip 100  # next 100
python refresh.py --source epa-echo --echo-limit 100   # ECHO enforcement enrichment
export ANTHROPIC_API_KEY=sk-ant-...
python refresh.py --source ai-summary --ai-limit 100   # Claude Haiku narrative summaries
python refresh.py --source ai-summary --dry-run        # cache-only re-build, no API key needed
python refresh.py --all                                # all connectors, ordered by run_order
python refresh.py --all --combined                     # also write a single fat sites.json (~2MB gz)
python refresh.py --source superfund-npl --no-cache
python refresh.py --source superfund-npl --dry-run     # use only cached responses
python refresh.py --pretty                             # pretty-printed JSON (default is minified)
```

Output:

- `docs/data/sites.json` — canonical fast-path the frontend loads first (~170KB gzipped, Superfund only).
- `docs/data/superfund-npl.json` — same as `sites.json`; written by `--all`.
- `docs/data/epa-acres.json` — ACRES brownfields (~36k records, ~1.5MB gzipped).
- `docs/data/dod-fuds.json` — USACE FUDS (~8.8k records, ~4MB); ~3k carry polygon-derived acreage.
- `docs/data/dod-brac.json` — DOD BRAC installations (27 records, polygon-derived acreage).
- `docs/data/epa-redev.json` — EPA RE-Powering qualitative infra signals (Superfund-only, ~1.9k records).
- `docs/data/infra-proximity.json` — universal HIFLD + TIGER mile-precision distances across all programs.
- `docs/data/epa-superfund-docs.json` — per-EPA_ID document lists (RODs, ESDs, Five Year Reviews, fact sheets).
- `docs/data/epa-echo.json` — EPA ECHO enforcement summary (5yr inspections / actions / penalties / compliance).
- `docs/data/ai-summary.json` — Claude-Haiku-generated 3-paragraph narrative per site, content-hash-cached.
- `docs/data/us-states.json` / `us-counties-topo.json` — vector basemap (states always; counties lazy past zoom 7).
- `data/changes.md` — diff vs prior run (canonical file only).

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

pytest tests/ --ignore=tests/e2e          # unit tests (252 tests, <1s)
pytest tests/e2e --browser chromium       # Playwright smoke tests (50 tests, ~75s)
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
├── refresh.py                       # CLI driver — picks connectors by run_order, validates, writes JSON
├── schema.py                        # Pydantic schema (single source of truth for SiteRecord shape)
├── diff.py                          # Diff prior vs current sites.json → data/changes.md
├── connectors/
│   ├── __init__.py                  # Connector registry
│   ├── base.py                      # Connector ABC + shared HTTP/cache infra (run_order, http_get_json, http_get_text)
│   ├── superfund_npl.py             # EPA NPL FeatureServer (producer; run_order=100)
│   ├── epa_acres.py                 # EPA ACRES Brownfield Properties (producer)
│   ├── dod_fuds.py                  # USACE FUDS layer-1+layer-4 join (producer)
│   ├── dod_brac.py                  # DOD BRAC milbases (producer)
│   ├── epa_redev.py                 # EPA RE-Powering qualitative infra (Superfund enrichment)
│   ├── epa_superfund_docs.py        # SEMS document scrape (Superfund enrichment, run_order=200)
│   ├── infra_proximity.py           # Universal HIFLD + TIGER mile-precision distances (run_order=300)
│   ├── epa_echo.py                  # EPA ECHO enforcement summary (Superfund enrichment, run_order=250)
│   ├── ai_summary.py                # Claude Haiku narrative summaries (run_order=400)
│   ├── geom.py                      # Shoelace + cos(lat) polygon area; envelope_center
│   ├── spatial.py                   # Pure-Python 0.25° spatial grid index (no shapely/rtree)
│   └── county_lookup.py             # Offline TIGER point-in-polygon county fill for ACRES
├── tests/
│   ├── test_normalize.py            # 252 unit tests across all connectors + shared infra
│   ├── test_envelope.py · test_fetch.py · test_schema.py
│   ├── test_dedupe.py · test_merge_by_epa_id.py · test_diff.py
│   ├── test_acres.py · test_brac.py · test_fuds.py · test_redev.py
│   ├── test_superfund_docs.py · test_infra_proximity.py · test_spatial.py
│   ├── test_geom.py · test_county_lookup.py
│   ├── test_echo.py · test_ai_summary.py
│   └── e2e/
│       └── test_smoke.py            # 50 Playwright smoke tests (golden path + UAT regressions)
├── scripts/
│   └── serve.py                     # local dev server (chdirs to docs/)
├── docs/                            # static site (deployed by Pages)
│   ├── index.html · style.css · app.js
│   └── data/                        # canonical + per-source JSONs (see "Output" above)
├── data/
│   ├── cache/                       # raw API + AI responses (gitignored)
│   └── changes.md                   # diff log from last refresh
├── .github/workflows/               # deploy.yml · refresh.yml · test.yml
├── requirements.txt                 # runtime deps (requests, pydantic)
├── requirements-dev.txt             # + pytest, playwright
├── backlog.md · issues.md · CLAUDE.md
```
