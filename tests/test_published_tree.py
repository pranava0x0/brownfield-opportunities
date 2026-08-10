"""Guards on what actually ships to the website.

`.github/workflows/deploy.yml` publishes `path: docs`, so `docs/` is the whole
public surface and everything else in the repo is build-time or reference
material. The research PDFs under `research/sources/` are committed
deliberately — pinned bytes beat a link that rots — on the explicit condition
that they never load with the site.

That condition is easy to break by accident: someone tidies "all the PDFs"
into one folder, or a connector writes a reference doc into `docs/data/`. The
result would be tens of megabytes silently added to a page whose whole design
premise is a small payload. So it is asserted here rather than remembered.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
RESEARCH = ROOT / "research"

# PDFs that legitimately live in the published tree. Both are linked on demand
# from the Nuclear Siting tab — a click, never a page-load fetch. Anything new
# here needs the same justification.
ALLOWED_PUBLISHED_PDFS = {
    "data/references/INL-AP1000-Opportunities-Sort128167.pdf",
    "data/references/Idaho-Advanced-Nuclear-Strategic-Framework.pdf",
}

# Nothing the browser pulls automatically should approach this. The existing
# reference PDFs are click-through, so they are excluded from the tally.
MAX_UNEXPECTED_PUBLISHED_PDF_MB = 0


def test_research_sources_live_outside_the_published_tree():
    """The research corpus must never sit under docs/."""
    if not RESEARCH.exists():
        return
    offenders = [
        p.relative_to(ROOT)
        for p in RESEARCH.rglob("*")
        if p.is_file() and DOCS in p.parents
    ]
    assert not offenders, (
        f"research files found inside the published directory: {offenders}. "
        "docs/ is deployed verbatim by deploy.yml; research belongs at the "
        "repo root."
    )


def test_no_unexpected_pdfs_in_the_published_tree():
    """A PDF in docs/ ships to the website — allowlist it or move it out."""
    found = {
        str(p.relative_to(DOCS)) for p in DOCS.rglob("*.pdf")
    }
    unexpected = sorted(found - ALLOWED_PUBLISHED_PDFS)
    assert not unexpected, (
        f"unexpected PDFs inside docs/: {unexpected}. These would be published "
        "with the site. Put reference documents in research/ (repo root), or "
        "add to ALLOWED_PUBLISHED_PDFS with a note on why the site needs them."
    )


def test_research_pdfs_are_not_referenced_by_any_published_asset():
    """No page may fetch or link a research PDF, even by hand-written path."""
    if not (RESEARCH / "sources").exists():
        return
    names = [p.name for p in (RESEARCH / "sources").glob("*.pdf")]
    if not names:
        return
    hits = []
    for asset in list(DOCS.rglob("*.html")) + list(DOCS.rglob("*.js")) \
            + list(DOCS.rglob("*.css")) + list(DOCS.rglob("*.txt")):
        try:
            text = asset.read_text(errors="ignore")
        except OSError:
            continue
        if "research/sources" in text:
            hits.append(f"{asset.relative_to(ROOT)}: references research/sources")
        for name in names:
            if name in text:
                hits.append(f"{asset.relative_to(ROOT)}: references {name}")
    assert not hits, hits


def test_deploy_workflow_still_publishes_only_docs():
    """Every guard above assumes docs/ is the entire published surface.

    If the deploy path ever widens, these tests stop meaning anything — so
    fail loudly here rather than quietly losing the protection.
    """
    wf = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "path: docs" in wf, (
        "deploy.yml no longer publishes `path: docs`. The published-tree "
        "guards in this file are scoped to docs/ and must be revisited."
    )
