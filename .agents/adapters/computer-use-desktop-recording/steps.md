# Computer Use Desktop Recording Steps

Use this adapter pattern for Computer Use workflows when API, MCP server, or project scripts cannot do the job.

When a concrete app workflow is approved:

1. Confirm the app is already open or available without entering secrets.
2. Define exact allowed actions and stop conditions.
3. Capture screenshot or exported evidence for every extracted value.
4. Record a blocked result if the app asks for login, 2FA, permissions, or manual verification.
5. Record the run with `system/tools/browser_computer_adapter.py record --adapter computer-use-desktop-recording --tool-type Computer ...`.
