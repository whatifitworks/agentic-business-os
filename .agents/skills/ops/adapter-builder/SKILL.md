---
name: adapter-builder
description: "Create or update Computer Use UI adapter contracts for app workflows without API/MCP access: inputs, steps, evidence, failure modes, validation."
---

# Adapter Builder

Build reusable Computer Use adapters. An adapter is a lower-trust UI workflow with a structured contract and evidence requirements, not an invisible scraper.

## Invocation Behavior

If the project owner invokes `$adapter-builder` without enough detail, ask for the missing minimum instead of stopping:

1. target app, site, or system surface
2. repeated action or data to collect
3. expected output fields or decision the adapter should support

Use Computer Use for adapter recording. Do not switch to Browser Use, AppleScript, shell commands, or ad-hoc screenshots as the recording mechanism. If Computer Use is unavailable, stop and say that adapter recording is blocked; ask the project owner whether to continue from manual descriptions as a definition-only adapter.

If the minimum is present, create or update the adapter files in this turn. Do not only explain the plan.

## Interactive Recording Mode

Use this mode when the project owner wants to build an adapter by walking through the UI step by step.

1. Ask: `Which app should I use?` If the goal was not already given, also ask for a short goal.
2. Start Computer Use for the named app.
   - do not use Browser Use for this skill
   - do not use shell commands, AppleScript, or screenshots as the recording mechanism
   - if Computer Use is unavailable, say that clearly and ask the project owner whether to continue from manual descriptions as definition-only
3. If the chosen app needs a starting URL, file, window, workspace, or account context, ask only for that next.
4. After the UI is open, ask: `What should I do next?`
5. For each the project owner instruction:
   - perform the UI action when the tool is available
   - record the step immediately in the working step list
   - include the action, visible anchor/selector if available, expected state after the step, and failure/block condition
   - persist the step with `python3 system/tools/browser_computer_adapter.py note-step ...` when the flow has a working slug
   - capture data-first evidence: visible anchors, extracted values, caveats, and optional artifacts only when needed
   - ask for the next instruction
6. Continue until the project owner says the goal is reached, done, finalize, or similar.
7. Before finalizing, ask only for missing adapter metadata that cannot be inferred:
   - adapter name, if the slug is ambiguous
   - owner domain, if unclear
   - output fields, if not clear from the recorded goal
   - freshness window, if default `30 days` is not appropriate
   - runtime defaults, only if the adapter should run without prompts and defaults cannot be inferred from the recorded flow
8. Scaffold the adapter, then replace the generated generic `steps.md` with the recorded replay steps.
9. Record a fixture run and validate.

Do not ask for all adapter fields upfront in interactive mode. The point is to discover the workflow by operating the UI with the project owner.

At the start of an interactive recording, create a concise working note when a slug can be inferred:

```bash
python3 system/tools/browser_computer_adapter.py start-recording \
  --name "<adapter-name-or-working-slug>" \
  --app "<app-name>" \
  --goal "<short goal>"
```

Use `tmp/adapter-recordings/<adapter-name>.md` as the working scratchpad for step notes. Do not write run evidence into `.agents/adapters/<adapter>/`; final run evidence belongs in `sources/adapters/runs/`.

Do not store raw Computer Use app state unless it is explicitly safe and necessary. Raw app state can expose secrets, private account data, and unrelated tabs. Prefer redacted visible-state summaries and extracted structured values.

### Recorded Step Format

Use this format while recording and in the final `steps.md`:

```markdown
1. <action>
   - Visible anchor: <text, selector, control, or screen region>
   - Expected state: <what should be true after the action>
   - Failure/block condition: <when to record blocked or failed>
   - Evidence: <redacted visible-state summary, extracted value, optional export/artifact, or none>
```

## Before Building

