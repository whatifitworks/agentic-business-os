---
name: skill-improvement-loop
description: "Review failed, awkward, praised, or manually corrected Agentic Business OS workflows and turn them into concrete agentic-OS improvements: skills, hooks, adapters, tools, evals, memory structure, file layout, context-loading docs, indexes, agents, or schedules. Use when the project owner corrects a workflow, says a skill behaved badly, repeats manual work, is frustrated/confused, praises a flow worth preserving, or an adapter/scheduler/hook/memory/context behavior produced an avoidable bad result."
---

# Skill Improvement Loop

Use this skill when the agentic OS can be improved. That includes a workflow failing, asking the wrong question, guessing, routing output incorrectly, missing memory, loading the wrong context, using the wrong file structure, lacking an index, or requiring the project owner to correct the agent. It also includes praised behaviors that should be preserved. The goal is to convert interaction evidence into durable system improvements instead of leaving it in chat history.

This skill improves the operating system around Agentic Business OS. It should not learn product facts, analytics conclusions, support facts, accounting facts, or strategy decisions directly. Route those through the relevant domain skill and memory-ingest flow.

## Inputs

Collect only the minimum needed:

- skill or workflow used
- expected behavior
- actual behavior
- the project owner's correction
- satisfaction/frustration/confusion signal, if present
- repeated manual step or misuse/alternate-use pattern, if present
- relevant command/tool output, if any
- changed files, if already fixed
- whether the failure is deterministic and can become an eval

Do not ask for these fields when they are already visible in the conversation or files.

## Workflow

1. Identify the owner.
   - Skill failure -> `.agents/skills/<namespace>/<skill>/`
   - Adapter failure -> `.agents/adapters/`, `sources/adapters/`, and adapter skills
   - Hook failure -> `.agents/hooks/` and `system/tools/agentic_os_hooks.py`
   - Routing or folder failure -> `AGENTS.md`, `00-start-here.md`, `indexes/`, `domains/`, or eval fixtures
   - Memory structure failure -> `inbox/`, `wiki/`, `outputs/`, `sources/`, `state/`, `indexes/`, memory skills, or memory graph audits
   - Context-loading failure -> `AGENTS.md`, `CLAUDE.md`, `00-start-here.md`, `system/context/context_index.json`, and relevant indexes
   - Agent/persona failure -> `.agents/agents/`, `AGENTS.md`, skill docs, or agent assignment rules
   - Schedule/recurring failure -> `.agents/schedules.yaml`, `.agents/recurring.yaml`, scheduler tools, and morning/friday planning skills
   - Tool failure -> `system/tools/`

2. Run the deterministic analyzer when enough data is available:

   ```bash
   python3 system/tools/skill_improvement_loop.py analyze --case <case.json>
   ```

   Use `--create-inbox-candidate` only when the learning has durable value and should go through memory ingest.

   If the request is to test a skill, the primary test is the documented skill workflow: load the relevant `SKILL.md`, follow its procedure, and judge the user-facing outcome. Supporting scripts and aggregate evals are validation evidence, not a substitute for exercising the skill body.

3. Decide the outcome:
   - `patch`: update the relevant skill, manifest, tool, adapter contract, hook, or eval now.
   - `system-structure-patch`: update memory/file layout, indexes, context-loading docs, agent definitions, schedules, or audits.
   - `inbox-candidate`: write a redacted memory candidate when the lesson is durable but not immediately actionable.
   - `no-change`: explain why the behavior was correct, unreproducible, or too one-off.
   - `blocked`: state the missing evidence or tool that prevents a safe fix.

4. Add a regression check when deterministic.
   - For skill/adapter/routing behavior, prefer `agentic_os_eval.py` fixtures.
   - For hook behavior, prefer `agentic_os_hooks.py` fixtures or focused CLI checks.
   - For memory/file-structure behavior, prefer memory graph/audit checks plus routing/first-read eval fixtures.
   - For context-loading behavior, prefer first-read or behavior fixtures that prove agents load the right entrypoint.
   - For scripts, prefer a small deterministic unit-like CLI fixture.

5. Validate the changed surface:

   ```bash
   python3 system/tools/agentic_os_eval.py
   python3 system/tools/agentic_os_hooks.py --hook all
   python3 system/tools/repo_audit.py --exit-zero
   git diff --check
   ```

## Output

Report:

- failure summary
- owner files changed or proposed
- improvement surface: skill, hook, adapter, memory structure, context-loading, index, agent, schedule, eval, or tool
- regression check added or why not
- validation commands run
- residual risk
- inbox candidate path, if created

## Rules

- Never capture secrets, credentials, private URLs, customer private data, or raw Computer Use state in an inbox candidate.
- Do not create broad "improve the system" notes without a concrete signal: failure, correction, frustration, confusion, repeated manual step, misuse/alternate use, or praised pattern.
- Do not mark the failure fixed unless the relevant file changed or a clear no-change rationale exists.
- If the project owner's correction contradicts an existing contract, update the contract or explicitly document why the contract wins.
- When the project owner asks to test a skill, do not stop at backing scripts. Treat script-only testing as incomplete unless the skill itself is only a script wrapper and that is explicit in `SKILL.md`.
- If the issue is a business/domain topic rather than an OS behavior, stop and route it to the domain skill, recurring-review, daily-planning, or memory-ingest instead of patching skill contracts.

## Good Failure Candidates

- A skill asked for inputs even though defaults existed.
- A memory update went directly to wiki instead of inbox.
- A recurring item kept surfacing after the underlying work was cancelled.
- An adapter returned unvalidated JSON.
- A hook produced a false positive that is likely to recur.
- The agent missed an important file because first-read/context-loading rules were incomplete.
- The memory graph or file structure made it unclear where artifacts belong.
- the project owner repeatedly uses a workflow differently than the skill expects.
- the project owner praises a workflow and it should be preserved as a documented pattern.
