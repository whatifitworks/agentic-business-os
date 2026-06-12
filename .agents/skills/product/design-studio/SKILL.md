---
name: design-studio
description: "Create or continue AI-assisted design projects: Stitch generation, references, DESIGN.md, prototypes, previews, handoff artifacts."
---

# Design Studio

Design Studio turns design work into a reusable project workspace. It is for visual exploration, design systems, reference analysis, Stitch iteration, competitive benchmarking, prototype refinement, visual QA, exports, and handoff preparation. It is not a production frontend implementation skill; use implementation skills or repo-specific dev workflows only after the project owner approves a design direction.

## Opening Interaction

Always start by asking:

```text
Do you want to start a new design project or continue an existing design project?
```

If the project owner already named the project and intent, infer the answer and continue.

For a new project, ask only the minimum missing details:

1. project name
2. target surface: website, web app, mobile app, brand system, component set, or other
3. short goal
4. audience or product, if unclear

Create the workspace with:

```bash
python3 .agents/skills/product/design-studio/scripts/design_studio.py init --name "<project name>" --surface "<surface>" --goal "<short goal>"
```

For an existing project, list or locate `projects/design-studio/<project-slug>/` and load only its `README.md`, `DESIGN.md`, `REFERENCES.md`, and `stitch.md`.

## Workspace Contract

Use `projects/design-studio/` as the durable design workspace:

```text
projects/design-studio/
  README.md
  <project-slug>/
    README.md                 project brief, status, and index
    DESIGN.md                 living design system and visual direction
    REFERENCES.md             reference inventory and extracted lessons
    stitch.md                 Stitch project/screen ids, prompt history, and current decision
    handoff.md                implementation handoff when approved
    prompts/                  prompt drafts sent to Stitch
    iterations/               per-iteration notes and critique
    references/
      files/                  permanent copies of approved reference files
      descriptions/           one concise markdown description per reference
```

Use `tmp/design-studio/<project-slug>/incoming/` as the temporary drop zone for reference files the project owner wants analyzed. After analysis, move or copy accepted references into `projects/design-studio/<project-slug>/references/files/`.

Use `outputs/design-studio/<project-slug>/` only for accepted human-facing exports, previews, final design packs, or handoff packages. Outputs must link back to the design project.

If a design artifact contains durable knowledge that should become part of the Agentic Business OS memory graph, create an inbox item and let `memory-ingest` decide. Do not write design learnings directly into `wiki/`.

Preferred output subfolders:

```text
outputs/design-studio/<project-slug>/
  README.md                  index of accepted exports
  screens/                   rendered PNG/HTML previews and share images
  benchmarks/                dated benchmark reports, manifests, and reference captures
  handoff/                   final implementation packages when approved
```

## Main Menu

After project selection, offer a numbered list. Keep it short and adapt it to project state:

1. Continue or create a design in Google Stitch
2. Add and analyze reference files
3. Benchmark the current design against real-world references
4. Critique the current design or compare variants
5. Build or refine a local prototype/design pack
6. Capture, verify, or export shareable previews
7. Update the project `DESIGN.md`
8. Prepare an implementation handoff
9. Check Stitch access mode
10. Something else

Ask the project owner to pick a number. If he gives a direct instruction instead, execute the matching option.

## Quality Floor

Do not call a design "stunning", "final", or "ready" from taste alone. For serious website/app design work, especially when the project owner asks for something impressive, use this ladder:

1. Load the project brief, `DESIGN.md`, `REFERENCES.md`, and the current selected direction from `stitch.md`.
2. Gather or select relevant references before generating. Prefer a weighted mix of direct category relevance, adjacent category quality, and high-craft inspiration.
3. Generate with Stitch when available, but judge the result honestly. If Stitch is incomplete, generic, or too template-like, record that and either send targeted edits or build a local prototype using the accepted direction.
4. Benchmark a serious candidate against 10-15 relevant real-world references when the goal is top-tier visual quality.
5. Render desktop and mobile previews. Check for horizontal overflow, clipped text, missing required sections, and weak mobile first-viewport impact.
6. Save accepted artifacts in `outputs/design-studio/<project>/`, update the output README, and record the decision in `stitch.md` or `iterations/`.

## Add Reference Files

Use this when the project owner wants to add screenshots, exported pages, Figma exports, moodboards, brand files, competitor examples, or UI captures.

1. Tell the project owner the temporary drop zone:

   ```text
   tmp/design-studio/<project-slug>/incoming/
   ```

2. Ask him to move the reference files there.
3. Inspect each file with the best available tool:
   - images: use visual inspection, `view_image`, or any active image/browser tool
   - HTML/PDF/text: read only enough to summarize structure and design lessons
   - URLs: browse only when the project owner explicitly gives the URL or asks for live reference capture
