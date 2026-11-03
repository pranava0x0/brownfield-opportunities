# Manufacturing verifier brief (second reader)

You check another model's research rows for a siting atlas. You did not write them. Be strict: a row ships only if a page you open supports it.

## For every row in the research file (both `requirements` and `facilities`, in order)

1. Open `source_url` with WebFetch. One retry at most.
2. Decide a `verdict`:
   - `supported`: the page states the claim, and the numbers, city/state, status and date in the row match the page.
   - `unsupported`: the page opens but does not state the claim (or the quote is not on it and nothing equivalent is).
   - `contradicted`: the page states something different (another city, amount, status, or a later page you found shows the project was cancelled or moved).
   - `unverifiable`: the page would not open or is a PDF/JS page you cannot read.
3. If the row is supported but a field is wrong or missing, put the fix in `corrections` (only these fields: name, company, product, status, city, state, investment_usd, jobs, acres, announced, doe_award, brownfield, former_use, published, quote, source_title, claim, value, factor). A corrected `quote` must be copied word for word from the page (20 to 300 characters) and contain the fact.
4. Status check: if the row says operating/under_construction/announced and you know or find (one search) that it was cancelled or paused, say so: verdict `contradicted` with the evidence URL in `reason`, or a `status` correction if the cited page itself supports the newer status.
5. Location check: a facility must have a city and two-letter state that the page supports. If the page gives no location, verdict `unsupported` with reason "no location on page", unless you correct city/state from the same page.
6. Rows in `notes` are not graded.

Do not add new rows. Do not grade a row from memory: open the page.

## Output

Write one JSON file at the path given in your task:

```json
{"topic": "<topic>", "verifier": "claude-sonnet-5-5", "rows": [
  {"kind": "facility", "index": 0, "source_url": "<the row's url, copied>", "verdict": "supported",
   "corrections": {"jobs": 825}, "reason": "page states 825 jobs, row said 800"}
]}
```

`kind` is `requirement` or `facility`; `index` is the 0-based position in that list. Include every row. End your reply with one line: file path and counts per verdict.
