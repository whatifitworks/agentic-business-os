# Computer Use Adapter Contract

Purpose: emulate MCP-like structured data collection for workflows where no reliable API or MCP server exists.

## When To Use

- The target data is available only through a website or desktop UI.
- The workflow is repeated enough to justify recorded steps.
- The result can be verified with screenshots, exported files, or stable visible values.

## When Not To Use

- A stable API, project script, or MCP server already exists.
- The workflow requires bypassing login, captcha, two-factor prompts, or other access controls.
- The UI result cannot be verified with durable evidence.

## Required Run Record

Every adapter run must capture:

- workflow name
- target app or site
- timestamp
- input parameters
- steps or selectors used
- output values or artifact paths
- evidence path
- confidence and caveats
- inbox envelope path when the result has durable value

## Output Policy

Raw evidence stays under `sources/adapters/` or another stable source path. Durable findings go to `inbox/` first, then ingest decides whether to promote, preserve, process, drop, or escalate.

## Failure Policy

If the UI changes, login expires, evidence is missing, or extracted values are ambiguous, stop and report the failed step. Do not guess values to preserve a tool-like interface.
