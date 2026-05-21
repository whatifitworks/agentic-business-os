# Setup

This is the setup path for a fresh Agentic Business OS project.

## 1. Clone Or Use The Template

Create a new repository from this template, then open it with Codex or Claude Code.

## 2. Run Project Onboarding

Ask your agent to run the `project-onboarding` skill:

```text
Run project-onboarding for this project. Learn the business, tools, routines, approval boundaries, and first useful automation candidates. Create a review pack before changing live files.
```

The agent should initialize local runtime state, run baseline checks, interview the owner, and create a review pack. The owner should not need to run setup scripts by hand during normal onboarding.

The onboarding skill creates a review pack under:

```text
inbox/project-onboarding/<date>-<project-name>/
```

Review the pack before promoting any proposed files into live `AGENTS.md`, `context/`, `domains/`, `wiki/`, `.agents/`, `rules/`, or `state/` paths.

Promote `proposed/AGENTS.md` first after review. The repository starts with a generic bootstrap contract, but a useful onboarded project should have a project-specific `AGENTS.md` with the learned mission, direct source-map references, known tools, known routines, and approval boundaries.

Manual fallback, if an agent is not running onboarding:

```bash
python3 system/tools/bootstrap_project.py
python3 system/tests/agentic_os_local_checks.py
```

## 3. Configure Local Secrets

Do not paste credentials into chat.

If a local script or MCP server needs environment variables, create:

```text
.claude/settings.local.json
```

Use `.claude/settings.local.example.json` as the shape. This file is gitignored.

## 4. Enable Hooks

Codex hooks are declared in `.codex/config.toml`.

Claude hooks are declared in `.claude/settings.json`.

The hooks capture compact learning signals and check `inbox/` for eligible memory-ingest work after agent turns. They do not connect external tools.

After onboarding, verify runtime activation:

- Codex may require hooks to be enabled or approved in the app/runtime UI even when `.codex/config.toml` is present.
- Claude Code hook behavior can vary by installed version; verify that `.claude/settings.json` hooks are being read by your runtime.

## 5. Optional: Install macOS Background Jobs

Install the scheduler only after reviewing `.agents/schedules.yaml`:

```bash
bash .agents/install-launchd.sh
```

Install the inbox auto-ingest watcher only after reviewing the memory workflow:

```bash
bash .agents/hooks/install-inbox-auto-ingest-launchd.sh
```

Both scripts are macOS launchd helpers. Other platforms can run the same Python tools directly or wire their own scheduler.

## 6. Add Tools After Boundaries Are Clear

Add MCP servers, APIs, exports, or adapters only after onboarding has captured:

- tool purpose
- owner
- read/write boundary
- approval rule
- first useful read-only workflow

## 7. Verify

The onboarding agent should run:

```bash
python3 system/tests/agentic_os_local_checks.py
```

Use `python3 system/tools/repo_audit.py --exit-zero` for a lighter check.

## 8. Help

Agentic Business OS is maintained by What If It Works: https://whatifitworks.co

Ask the agent to run `get-help` when setup, onboarding, hooks, sync, publishing, or customization is unclear.
