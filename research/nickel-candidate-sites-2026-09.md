# Candidate sites for a US nickel refinery or smelter

Generated 2026-09-08 from the two lenses in `docs/nickel-score.js` over all
46,759 corpus sites, plus the DOE dossiers. Ordered by land-ownership class —
Department of War (FUDS/BRAC), then DOE, then Superfund NPL, then EPA
brownfields — with swing states first.

**Land is the filter that matters.** A refinery needs roughly 300–500 acres
(Long Harbour is ~370 including residue ponds; Westwin's tract is 480). Every
site below carries a *confirmed* acreage. Sites whose acreage is unknown are
excluded here even when they score higher, because EPA publishes no acreage at
all for its ~36,000 brownfield properties and an unknown parcel is not a
shortlist entry.

Water figures are long-run annual mean flow, not permittable low flow.

---

## The single strongest finding: the Granite City / East St. Louis smelter district

Three former non-ferrous smelters sit within a few miles of each other on the
Mississippi, all rail-served, all about 75 miles from an operating
cobalt-nickel mine (Madison Mine, Fredericktown MO).

| Score | Site | State | Acres | Water | Grid | Rail | Feedstock |
|---|---|---|---|---|---|---|---|
| 93 | **NL Industries / Taracorp Lead Smelter**, Granite City | IL | 1,367 | 200,224 cfs | 138 kV @ 0.4 mi | 0.2 mi | 79 mi |
| 93 | **Alcoa Properties**, East St. Louis | IL | 409 | 200,224 cfs | 138 kV @ 1.1 mi | 0.1 mi | 73 mi |
| 91 | **Old American Zinc Plant**, Fairmont City | IL | 1,221 | 200,224 cfs | 138 kV @ 2.0 mi | 0.5 mi | 76 mi |
| 83 | **Circle Smelting Corp**, Beckemeyer | IL | 533 | 590 cfs | 138 kV | 0.0 mi | 86 mi |

These were built to smelt non-ferrous metal. They have the river, the rail, the
industrial zoning, and the nearest US nickel-cobalt feedstock. Not a swing
state, and the contamination is serious — Taracorp is a lead site — but on
siting fundamentals nothing else in the corpus comes close.

## Best smelter-scale candidate: Massena, New York

| Score | Site | Acres | Water | Grid |
|---|---|---|---|---|
| 85 | **GM Central Foundry Division**, Massena | 258 | 256,023 cfs (St. Lawrence) | 115 kV @ 0.0 mi |
| 82 | **Alcoa Aggregation Site**, Massena | 380 | 256,023 cfs | 115 kV @ 2.4 mi |

The historic US aluminium smelting corridor, on the St. Lawrence, adjacent to
NYPA hydro. A smelter is the facility type this dashboard deliberately does not
score — no US precedent, a case-by-case MACT determination, and a captive-power
model — but if one is ever built, this is where the power and water already are.

---

## Swing states

### Michigan — the feedstock case

| Score | Site | Program | Acres | Water | Grid | Feedstock |
|---|---|---|---|---|---|---|
| 81 | **K.I. Sawyer AFB**, Marquette | BRAC/FUDS | 5,222 | 198 cfs | 345 kV @ 3.9 mi | **16 mi** |
| 87 | **Midland CWS Plant** | FUDS | 497 | 1,815 cfs | 138 kV @ 1.1 mi | 260 mi |
| 96 | NIRP McLouth Steel, Trenton | FUDS | unknown | 208,569 cfs | 230 kV @ 0.4 mi | 366 mi |
| 80 | NIKE D-57/58, Newport | FUDS | 436 | 777 cfs | 345 kV @ 1.3 mi | — |

**K.I. Sawyer is 16 miles from Eagle Mine's feedstock — the closest site in the
entire corpus.** 5,222 acres, 345 kV, and an IRA energy community. Its weakness
is water: 198 cfs is a small river, and that is the constraint to test first.
It is the direct answer to "the only US nickel mine ships its concentrate to
Ontario."

McLouth Steel scores highest in the state on infrastructure — Detroit River
water, 230 kV, rail on site — but its acreage is unpublished and it is 366
miles from feedstock, so it fits the imported-feed model, not Eagle Mine.

### Pennsylvania

| Score | Site | Acres | Water | Grid | Demand |
|---|---|---|---|---|---|
| 80 | **Marietta Air Force Station** | 405 | 38,183 cfs (Susquehanna) | 230 kV @ 0.6 mi | 236 mi |
| 80 | **Keystone Ordnance Works**, Geneva | 13,213 | 1,674 cfs | 115 kV @ 1.0 mi | **36 mi** |

Marietta pairs a big river with 230 kV on a 405-acre parcel — the cleanest
refinery-scale fit in the state. Keystone is enormous and 36 miles from
battery-corridor demand, but its power is only 115 kV and its water is modest.

### Wisconsin, Georgia

| Score | Site | State | Acres | Water | Grid |
|---|---|---|---|---|---|
| 90 | **National Presto Industries**, Eau Claire | WI | 314 | 7,114 cfs | 161 kV @ 0.2 mi |
| 80 | **Camp Wheeler**, Macon | GA | 14,867 | 2,656 cfs | 230 kV @ 0.3 mi |
| 79 | **Turner AFB**, Albany | GA | 2,591 | 5,908 cfs | 115 kV @ 0.3 mi |

Georgia is the state Electra's own criteria point at — battery corridor, deep
water. Camp Wheeler has the land and the voltage; Turner has better water and
is an IRA energy community.

No qualifying candidates surfaced in Arizona or Nevada at refinery scale with
adequate water, which is the expected result for a water-intensive plant in the
arid West and is what the drought penalty is there to express.

---

## DOE sites

From the five DOE dossiers. These are federal land with existing industrial
service, and DOE is actively marketing several of them.

| Site | Parcel | Acres | Availability |
|---|---|---|---|
| **Savannah River** | D-Area, retired coal powerhouse | 210 | DOE-EM's stated goal is returning all 210 acres to reuse |
| **Savannah River** | AI data-center / energy lease tract | 3,103 | Not yet leased; selection explicitly open |
| **Hanford** | 300 Area, fuel-fabrication legacy | 1,500 | Medium-term, adjacent to PNNL |
| **Hanford** | 1100 Area / Horn Rapids | 768 | Available now under Port of Benton / City of Richland |
| **Paducah** | AI/HPC innovation campus | 600 | Committed under the July 2026 award |
| **Portsmouth** | SODI transferred parcels | 354 | Out of DOE ownership, already transferred |

**Savannah River D-Area is the most directly available**: a retired coal
powerhouse site with existing heavy electrical service that DOE-EM wants
reused. Hanford's 1100 Area is available now but is in a water-constrained
basin under senior downstream rights.

These parcels were screened for data centers and reactors, not for a chemical
plant. Their NEPA screens, permitting pathways, and infrastructure rows carry
over; their facility-fit ratings do not.

---

## Superfund NPL, outside swing states

| Score | Site | State | Acres | Water | Grid |
|---|---|---|---|---|---|
| 91 | Indian Refinery–Texaco, Lawrenceville | IL | 927 | 2,528 cfs | 138 kV @ 0.2 mi |
| 89 | Jacobsville Neighborhood, Evansville | IN | 3,114 | 132,549 cfs (Ohio) | 138 kV @ 0.2 mi |
| 89 | Memphis Defense Depot | TN | 611 | 510,036 cfs (Mississippi) | 161 kV @ 0.2 mi |
| 87 | Washington County Landfill | MN | 1,632 | 6,058 cfs | 230 kV @ 0.3 mi |
| 83 | Joliet Army Ammunition Plant | IL | 8,945 | 4,895 cfs | **765 kV** @ 1.6 mi |

Joliet carries the highest transmission voltage in the shortlist by a wide
margin and 8,945 acres, in an IRA energy community.

---

## What this list cannot tell you

* **Acreage is missing for most of the corpus**, so a better site may exist
  that is invisible here. Michigan has confirmed acreage on 4.3% of its sites
  and Maine on 8.4%, and neither state is in the parcel registry.
* **Flow is an annual mean.** Every water figure needs a low-flow check before
  it means anything for a withdrawal permit.
* **Ownership and availability are not established** for the FUDS and NPL
  entries. A high score says the infrastructure is there, not that the land can
  be bought.
* **Contamination is not scored at all.** Taracorp is a lead smelter site and
  Old American Zinc is a zinc smelter site; their remediation status governs
  whether either is realistic and is not part of the ranking.
