"""Shared text normalization for connector `normalize()` methods.

Federal GIS sources spell "we don't know" a dozen different ways, and each
one is a string, so it survives every null check downstream. USACE writes
`NO CITY`, EPA Superfund writes `-- Not Defined --`, ACRES writes some mix of
`n/a` / `N/A` / `NA` / `None` / `Unknown` / `unknown` / `UNKNOWN` / empty.

Collapsing these at the connector is the right layer, for two reasons:

1. The frontend's `prettyPlace()` only knows five of the variants and only
   runs in the browser — so `NO CITY` was rendering in the detail panel as
   "No City", and every non-browser consumer (CSV export, `llms.txt`
   readers, the JSON API surface) saw the raw sentinel regardless.
2. `SiteRecord` is serialized with `exclude_none=True`, so a collapsed value
   disappears from the payload entirely rather than shipping as an empty
   string — smaller files and an unambiguous "absent means unknown" contract.

Deliberately NOT a title-caser or a general prettifier: `prettyPlace()` and
`prettyName()` own presentation, this owns truth. Keep the two separate —
mixing them is how a display tweak ends up silently mutating stored data.
"""
from __future__ import annotations

from typing import Optional

# Lowercased, whitespace-stripped forms that mean "no value". Every entry
# here was observed in the shipped corpus on 2026-08-09; the counts in the
# comments are how many records carried it.
PLACE_SENTINELS: frozenset[str] = frozenset({
    "",
    "-- not defined --",   # EPA Superfund county (29)
    "no city",             # USACE FUDS city (615)
    "unknown",             # ACRES address (126), FUDS city (28)
    "n/a",                 # ACRES address (254)
    "na",                  # ACRES address (16)
    "none",                # ACRES address (70)
    "null",
    "_null_",              # occasional ACRES rows
    "not defined",
    "not available",
    "not applicable",
    "tbd",
    "--",
    "-",
    ".",
})


def collapse_sentinel(value: object) -> Optional[str]:
    """Return the trimmed string, or None when it is a placeholder.

    >>> collapse_sentinel("  Hattiesburg ")
    'Hattiesburg'
    >>> collapse_sentinel("NO CITY") is None
    True
    >>> collapse_sentinel("-- Not Defined --") is None
    True
    >>> collapse_sentinel(None) is None
    True

    Non-string values pass through `str()` first so an accidental numeric
    ZIP or a stray float doesn't explode; genuine zero-like values ("0") are
    NOT treated as sentinels, because a street address of "0" is rare but a
    silently-dropped one is worse than a odd-looking one.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in PLACE_SENTINELS:
        return None
    return text
