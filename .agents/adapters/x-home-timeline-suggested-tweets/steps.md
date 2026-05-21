# x-home-timeline-suggested-tweets Steps

Use Computer Use for this workflow. Stop and record `blocked` if login, captcha, two-factor verification, sensitive confirmation, account verification, or missing evidence prevents a safe run.

## Inputs

- `app_name`: normally `Safari`
- `starting_url`: normally `https://x.com`
- `item_count`: default `3`

These are contract defaults. `adapter-runner` should use them without asking unless the project owner explicitly provides overrides.

## Expected Output

Return a JSON array with exactly `item_count` maps. Each map must have exactly these keys:

- `author_name`
- `author_username`
- `text`
- `quote`
- `visual_description`

Use `null` for `quote` or `visual_description` when no quote or visual is visible.

## Procedure

1. Open the target app.
   - Visible anchor: Safari app window.
   - Expected state: Safari is active and ready for Computer Use inspection.
   - Failure/block condition: app cannot be opened or Computer Use cannot read the app state.
   - Evidence: redacted Computer Use visible-state summary.

2. Navigate to the X starting URL.
   - Visible anchor: Safari address field or current X page.
   - Expected state: Safari loads `https://x.com/home` or the signed-in X home timeline.
   - Failure/block condition: login wall, captcha, 2FA, account verification, network failure, or the X timeline does not load.
   - Evidence: redacted Computer Use visible-state summary showing the X home timeline.

3. Identify the feed scope.
   - Visible anchor: `Home timeline`, `For you`, and `Your Home Timeline`.
   - Expected state: the composer is visible above the feed, and feed cards are visible below it.
   - Failure/block condition: the page is on a different tab, search page, profile page, notification page, or an ambiguous timeline.
   - Evidence: redacted Computer Use visible-state summary with the timeline container.

4. Collect the first `item_count` feed cards after the composer.
   - Visible anchor: first post containers inside `Timeline: Your Home Timeline`.
   - Expected state: each collected card has author, username, main text, optional quote, and optional visual signal.
   - Failure/block condition: fewer than `item_count` cards are loaded, a card cannot be read, or the card structure changed enough that fields are ambiguous.
   - Evidence: redacted visible-state summary for the visible feed cards.

5. For each feed card, extract fields.
   - Visible anchor: card author links, text nodes, quote containers, image/video/link-preview labels.
   - Expected state:
     - `author_name` is the visible display name.
     - `author_username` is the visible `@username`.
     - `text` is the card's main text, excluding engagement counts.
     - `quote` is the quoted post text when visible, otherwise `null`.
     - `visual_description` describes visible images, videos, quote-card images, or link-preview media; use `null` when no visual is visible.
   - Failure/block condition: required fields cannot be read directly from visible state.
   - Evidence: extracted JSON plus redacted visible-state summary.

6. Return the JSON array only when requested as machine-readable output.
   - Visible anchor: user-requested output schema.
   - Expected state: output is valid JSON and each map has exactly the five required keys.
   - Failure/block condition: output would require guessing beyond visible evidence.
   - Evidence: adapter run record under `sources/adapters/runs/`.

## Confidence Rules

- `high`: all required fields are visible in the redacted visible-state summary and extracted values.
- `medium`: text is visible but one or more visual descriptions require human interpretation from partially visible UI state.
- `low`: evidence is stale, incomplete, or ambiguous; record `blocked` instead of returning guessed values.

## Failure Behavior

Record `blocked` or `failed` instead of guessing when:

- X timeline unavailable or login expired.
- Captcha, 2FA, or account verification prompt appears.
- Fewer than three feed cards are visible or loaded.
- Tweet card structure changed or visual content cannot be inspected.
- Computer Use cannot provide app state.
