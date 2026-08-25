# Spec 13a: Microreactors Tab — NEPA Expansion, Citations & Walkthrough

**Status:** Ready.
**Lead components:** `scripts/build_janus_nepa.py`, `docs/data/janus-nepa.json`, `docs/data/microreactor-fleet.json` + `scripts/build_microreactor_fleet.py`, `docs/app.js` (micro view), `docs/microreactor-score.js`.

## Target users

- **The federal/defense energy program officer** (Army Janus, AF, DOE
  pilot) tracking which installations carry which environmental context
  before vendor pairing. Reads the Janus screens.
- **The microreactor vendor BD lead** qualifying commitments and sites:
  "where is my licensing path fastest, and what consultation burden comes
  with each candidate?"
- **The project developer / offtaker** (remote industrial, utility pilot)
  using the siting screen's ranked corpus — needs to get from a ranked
  row to "what would the review look like there" without leaving the tab.

## Jobs to be done (ranked)

1. "Which committed sites are real, and how far along?" — the
   commitments table does this, but rows lack `verified_at` (backlog
   flag) and citations are uneven. **Fix: per-row provenance.**
2. "What's the environmental context at each Janus installation?" —
   exists (6-source screen) but is a wall of nine cards with counts and
   no reading guide, and is missing flood + biodiversity (the DOE sites
   run 8 sources). **Fix: 6→8 sources + readings + walkthrough order.**
3. "For a site I found in the siting screen, what next?" — today the
   ranked table dead-ends. **Fix: a 'What a screen here would cover'
   click-through** that reuses the corpus record's existing enrichments
   (flood/NRI/tribal already joined!) as a mini-screen, and links the
   site's detail panel evidence block. No new per-site network — the
   19-hour-per-layer trap stays refused.
4. "Which designs could serve this site class?" — keep the deliberately
   narrow off-grid filter (backlog: only the published no-grid-required
   claims are defensible); cite each design row's spec_source.

## What ships

### Data
- **Janus screens 6→8**: add `fema_nfhl` (2-mi) + `gbif` (threatened,
  ≥2000) to `build_janus_nepa.py`'s matrix — pure engine reuse. Re-run
  is cache-cheap for the six existing sources.
- **`reading` strings** per source per installation (same pattern as
  spec 13b), e.g. Eielson: "IPaC counts here reflect interior-Alaska
  datasets' sparsity, not absence of resources."
- **Fleet + commitments provenance**: every vendor row and commitment row
  gains `source_url` + `verified_at` (quarterly cadence — matches
  `STATE_DC_REGULATION`); register `microreactor-fleet.json` in
  `CURATED_PROVENANCE_FILES` + pr_gate. This closes the backlog "[low]
  fleet rows carry no verified_at" item at [med] priority because the
  commitments move monthly.

### UI (answers-first reorder, DOE grammar)
Current order interleaves fleet/commitments/siting/Janus. New order:
1. **At-a-glance strip**: committed MWe by evidence band (existing,
   promoted), fleet count, "N corpus sites clear the siting screen at
   ≥<tier>" — three numbers, cited.
2. **Siting screen** (the ranked corpus table) with the new per-row
   "screening preview →" click-through (job 3): opens a drawer showing
   the corpus record's already-joined environmental fields (flood zone /
   SFHA, NRI wildfire/drought, tribal context, OZ/IRA status) formatted
   as a mini-screen with per-field provenance links, plus "Open the
   tracked site record" and a plain sentence on what a REAL nepa-mcp
   screen would add.
3. **Commitments** table (now cited per row).
4. **Fleet** table (cited per row; off-grid filter kept).
5. **Janus installation screens** — reformatted from nine stacked cards
   into the card-grid + one-drawer pattern; drawer = 8-source table with
   readings + map button.
6. Bottom: methodology + limitations + AI-disclosure note (all
   qualifiers move here; the top keeps one line).

## UI/UX ease

- The developer's path: ranked row → 1 click → mini-screen drawer.
- The program officer's path: jump link → Janus grid → 1 click → drawer.
- No new tabs; the tab's three audiences get three entry points from the
  at-a-glance strip's jump links (the DOE `doe-jumps` component reused).

## Readability / simple English

- "Screening preview — from data already on this dashboard" labels job
  3's drawer honestly (it is NOT a live nepa-mcp screen; the sentence
  "A full screen would add: species lists, historic properties, USACE
  district, protected-area context" says exactly what's missing).
- Counts never render without a reading; installation names use plain
  names ("Fort Wainwright, AK"), never program codes alone.

## Contracts / guards

- The inverted-grid lens, tier breaks, and `microreactorIsOffGrid` are
  UNTOUCHED (their CLAUDE.md entries are load-bearing; this spec is
  presentation + provenance + screens, not scoring).
- `janus-nepa.json` refresh keeps `--site` merge semantics; never
  concurrent with other builders; `purge_server_src_namespace` covers
  the multi-server path already.
- e2e: Janus drawer 8 rows + readings; commitments rows all carry
  verified_at; screening-preview drawer renders for a ranked site with
  zero new network requests (assert via request count).

## Sizing

Screens re-run ~1 hr wall (cache + 2 new sources × 9 sites). Provenance
pass on 12 fleet + 32 commitment rows is the research cost (~half day,
agent-assisted with the numbered-claims format). UI reorder ~1 day.
