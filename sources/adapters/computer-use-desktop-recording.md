# Computer Use Desktop Recording Adapter Contract

Purpose: define the Computer Use pattern for app workflows that cannot be handled by APIs, MCP servers, or project scripts.

Computer Use is lower trust than API/MCP access. It should produce evidence and fail closed.

## Use Rules

- Use only already-authorized local sessions.
- Stop for passwords, 2FA, captcha, permission prompts, or sensitive confirmations.
- Capture screenshot/export evidence for every extracted value.
- Prefer a blocked run over guessing.

## Current Status

Active template. Concrete adapters should be created from this pattern and recorded with Computer Use.
