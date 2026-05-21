#!/usr/bin/env python3
"""Run generic Agentic Business OS fixture checks."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

@dataclass
class Result:
    area: str
    case_id: str
    status: str
    message: str

def read_json(path: Path) -> dict:
    return json.loads(path.read_text())

def skill_exists(root: Path, name: str) -> bool:
    return any(p.parent.name == name for p in (root / '.agents' / 'skills').rglob('SKILL.md'))

def manifest_text(root: Path, skill: str) -> str:
    for p in (root / '.agents' / 'skills').rglob('manifest.yaml'):
        if p.parent.name == skill:
            return p.read_text(errors='replace')
    return ''

def add(results: list[Result], area: str, case_id: str, ok: bool, message: str) -> None:
    results.append(Result(area, case_id, 'pass' if ok else 'fail', message))

def run(root: Path) -> list[Result]:
    results: list[Result] = []
    routing = read_json(root / 'evals/routing/cases.json')
    for case in routing.get('cases', []):
        skill = str(case.get('expected_skill'))
        domain = str(case.get('expected_domain'))
        out = str(case.get('expected_output_area'))
        ok = skill_exists(root, skill) and (root / f'domains/{domain}.md').exists() and (root / out).exists()
        add(results, 'Routing', str(case.get('id')), ok, f'skill={skill} domain={domain} output={out}')
    skills = read_json(root / 'evals/skills/cases.json')
    for case in skills.get('cases', []):
        skill = str(case.get('skill'))
        text = manifest_text(root, skill)
        required = [str(x) for x in case.get('required_manifest_fields', [])]
        missing = [field for field in required if field not in text]
        add(results, 'Skills', skill, bool(text) and not missing, 'missing=' + ','.join(missing))
    behavior = read_json(root / 'evals/skills/behavior-cases.json')
    for case in behavior.get('cases', []):
        paths = [str(x) for x in case.get('expected_paths', [])]
        missing = [p for p in paths if not (root / p).exists()]
        add(results, 'Skill-Behavior', str(case.get('id')), not missing, 'missing=' + ','.join(missing))
    first = read_json(root / 'evals/routing/first-read.json')
    for case in first.get('cases', []):
        files = [str(x) for x in case.get('first_files', [])]
        missing = [p for p in files if not (root / p).exists()]
        add(results, 'First-Read', str(case.get('id')), not missing, 'missing=' + ','.join(missing))
    for path in ['evals/ingest/cases.json', 'evals/routing/artifact-placement.json', 'evals/agents/cases.json', 'evals/recurring/cases.json', 'evals/structure/cases.json']:
        add(results, 'Structure', path, (root / path).exists(), 'exists' if (root / path).exists() else 'missing')
    for folder in ['inbox','wiki','outputs','sources','state','.agents','system','evals','domains','indexes']:
        add(results, 'Structure', f'folder-{folder}', (root / folder).is_dir(), folder)
    return results

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    root = Path.cwd()
    results = run(root)
    passed = sum(1 for r in results if r.status == 'pass')
    failed = sum(1 for r in results if r.status == 'fail')
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
    print('# Agentic Business OS Eval Results')
    print()
    print(f'Root: `{root}`')
    print(f'Generated: `{now}`')
    print()
    print('## Summary')
    print()
    print(f'- Passed: {passed}')
    print(f'- Failed: {failed}')
    current = None
    for result in results:
        if result.area != current:
            current = result.area
            print(f'\n## {current}\n')
        print(f'- `{result.status}` `{result.case_id}` - {result.message}')
    return 1 if failed else 0

if __name__ == '__main__':
    raise SystemExit(main())
