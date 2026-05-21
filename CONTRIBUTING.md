# Contributing

Agentic Business OS is a public template. Contributions should improve the generic operating system without leaking private business context.

Before opening a pull request:

- keep examples generic and reusable
- avoid customer data, credentials, private logs, raw transcripts, local personal paths, and internal metrics
- run `python3 system/tests/agentic_os_local_checks.py`
- run a privacy/private-name scan for project-specific terms
- explain whether the change affects onboarding, hooks, memory ingest, scheduler behavior, skills, or downstream sync

Good contributions include generic skills, docs, eval fixtures, hooks, adapter contracts, setup improvements, and privacy-safe tooling.

Project-specific integrations should usually live in the downstream private project unless they can be generalized safely.
