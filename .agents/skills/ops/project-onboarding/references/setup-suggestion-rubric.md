# Setup Suggestion Rubric

Use this rubric to classify onboarding suggestions before writing them into a review pack.

## Suggestion Kinds

- `connected-app`: a tool/account/source that may need setup later.
- `skill`: a repeatable assistant procedure worth codifying.
- `routine`: a recurring human or assistant-supported workflow.
- `script`: deterministic local helper that can safely run without account access.
- `template`: reusable document, message, report, or planning structure.
- `memory`: source material or context that should be summarized and ingested.
- `review`: a human decision or open question that must be resolved first.

## Safety Classes

- `safe-local`: uses only local project files and produces drafts or summaries.
- `review-only`: should be recorded as an idea, not executed yet.
- `needs-permission`: requires access to an external app, API, browser session, or account.
- `needs-credentials`: needs credentials or tokens, but the assistant must not ask for them in chat.

## Ranking

Score each candidate informally:

- impact: direct effect on revenue, retention, support quality, reliability, compliance, or owner time
- frequency: daily and weekly beats monthly and one-off
- readiness: local files or existing exports beat unclear integrations
- risk: read-only and draft-only beat external writes
- learning value: candidates that teach the project durable context are valuable early

Prefer the highest impact low-risk candidate as the first routine.

## Output Requirements

Every suggestion should include:

- stable lowercase id
- kind
- title
- summary
- reason
- safety class
- recommended decision: `prepare`, `review-later`, or `skip`
- proposed destination in the project

External apps should default to `review-later` unless the user explicitly asks to set them up.
