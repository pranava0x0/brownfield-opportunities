# E. Scriptable work audit (Brownfield Opportunities, 2026-08-18 to 2026-10-18)

Method: 68 commits, 45 PRs (review comments on #37-#42 read), 25 local transcripts (22 are the daily routine, 3 are interactive sessions; 557 Bash calls, 38 Agent calls), the routine SKILL.md, scripts/, backlog.md, issues.md. Counts are from the transcripts unless marked "estimate".

## 1. Where the work goes

Commits since 2026-08-18 by class (rough, by subject line):
- Research dossier commits (routine): 18 (16 `research:` + PR "Daily site research"). 5 more are review-fix commits on those PRs (#40, #41, #42).
- Docs / CLAUDE.md lessons / backlog bookkeeping: 15
- Bug fixes (incl. PR-review fixes): ~16
- Features (squash-merged PRs: Nickel, Maritime, DOE Sites, Coal, NEPA, evidence categories...): ~11
- Data refresh / curated-row correction: 3 (`acf04d9`, `b9ea884`, `5b41b8e`)
- Merge / close-out: 5

So about half of all commits (research + backlog docs + their review fixes) come from one loop: the daily routine and the maintenance around it.

Routine transcripts (22 of 25 files): 7-29 tool calls and 19-27k output tokens per run in the orchestrator alone, plus 1-2 subagents. Bash call mix across all transcripts:
- backlog.md edited through inline `python - <<EOF` or `sed -i`: 109 calls in 21 sessions
- `date +%s` elapsed-time bookkeeping: 68 calls in 19 sessions
- `pytest tests/test_site_research.py`: 54 calls in 18 sessions
- `site_research.py add`: 31 calls; `validate_data.py --only site-research-contract`: 25 calls
- `gh api .../pulls/N/comments`: 33 calls in 9 sessions; `gh pr checks/watch`: 27 calls in 8 sessions
- `merge origin/main` into the worktree: 19 calls in 19 sessions
- `G=/Library/Developer/CommandLineTools/usr/bin/git; PY=...; WT=...` preamble re-typed in roughly 60 commands
- orphan-server sweep (`pgrep`/`lsof`): 16 calls in 10 sessions

Interactive sessions: "look at all sessions, uncommitted changes, open PRs, evaluate what is remaining" (31cdbf2a, 105 tool calls, 7 agents) and "sync with latest and take stock" (f1dce825, 278 tool calls: 25 pytest, 22 refresh.py, 16 validate_data, 12 check_upstream_freshness). Mostly status gathering.

## 2. Ranked script proposals (max 10)

### 1. `scripts/research_queue.py` (queue and run-log bookkeeping)
- Replaces: the orchestrator reading backlog section 6, picking sites, then rewriting table rows with inline Python (109 Bash calls, 21 sessions). Also Codex finding on PR #37 ("Refill the queue to its ten-site minimum", backlog.md:297) and the PR #39 mismatch between row Next due and the dossier's `next_review`.
- Inputs: backlog.md section 6 table, `docs/data/site-research.json`, `site_research.py due`.
- Outputs: `next` creates the temp dir and writes the 2 picked ids plus `<ID>.context.json` for each; `mark ID --done|--retry "reason"` edits the row; `runlog "..."` appends the line; `check` exits non-zero on a rule break.
- Logic:
  - Parse the markdown table; order = overdue dossiers, then `queued`/`retry` top-down (rules at backlog.md:294-297).
  - On `mark --done`, read `last_researched`/`next_review` back from the dossier (never typed by the model).
  - Keep done rows below queued rows; renumber nothing.
  - `check`: at least 10 `queued` rows; every done row's Next due equals the dossier's `next_review`; every id exists in the corpus.
  - `refill` proposes candidate ids from pool (2) (corpus sites within 1 mi of a curated asset) using existing join files, so the model only writes the one-line reason.
- Invoked: routine steps 2 and 5; `check` also in `validate_data.py` (WARN) and CI.
- Saves (estimate): 6-10 Bash calls and about 5-8k output tokens per run; removes the whole "queue below 10" and "Next due mismatch" defect class.

### 2. `scripts/routine_ctl.py` (workspace sync, PR comments, close-out gate, clock)
- Replaces: routine steps 0, 1 and the close-out check, all done by agent reasoning today. Evidence: worktree merge in 19 of 19 routine sessions, comment listing 33 calls, `gh pr checks` 27 calls, `date +%s` 68 calls. The 2026-10-09 user prompt "don't go in a loop forever on waiting for codex. cap the rounds." is a rule a script can enforce.
- Subcommands:
  - `sync`: fetch, create the worktree if missing, choose ff / merge / reset per SKILL.md step 0, refuse to discard unmerged commits. Prints JSON `{pr, createdAt, age_days, base_state}`.
  - `comments`: for the open PR list top-level review comments with no reply starting "Fixed in" or "Not changed:" (id, path, line, body[:700]).
  - `reply ID "Fixed in <sha>: ..."`: posts the reply using the sha of HEAD.
  - `closeout`: exits 0 only if age is 3 days or more, every comment is answered, `gh pr checks --json` is all green (poll up to 15 min), and the four local checks pass; with `--merge` runs `gh pr merge --merge`. Counts fix rounds in a state file and stops at 2.
  - `clock`: prints elapsed minutes since `sync` and the phase ("research ok" until minute 14, "wrap up" at 18).
- Invoked: routine steps 0, 1, 6, 7. Also gives the CLI-first, reproducible close-out the repo asked for.
- Saves (estimate): 8-12 Bash calls and 4-6k tokens per run; removes the stale-comment re-reads. Also fixes the 2026-10-10 failure where the researcher ran 20 minutes and left no time for the check (the clock becomes a hard gate, not a prose rule).

### 3. `scripts/check_citations.py` (deterministic pass before the Sonnet checker)
- Replaces: part of the citation-check subagent (about 25 tool calls and 100-290k tokens per agent; 38 Agent calls in total), and some Codex rounds. Evidence: PR #39 "Replace the unopened FUDS citation" (Ordnance General Supply); PR #42 Harbor Oil 2012 article treated as a 2026 lead; the 2026-10-09 trial where the Haiku researcher built a query URL itself.
- Inputs: a dossier JSON (or all of `site-research.json`) plus the researcher's list of opened URLs (written to a file by the researcher; the routine prompt already asks for it).
- Outputs: per-claim table: URL, HTTP status, final URL, `Last-Modified`/in-page date, and flags.
- Logic:
  - Flag any cited URL not in the opened-URL list, any `http://`, any URL with a query string the researcher could have built.
  - Fetch each URL once (1.5 s per host, existing house rule); status 4xx/5xx = fail; 403 and TLS drops = INCONCLUSIVE (same policy as pr_gate step 4).
  - Extract the page text; for each item/summary sentence check that its numbers and dates (acreage, years, dollar amounts, MW) appear in the page text; flag misses as "unsupported number".
  - Flag a development whose date is more than 12 months before the page's own published/modified date or whose URL/page year is far older than the item date (Harbor Oil 2012 case).
  - Skip PDFs it cannot parse; mark "unreadable", and the dossier may not cite them for contents (rule already in the prompt).
- Invoked: routine step 3 (between researcher and checker; the checker only gets the flagged claims), and by hand on the full file quarterly.
- Saves (estimate): cuts the checker to flagged claims only, about 40-60% of its tokens (roughly 80-120k per run) and catches the "unopened source" class mechanically. It does not replace judgment on "right page, wrong site"; keep Sonnet for the flagged and unclear ones.

### 4. `site_research.py lint` (extend the existing validator with the contradictions reviewers found)
- Replaces: Codex review rounds on dossier text. Evidence: PR #37 (Paducah summary says "currently on the Final NPL" while its own `npl_status_code` note says unverified), PR #41 (Fort Ord partial deletion), PR #42 (Anaconda open question already answered by `docs/data/epa-superfund-docs.json` entry 100017900 dated 2025-09-25; Site 300 "differs" for a rounding case; Mound compared against a different boundary).
- Logic (all offline):
  - If a validation note on a field is `unverifiable`, the summary may not assert that field (NPL status words, acreage numbers). Regex check, WARN list.
  - Acreage compare helper: parse "N square miles / acres" from the note text, convert, and mark `confirmed` when the shipped acreage rounds to the source figure at the source's precision (Site 300: 6,809.7 ac = 10.64 sq mi, source says 11). Flag a "differs" that fails this.
  - For each `open_questions` entry that names a document type (five-year review, ROD, ESD), look in `epa-superfund-docs.json` for a matching dated document and flag "already answered".
  - Run `check_writing.py` rules over dossier `summary`, `title`, item summaries (today `check_writing.py` scans only app.js, index.html, llms.txt, README and `*e2e.json`; dossier text is user-visible but not linted).
  - Flag any item whose date is the page publication date rather than the event date when the note says "published" (Umatilla, PR #41): only a hint, needs a `event_date` vs `published` field comparison already in the schema.
- Invoked: inside `site_research.py add` and the CI `site-research-contract` check.
- Saves (estimate): removes 2-3 reviewer findings per PR (PR #37: 1, #39: 8, #41: 2, #42: 4 of which 3 fit these rules), so about 1 fix round per rolling PR, which is one routine run of about 25k tokens.

### 5. `scripts/check_megasite_acreage.py` (systemic boundary-artifact finder)
- Replaces: one agent research pass per site for the same question. Backlog rows 5, 9, 14, 19, 20, 27, 28, 29 all say "Shipped N acres looks like a boundary artifact" and each cost a routine slot (about 8 of 34 dossiers). Backlog already lists "a systemic check (Superfund acreage vs county area)" as a to-do (CLAUDE.md 2026-09-25 entry on Tar Creek).
- Inputs: `docs/data/superfund-npl.json`, `docs/data/us-counties-topo.json`, `docs/data/us-states.json` (already offline).
- Outputs: `docs/data/..` is untouched; prints a ranked table: id, acreage, bbox acres, area of the county containing the centroid, ratio, distance from centroid to the polygon's densest vertex cluster, suggested status (`county_outline` / `watershed` / `plausible`).
- Logic:
  - Ratio of reported acreage to the area of the county polygon containing the point (reuse `connectors/county_lookup.py`); flag at 0.5 or more.
  - Flag polygon vertex sets that coincide with a county or state boundary (shared vertices with the TopoJSON arcs).
  - Flag centroid more than N miles from the polygon's concave hull when multipart.
  - Output feeds `coord-quality`-style flags so the UI can warn on its own, and so research slots are spent only on cases the script cannot classify.
- Invoked: by hand after each Superfund refresh, then in `validate_data.py` as a WARN check.
- Saves (estimate): replaces about 8 queued agent runs now (about 25k tokens x 8 = 200k) and all later ones; gives a deterministic answer to something the dossiers can only report as "differs".

### 6. `scripts/project_status.py` ("take stock" in one call)
- Replaces: the interactive prompts "look at all sessions, uncommitted changes, open PRs, evaluate what's remaining" (31cdbf2a: 105 tool calls, 7 agents) and "sync with latest and take stock" (f1dce825: 278 tool calls). CLAUDE.md git discipline (fetch, origin/main log, open PRs, newest branches) is a checklist today.
- Outputs: one page: origin/main vs local, worktrees and their dirty/ahead state, open PRs with check status and unanswered comment count, branches newer than main with unmerged diff, `check_upstream_freshness.py --json` verdicts, stale `generated_at` per data file against its cadence, count of overdue dossiers, orphan `http.server` listeners (port-agnostic `pgrep -fl http.server` plus `lsof`), run of `validate_data.py --fail-on NEVER` summary line.
- Invoked: by hand at session start; the routine's final report can include its one-line output.
- Saves (estimate): 20-40 tool calls and 10-30k tokens per status request; the output is identical every time instead of re-derived by an agent.

### 7. Update the freshness table from `check_upstream_freshness.py --markdown` (existing script, not wired)
- Evidence: the backlog section 1 "Data freshness" table is hand-transcribed ("checked live today via scripts/check_upstream_freshness.py"); Now item 12 already says to wire it into CI; refresh.yml runs weekly (Monday 07:00 UTC) and the table says "cron broken". f1dce825 ran the script 12 times by hand.
- Logic: add `--markdown` output; add a CI/cron step that runs it before the refresh and skips connectors whose source has not changed; write the result between marker comments in backlog.md or to `docs/data/freshness.md`.
- Invoked: CI (weekly, ahead of refresh.yml) and `project_status.py`.
- Saves (estimate): about 5-10 tool calls per audit and keeps the table from drifting.

### 8. Stop the e2e server leak at the source (`tests/e2e/conftest.py`) plus `scripts/sweep_orphans.sh`
- Evidence: CLAUDE.md records the same incident three times (2026-08-09, 2026-09-08 twice, 2026-09-08 sweep rewrite); 16 pgrep/lsof calls across 10 sessions; the 4 red e2e tests on a markdown-only diff (commit `6bc9b99`). conftest.py:44 starts `python -m http.server` with `Popen` and no process-group kill on interrupt.
- Logic: start the server in its own process group and kill the group in a `finally`/`atexit`; a 10-line `sweep_orphans.sh` that lists `http.server` listeners with PPID 1 and kills them with `--dry-run` default.
- Invoked: pytest fixture (automatic) and `pr_gate.sh` first step.
- Saves (estimate): 5-8 tool calls per affected session plus the hour of debugging a false red gate; prevents a repeat of the 19-hour orphan.

### 9. `scripts/env.sh` (one sourced preamble) and a `scripts/rt` wrapper
- Evidence: the git/python/gh quirk block (`G=/Library/Developer/CommandLineTools/usr/bin/git`, `PY=.../.venv/bin/python`, `PATH=$HOME/.local/bin`, quoted repo path) is re-typed in about 60 Bash commands, 136+65 commands start with a `cd "<path with space>"`, and the SKILL.md carries 15 lines of it.
- Logic: `source scripts/env.sh` exports `G`, `PY`, `MAIN`, `WT`, PATH; `scripts/rt git|py|gh ...` runs the right binary. The routine prompt and CLAUDE.md say "source env.sh" instead of describing the quirks.
- Invoked: routine and interactive sessions. Removes a class of failures (Xcode-license `/usr/bin/git`) permanently.
- Saves (estimate): 100-200 tokens per command x 60+ commands per week, and fewer retries; small but certain.

### 10. Wire existing guards into the routine and CI (no new code beyond a few lines)
- `pr_gate.sh` step 4 (citation liveness) covers coal, federal, hanford, maritime and nickel overlays but not `docs/data/site-research.json`; the 400+ dossier citations are never checked for dead links after merge. Add it, on the same 403 = inconclusive policy.
- `pr_gate.sh` is not in any workflow (`.github/workflows/test.yml` has unit, `data-integrity` = `validate_data.py --fail-on FAIL`, and e2e only). The routine runs 4 hand-picked checks. Replace them with `pr_gate.sh --fast` plus the site-research checks.
- `validate_against_sources.py` runs by hand only; add `--site ID` mode so the routine's field checks (acreage, location, status) come from the source layer instead of an agent search. It already re-queries the owning FeatureServer.
- `scripts/finish-data-refresh.sh` still targets a retired "brownfields-data-updates" scheduled task and uses `python3`, which fails on this Mac (Xcode license); either fold into `refresh.py` or delete.
- Saves: Codex findings caught earlier, and no more claims shipped with dead links.

## 3. Top 5 recurring defect types found by reviewers (PRs #37-#42, Codex bot)

1. A summary or open question that contradicts its own evidence or the repo's own data. Paducah "currently on the Final NPL" with an unverified-status note (#37); Anaconda review-date question already answered in `epa-superfund-docs.json` (#42); Site 300 review described as whole-site when the notice names three operable units (#42); Fort Ord partial deletion missed (#41); a Harbor Oil 2026 lead built on a 2012 article (#42). Scripts 3 and 4 target this.
2. Date semantics. Coverage "since" date later than the oldest displayed item (INL, Tittabawassee, #39); event date vs publication date (Umatilla, #41); review-cadence rule applied wrongly (Oak Ridge, Colstrip, Watercrest, #39); future-dated or post-research-date entries (#38 history dates, #40). Code now enforces the window, cadence and future-date rules, which is the model for the rest.
3. Citations the author never opened or cannot be traced. Unopened FUDS portal URL as the only summary source (#39); archived summaries losing `summary_sources`, and unvalidated `accessed`/`published` dates on archived citations (#38). Script 3 and the opened-URL list.
4. False "differs" from unit, rounding or boundary non-comparability. Site 300 sq mi rounding, Mound business-park 306 ac vs the whole site, megasite acreage that is really a county outline. Scripts 4 and 5.
5. Bugs in the tooling itself, found only after merge: malformed input before schema validation (`"items": [null]`), required field checked before it is derived (`next_review`), provenance clobbered by a rebuild (nuclear join `generated_at`), a loader promise that never retries, append-only history silently truncated at 12, queue minimum not met (#37-#40). Each got a regression test; the pattern suggests a fuzz test of `site_research.py add` over malformed JSON (a 30-line test, not a script) would have caught three of the six.

Also noted: PR #42's two post-merge findings were left "Not changed: logged to backlog" under the 2-round cap; a deterministic `closeout` gate (script 2) makes that trade-off explicit and logged instead of improvised.

## 4. Existing scripts not wired in, or run only by hand
- `check_upstream_freshness.py`: by hand only (12 calls in f1dce825); backlog Now #12 says wire into CI.
- `validate_against_sources.py`: by hand only; not used by the routine for field checks.
- `pr_gate.sh`: by hand; not in any workflow; no site-research citation check.
- `check_writing.py`: does not scan `docs/data/site-research.json` prose (only `*e2e.json` data files are listed at line 63).
- `repair_known_data_defects.py`: by hand after connector fixes; no CI check that its transformations are already applied (`validate_data.py` covers most invariants).
- `finish-data-refresh.sh`: stale (refers to a retired scheduled task, uses `python3`).
- `site_research.py due/context/add/validate`: all used by the routine, but nothing handles the backlog table or the PR (scripts 1 and 2).
