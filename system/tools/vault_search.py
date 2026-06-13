#!/usr/bin/env python3
"""Snippet-level retrieval over the knowledge vault.

context_loader.py answers "which files should I read first?". This tool answers
"what does the vault actually say about X?" by returning ranked section-level
snippets (path + heading breadcrumb + excerpt) so an agent reads ~300 tokens of
relevant passages instead of loading whole pages.

Pure stdlib, deterministic. Ranking is BM25-lite over markdown sections, with a
canonical-precedence boost so context/ source-of-truth files outrank their
wiki/ evidence shadows.

Usage:
    python3 system/tools/vault_search.py "annual discount churn"
    python3 system/tools/vault_search.py "your topic" --k 8 --json
    python3 system/tools/vault_search.py "pricing" --scope wiki,context
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, asdict
from pathlib import Path

# Durable, human-curated text corpus. outputs/ is included but capped to text;
# logs/, state/, archives/, inbox/, sources/data are excluded as non-durable or
# raw. Add scopes explicitly via --scope to widen.
DEFAULT_SCOPES = ["context", "wiki", "decisions", "rules", "outputs", "projects"]
EXCLUDED_PARTS = {".git", "node_modules", "__pycache__", ".obsidian"}
MAX_FILE_BYTES = 400_000  # skip huge generated artifacts
SNIPPET_LINES = 6

# Canonical files outrank their derived shadows on ties (see repo_audit
# canonical-shadow guardrail). Boost is multiplicative on the section score.
CANONICAL_BOOST = 1.25
SHADOW_PENALTY = 0.85
SHADOW_DIRS = ("wiki/evidence/context", "wiki/themes")

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "for", "on", "with",
    "this", "that", "it", "as", "by", "be", "are", "at", "from", "we", "i",
    "how", "what", "when", "should", "do", "does", "can",
}
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-']+")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


@dataclass
class Section:
    path: str
    heading_path: str
    start_line: int
    text: str
    tokens: list[str]


def iter_files(root: Path, scopes: list[str]):
    for scope in scopes:
        base = root / scope
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            if any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path


def split_sections(path: Path, root: Path) -> list[Section]:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    rel = path.relative_to(root).as_posix()
    sections: list[Section] = []
    # heading stack: list of (level, title)
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    buf_start = 1
    in_frontmatter = False

    # Files with few headings (e.g. a long bullet list under one title) would
    # otherwise become one giant low-density section that BM25 penalizes for
    # length, burying specific answers. Sub-chunk large sections at blank lines
    # so each paragraph/bullet block is independently rankable.
    CHUNK_CHARS = 700

    def flush(end_line: int):
        if not buf:
            return
        body = "\n".join(buf).strip()
        if not body:
            return
        crumb = " > ".join(t for _, t in stack) or "(top)"
        if len(body) <= CHUNK_CHARS:
            sections.append(Section(rel, crumb, buf_start, body, tokenize(crumb + " " + body)))
            return
        # Split into blank-line-separated blocks, tracking line offsets.
        block_lines: list[str] = []
        block_start = buf_start
        cur = buf_start
        chunks: list[tuple[int, str]] = []
        for ln in buf:
            if ln.strip() == "" and block_lines:
                chunks.append((block_start, "\n".join(block_lines).strip()))
                block_lines = []
                block_start = cur + 1
            else:
                if not block_lines:
                    block_start = cur
                block_lines.append(ln)
            cur += 1
        if block_lines:
            chunks.append((block_start, "\n".join(block_lines).strip()))
        for start, chunk in chunks:
            if chunk:
                sections.append(Section(rel, crumb, start, chunk, tokenize(crumb + " " + chunk)))

    for idx, line in enumerate(lines, start=1):
        if idx == 1 and line.strip() == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if line.strip() == "---":
                in_frontmatter = False
                buf_start = idx + 1
            continue
        m = HEADING_RE.match(line)
        if m:
            flush(idx - 1)
            buf = []
            buf_start = idx
            level = len(m.group(1))
            title = m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            buf.append(line)
        else:
            buf.append(line)
    flush(len(lines))
    return sections


def build_index(root: Path, scopes: list[str]) -> list[Section]:
    sections: list[Section] = []
    for path in iter_files(root, scopes):
        sections.extend(split_sections(path, root))
    return sections


def bm25_rank(sections: list[Section], query: str, k: int) -> list[tuple[float, Section]]:
    q_terms = tokenize(query)
    if not q_terms:
        return []
    N = len(sections) or 1
    avg_len = sum(len(s.tokens) for s in sections) / N or 1.0
    # document frequency
    df: dict[str, int] = {}
    for s in sections:
        for term in set(s.tokens):
            df[term] = df.get(term, 0) + 1
    k1, b = 1.5, 0.75
    scored: list[tuple[float, Section]] = []
    for s in sections:
        if not s.tokens:
            continue
        tf: dict[str, int] = {}
        for t in s.tokens:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        dl = len(s.tokens)
        for term in q_terms:
            if term not in tf:
                continue
            idf = math.log(1 + (N - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            freq = tf[term]
            score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avg_len))
        if score <= 0:
            continue
        # canonical precedence adjustment
        if s.path.startswith("context/"):
            score *= CANONICAL_BOOST
        elif s.path.startswith(SHADOW_DIRS):
            score *= SHADOW_PENALTY
        scored.append((score, s))
    scored.sort(key=lambda x: (-x[0], x[1].path, x[1].start_line))
    return scored[:k]


def excerpt(section: Section, query: str) -> str:
    """Return the most query-dense window of the section body."""
    lines = section.text.splitlines()
    body_lines = [ln for ln in lines if not HEADING_RE.match(ln)]
    if not body_lines:
        body_lines = lines
    q = set(tokenize(query))
    best_i, best_hits = 0, -1
    for i in range(len(body_lines)):
        window = body_lines[i : i + SNIPPET_LINES]
        hits = sum(1 for ln in window for t in tokenize(ln) if t in q)
        if hits > best_hits:
            best_hits, best_i = hits, i
    window = body_lines[best_i : best_i + SNIPPET_LINES]
    return "\n".join(ln.rstrip() for ln in window).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", help="search query")
    parser.add_argument("--root", default=".")
    parser.add_argument("--k", type=int, default=5, help="number of snippets (default 5)")
    parser.add_argument("--scope", default=None, help="comma-separated scopes (default: context,wiki,decisions,rules,outputs,projects)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    scopes = args.scope.split(",") if args.scope else DEFAULT_SCOPES
    sections = build_index(root, scopes)
    hits = bm25_rank(sections, args.query, args.k)

    if args.json:
        out = [
            {
                "path": s.path,
                "line": s.start_line,
                "heading": s.heading_path,
                "score": round(score, 3),
                "snippet": excerpt(s, args.query),
            }
            for score, s in hits
        ]
        print(json.dumps({"query": args.query, "scopes": scopes, "results": out}, indent=2))
        return 0

    if not hits:
        print(f"No matches for '{args.query}' in {', '.join(scopes)}.")
        return 0
    print(f"# vault-search: '{args.query}'  ({len(hits)} of {len(sections)} sections)\n")
    for rank, (score, s) in enumerate(hits, start=1):
        print(f"## {rank}. {s.path}:{s.start_line}  ·  {s.heading_path}  ·  score {score:.2f}")
        print(excerpt(s, args.query))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
