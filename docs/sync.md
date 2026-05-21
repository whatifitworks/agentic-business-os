# Sync And Upstream Contributions

Agentic Business OS should be treated as the public upstream template. Real business projects will usually need local overlays for private context, tools, schedules, and domain-specific skills.

This repo intentionally does not ship a downstream project's private sync bridge. Keep that bridge in the downstream private repo so it can encode local redaction rules, blocked terms, and overlay decisions.

After onboarding, downstream `AGENTS.md` is usually project-specific. Treat it as a private overlay file unless you are deliberately extracting a generic improvement back to the public template. When pulling upstream changes, merge the generic bootstrap guidance into the local `AGENTS.md` manually instead of blindly replacing the learned project mission and source map.

Recommended contribution loop:

1. Develop and dogfood changes in a private project.
2. Extract only generic files or sanitized variants into a public branch.
3. Run privacy and secret scans before commit.
4. Open a pull request back to Agentic Business OS.
5. Downstream projects pull upstream changes through their local bridge or normal Git merge process.

Use Computer Use for GitHub organization or repository setup only when the GitHub connector or CLI cannot cover the action. Record repeatable UI-only publishing work as an adapter before relying on it.
