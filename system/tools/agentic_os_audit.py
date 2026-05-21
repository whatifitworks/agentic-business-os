#!/usr/bin/env python3
"""Generic Agentic Business OS structure audit."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from repo_audit import run as run_repo_audit


def run(root: Path, phase: str = "scaffold"):
    return run_repo_audit(root)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', default='scaffold')
    args = parser.parse_args()
    root = Path.cwd()
    issues = run(root, args.phase)
    errors = [i for i in issues if i.level == 'error']
    warns = [i for i in issues if i.level == 'warn']
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
    print('# Agentic Business OS Audit')
    print()
    print(f'Root: `{root}`')
    print(f'Phase: `{args.phase}`')
    print(f'Generated: `{now}`')
    print()
    print('## Summary')
    print()
    print(f'- Errors: {len(errors)}')
    print(f'- Warnings: {len(warns)}')
    if issues:
        for title, items in [('Errors', errors), ('Warnings', warns)]:
            if items:
                print('\n## ' + title + '\n')
                for issue in items:
                    print(f'- `{issue.code}` [{issue.path}] {issue.message}')
    else:
        print('\nNo audit issues found.')
    return 1 if errors else 0

if __name__ == '__main__':
    raise SystemExit(main())
