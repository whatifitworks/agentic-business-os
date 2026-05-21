# Scripts

Deterministic project-owned scripts live here.

Use scripts for repeatable API pulls, report generation, data cleanup, or local automation that should not be left as manual chat steps.

`get_env.py` reads project-local secrets from gitignored `.claude/settings.local.json` so committed MCP/runtime configs can avoid embedding credentials.