1. Read `00-start-here.md`, `.agents/adapters/README.md`, and `indexes/ui-adapters.md`.
2. Confirm no stable API, MCP server, or project script already covers the workflow.
3. Use `Computer` as the adapter tool type. Use `Fixture` only for contract tests.
4. Stop if the workflow requires entering secrets, bypassing login, captcha, 2FA, or sensitive confirmations.

## Files To Create

For adapter `<name>`:

- `.agents/adapters/<name>/adapter.yaml`
- `.agents/adapters/<name>/steps.md`
- `sources/adapters/<name>.md`
- update `.agents/adapters/registry.yaml`
- update `indexes/ui-adapters.md` when the adapter should be discoverable

Do not put run evidence in the adapter definition folder. Run evidence belongs in `sources/adapters/runs/`.

## Contract Requirements

Every adapter must define:

- `name`
- `owner_domain`
- `purpose`
- `target_app`
- `tool_type`
- `login_requirements`
- `inputs`
- `outputs`
- `evidence_requirements`
- `freshness_window`
- `failure_modes`
- `confidence_rules`
- `recording_path`
- `source_contract`
- `last_verified_at`
- `status`

## Build Workflow

1. Choose an adapter name as a lowercase slug, for example `email-platform-campaign-status-check`.
2. Scaffold the contract:

   ```bash
   python3 system/tools/browser_computer_adapter.py scaffold \
     --name "<adapter-name>" \
     --owner-domain "<domain>" \
     --purpose "<one sentence>" \
     --target-app "<app-name>" \
     --tool-type Computer \
     --input "<input-name>" \
     --output "<output-name>" \
     --evidence-requirement "<evidence-item>" \
     --failure-mode "<failure-mode>"
   ```

3. Edit the generated `adapter.yaml`, `steps.md`, and source contract when the scaffold is too generic.
   - If the adapter should run without prompts, write every runtime input under `default_inputs` in `adapter.yaml`.
   - Do not leave zero-prompt defaults only in prose such as "normally Safari"; the runner needs machine-readable defaults.
4. Create a fixture run unless the project owner asked for definition-only:

   ```bash
   python3 system/tools/browser_computer_adapter.py record \
     --adapter "<adapter-name>" \
     --workflow "<adapter-name>-fixture" \
     --target "<fixture-target>" \
     --tool-type Fixture \
     --field scaffolded=true \
     --confidence medium \
     --caveat "Fixture validates the adapter contract, not the live UI."
   ```

   For nested output data, write a temporary JSON file and use one of:

   ```bash
   python3 system/tools/browser_computer_adapter.py record \
     --adapter "<adapter-name>" \
     --target "<url-or-app>" \
     --tool-type Computer \
     --field-json result_json=tmp/adapter-recordings/result.json

   python3 system/tools/browser_computer_adapter.py record \
     --adapter "<adapter-name>" \
     --target "<url-or-app>" \
     --tool-type Computer \
     --values-json tmp/adapter-recordings/structured-values.json
   ```

5. Run:

   ```bash
   python3 system/tools/browser_computer_adapter.py validate
   python3 system/tools/agentic_os_hooks.py --hook adapter-evidence-check
   python3 system/tools/agentic_os_audit.py --phase final
   ```

## Example Requests

- `$adapter-builder Record a Safari workflow that checks whether a campaign page is ready to send and records campaign status, subject, audience, and preview URL.`
- `$adapter-builder Build a Computer adapter definition for exporting a monthly report from an accounting app.`
- `$adapter-builder I need a repeatable app workflow for checking whether a website CTA link opens the right app-store page in Safari.`

## Done Criteria

- `validate` passes.
- The adapter source contract exists.
- At least one fixture, live success, or blocked run exists unless the project owner explicitly wants definition-only.
- Nested outputs are recorded as JSON, not stringified JSON.
- Run evidence is data-first and redacted; screenshots or raw app-state artifacts are optional, not required.
- Durable findings from real runs go to `inbox/` through the runner's `--create-inbox-envelope` option.
