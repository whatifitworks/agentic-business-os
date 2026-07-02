#!/usr/bin/env python3
"""Golden-question freshness eval for the knowledge vault.

Withdrawn or superseded claims that linger in the vault after being corrected
silently mislead future decisions. This eval guards against that:

1. ANSWERABILITY — for each golden question, vault_search must surface the
   canonical file in its top results and the answer must contain the expected
   phrases. Catches "the right answer is no longer findable / went stale".

2. CONTRADICTION — withdrawn/disproven "stale_claims" must not reappear
   anywhere in the durable corpus, EXCEPT on a line that also carries a
   negation/correction marker (so "X is NOT true" on a correction line is
   fine, but a fresh uncorrected "X is true" anywhere is flagged).

Definitions live in state/golden-questions.json. Pure stdlib. Exit non-zero on
failure unless --exit-zero. Wire into the scheduler / repo-health.

Runs recorded with --record append one summary line to
state/golden-question-runs.jsonl; --trend prints the score history, which is
the memory-benchmark proof that vault knowledge is compounding, not rotting.

Usage:
    python3 system/tools/golden_questions.py
    python3 system/tools/golden_questions.py --json
    python3 system/tools/golden_questions.py --exit-zero
    python3 system/tools/golden_questions.py --record
    python3 system/tools/golden_questions.py --trend
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Reuse the retrieval ranking so the eval tests what agents actually retrieve.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_search  # noqa: E402

CORPUS_SCOPES = vault_search.DEFAULT_SCOPES
TOP_K = 5
RUNS_REL = "state/golden-question-runs.jsonl"


def load_spec(root: Path) -> dict:
    return json.loads((root / "state" / "golden-questions.json").read_text())


def load_runs(root: Path) -> list[dict]:
    path = root / RUNS_REL
    if not path.exists():
        return []
    runs = []
    for line in path.read_text(errors="replace").splitlines():
        if line.strip():
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return runs


def record_run(root: Path, answer_results: list[dict], contradictions: list[dict]) -> dict:
    total = len(answer_results)
    passed = len([r for r in answer_results if r["ok"]])
    run = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": total,
        "passed": passed,
        "failed_ids": [r["id"] for r in answer_results if not r["ok"]],
        "contradictions": len(contradictions),
        "score": round(passed / total, 4) if total else None,
    }
    path = root / RUNS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run, ensure_ascii=False, sort_keys=True) + "\n")
    return run


def print_trend(root: Path) -> int:
    runs = load_runs(root)
    if not runs:
        print("No recorded runs yet — run with --record after the question set has entries.")
        return 0
    print("# Memory benchmark trend\n")
    prev_score = None
    for run in runs:
        score = run.get("score")
        pct = f"{score * 100:.0f}%" if isinstance(score, (int, float)) else "n/a"
        delta = ""
        if isinstance(score, (int, float)) and isinstance(prev_score, (int, float)):
            diff = (score - prev_score) * 100
            delta = f" ({'+' if diff >= 0 else ''}{diff:.0f}pt)"
        contra = f", {run.get('contradictions', 0)} contradictions" if run.get("contradictions") else ""
        failed = f" — failed: {', '.join(run['failed_ids'])}" if run.get("failed_ids") else ""
        print(f"  {run.get('ts', '?')}: {run.get('passed', '?')}/{run.get('total', '?')} ({pct}){delta}{contra}{failed}")
        prev_score = score if isinstance(score, (int, float)) else prev_score
    latest, first = runs[-1], runs[0]
    if isinstance(latest.get("score"), (int, float)) and isinstance(first.get("score"), (int, float)) and len(runs) > 1:
        overall = (latest["score"] - first["score"]) * 100
        direction = "improving" if overall > 0 else ("holding" if overall == 0 else "REGRESSING")
        print(f"\nOverall: {direction} ({'+' if overall >= 0 else ''}{overall:.0f}pt across {len(runs)} runs)")
    return 0


def corpus_lines(root: Path, scopes: list[str]):
    for path in vault_search.iter_files(root, scopes):
        try:
            for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                yield path.relative_to(root).as_posix(), n, line
        except OSError:
            continue


def check_answerability(sections, q: dict, root: Path) -> dict:
    hits = vault_search.bm25_rank(sections, q["question"], TOP_K)
    paths = [s.path for _, s in hits]
    # Accept canonical_paths (list) or legacy canonical_path (str).
    acceptable = q.get("canonical_paths") or [q["canonical_path"]]
    found = [p for p in acceptable if p in paths]
    canonical_found = bool(found)
    canonical_rank = min((paths.index(p) + 1 for p in found), default=None)
    # Phrase check against the full text of the best-ranked acceptable file
    # (the fact must exist in a retrievable canonical source), not just one
    # chunk — chunking can place the matched snippet away from the phrase.
    answer_text = ""
    best_path = next((p for p in paths if p in acceptable), None)
    if best_path:
        try:
            answer_text = (root / best_path).read_text(errors="replace")
        except OSError:
            answer_text = ""
    if not answer_text and hits:
        answer_text = hits[0][1].text
    missing = [p for p in q.get("must_include", []) if p.lower() not in answer_text.lower()]
    ok = canonical_found and not missing
    return {
        "canonical_found": canonical_found,
        "canonical_rank": canonical_rank,
        "acceptable": acceptable,
        "top_paths": paths,
        "missing_phrases": missing,
        "ok": ok,
    }


def check_contradictions(root: Path, spec: dict) -> list[dict]:
    markers = [m.lower() for m in spec.get("negation_markers", [])]
    claims: list[tuple[str, str]] = []  # (question_id, claim)
    for q in spec["questions"]:
        for c in q.get("stale_claims", []):
            claims.append((q["id"], c.lower()))
    if not claims:
        return []
    violations: list[dict] = []
    for path, n, line in corpus_lines(root, CORPUS_SCOPES):
        low = line.lower()
        if any(m in low for m in markers):
            continue  # correction / negation line — exempt
        for qid, claim in claims:
            if claim in low:
                violations.append({
                    "question_id": qid, "claim": claim,
                    "path": path, "line": n, "text": line.strip()[:160],
                })
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--exit-zero", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help="Append this run's summary to state/golden-question-runs.jsonl")
    parser.add_argument("--trend", action="store_true",
                        help="Print recorded run history instead of evaluating")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if args.trend:
        return print_trend(root)
    spec = load_spec(root)
    sections = vault_search.build_index(root, CORPUS_SCOPES)

    answer_results = []
    for q in spec["questions"]:
        r = check_answerability(sections, q, root)
        r["id"] = q["id"]
        answer_results.append(r)
    contradictions = check_contradictions(root, spec)

    failed_answers = [r for r in answer_results if not r["ok"]]
    has_failure = bool(failed_answers or contradictions)

    if args.record:
        if answer_results:
            record_run(root, answer_results, contradictions)
        else:
            print("Not recording: question set is empty, a 100% score would be noise.\n")

    if args.json:
        print(json.dumps({
            "answerability": answer_results,
            "contradictions": contradictions,
            "passed": not has_failure,
        }, indent=2))
        return 0 if (args.exit_zero or not has_failure) else 1

    print("# Golden-question freshness eval\n")
    print(f"Answerability: {len(answer_results) - len(failed_answers)}/{len(answer_results)} passed")
    for r in answer_results:
        mark = "PASS" if r["ok"] else "FAIL"
        detail = ""
        if not r["canonical_found"]:
            detail = f" — canonical {r['top_paths'][:1]} not in top {TOP_K}"
        elif r["missing_phrases"]:
            detail = f" — missing phrases {r['missing_phrases']}"
        elif r["canonical_rank"] and r["canonical_rank"] > 1:
            detail = f" (canonical at rank {r['canonical_rank']})"
        print(f"  [{mark}] {r['id']}{detail}")

    print(f"\nContradictions (stale claims reappearing): {len(contradictions)}")
    for v in contradictions:
        print(f"  [STALE] {v['path']}:{v['line']} — '{v['claim']}' → {v['text']}")
    if not contradictions:
        print("  none")

    print(f"\nResult: {'PASS' if not has_failure else 'FAIL'}")
    return 0 if (args.exit_zero or not has_failure) else 1


if __name__ == "__main__":
    raise SystemExit(main())
