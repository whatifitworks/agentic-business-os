# Website Visual Check Adapter Contract

Purpose: preserve a repeatable evidence contract for website pages.

## Use Cases

- Verify landing page or CTA visibility.
- Capture evidence after copy/layout changes.
- Check mobile/desktop layout regressions before or after publishing.
- Record visual evidence for a growth, support, or product decision.

## Evidence Rules

Each successful run needs:

- target URL
- viewport
- timestamp
- screenshot or exported browser evidence
- checklist result
- confidence and caveats

If the result affects durable strategy, conversion analysis, or product priorities, create an inbox envelope and let memory ingest decide whether to promote it.

## Failure Rules

Record `blocked` or `failed` when the browser cannot load the page, evidence is missing, a login/manual verification gate appears, or the checklist cannot be answered from visible evidence.
