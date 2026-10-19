# Adversarial review: Maritime Siting and Nickel Refining tabs

Method: merged the four program files with fill-if-empty (as the browser does), joined port-proximity, water-proximity, infra-proximity and parcel-owner, then counted. Source checks are WebSearch results unless marked otherwise.

## (a) Holes, by severity

1. **Neither tab answers "where do I look first."** Both sort alphabetically (`evidenceNameOrder`, app.js:770) and show 150 rows. Maritime offshore has 22,938 eligible rows. Its first rows are ` 317-090-46, -48, -49`, ` 317-101-02` and `Former Barton Mini Mart`. The scores were removed, so there is no ranking at all. Nickel import shows 901 confirmed rows, and domestic shows 2,046, in the same A-Z order.
2. **Nickel's default "confirmed ≥300 ac" set is dominated by military ranges and polygon artifacts.** Of the 901 import rows, 619 are FUDS. The top rows are Cook Inlet Air Force Range (1,211,889 ac), Fox River NRDA/PCB releases (1,129,744 ac, a river-reach polygon of the kind CLAUDE.md already flags), and Edwards AFB (305,104 ac). The 300-acre figure is not a government threshold. Research note line 85 derives it from analogs (Long Harbour 371 ac, Westwin 480 ac).
3. **The Nickel domestic gate excludes almost nothing.** `buildNickelView` gates only on `rail_mi != null`. 45,987 of 46,759 sites (98.3%) have a rail line within 100 mi, and 31,306 are within 1 mi. The feedstock and demand anchors (`nickel_feedstock_mi`) are displayed but never gate or order anything, so the "domestic feed" lens does not test feed.
4. **Port Nickel, the one former US nickel refinery, is not a row.** The nearest corpus row is FUDS "MISSISSIPPI RIVER (BRAITHWAITE), LO" at 0.98 mi, with no acreage, so the 300-acre gate drops it.
5. **Acreage is unknown for most of the Maritime tab.** 17,002 of 22,938 offshore rows (74%) have no acreage. ACRES (36,003 sites) publishes none, and the Maritime tab has no land gate at all.
6. **Port distance is measured to a bounding-box centre, not a berth.** `ports.json` lat/lon is `envelope_center`. NTAD polygons span up to 113 mi: USACE port code 550 (Coastal) is 112.8 mi wide, code 4820 (AK) 108 mi, code 4646 101 mi, and code 2255 (South Louisiana) 72 mi, centred at 29.38 N, 89.48 W. Channel depth is absent. BTS says depth comes from USACE eHydro and PPFS, and the Principal Ports table has no depth field.
7. **The shipyard list includes federal yards and omits commercial ones.** Three of 16 entries are Navy yards (Norfolk, Puget Sound, Portsmouth), which a private developer cannot use. Bollinger's Louisiana yards (Fourchon, 3 mi from the Gulf, per a 2012 facility sheet) and Conrad Industries are missing; Conrad was not confirmed in search. Nearest listed yard to Golden Meadow / Port Fourchon is about 38 mi (Houma), approximate coordinates. Gulf Island's Houma entry is still listed under Gulf Island, but a search headline reports Bollinger acquired Gulf Island's shipyard facilities. Verify the date and operator.
8. **Water is annual mean flow from gages up to 50 mi away.** `water_flow_cfs` is the USGS annual mean, not 7Q10. Permit practice uses 7Q10: Kentucky's default minimum flow, Mississippi's statutory criterion, NY's passby floor above monthly 7Q10, and Georgia's lesser-of-7Q10-or-inflow rule. 822 sites lack flow (641 no gage, 181 unsupported region). A gage 11.9 mi away (WI0001954841, Peshtigo River) is treated as this site's supply.
9. **Coherence.** The Maritime lens rests on a 1978 NRC floating-plant manufacturing review (NUREG-0502 Part III), not a siting precedent. The Nickel tab asks a brownfield atlas to screen for a refinery, but the fields it needs (acreage, water rights, feed rail) are absent for most of the corpus. 48C is reported fully allocated (secondary source, Oct 2026), so the tab should not imply an open 48C path.
10. **Dead code.** `docs/maritime-score.js` and `docs/nickel-score.js` still exist, though index.html loads only siting-context.js and evidence-categories.js.

Not verified: the EPA nickel-refining NESHAP. Search returned only copper, petroleum and metal-finishing rules, so the "no nickel NESHAP" claim in the research note is unconfirmed. USGS MCS 2026 nickel chapter not read (PDF is a download; I did not retry).

## (b) Criteria table

| Criterion | Published basis | Source |
|---|---|---|
| Principal port | USACE definition by tonnage; BTS CY2023 list | https://geodata.bts.gov/content/e3b6065cce144be8a13a59e03c4195fe |
| Channel depth | Authorized federal depth; eHydro surveys | https://www.bts.gov/PPFS-Tech-Docs |
| Floating plant | NRC FES on floating plants (Part III, NUREG-0502, Dec 1978) | https://www.osti.gov/biblio/6638960 ; https://www.nrc.gov/docs/ML1928/ML19289D149.pdf |
| Water (permit basis) | 7Q10 criterion, state-specific | https://extapps.dec.ny.gov/docs/water_pdf/flowtogsfinal.pdf ; https://www.epa.gov/hydrowq/definition-and-characteristics-low-flows |
| Nickel refinery acreage | None government-published; analog-derived | research/nickel-refining-siting-2026-09.md:85 |
| Energy-community priority | $4B of $10B reserved (FR notice, secondary summary) | https://www.govinfo.gov/content/pkg/FR-2026-10-14/pdf/2026-20962.pdf |

## (c) Proposals

**Maritime: drop the ranking, merge the data into the Nuclear Siting tab.** Keep port and shipyard as evidence rows on site cards, with distance to polygon edge (not centroid) and the port's authorized depth. Drop the coastal-generation lens: port access is not a siting criterion for a grid-connected plant.

**Nickel: merge into a catalog overlay, no ranking.** Keep the 16 anchors as a map and table with their own sources. If a screen survives, use four criteria: (1) port polygon edge within 10 mi, import only; (2) authorized channel depth at that port, value set from the design's draft and cited; (3) parcel-level confirmed land of at least 300 ac, excluding FUDS maneuver areas and river-reach polygons (flag, do not delete); (4) 7Q10 at the nearest gage, not mean flow, with the gage distance shown. The 300-ac and 10-mi thresholds are analyst choices and must be labeled as such.

**Immediate fixes regardless:** sort by something other than name, remove the dead score files, and correct the shipyard list (remove the three naval yards from private screens, add Bollinger and Conrad after verification, check Gulf Island's operator).
