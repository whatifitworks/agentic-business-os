---
name: adapter-runner
description: Run an existing Computer Use adapter workflow, record structured evidence, validate the run record, or create an inbox envelope from output.
---

# Adapter Runner

Run a registered adapter and record its evidence with `system/tools/browser_computer_adapter.py`.

## Before Running

1. Read `.agents/adapters/README.md`.
2. List adapters if needed:

   ```bash
   python3 system/tools/browser_computer_adapter.py list
   ```

3. Show the adapter contract:

   ```bash
   python3 system/tools/browser_computer_adapter.py show <adapter>
   ```

4. Confirm the workflow does not require secrets, captcha, 2FA, or unsupported external mutation.

5. Resolve runtime inputs:
   - if `adapter.yaml` defines `default_inputs` for all listed `inputs`, use those defaults without asking
   - if the steps/source contract explicitly says the adapter is zero-prompt or all runtime inputs have defaults, use those defaults without asking
   - if the project owner provides an override, use the override
   - ask only for required inputs that have no contract default

Contract defaults are not assumptions. They are part of the adapter interface.

## Run Workflow

1. Execute the UI workflow with Computer Use according to `<adapter>/steps.md`.
   - do not use Browser Use for adapter execution
   - do not use shell commands, AppleScript, or ad-hoc screenshots as the execution mechanism
   - if Computer Use is unavailable, record the run as blocked instead of guessing
2. Capture data-first evidence: visible anchors, extracted values, caveats, or an explicit blocked step. Screenshots, exports, and raw app-state artifacts are optional and should be used only when they are needed to make the run auditable.
   - never store raw Computer Use state if it contains secrets, credentials, unrelated tabs, private account data, or sensitive business/customer data
   - store a redacted summary instead
3. Record the run:

   ```bash
   python3 system/tools/browser_computer_adapter.py record \
     --adapter <adapter> \
     --workflow <workflow-name> \
     --target <url-or-app> \
     --tool-type Computer \
     --input key=value \
     --field key=value \
     --confidence high
   ```

   For nested JSON output, prefer:

   ```bash
   python3 system/tools/browser_computer_adapter.py record \
     --adapter <adapter> \
     --workflow <workflow-name> \
     --target <url-or-app> \
     --tool-type Computer \
     --values-json tmp/adapter-recordings/structured-values.json \
     --confidence high
   ```

4. Use `--status blocked` or `--status failed` instead of guessing when evidence is missing or UI changed.
5. Use `--create-inbox-envelope` only when the result has durable value.

## Validation

Always run:

```bash
python3 system/tools/browser_computer_adapter.py validate
python3 system/tools/agentic_os_hooks.py --hook adapter-evidence-check
```

## Output

Report:

- adapter name
- target
- status
- JSON run record path
- Markdown evidence path
- confidence
- caveats
- inbox envelope path, if created

Run records and redacted evidence summaries stay in `sources/adapters/runs/`. Durable findings enter memory through `inbox/`.
