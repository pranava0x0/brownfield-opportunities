# AP1000 Water Validation — Evidence

Source artifacts backing [`../ap1000-water-validation.md`](../ap1000-water-validation.md).
Saved 2026-06-25. Machine-readable USGS data is captured here directly (more
reproducible than a screenshot); qualitative/agency sources are cited by URL +
verbatim quote in the validation doc.

## `usgs/` — USGS NWIS streamflow (authoritative, no API key)

- **`site-metadata.rdb.txt`** — drainage area + station metadata for all 13
  validated gauges (NWIS *site* service). Confirmed drainage areas (mi²):
  Cape Fear @ Lillington 02102500 = 3,464 · Little River @ Manchester 02103000 =
  348 · Ocmulgee @ Macon 02213000 = 2,240 · Ocmulgee nr Warner Robins 02213700 =
  2,690 · Chattahoochee @ Columbus 02341460 = 4,630 · Cumberland @ Nashville
  03431500 = 12,856 · S.F. Holston @ Kingsport 03487500 = 1,935 · Tennessee @
  Whitesburg 03575500 = 25,610 · Elk @ Estill Springs 03579100 = 275 · Black @
  Watertown 04260500 = 1,864 · Nisqually @ McKenna 12089500 = 517 · Chena @
  Fairbanks 15514000 = 1,990 · Tanana @ Nenana 15515500 = 25,560.
- **`02213000-annual-mean.rdb.txt`** — Ocmulgee @ Macon annual means (98 yrs).
  Key row: `2012 → 854.1 cfs` — the drought low that downgraded **Robins
  abundant → adequate**.
- **`02102500-annual-mean.rdb.txt`** — Cape Fear @ Lillington annual means (44
  yrs, mean ~3,224 cfs) — the basis for the **Fort Bragg** source correction
  (Cape Fear, not the Little River).
- **`03431500-annual-mean.rdb.txt`** — Cumberland @ Nashville annual means —
  Fort Campbell's abundant-but-distant river source.

### Reproduce (no API key)
```
curl "https://waterservices.usgs.gov/nwis/site/?format=rdb&sites=<GAUGE>&siteOutput=expanded"
curl "https://waterservices.usgs.gov/nwis/stat/?format=rdb&sites=<GAUGE>&statReportType=annual&statTypeCd=mean&parameterCd=00060"
```
The human-facing `waterdata.usgs.gov/monitoring-location/<id>/` pages are
JS-rendered and return nothing to curl/WebFetch — use the RDB endpoints above.
The multi-site *stat* query is flaky; fetch annual means one gauge at a time.

## AP1000 demand
Per unit ~26.8 MGD withdrawal / ~20.1 MGD consumptive (Vogtle 3&4 NRC EIS /
DOE EIS-0476; `nrc.gov/docs` times out — use the energy.gov mirror). Full quotes
in the validation doc §1.
