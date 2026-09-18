# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, etc.) when working with code in this repository.

## Project Overview

Stash plugin repository template for hosting and distributing plugins for [Stash](https://stashapp.cc/), an adult entertainment library management application. The repository auto-builds and publishes a plugin source index to GitHub Pages.

## Build Commands

```bash
# Build plugins locally (outputs to _site/ by default)
./build_site.sh

# Build to a custom directory
./build_site.sh custom_output_dir
```

The build script:
- Scans `plugins/` for `*.yml` files
- Creates ZIP archives for each plugin
- Generates `index.yml` with metadata and SHA256 checksums
- Versions combine YAML version + git short hash (e.g., `1.0.0-abc1234`)

## Plugin Structure

Each plugin lives in its own directory under `plugins/`:

```
plugins/
└── my-plugin/
    ├── plugin.yml      # Required: metadata file
    └── ...             # Plugin source files
```

### plugin.yml Format

```yaml
name: My Plugin
description: What it does
version: 1.0.0
# requires: dependency1, dependency2
```

The `# requires:` comment (if present) specifies comma-separated plugin dependencies.

## Deployment

- Auto-deploys via GitHub Actions when `plugins/**` changes on `main`
- Manual trigger available via workflow_dispatch
- Published index URL: `https://<username>.github.io/<repo>/main/index.yml`

## Stash Plugin Development

- Plugin docs: https://docs.stashapp.cc/in-app-manual/plugins/
- Community reference: https://github.com/stashapp/CommunityScripts/

## Privacy & content guardrails

This repo is public. Any contributor's personal Stash instance, and any real data from it, is
private and must never be exposed here — in issues, PR descriptions, PR/review comments, commit
messages, code comments, docs, or example fixtures. A contributor's own `AGENTS.local.md`
(gitignored, never committed) lists the specific identifiers this applies to for them — check
drafts against it before publishing anything to GitHub.

**Never publish to GitHub on this repo:**
- Any personal username, hostname, or domain tied to a real Stash instance.
- Real scene/performer/studio/gallery names, titles, or IDs from a real Stash library.
- URLs pointing at a live personal Stash instance (e.g. `.../scenes/<id>`, `.../performers/<id>`).

**When writing bug reports, examples, or test fixtures for GitHub:**
- Use fully generic placeholders: `Some Scene Title (2008)`, `http://stash.example/scenes/123`,
  `Performer A & Performer B`, etc.
- Never copy real-world testing output (titles, names, URLs) verbatim into an issue/PR/comment —
  genericize it first, even if it means the reproduction is a bit less concrete.
- If a bug was found via real data, describe the *shape* of the input (e.g. "a bare 4-digit
  year in parens") rather than the specific data itself.
- Keep examples content-neutral. Stash is an adult-content media manager, but GitHub's terms
  restrict sexually explicit content — don't use explicit titles, performer names, studio names,
  or descriptions in issues/PRs/comments/docs, even as illustrative examples. Neutral stand-ins
  (movie/TV-style titles, "Performer A", generic studio names) work fine for reproductions.

Before opening or editing any issue/PR/comment on this repo, scan the draft against these rules
and against your `AGENTS.local.md`, and scrub before publishing. If in doubt, check with the
repo owner rather than publishing.

## Agent skills

### Issue tracker

Issues live on GitHub (`thismanyboyfriends2/stash-plugins`); external PRs are treated as feature requests. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical label names, 1:1 with the five triage roles. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`CONTEXT.md` + `docs/adr/` at repo root). See `docs/agents/domain.md`.
