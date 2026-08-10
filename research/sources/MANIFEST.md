# Source manifest — DOE national-lab research

Primary documents behind [`../doe-lab-brownfield-reuse.md`](../doe-lab-brownfield-reuse.md), retrieved **2026-08-09**.

The PDFs are **deliberately not committed** — ~14 MB of re-fetchable federal
documents would violate the repo's no-large-binaries rule, and the findings
that matter are extracted into the research note. This manifest makes the set
reproducible: same URLs, same bytes, verifiable by checksum.

Re-fetch everything:

```bash
bash research/sources/fetch.sh
```

Some of these hosts reject a bare fetch (`eta-publications.lbl.gov` 403s
without a browser User-Agent) and NREL's own host did not resolve at all —
see the data-source notes in the research note.

## `inl-c2n-coal-to-nuclear-2022.pdf`

- **INL/ANL/ORNL — Investigating Benefits and Challenges of Converting Retiring Coal Plants into Nuclear Plants (INL/RPT-22-67964, Sept 2022)**
- URL: https://gain.inl.gov/content/uploads/4/2024/11/INL-RPT-22-67964-Investigating-Benefits-and-Challenges-C2N.pdf
- SHA-256: `087cddb2f7273f93c16609fe2b5161d1f2126509900aa19fdb1d07ea478189b9`
- Size: 1,787,113 bytes

## `lbnl-2024-data-center-energy.pdf`

- **LBNL — 2024 United States Data Center Energy Usage Report (Dec 2024)**
- URL: https://eta-publications.lbl.gov/sites/default/files/2024-12/lbnl-2024-united-states-data-center-energy-usage-report_1.pdf
- SHA-256: `3a2257cdf4c350356062ffd8f75e886f099b13781b0a37af5605d65d5e46c2eb`
- Size: 4,031,183 bytes

## `inl-bridging-the-gap-powering-data-centers.pdf`

- **INL — Bridging the Gap for Powering Data Centers (INL/RPT-26-89901, Jan 2026)**
- URL: https://inl.gov/content/uploads/2026/01/Bridging-the-Gap-for-Powering-Data-Centers.pdf
- SHA-256: `11ff2607d64fdb30cbc1cf87f3af85d59f338515394f23fb5a4745b13ffdc184`
- Size: 813,086 bytes

## `lbnl-large-load-literature-review-2025-11.pdf`

- **LBNL — Large Load Literature Review, November 2025 Update**
- URL: https://eta-publications.lbl.gov/sites/default/files/2025-11/wip_lbnl_lllreview_oct_update_2025.pdf
- SHA-256: `d35d41afd1b68a843a55a378a7175c6e25b6d3e54136af6a83fd8947e3c0ef53`
- Size: 3,464,040 bytes

## `nrel-data-centers-gap-analysis.pdf`

- **NREL / National Laboratory of the Rockies — Data Centers Gap Analysis (GDO Planning for Large Loads, Feb 2026)**
- URL: https://docs.nlr.gov/docs/fy26osti/97168.pdf
- SHA-256: `cf4560ccbea28e0c02f978ab2c2609256fa854d00f7cd584cc6b8835c025af45`
- Size: 3,389,032 bytes

## `nrel-smart-data-center-siting.pdf`

- **NREL / National Laboratory of the Rockies — Smart Data Center Siting Backed by NREL Expertise**
- URL: https://docs.nlr.gov/docs/gen/fy25/96080.pdf
- SHA-256: `f4c5beda2764fae0a18c56ab2dc5c46e9a4dc811520404cc4a40e373e7162caf`
- Size: 639,846 bytes
