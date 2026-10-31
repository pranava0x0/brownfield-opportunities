# Tab validation pipeline

How the technology-specific tabs (Screens, Nuclear, Coal plants, Retired industry, DOE Sites) are checked, and how to rerun it. Code does everything it can. Models do only what code cannot: find pages and judge whether a page says what a claim says.

## Roles

| Step | Who | What |
| --- | --- | --- |
| Which sites do the tabs show | `scripts/tab_sites.py` | First N rows of each screen, the cleanup record behind each retired-industry row, brownfields listed beside civilian nuclear sites. Writes `data/validation/tab-sites.json`. |
| Numbers re-derived from source | `scripts/audit_tabs.py` | Line, rail, road and gas distances re-measured from the source layers; voltage-qualified line distances; USGS seismic and river flow; nearest-city distance; coordinate inside stated state; every cited URL. |
| Links bot protection hides | `scripts/check_links_browser.py` | Loads each `INCONCLUSIVE` link in Chromium and reads the page. A 403 to a script was a "Page not found" for a person on nrc.gov. |
| Distances shown on a map | `docs/verify.html` | `verify.html?site=<id>` redraws the lines, plants, substations, rail, roads and pipelines from the live sources and compares each with the stored value. |
| Parcel layer re-query | `scripts/local_records.py parcels` | Point-in-polygon on the state parcel layer: does it still return the owner and parcel id the atlas shows? |
| Local-record research | Haiku agents | One agent per `batches/batch-NN.json`. Prompt: `scripts/local_records_prompts/researcher.md`. Finds county, city and state portals and dated records, each with a verbatim quote. |
| Independent verification | Sonnet agents | One agent per research file. Prompt: `verifier.md`. Opens every cited page and judges each claim from scratch. |
| Quote check and decision | `scripts/local_records.py adjudicate` | Re-fetches each cited page, looks for the quote, applies the rule table in `decide()`. Nothing ships without a second model's read. |
| Disputes | Opus agent | Only where code and the Sonnet verifier disagree. Prompt: `adjudicator.md`. |
| Click depth and load time | `scripts/uat_depth.py` | Clicks to reach each leaf, three viewports, throttled CPU and network on mobile and tablet. |

## Run it

```bash
scripts/validate_tabs.sh deterministic   # tab sites, audit, queue, parcel checks (no model)
# agents: Haiku per batch file, then Sonnet per research file (two at a time)
scripts/validate_tabs.sh adjudicate      # quote-check, decide, list disputes, publish
scripts/validate_tabs.sh uat             # click depth and performance
```

Agent concurrency is capped by `.claude/agent-cap` (default 2). Raise it only deliberately; the Haiku and Sonnet runs are the cost.

## Adjudication table

| Code finds the quote | Sonnet says | Result |
| --- | --- | --- |
| found | supported | accepted |
| found | unverifiable | `accepted_code_only` (the words are on the page; no model judged the summary against them) |
| found | unsupported / contradicted | disputed (Opus) |
| missing | supported | disputed (Opus) |
| missing | unsupported / contradicted | rejected |
| page unreadable by code | supported | accepted, flagged `accepted_model_only` |
| page is gone (404/410) | anything | rejected |
| anything | not verified by a second model | rejected |

## What the first run found (2026-10-31)

Reports are in `data/validation/`: `audit-offline.json`, `audit-network.json`, `browser-links.json`, `uat-report.json`, `local-records/`.

- **Grid and corridor distances hold.** 949 of 950 line, rail, road and gas re-measurements for the 74 corpus sites, 14 installations and 10 coal plants match the source layers within 0.35 mi. The one miss is a rail distance (Celanese Shelby: stored 0.1 mi, Census now shows none within 1 mi).
- **Citations.** 11 Nuclear source links returned 404; 7 more that returned 403 to a script were dead in a browser. All 18 replaced. 4 links remain bot-blocked and unjudged.
- **River flow.** Fort Wainwright (41,000 vs 24,825 cfs), JBLM (2,000 vs 1,321) and Robins' gauge (no discharge record) corrected from NWIS. No screen result changed.
- **Land is the weak input.** Acreage is unknown for 78% of the corpus, so the land check on the data-center, solar, port and nickel screens is "unknown" for most sites.
- **Parcels.** 41 of 53 researched sites are in states with no statewide parcel layer. For 8 of 14 FUDS sites in covered states the atlas shows a USACE ownership category while the layer names the owner.
- **Local records.** 53 sites researched; 68 portals and 90 facts shipped; 35 facts held back. County recorder and assessor systems were mostly unreadable, so few transfers surfaced (9 transfer facts, 1 deed).
- **Click depth and load.** All 14 leaf tasks need 3 clicks or fewer on phone, tablet and desktop. First-load "ready" is 1.7 s desktop, 11.2 s tablet and 26.4 s phone under throttling, against budgets of 4, 9 and 12 s.
