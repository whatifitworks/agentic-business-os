# Runtime State

`ops.db` is the local SQLite state spine for mutable operations data.

The database is generated and intentionally gitignored. Tracked code should define how to rebuild and update it; the binary database should not become a source-control conflict surface.

Current owner:

- [system/tools/ops_state.py](../tools/ops_state.py)

Typical scope:

- scheduler run history
- latest scheduler task state
- markdown brief queue metadata
- repo validation results
- component health summaries
- recurring task mirror with computed due/overdue/paused/cancelled state from `.agents/recurring.yaml`

Markdown briefs remain the human-readable output layer. SQLite is the machine-readable runtime layer for reminders, health views, and context loading.

`.agents/recurring.yaml` remains the editable source for recurring obligations. Use `ops_state.py complete-recurring` for actual completions and `ops_state.py set-recurring-status` when work is paused or cancelled.
