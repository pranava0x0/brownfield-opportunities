#!/usr/bin/env bash
# Re-fetch the DOE national-lab source documents behind
# research/doe-lab-brownfield-reuse.md, then verify against MANIFEST.md.
#
# A browser User-Agent is required: eta-publications.lbl.gov returns 403
# otherwise. Checksums are printed so a silently-changed document is visible.
set -euo pipefail
cd "$(dirname "$0")"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

echo "→ inl-c2n-coal-to-nuclear-2022.pdf"
curl -sSL --max-time 180 -A "$UA" -o "inl-c2n-coal-to-nuclear-2022.pdf" "https://gain.inl.gov/content/uploads/4/2024/11/INL-RPT-22-67964-Investigating-Benefits-and-Challenges-C2N.pdf"
echo "→ lbnl-2024-data-center-energy.pdf"
curl -sSL --max-time 180 -A "$UA" -o "lbnl-2024-data-center-energy.pdf" "https://eta-publications.lbl.gov/sites/default/files/2024-12/lbnl-2024-united-states-data-center-energy-usage-report_1.pdf"
echo "→ inl-bridging-the-gap-powering-data-centers.pdf"
curl -sSL --max-time 180 -A "$UA" -o "inl-bridging-the-gap-powering-data-centers.pdf" "https://inl.gov/content/uploads/2026/01/Bridging-the-Gap-for-Powering-Data-Centers.pdf"
echo "→ lbnl-large-load-literature-review-2025-11.pdf"
curl -sSL --max-time 180 -A "$UA" -o "lbnl-large-load-literature-review-2025-11.pdf" "https://eta-publications.lbl.gov/sites/default/files/2025-11/wip_lbnl_lllreview_oct_update_2025.pdf"
echo "→ nrel-data-centers-gap-analysis.pdf"
curl -sSL --max-time 180 -A "$UA" -o "nrel-data-centers-gap-analysis.pdf" "https://docs.nlr.gov/docs/fy26osti/97168.pdf"
echo "→ nrel-smart-data-center-siting.pdf"
curl -sSL --max-time 180 -A "$UA" -o "nrel-smart-data-center-siting.pdf" "https://docs.nlr.gov/docs/gen/fy25/96080.pdf"

echo; echo "sha256 (compare against MANIFEST.md):"
shasum -a 256 ./*.pdf
