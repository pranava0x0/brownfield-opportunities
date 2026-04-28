"""Diff two sites.json payloads → human-readable changes summary.

Used by refresh.py after each successful run, and by the refresh.yml workflow
to build commit-message subjects.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# Fields whose changes we surface in the per-site changed list. Everything
# else (geometry, addresses, profile URLs) churns too much to be useful.
TRACKED_FIELDS = ("acreage", "npl_status_code", "npl_status", "name", "state")


def load_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def diff_payloads(
    prior: dict[str, Any] | None, current: dict[str, Any]
) -> dict[str, Any]:
    """Compute added / removed / changed sites by EPA_ID."""
    cur_by_id = {s["epa_id"]: s for s in current.get("sites", []) if s.get("epa_id")}
    prior_sites = (prior or {}).get("sites", [])
    prior_by_id = {s["epa_id"]: s for s in prior_sites if s.get("epa_id")}

    added_ids = sorted(set(cur_by_id) - set(prior_by_id))
    removed_ids = sorted(set(prior_by_id) - set(cur_by_id))

    changed: list[dict[str, Any]] = []
    for epa_id in sorted(set(cur_by_id) & set(prior_by_id)):
        before = prior_by_id[epa_id]
        after = cur_by_id[epa_id]
        deltas = {
            f: (before.get(f), after.get(f))
            for f in TRACKED_FIELDS
            if before.get(f) != after.get(f)
        }
        if deltas:
            changed.append({"epa_id": epa_id, "name": after.get("name"), "deltas": deltas})

    return {
        "prior_count": len(prior_by_id),
        "current_count": len(cur_by_id),
        "added": [cur_by_id[i] for i in added_ids],
        "removed": [prior_by_id[i] for i in removed_ids],
        "changed": changed,
    }


def short_summary(diff: dict[str, Any]) -> str:
    """One-line summary, suitable for a commit message subject."""
    return f"+{len(diff['added'])} −{len(diff['removed'])} ~{len(diff['changed'])} sites"


def render_markdown(diff: dict[str, Any], generated_at: str) -> str:
    """Full Markdown report for `data/changes.md`."""
    lines: list[str] = [
        f"# Changes — {generated_at}",
        "",
        f"**Summary:** {short_summary(diff)}  ",
        f"prior: {diff['prior_count']} sites → current: {diff['current_count']} sites",
        "",
    ]

    if diff["added"]:
        lines.append(f"## Added ({len(diff['added'])})")
        lines.append("")
        for s in diff["added"]:
            ac = f"{s['acreage']:,.1f} ac" if s.get("acreage") is not None else "no acreage"
            lines.append(f"- `{s.get('epa_id')}` — {s.get('name')} ({s.get('state')}) — {ac}")
        lines.append("")

    if diff["removed"]:
        lines.append(f"## Removed ({len(diff['removed'])})")
        lines.append("")
        for s in diff["removed"]:
            lines.append(f"- `{s.get('epa_id')}` — {s.get('name')} ({s.get('state')})")
        lines.append("")

    if diff["changed"]:
        lines.append(f"## Changed ({len(diff['changed'])})")
        lines.append("")
        for c in diff["changed"]:
            lines.append(f"- `{c['epa_id']}` — {c['name']}")
            for field, (before, after) in c["deltas"].items():
                lines.append(f"  - **{field}:** `{before}` → `{after}`")
        lines.append("")

    if not (diff["added"] or diff["removed"] or diff["changed"]):
        lines.append("_No changes._")
        lines.append("")

    return "\n".join(lines)
