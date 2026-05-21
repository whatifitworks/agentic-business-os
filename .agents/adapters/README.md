# Adapters

Computer Use adapters are structured UI workflows for repeated app tasks that do not have a reliable API, MCP server, or project script.

Use adapters as lower-trust evidence producers, not as invisible scrapers. Every successful run needs a contract, recorded steps, data evidence, confidence, and caveats.

Computer Use is the recording and execution tool. Do not use Browser Use, shell commands, AppleScript, or ad-hoc screenshots as the adapter path. If Computer Use is unavailable, the adapter run is blocked or definition-only.

Evidence is data-first. Store extracted values, visible anchors, caveats, and redacted summaries by default. Screenshots, raw accessibility trees, exported files, or recordings are optional and should be attached only when they are necessary to make the result auditable. Never store secrets, credentials, private account data, unrelated tabs, or raw Computer Use state that contains sensitive material.

## Commands

```bash
python3 system/tools/browser_computer_adapter.py list
python3 system/tools/browser_computer_adapter.py show website-visual-check
python3 system/tools/browser_computer_adapter.py start-recording --name example-app-check --app Safari --goal "Check a repeatable UI workflow"
python3 system/tools/browser_computer_adapter.py note-step --name example-app-check --action "Open the target page" --visible-anchor "Safari address field" --expected-state "Target page loads" --failure-block "Login or verification appears"
python3 system/tools/browser_computer_adapter.py scaffold --name example-app-check --purpose "Capture repeatable Computer Use evidence for an example workflow." --target-app Safari --tool-type Computer --input url --output result --evidence-requirement "redacted visible-state summary"
python3 system/tools/browser_computer_adapter.py record --adapter example-app-check --tool-type Computer --target Safari --field status=visible
python3 system/tools/browser_computer_adapter.py record --adapter example-app-check --tool-type Computer --target Safari --values-json tmp/adapter-recordings/structured-values.json
python3 system/tools/browser_computer_adapter.py validate
```

## Folder Contract

- `registry.yaml` lists callable adapter-like workflows.
- `<adapter>/adapter.yaml` defines inputs, outputs, evidence, failure modes, and confidence rules.
- `<adapter>/adapter.yaml` may define `default_inputs`; if every listed input has a default, adapter-runner should run without asking for inputs.
- `<adapter>/steps.md` records the replay procedure.
- `sources/adapters/<adapter>.md` explains source policy and output routing.
- `sources/adapters/runs/` stores structured run records and redacted evidence notes.
- `tmp/adapter-recordings/` stores temporary recording scratchpads while building an adapter.

Durable findings from an adapter run go to `inbox/` first, usually through `--create-inbox-envelope`.
