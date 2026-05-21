# X Home Timeline Suggested Tweets Adapter Contract

Purpose: collect a small structured sample from an already-authorized X home timeline session as a UI-adapter example.

## Target

- App/site: browser or desktop browser session
- Login: already-authorized X session only; stop for login, captcha, 2FA, account lock, or sensitive confirmation prompts
- Normal URL: `https://x.com`
- Normal resolved page: `https://x.com/home`
- Default inputs: `item_count=3`

## Evidence Rules

- Redacted visible-state summary showing the X home timeline and extracted feed cards.
- Structured JSON array with author name, handle, text, quote, and visual description for each collected item.
- If a visual is only partially visible, say that in the caveats or use medium confidence.
- Do not store raw Computer Use state for this adapter; personalized timelines can expose unrelated private account state.

If the result affects durable strategy, product priorities, or operating-system behavior, create an inbox envelope and let memory ingest decide whether to promote it.

## Caveats

- X home timelines are personalized, time-sensitive, and reorder frequently.
- Ads may appear in the first visible feed cards. Include them when they occupy a sampled position and mark the ad status when visible.
- This adapter is useful for repeatable UI extraction and adapter-system testing; it is not a stable research source without run evidence.
- The output schema lives at `.agents/adapters/x-home-timeline-suggested-tweets/output_schema.json`.

## Failure Rules

Record `blocked` or `failed` when evidence is missing, the UI changes, manual verification appears, or the requested value cannot be read directly from captured evidence.
