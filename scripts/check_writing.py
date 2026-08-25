#!/usr/bin/env python3
"""Flag AI-slop writing in user-visible copy, commit messages, and PR text.

The problem this exists for: LLM-drafted prose has a small set of recurring
tells, and they cluster in exactly the surfaces users read — tab leads,
section intros, curated dossier text, commit subjects, PR bodies. They are
easy to spot once named and almost invisible while writing.

Two severities, and the split is the whole design:

  BANNED (FAIL)  phrases with no legitimate use in this repo's copy —
                 "off the table", "end-to-end", "hand-curated", puffery
                 ("a testament to", "delve", "nestled"), and self-praise
                 about the tool's own honesty. These are never right; if one
                 is genuinely needed, add it to ALLOW_PHRASES with a reason.

  REVIEW (WARN)  patterns that are usually slop but sometimes load-bearing —
                 talking about citations instead of just linking them,
                 negative parallelism ("X, not Y"), em-dash pile-ups, vague
                 attribution. A human decides. WARN keeps them visible
                 without blocking a merge on a judgement call.

Only prose is scanned. HTML tags and comments, JS comments, Markdown code
fences, and inline code are stripped first, so identifiers and URLs never
trip a rule (`hanford-e2e.json` is a filename, not the phrase "end to end").

Usage:
  python3 scripts/check_writing.py                    # user-visible copy
  python3 scripts/check_writing.py --commits origin/main..HEAD
  python3 scripts/check_writing.py --pr 24
  git log -1 --format=%B | python3 scripts/check_writing.py --stdin
  python3 scripts/check_writing.py --list             # show the rules
  python3 scripts/check_writing.py --fail-on WARN     # strict

Reference for the pattern families: Wikipedia's "Signs of AI writing"
(negative parallelism, puffery, self-referential meta-commentary about
sources rather than just citing them).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------
# What counts as user-visible copy. Internal docs (CLAUDE.md, AGENTS.md,
# issues.md, backlog.md) are deliberately EXCLUDED: they are engineering
# notes for contributors, they quote the very phrases this tool bans when
# recording why they were banned, and holding them to marketing-copy
# standards would be noise.
# --------------------------------------------------------------------------
COPY_GLOBS = (
    "docs/index.html",
    "docs/app.js",
    "docs/llms.txt",
    "README.md",
    "docs/data/*e2e.json",
)


class Rule:
    def __init__(self, rule_id: str, level: str, pattern: str, why: str,
                 slogan_only: bool = False,
                 scopes: tuple = ("copy", "text")) -> None:
        self.id = rule_id
        self.level = level  # FAIL | WARN
        self.rx = re.compile(pattern, re.I)
        self.why = why
        # Where the rule applies. "copy" = user-visible product text;
        # "text" = commit messages and PR bodies. They are different
        # registers: a PR body saying "extended the citation-liveness
        # check" is engineering vocabulary, while product copy saying
        # "every claim is cited" is the tell this rule exists for.
        self.scopes = scopes
        # Fire only when the match is a short trailing flourish rather than
        # part of a sentence that is explaining something. See SLOGAN_MAX_*.
        self.slogan_only = slogan_only


# A negation reads as a slogan when the sentence carrying it is short and the
# negation sits at its end ("screening evidence, never an agency
# determination"). The same words inside a longer sentence are usually doing
# real explanatory work and should not be flagged.
SLOGAN_MAX_SENTENCE = 110
SLOGAN_TAIL_CHARS = 45


def _is_slogan(line: str, start: int, end: int) -> bool:
    """True when the match sits at the tail of a short sentence."""
    left = max(line.rfind(".", 0, start), line.rfind(";", 0, start)) + 1
    right = min((i for i in (line.find(".", end), line.find(";", end))
                 if i != -1), default=len(line))
    sentence = line[left:right]
    if len(sentence.strip()) > SLOGAN_MAX_SENTENCE:
        return False
    return (right - end) <= SLOGAN_TAIL_CHARS


# --- BANNED: no legitimate use in this repo's user-visible copy ------------
BANNED = [
    Rule("off-the-table", "FAIL", r"\boff the table\b",
         'idiom; name the actual constraint ("designation rules it out")'),
    Rule("end-to-end", "FAIL", r"\bend[-\s]to[-\s]end\b",
         'buzzword; say what it actually covers'),
    Rule("hand-curated", "FAIL", r"\bhand[-\s]curated\b",
         'usually untrue of AI-drafted text; say how it was produced'),
    Rule("puffery", "FAIL",
         r"\b(a testament to|stands? as a testament|delve|tapestry|nestled|"
         r"vibrant|groundbreaking(?!\s+(?:held|already|ceremony|took place|on\b))|"
         r"game[-\s]chang(?:er|ing)|"
         r"unlock(?:ing)? the (?:power|potential)|seamlessly integrat\w*)\b",
         'promotional filler'),
    Rule("self-praise", "FAIL",
         r"\b(out loud|with the same confidence|textbook case|"
         r"the ideal [\w\s-]{0,25}example|rather than invented|"
         r"never silently|honest(?:ly)? (?:siting|about|assessment)|"
         r"an honest [\w\s-]{0,20}(?:call|tool|dossier))\b",
         'the copy praising its own integrity; state the fact instead'),
    Rule("citation-boast", "FAIL",
         r"\b(every claim links its source|links? its source|"
         r"carries its citation|cited per row|each row'?s own)\b",
         'talking about citations instead of just linking them'),
    Rule("negation-slogan", "FAIL",
         r"\b(it'?s not just|not just [\w\s]{1,20}(?:but|it'?s)|"
         r"is never a no-hit|not no-hit)\b",
         'negative-parallelism slogan'),
    Rule("ai-opener", "FAIL",
         r"\b(in today'?s (?:world|landscape|digital age)|let'?s dive in|"
         r"navigating the complex\w*|it'?s important to note|"
         r"when it comes to)\b",
         'chatbot connective tissue'),
]

# --- REVIEW: often slop, sometimes load-bearing ----------------------------
REVIEW = [
    Rule("citation-meta", "WARN", r"\b(cited|citing|citations?)\b",
         'prefer adding the link over describing that it is cited',
         scopes=("copy",)),
    Rule("negative-parallelism", "WARN",
         r"(,\s+not (?:a|an|the|just)\b|\bnever an?\s+\w+|\bnot merely\b)",
         'define by what a thing IS; keep only load-bearing caveats',
         slogan_only=True),
    Rule("vague-attribution", "WARN",
         r"\b(is|are) cited at\b|\b(experts|observers|analysts) (say|argue|cite)\b"
         r"|\bindustry reports\b|\bstudies show\b|\bit is (?:widely )?believed\b",
         'name the source or drop the claim'),
    Rule("hedge-stack", "WARN",
         r"\b(might potentially|could possibly|may perhaps|somewhat unclear)\b",
         'two hedges where one would do'),
    Rule("em-dash-pileup", "WARN", r"—[^—]{0,120}—[^—]{0,120}—",
         'three or more em dashes in close succession; use sentences'),
]

RULES = BANNED + REVIEW

# --------------------------------------------------------------------------
# Suppressions. A match is dropped when it falls inside one of these spans.
# Each entry needs a reason — this list is the escape hatch, and an
# unexplained entry is how a ban quietly stops meaning anything.
# --------------------------------------------------------------------------
ALLOW_PHRASES = [
    # Statutory / official program names keep their real wording.
    ("Clean Energy on Mine Lands", "DOE program name"),
    ("Cleanup to Clean Energy", "DOE program name"),
    # Short legal caveats that must state what a thing is NOT.
    ("not a determination", "required NEPA disclaimer"),
    ("agencies make the actual determinations", "required NEPA disclaimer"),
    ("not an agency determination", "required NEPA disclaimer"),
    ("different from a result of zero", "distinguishes unavailable from zero"),
    # Scoring vocabulary that is genuinely contrastive.
    ("not a ranked factor", "threshold-vs-ranked is a real scoring distinction"),
    ("not a computed score", "distinguishes EPA's flag from our score"),
    ("not the computed scores", "distinguishes editorial from computed"),
    ("not calculated from them", "distinguishes editorial from computed"),
    ("not a measured layer", "distinguishes analyst research from GIS"),
    ("not a design-feasibility finding", "required scoping caveat"),
    ("not a new site list", "required scoping caveat"),
    ("not surveyed parcel boundaries", "coordinate precision caveat"),
    ("not a permit decision", "required NEPA disclaimer"),
    ("not a suitability score", "required NEPA disclaimer"),
    ("not a project footprint", "buffer-vs-footprint caveat"),
    ("not a conclusion", "tribal-consultation caveat"),
    ("not a disqualifier", "flood-context caveat"),
    ("not a block", "regulatory-friction caveat"),
    ("not a like-for-like", "reactor-class caveat"),
    ("not a hole", "explains a meaningful null"),
    ("not a bug", "explains intended behaviour"),
    ("not the largest", "explains the peaked acreage curve"),
    ("not the plant parcel", "buffer-vs-parcel caveat"),
]


class Hit:
    def __init__(self, rule: Rule, source: str, line_no: int,
                 matched: str, context: str) -> None:
        self.rule = rule
        self.source = source
        self.line_no = line_no
        self.matched = matched
        self.context = context

    def line(self) -> str:
        loc = f"{self.source}:{self.line_no}" if self.line_no else self.source
        return (f"[{self.rule.level}] {self.rule.id:22} {loc:46} "
                f"{self.matched!r} — {self.rule.why}\n"
                f"         … {self.context.strip()[:150]}")

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule.id, "level": self.rule.level,
                "source": self.source, "line": self.line_no,
                "matched": self.matched, "why": self.rule.why,
                "context": self.context.strip()[:300]}


# --------------------------------------------------------------------------
# Prose extraction. Everything here exists to avoid false positives: a rule
# should only ever see text a human reads.
# --------------------------------------------------------------------------
def _blank_out(text: str, pattern: str) -> str:
    """Remove matches but keep newlines, so line numbers stay correct."""
    return re.sub(pattern, lambda m: "\n" * m.group(0).count("\n"), text,
                  flags=re.S)


def prose_lines_html(text: str) -> Iterator[tuple[int, str]]:
    text = _blank_out(text, r"<!--.*?-->")
    text = _blank_out(text, r"<script\b.*?</script>")
    text = _blank_out(text, r"<style\b.*?</style>")
    for i, raw in enumerate(text.splitlines(), 1):
        # Drop tags (and with them every attribute value and URL).
        yield i, re.sub(r"<[^>]*>", " ", raw)


def prose_lines_js(text: str) -> Iterator[tuple[int, str]]:
    text = _blank_out(text, r"/\*.*?\*/")
    out = []
    for raw in text.splitlines():
        stripped = raw.lstrip()
        # Whole-line comments are engineering notes, not user copy.
        out.append("" if stripped.startswith("//") else raw)
    for i, raw in enumerate(out, 1):
        # JS string literals carry HTML; strip tags so class names and URLs
        # cannot match a prose rule.
        yield i, re.sub(r"<[^>]*>", " ", raw)


def prose_lines_md(text: str) -> Iterator[tuple[int, str]]:
    text = _blank_out(text, r"```.*?```")
    for i, raw in enumerate(text.splitlines(), 1):
        line = re.sub(r"`[^`]*`", " ", raw)          # inline code
        line = re.sub(r"\]\([^)]*\)", "] ", line)     # link targets
        line = re.sub(r"<[^>]*>", " ", line)
        yield i, line


def prose_lines_json(text: str) -> Iterator[tuple[str, str]]:
    """Yield (json path, string value) for every human-readable string."""
    doc = json.loads(text)
    skip_keys = {"source_url", "url", "geojson_url", "id", "type", "fit",
                 "constraint", "category", "verified_at", "generated_at"}

    def walk(node: Any, path: str) -> Iterator[tuple[str, str]]:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in skip_keys:
                    continue
                yield from walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and len(node) > 12 and " " in node:
            yield path, node

    yield from walk(doc, "")


def allowed_spans(line: str) -> list[tuple[int, int]]:
    spans = []
    low = line.lower()
    for phrase, _reason in ALLOW_PHRASES:
        start = 0
        p = phrase.lower()
        while (idx := low.find(p, start)) != -1:
            spans.append((idx, idx + len(p)))
            start = idx + 1
    return spans


def scan_text(source: str, units: Iterable[tuple[Any, str]],
              rules: list[Rule]) -> Iterator[Hit]:
    for loc, line in units:
        if not line.strip():
            continue
        skip = allowed_spans(line)
        for rule in rules:
            for m in rule.rx.finditer(line):
                # Overlap, not containment: a rule often matches a slightly
                # wider span than the allowed phrase (", not a" vs "not a
                # determination"), and requiring containment would let the
                # suppression silently miss.
                if any(m.start() < e and s < m.end() for s, e in skip):
                    continue
                if rule.slogan_only and not _is_slogan(line, m.start(), m.end()):
                    continue
                yield Hit(rule, source if isinstance(loc, int) else f"{source}{loc}",
                          loc if isinstance(loc, int) else 0, m.group(0), line)


def scan_file(path: Path, rules: list[Rule]) -> Iterator[Hit]:
    rel = str(path.relative_to(ROOT))
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        yield from scan_text(rel, prose_lines_html(text), rules)
    elif path.suffix == ".js":
        yield from scan_text(rel, prose_lines_js(text), rules)
    elif path.suffix == ".json":
        yield from scan_text(rel, prose_lines_json(text), rules)
    else:
        yield from scan_text(rel, prose_lines_md(text), rules)


def collect_copy_files() -> list[Path]:
    out: list[Path] = []
    for pattern in COPY_GLOBS:
        out.extend(sorted(ROOT.glob(pattern)))
    return [p for p in out if p.is_file()]


def git_commit_messages(rev_range: str) -> list[tuple[str, str]]:
    """[(sha, message)] for a range like origin/main..HEAD."""
    sep = "\x1e"
    proc = subprocess.run(
        ["git", "log", f"--format=%H%x1f%B{sep}", rev_range],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git log failed")
    out = []
    for chunk in proc.stdout.split(sep):
        if not chunk.strip():
            continue
        sha, _, body = chunk.strip().partition("\x1f")
        out.append((sha[:9], body))
    return out


def pr_text(number: int) -> str:
    proc = subprocess.run(
        ["gh", "pr", "view", str(number), "--json", "title,body"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "gh pr view failed")
    d = json.loads(proc.stdout)
    return f"{d.get('title', '')}\n\n{d.get('body', '')}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commits", metavar="RANGE",
                    help="Scan commit messages in a git range (origin/main..HEAD).")
    ap.add_argument("--pr", type=int, help="Scan a PR's title and body via gh.")
    ap.add_argument("--stdin", action="store_true", help="Scan text on stdin.")
    ap.add_argument("--files", nargs="*", default=None,
                    help="Scan these files instead of the default copy set.")
    ap.add_argument("--no-copy", action="store_true",
                    help="Skip the user-visible copy scan.")
    ap.add_argument("--only", nargs="*", default=None,
                    help="Run only these rule ids.")
    ap.add_argument("--json", type=Path, default=None, help="Write findings here.")
    ap.add_argument("--list", action="store_true", help="List rules and exit.")
    ap.add_argument("--fail-on", default="FAIL", choices=["FAIL", "WARN", "NEVER"],
                    help="Exit non-zero at this severity or worse (default FAIL).")
    args = ap.parse_args()

    if args.list:
        for r in RULES:
            print(f"{r.level:5} {r.id:22} [{'+'.join(r.scopes)}] {r.why}")
        return 0

    rules = [r for r in RULES if not args.only or r.id in args.only]
    text_rules = [r for r in rules if "text" in r.scopes]
    copy_rules = [r for r in rules if "copy" in r.scopes]
    hits: list[Hit] = []

    if args.stdin:
        text = sys.stdin.read()
        hits += list(scan_text("<stdin>", enumerate(text.splitlines(), 1), text_rules))

    if args.commits:
        for sha, body in git_commit_messages(args.commits):
            hits += list(scan_text(f"commit {sha}",
                                   enumerate(body.splitlines(), 1), text_rules))

    if args.pr is not None:
        hits += list(scan_text(f"PR #{args.pr}",
                               enumerate(pr_text(args.pr).splitlines(), 1), text_rules))

    scan_copy = not args.no_copy and not (args.stdin or args.commits or args.pr) \
        or args.files is not None
    if scan_copy:
        targets = ([Path(f).resolve() for f in args.files]
                   if args.files is not None else collect_copy_files())
        for path in targets:
            hits += list(scan_file(path, copy_rules))

    fails = [h for h in hits if h.rule.level == "FAIL"]
    warns = [h for h in hits if h.rule.level == "WARN"]

    for h in fails:
        print(h.line())
    if fails and warns:
        print()
    for h in warns:
        print(h.line())

    print("\n" + "=" * 78)
    print(f"{len(fails)} banned · {len(warns)} review   "
          f"({len(hits)} findings across {len({h.source for h in hits})} sources)")
    if not hits:
        print("no slop found")

    if args.json:
        args.json.write_text(json.dumps([h.to_dict() for h in hits], indent=1))
        print(f"full detail → {args.json}")

    if args.fail_on == "NEVER":
        return 0
    if fails:
        return 1
    if args.fail_on == "WARN" and warns:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
