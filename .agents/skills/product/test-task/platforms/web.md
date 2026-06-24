# test-task - web sidecar

Platform mechanics for verifying a **web** change. The shared spine is in [../SKILL.md](../SKILL.md); this is
the *how* for web. The driver is a **browser-automation tool / MCP** - e.g. a **Playwright** MCP (or
Puppeteer / Selenium) - not the mobile flow runner; the rest of the spine is the same (AI integrity +
aesthetic -> publish).

## 🚨 Safety - know what your local build touches
- **Never run a build/up command that mutates production at build time.** If the app's container/build runs
  database migrations or other prod-touching steps against the configured (prod) connection, building it
  would hit production. Serve the app from already-running local services instead; do not start/stop/build
  containers as part of verification.
- Beyond public pages, use a **designated test account** - login + actions are fine *scoped to that test
  account's own data*. **Never** touch real users/payments/data, run migrations/schema changes, or truncate.

## Flow
1. Confirm the app serves locally (a quick HTTP status check on the local URL).
2. With the browser tool: set a desktop viewport (and a mobile width for responsive), navigate the changed
   route(s), and **screenshot per viewport section** (a full long-page shot is too small to review).
3. Look at each capture -> integrity (+ aesthetic on UI changes). **Console errors are a web integrity
   signal** - capture and judge them.
4. Publish the verdict + screenshot to the PR (host the image where the PR can render it).
