# Tools

Deterministic local tools live here.

- `bootstrap_project.py` initializes local runtime state and runs baseline checks.
- `repo_audit.py` checks repository structure and privacy guards.
- `agentic_os_audit.py`, `agentic_os_eval.py`, and `agentic_os_hooks.py` run template health checks.
- `ops_state.py` owns the generated SQLite runtime state at `system/state/ops.db`.
- `context_loader.py` routes agents to the smallest useful context.
- `memory_graph_audit.py` checks the local wiki/source graph.