4. For each reference, write a concise description:
   - what the reference is
   - layout pattern
   - typography and density
   - color/material/lighting style
   - motion or interaction ideas, if visible
   - what to steal
   - what to avoid
   - relevance score: high, medium, or low
5. Register the reference:

   ```bash
   python3 .agents/skills/product/design-studio/scripts/design_studio.py add-reference --project "<project-slug>" --source "<path>" --description "<short description>" --move
   ```

6. Update `DESIGN.md` only with reusable lessons, not a full dump of every reference.

Do not keep rejected or irrelevant reference files in the project. Either leave them in `tmp/` or move a short reject note to `dropped/` only when the rejection itself is useful.

## Benchmark And Design Quality Loop

Use this when the project owner asks whether a design is truly good, wants a standout result, or says the result still does not look impressive.

Create a benchmark workspace:

```bash
python3 .agents/skills/product/design-studio/scripts/design_studio.py benchmark-init --project "<project-slug>" --name "<benchmark name>" --candidate "<candidate path or URL>"
```

Reference set rules:

- Use 10-15 references for serious visual work.
- Ask what to optimize for if unclear: direct category relevance, visual craft, conversion, or a weighted mix.
- For niche products, do not benchmark only against famous generic SaaS sites. Include direct competitors and adjacent products, then add a smaller set of high-craft references.
- Capture evidence screenshots into `outputs/design-studio/<project>/benchmarks/<date-name>/screens/`.
- Record source URLs, role, notes, and scores in `manifest.json`.

Benchmark rubric:

- audience fit
- category clarity
- visual craft
- distinctive first impression
- conversion utility
- responsive and motion potential

Write the benchmark report under `outputs/design-studio/<project>/benchmarks/<date-name>/report.md`. Separate deterministic findings from taste. End with concrete next-pass changes.

## Local Prototype And Preview Loop

Use local prototypes when:

- Stitch produces only a partial page, misses required sections, or looks too template-like.
- the project owner wants to see a full-page website direction, not just a single generated screen.
- The best next step is art direction, layout, responsiveness, or shareable preview quality.

Rules:

- Keep local prototypes under `outputs/design-studio/<project>/screens/`.
- Treat them as design artifacts, not production code.
- Use the project `DESIGN.md`, references, and benchmark findings as constraints.
- Render and inspect desktop first viewport, desktop full page, mobile first viewport, and mobile full page before presenting.
- For shareable review, create a clearly named full-page PNG, for example `screens/<project>-<version>-share-fullpage.png`.
- Register accepted outputs:

```bash
python3 .agents/skills/product/design-studio/scripts/design_studio.py register-output --project "<project-slug>" --kind screen --title "<title>" --path "<artifact path>" --notes "<short notes>"
```

Verification checklist:

- no document-level horizontal overflow on mobile and desktop
- primary hero, offer, process, proof/trust, and CTA content exists
- mobile first viewport contains enough of the visual idea, not only text
- text does not clip or overlap key UI
- screenshots are saved and linked from the output README

## Stitch Access Modes

For Codex, use the best available path in this order:

1. **Stitch MCP mode** - Preferred path. Use when `mcp__stitch__` tools are visible in Codex or Claude. This may be backed by API-key auth, OAuth, or another runtime-supported auth method; do not expose or print the credential.
2. **Stitch Web UI mode** - Use Computer Use to operate `stitch.withgoogle.com` in a browser when the project owner is signed in. Use this when MCP tools are unavailable or when the task requires UI-only export/review behavior.
3. **Stitch MCP OAuth/proxy setup mode** - Use only when the project owner wants MCP without an API key or when direct remote auth fails. This may require `gcloud auth login`, `gcloud auth application-default login`, a Google Cloud project, and enabling `stitch.googleapis.com`.
4. **Manual prompt package mode** - Build polished Stitch-ready prompts and ask the project owner to paste them into Stitch manually, then move screenshots/exports into `tmp/design-studio/<project>/incoming/` for analysis and registration.

Never print, persist, or commit Stitch credentials. If MCP tools are visible, assume auth is already configured and proceed.

## Build Or Iterate In Google Stitch

Before using Stitch from Codex, prefer Stitch MCP mode when `mcp__stitch__` tools are visible. To check project config wiring:

```bash
python3 .agents/skills/product/design-studio/scripts/design_studio.py check-mcp
```

Stitch is a dual-runtime dependency:

- Codex project config: `.codex/config.toml` must include `[mcp_servers.stitch]` with `url = "https://stitch.googleapis.com/mcp"`.
- Claude Code project config: `.mcp.json` must include `mcpServers.stitch` with `type = "http"` and `url = "https://stitch.googleapis.com/mcp"`.
- Authentication is per runtime/session and may be API-key or OAuth-backed. Codex direct remote OAuth may fail with `Dynamic client registration not supported`; if that happens, use the configured API-key path, OAuth/proxy setup mode, or Stitch Web UI mode.
- Do not commit API keys or print configured secrets.

