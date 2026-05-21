#!/usr/bin/env python3
"""Run local v2 checks that do not require external APIs."""

from __future__ import annotations

import subprocess
import sys


COMMANDS = [
    ["python3", "system/tools/repo_audit.py", "--exit-zero"],
    ["python3", "system/tools/memory_graph_audit.py", "--scope", "root"],
    ["python3", "system/tools/ops_v2_audit.py", "--phase", "scaffold"],
    ["python3", "system/tools/ops_v2_hooks.py", "--hook", "all"],
    ["python3", "system/tools/ops_v2_eval.py"],
    ["python3", "system/tools/context_loader.py", "validate"],
    ["python3", "system/tools/context_loader.py", "load", "--domain", "acquisition", "--paths-only"],
    ["python3", "system/tools/context_loader.py", "load", "--domain", "activation", "--paths-only"],
    ["python3", "system/tools/context_loader.py", "load", "--domain", "retention", "--paths-only"],
    ["python3", "system/tools/context_loader.py", "load", "--domain", "monetization", "--paths-only"],
    ["python3", "system/tools/context_loader.py", "load", "--domain", "product", "--paths-only"],
    ["python3", "system/tools/context_loader.py", "load", "--domain", "support", "--paths-only"],
    ["python3", "system/tools/context_loader.py", "load", "--domain", "analytics", "--paths-only"],
    ["python3", "system/tools/context_loader.py", "load", "--domain", "finance", "--paths-only"],
    ["python3", "system/tools/context_loader.py", "load", "--domain", "ops", "--paths-only"],
    ["python3", "system/tools/context_loader.py", "load", "--domain", "tooling", "--paths-only"],
    ["python3", "system/tools/skill_namespace.py"],
    ["python3", "system/tools/ops_v2_acceptance.py"],
    ["python3", "system/tools/ops_v2_health.py"],
]


def main() -> int:
    failures = 0
    for cmd in COMMANDS:
        print("$ " + " ".join(cmd))
        result = subprocess.run(cmd, text=True)
        if result.returncode != 0:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
