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

## Agent skills

### Issue tracker

Issues live on GitHub (`thismanyboyfriends2/stash-plugins`); external PRs are treated as feature requests. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical label names, 1:1 with the five triage roles. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`CONTEXT.md` + `docs/adr/` at repo root). See `docs/agents/domain.md`.
