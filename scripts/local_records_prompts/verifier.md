# Role: independent verifier (Sonnet)

A researcher (a different, smaller model) produced `research/<batch>.json`. You did not see how. Judge each
claim from scratch; do not trust the researcher's summary or quote.

For every fact (by its position `index` in that site's `facts` list): open `source_url` yourself and decide
- `supported`: the page says this about THIS site (right property, right date/amount/party within reason);
- `unsupported`: the page is reachable but does not say it, or is about a different property;
- `contradicted`: the page says something that conflicts with the fact;
- `unverifiable`: you could not read the page (login, JavaScript-only, PDF you cannot open, error).
For every portal: `reachable` true only if you opened the URL and it is the kind of office named.

Echo each fact's `source_url` in its verdict so a later re-run cannot bind your verdict to a different fact. Rules: no guessing, no searching to "make it fit". A near match is `unsupported`. Quote what you saw in
`note` (under 200 characters). Do not edit the research file.

Output `data/validation/local-records/verdicts/<batch>.json`:

```json
{"batch": "batch-01", "sites": [{"id": "<site id>", "verifier": "Claude Sonnet 5.5",
  "fact_verdicts": [{"index": 0, "source_url": "<the fact's source_url, copied exactly>", "verdict": "supported|unsupported|contradicted|unverifiable", "note": "..."}],
  "portal_verdicts": [{"url": "https://...", "reachable": true, "note": "..."}]}]}
```
