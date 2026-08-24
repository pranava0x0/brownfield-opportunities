# Spec 09: Interconnection Queue Dynamics & Federal Regulatory Change Intelligence (LBNL Queued Up + eCFR Automated Re-Audit)

**Status:** Proposed  
**Priority:** Medium (Impact: 4/5, Size: 3/5, Completeness: 4/5)  
**Target Version:** v1.15.0  
**Lead Component:** `connectors/cfr_tracker.py`, `connectors/iso_queue.py`, `docs/app.js`, `docs/provenance.js`

---

## 1. Executive Summary & Value Proposition

Two major operational and market challenges exist in data center and generation siting:
1. **Interconnection Queue Duration**: LBNL's *Queued Up* report documents that typical interconnection request study durations have surged to **over 55 months (4.5+ years)** nationally. However, FERC Order 2023 compliance, PJM's new Cycle reform, ERCOT Batch Zero, and MISO expedited generator replacement rules mean queue delays vary drastically by ISO/RTO and site type.
2. **Automated Regulatory Re-Audit**: Siting policies (`STATE_DC_REGULATION`, `STATE_DC_INCENTIVES`, NRC 10 CFR 50/52/53 rulemaking, EO 14318, NEPA Phase 2 rules) require frequent maintenance. Currently, re-auditing these rows is a manual process vulnerable to doc drift. The Aug-2026 sweep widens the audit scope: the state bill mix flipped from tax incentives (58%→14.9% of DC bills, 2024→2026) to **ratepayer/rate-class measures** (5%→11.7%), and utility **DC-specific tariffs** (TVA's Aug-2026 rate class is the template) now move faster than statutes — the quarterly re-audit must sweep utility board actions, not just legislatures.

This initiative implements:
1. **ISO/RTO Queue Reform Contextual Chips** reflecting market-specific queue timelines, cluster study windows, and repowering fast-track rules.
2. **An automated eCFR Change Tracker** utilizing `nepa-mcp`'s `cfr_compare_versions` and `cfr_history` tools to automate federal regulatory audits.

---

## 2. The Federal Clock, then the Queue Matrix

**Anchor every queue chip to the FERC large-load docket timeline** (verified Aug 2026 — see
[research/industry-topical-2026-08.md](../../research/industry-topical-2026-08.md) §T2):

1. Oct 2025 — DOE Organization Act §403 directive forces a FERC large-load (>20 MW) rulemaking.
2. Dec 2025 — FERC orders PJM to write explicit co-location rules (post-Talen/Susquehanna).
3. Jun 2026 — FERC §206 **show-cause orders to all six RTOs/ISOs** on large-load integration
   (five named issues: study process incl. "electrically proximate"/co-located loads, cost-shift
   prevention, transparency, alternative transmission tech, timelines).
4. H2 2026 — RTO compliance filings; FERC action on the docket.

This is also the subject of the companion **FERC Show Cause Orders microsite** — the queue chips
should deep-link to it rather than duplicating its tracking.

| RTO / ISO | Standard Study Reality | Verified Fast-Track / POI-Reuse Mechanism | Queue Risk Rating |
|---|---|---|---|
| **PJM** | 2-year transition cycles (2025-26) | **Surplus Interconnection Service** (Order 845) + **generator Replacement process**; RRI (Dec 2024); **Expedited Interconnection Track** — FERC-approved 2026-06-09, accepting requests (≥500 MW, state-sponsored, ≤10/yr, sunsets 2027) | Medium-High |
| **ERCOT** | Connect-and-manage (gen); new PUCT-approved **Batch Study** framework for large loads — **Batch Zero** classifications were due 2026-08-07 but are **paused** under the Governor's large-load verification directive (PCLR / WLPUN designations) | TX **SB6 (2025)** co-location + interconnection statute | Low-Medium |
| **MISO** | 4–5 years (backlogs) | Generator Replacement + surplus study; **ERAS** (Expedited Resource Addition Study, 2025) | High |
| **SPP** | 3–4 years | DISIS cluster study; expedited RA study proposals | Medium |
| **NYISO** | 2–3 years | Class Year reform; note the state-level **Responsible Data Center Development Act** (passed 2026-06-04) + EO 62 gate large loads before the queue | Medium-High |
| **CAISO** | 4+ years (Track 2 super-clusters) | Interconnection Process Enhancements (IPE) | High |
| **TVA / SERC / Non-RTO** | Bilateral utility (1–3 years) | Direct-serve agreements (e.g. xAI→TVA Aug 2026) — but see **TVA's new DC rate class** (+10% phased, capacity-commitment charge, >5 MW adder, eff. Oct 2026) | Low-Medium |

**Never cite a tariff section number that has not been read** — the v1 draft's "PJM Section 49 /
MISO Attachment X" shorthand conflated document names with mechanisms; use the mechanism names
above and link primary sources.

---

## 3. Data Schema & Contracts

### 3.1 Python CFR Regulatory Audit Schema (`schema.py`)

```python
class CfrAuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    citation: str = Field(description="e.g. '10 CFR 50.47' or '40 CFR 1502.10'")
    title: str
    last_verified_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    last_amended_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    has_pending_amendments: bool
    summary_of_changes: Optional[str] = None
    cfr_url: HttpUrl
```

---

## 4. UI/UX Integration

- **Rankings Table & Detail Panel**:
  - Adds an **"ISO Queue Context"** pill (e.g. `⚡ PJM: Section 49 Queue-Skip Eligible` or `⏳ MISO: 4-Yr Queue Stagnation Risk`).
- **Regulatory Status Badge**:
  - Displays automated verified timestamps for federal regulations in the detail panel evidence section.

---

## 5. Verification & Test Plan

- **Unit Tests (`tests/test_cfr_tracker.py`)**:
  - Test eCFR version diffing against historical known rule changes.
- **E2E Playwright Tests (`tests/e2e/test_queue_chips.py`)**:
  - Verify queue context chips render accurately based on site state and ISO/RTO jurisdiction.
---

## NEPA-MCP expansion (2026-08-24)

- The `cfr` server's seven tools are confirmed live and credential-free
  (`cfr_resolve_citation`, `cfr_resolve_executive_order`,
  `cfr_resolve_fr_citation`, `cfr_history`, `cfr_rulemaking`,
  `cfr_compare_versions`, `cfr_browse_structure`) — the federal half of the
  automated re-audit has a working backend today.
- Concrete first target set for `cfr_history`/`cfr_rulemaking` sweeps, each
  with a `verified_at` already in the repo: EO 14299 + EO 14318 (via
  `cfr_resolve_executive_order`), 10 CFR 50/52/53 rulemaking (NRC Part 53
  finalization watch), 10 CFR 1021 (DOE NEPA procedures — the Hanford
  pathway table cites it), 40 CFR 1500-1508 (CEQ), and the IRA 48E/45X
  guidance trail. Empty window → bump `verified_at` with evidence;
  non-empty → human reads the diff.
- The split stays honest: state statutes and utility tariffs are NOT in the
  CFR — `STATE_DC_REGULATION`/`STATE_DC_INCENTIVES` keep their manual
  evidence stream; this automates only the federal instruments.
