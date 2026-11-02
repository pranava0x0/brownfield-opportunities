# Manufacturing research brief (shared by every researcher)

Goal: cited facts for a brownfield siting atlas. Two kinds of rows:

1. **requirements**: what a plant of this type needs from a site (land, power, rail, road, port, water, natural gas, workforce, flood, heavy-haul, other).
2. **facilities**: named US plants (operating, under construction, announced, expanding, cancelled) with city and state.

## Rules

- Use WebSearch to find pages, then WebFetch to OPEN each page you cite. Cite only pages you opened.
- `source_url` must be https and must be the page you opened (not a search-results URL, not a URL you built).
- `quote` must be copied word for word from that page, 20 to 300 characters, and must contain the number or fact you report. If WebFetch only gives you a paraphrase, do not invent a quote: put the row in `notes` instead.
- Prefer primary sources: company press releases, state/county economic development announcements, DOE/DoD/agency pages, SEC filings. Trade press (Utility Dive, Canary, E&E, Reuters, local newspapers) is fine when it states the fact.
- City and state only; never invent coordinates or street addresses. Give `address` only when the page states it.
- Report numbers as the page states them (e.g. "$457 million", "300 acres"). Use null when unknown. Never guess.
- `status` is one of: operating, under_construction, announced, expansion, cancelled, paused.
- `brownfield`: true only if the page says the site is a former industrial/mill/plant/base/landfill site; false if it says greenfield/new site; else null. Put the prior use in `former_use`.
- Dates: `published` is the page's date (YYYY-MM-DD, or YYYY-MM if that is all it shows).
- Aim for 12 to 25 facilities and 4 to 8 requirement rows. Quality over count. Stop at about 30 tool calls.

## Output

Write exactly one JSON file at the path given in your task (use the Write tool), shaped:

```json
{
  "topic": "<topic key>",
  "researched_at": "2026-11-02",
  "requirements": [
    {"factor": "land", "claim": "Large power transformer plants occupy 40-100 acres", "value": "40-100 acres",
     "source_url": "https://...", "source_title": "...", "published": "2025-03", "quote": "..."}
  ],
  "facilities": [
    {"name": "Hitachi Energy South Boston transformer factory", "company": "Hitachi Energy", "product": "large power transformers",
     "status": "expansion", "city": "South Boston", "state": "VA", "address": null,
     "investment_usd": 457000000, "jobs": 825, "acres": null, "announced": "2025-09",
     "doe_award": null, "brownfield": null, "former_use": null,
     "source_url": "https://...", "source_title": "...", "published": "2025-09-04", "quote": "..."}
  ],
  "notes": ["anything useful that you could not quote"]
}
```

`doe_award`, when the plant received federal money, is `{"program": "...", "amount_usd": 0, "agency": "DOE"}` (agency may be DOE, DoD, LPO, etc.), and the quote or a second row must support it.

End your reply with one line: the file path and the counts of requirement and facility rows.
