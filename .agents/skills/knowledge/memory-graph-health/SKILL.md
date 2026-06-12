---
name: memory-graph-health
description: Audit the Obsidian memory vault for orphan wiki pages, broken memory links, stale inbox items, and skills missing from the skill index.
---

# Memory Graph Health

Use this skill when the project owner asks for memory health, Obsidian graph cleanup, orphan note checks, inbox hygiene, or repo-health follow-up related to memory.

## Workflow

1. Run:

   ```bash
   python3 system/tools/memory_graph_audit.py
   ```

2. Review issues in this order:
   - broken memory links
   - orphan `wiki/` pages
   - skills missing from `indexes/skills.md`
   - stale inbox items

3. Fix the smallest useful set:
   - add missing index links
   - update or remove broken links
   - move processed inbox items through `memory-ingest`
   - add missing skill ownership entries

4. Re-run the audit and report the remaining issues.

## Rules

- Do not solve orphan pages by creating a catch-all dump index.
- Prefer topic/domain indexes over long wiki pages.
- Do not delete inbox or processed material unless the project owner explicitly approves deletion.