If no Stitch MCP tools are available, do not stop the whole workflow. Say MCP generation is unavailable in this runtime, then continue with Stitch Web UI mode or Manual prompt package mode.

When Stitch MCP is available:

1. Load the project `DESIGN.md`, `REFERENCES.md`, and `stitch.md`.
2. Ask for the design target if unclear:
   - page/screen name
   - desktop/mobile/responsive target
   - desired vibe
   - required sections or components
   - constraints and anti-patterns
3. Build a Stitch prompt with this structure:
   - product and user context
   - screen/page goal
   - information hierarchy
   - reference lessons to apply
   - design system constraints from `DESIGN.md`
   - explicit anti-patterns
   - requested outputs: screens, variants, design system, prototype links, or code/export if supported
4. Save the exact prompt to `projects/design-studio/<project-slug>/prompts/YYYY-MM-DD-<screen>-vNN.md`.
5. Send the prompt through Stitch MCP. Expected tool families may appear as `stitch:*`, `mcp__stitch__*`, or a runtime-specific Stitch prefix. Useful tools include project listing/creation, design system listing/management, text-to-screen generation, image-to-screen generation, screen editing, variant generation, screen retrieval, and asset download.
6. Record result identifiers, links, screenshots, exports, or notes in `stitch.md`.
7. Ask the project owner to review the result.
8. Iterate by sending targeted change prompts instead of regenerating from scratch unless the direction is rejected.
9. If Stitch output is incomplete or not strong enough, do not keep forcing the same prompt. Record the limitation, improve the prompt if the problem is specific, or switch to the local prototype loop if the problem is art direction or completeness.

When using Stitch Web UI mode:

1. Ask the project owner to confirm the browser/app to use and that he is signed into Stitch.
2. Use Computer Use, not Browser Use, when operating the Stitch website as a UI workflow.
3. Open `stitch.withgoogle.com`.
4. Create or select the project manually through the UI.
5. Paste the saved prompt from `prompts/`.
6. Wait for the visible result.
7. Record the project/screen link, visible result summary, and any export/screenshot path in `stitch.md`.
8. Ask the project owner for review and iterate with targeted edit prompts.

When using Manual prompt package mode:

1. Save the polished prompt in `prompts/`.
2. Tell the project owner exactly which prompt file to paste into Stitch.
3. Ask the project owner to place screenshots, HTML exports, or links in `tmp/design-studio/<project>/incoming/`.
4. Analyze those files through the reference workflow and update `DESIGN.md`, `REFERENCES.md`, `stitch.md`, or `handoff.md` as appropriate.

Prefer precise critique loops:

```text
Keep: <specific elements>
Change: <specific elements>
Avoid: <specific failure mode>
Next output: <screen or variant request>
```

## Critique And Variant Selection

When reviewing a design, judge it against:

- business goal and audience fit
- first-viewport clarity
- information hierarchy
- visual distinctiveness
- product credibility
- typography quality
- spacing and rhythm
- motion/interaction plausibility
- responsiveness risk
- consistency with `DESIGN.md`
- whether it avoids generic AI SaaS tropes
- whether it competes with the selected reference set, not just with the previous internal variant

Write critique notes under `iterations/`, then update `stitch.md` with the current selected direction.

## DESIGN.md Rules

`DESIGN.md` is the portable design source of truth. Keep it short enough for an agent to read quickly. It should contain:

- brand/product positioning
- target feeling
- color tokens
- type scale and font direction
- spacing and layout rules
- component patterns
- imagery and icon rules
- motion rules
- accessibility constraints
- do/don't list
- current open questions

Do not turn `DESIGN.md` into a journal. Detailed critique and per-iteration notes belong in `iterations/`.

## Handoff

Prepare `handoff.md` only after the project owner chooses a direction. Include:

- final target screens/pages
- accepted Stitch links or ids
- final `DESIGN.md` summary
- assets and export paths
- implementation constraints
- responsive behavior
- interaction/motion notes
- open questions
- explicit non-goals

If the handoff is ready for app or website implementation, route the actual code work to the appropriate repo and skill. Do not implement frontend code inside Agentic Business OS unless the target project itself lives here.

## Done Criteria

A design-studio run is complete when:

- the project folder exists and is indexed
- references are either registered, rejected, or left in `tmp/` intentionally
- Stitch prompt/result history is recorded when generation occurs
- `DESIGN.md` reflects the current reusable design direction
- serious design directions have benchmark or critique evidence when quality is uncertain
- desktop and mobile previews are rendered when the output is visual
- accepted exports live under `outputs/design-studio/<project-slug>/` when a human-facing artifact is finalized
- shareable review artifacts have clear filenames and are registered in the output README
- unresolved durable insights go through `inbox/`, not direct wiki edits
