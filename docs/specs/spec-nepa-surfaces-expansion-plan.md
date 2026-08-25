# Spec 13 (master): NEPA Surfaces Expansion — Microreactors, Coal, Infra Audit, nepa-mcp Gaps

**Status:** Plan written 2026-08-24 (same session as the DOE Sites v2 restructure). Specs 13a-13d below are ready to implement; the freshness-audit script (13d's first deliverable) shipped this session.
**Origin:** User direction 2026-08-24: expand the Microreactor and Coal tabs with more nepa-mcp information + better citations and walkthroughs; audit all proximate-infra data for freshness/accuracy; identify nepa-mcp gaps and propose new servers; build more efficient future data pulls. Written to disk incrementally for fast resume (window-limit discipline).

---

## The template every child spec follows (user-directed)

Each spec answers, in plain English:
- **Target users** — named personas, not "users."
- **Jobs to be done** — the questions each persona walks in with, ranked.
- **UI/UX ease** — click depth to each answer, scroll budget, where
  qualifiers/disclaimers live (BOTTOM, per user direction — the honesty
  rails stay, but they stop being the opening act).
- **Readability** — simple-English rules: every number cited, every
  AI-drafted sentence disclosed, no tool jargon above the fold
  ("Environmental screen", never "nepa-mcp source matrix" in a heading).

## What the DOE Sites v2 restructure proved (reuse, don't re-derive)

The 2026-08-24 practitioner evaluation (spec 11 §0) produced a layout
grammar that measurably worked — whole dossier ≈ 3.8 screens with the
answers OPEN, vs 8+ screens before:

1. **Answers first**: at-a-glance verdict strip → the decision matrix →
   evidence on demand (drawer/click-through) → infrastructure → collapsed
   reference sections (permitting, managers, methodology) → method note.
2. **One-at-a-time drawers** beat stacked accordions.
3. **Click-revealed reasoning** beats tooltips (touch + AT + citations).
4. **Constraint vocabulary** (mission/land/licensing/power/water/gas/
   workforce/security) turns a color into a WHY.
5. **AI-narrative disclosure** as a visible note, not fine print.
6. **Honest absence**: a source that is Pacific-only is not rendered as
   "Unavailable" inland; a category with no citable source is omitted;
   "size not published" beats an invented acreage.

Specs 13a (Microreactors) and 13b (Coal) are applications of this grammar
to their tabs. 13c (nepa-mcp gaps) and 13d (infra audit + efficient
refresh) feed them data.

## Sequencing

| Order | Spec | Size | Why this order |
|---|---|---|---|
| 1 | **13d** — infra freshness audit + `check_upstream_freshness.py` | S (script shipped this session) | Cheap, unblocks everything: tells us which datasets to re-pull BEFORE building new surfaces on them |
| 2 | **13b** — Coal tab NEPA walkthrough | M | Smallest surface delta (drawer already exists; backlog already scoped "bring to Hanford's level"); the 18-plant catalog is the most commercially-live audience |
| 3 | **13a** — Microreactors tab walkthrough | M-L | Bigger IA change (three surfaces on one tab today); Janus screens upgrade from 6→8 sources rides the same builder patterns |
| 4 | **13c** — nepa-mcp gap analysis → upstream proposals + local stopgaps | ongoing | The census + this session's build experience make the gap list concrete now; upstream contribution is its own track |

## Cross-cutting rules for all four

- Every new curated row: `source_url` + `verified_at`, registered in the
  three validator rosters AND pr_gate citation liveness (the
  half-registration trap).
- Every screening surface renders only DECLARED sources (the
  `_doeScreenRows` pattern) and treats unavailable ≠ no-hit.
- Never run two screening builders concurrently (per-process throttle).
- Multi-server nepa-mcp processes need `purge_server_src_namespace()`
  (sys.modules AND sys.path — see CLAUDE.md 2026-08-24).
- Disclaimers/limitations render at the BOTTOM of each tab as a collapsed
  "Sources & methodology" + limitations strip; the top of the tab carries
  at most one one-line qualifier ("screening evidence, never an agency
  determination").
