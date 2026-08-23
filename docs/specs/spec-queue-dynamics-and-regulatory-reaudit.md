# Spec 09: Interconnection Queue Dynamics & Federal Regulatory Change Intelligence (LBNL Queued Up + eCFR Automated Re-Audit)

**Status:** Proposed  
**Priority:** Medium (Impact: 4/5, Size: 3/5, Completeness: 4/5)  
**Target Version:** v1.15.0  
**Lead Component:** `connectors/cfr_tracker.py`, `connectors/iso_queue.py`, `docs/app.js`, `docs/provenance.js`

---

## 1. Executive Summary & Value Proposition

Two major operational and market challenges exist in data center and generation siting:
1. **Interconnection Queue Duration**: LBNL's *Queued Up* report documents that typical interconnection request study durations have surged to **over 55 months (4.5+ years)** nationally. However, FERC Order 2023 compliance, PJM's new Cycle reform, ERCOT Batch Zero, and MISO expedited generator replacement rules mean queue delays vary drastically by ISO/RTO and site type.
2. **Automated Regulatory Re-Audit**: Siting policies (`STATE_DC_REGULATION`, `STATE_DC_INCENTIVES`, NRC 10 CFR 50/52/53 rulemaking, EO 14318, NEPA Phase 2 rules) require frequent maintenance. Currently, re-auditing these rows is a manual process vulnerable to doc drift.

This initiative implements:
1. **ISO/RTO Queue Reform Contextual Chips** reflecting market-specific queue timelines, cluster study windows, and repowering fast-track rules.
2. **An automated eCFR Change Tracker** utilizing `nepa-mcp`'s `cfr_compare_versions` and `cfr_history` tools to automate federal regulatory audits.

---

## 2. Queue Reform Matrix & ISO Rules

| RTO / ISO | Standard Cluster Study Delay | Fast-Track / Repowering Transfer Mechanism | Queue Risk Rating |
|---|---|---|---|
| **PJM Interconnection** | New 2-year transition cycle (2025-2026) | Section 49 Generator Replacement (180-day transfer) | Medium-High |
| **ERCOT** | 12 – 18 months (Batch Zero reform) | Large Load Co-Location / Direct Interconnect Study | Low-Medium |
| **MISO** | 4 – 5 years (significant backlogs) | Attachment X Generator Replacement Fast Track | High |
| **SPP** | 3 – 4 years | DISIS Cluster Study Tariff | Medium |
| **NYISO** | 2 – 3 years | Class Year Study Reform | Medium |
| **CAISO** | 4+ years (Track 2 super-clusters) | Interconnection Process Enhancements (IPE) | High |
| **SERC / Non-RTO** | Bilateral utility IRP (1 – 3 years) | Direct utility power purchase / co-location agreement | Low-Medium |

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
