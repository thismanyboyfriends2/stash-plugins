# Stash Plugin Development Skill - Design Document

## Overview

A Claude Code plugin providing comprehensive support for developing Stash plugins, including scaffolding, reference documentation, and workflow guidance.

## Plugin Location

```
~/.claude/plugins/local/stash-plugin-dev/
```

Globally available across all projects.

## Plugin Structure

```
stash-plugin-dev/
├── .claude-plugin/
│   └── plugin.json              # Plugin metadata
├── commands/
│   └── stash-plugin.md          # Interactive /stash-plugin command
└── skills/
    └── developing-stash-plugins/
        ├── SKILL.md             # Main skill (~300 words)
        └── references/
            ├── plugin-yml-syntax.md      # Full plugin.yml schema
            ├── hooks-reference.md        # All available hooks
            ├── settings-reference.md     # Setting types and patterns
            ├── python-patterns.md        # Python backend patterns
            ├── javascript-patterns.md    # JS UI patterns
            └── publishing-guide.md       # Manual publishing steps
```

## Command Design: `/stash-plugin create`

### Interactive Flow

1. **Plugin name** - Validates: lowercase, hyphens only
2. **Plugin type** - UI-only, Backend-only, or Hybrid
3. **Features** - Checkboxes based on type:
   - UI: JavaScript, CSS, CDN dependencies, settings
   - Backend: Tasks, Hooks, Settings
   - Hybrid: All options
4. **Target directory** - Default: current working directory
5. **Generate** - Create files and report

### Generated Files by Type

| Type | Files |
|------|-------|
| UI-only | `plugin.yml`, `plugin-name.js`, `plugin-name.css` (optional) |
| Backend-only | `plugin.yml`, `plugin_name.py`, `log.py` |
| Hybrid | `plugin.yml`, `plugin-name.js`, `plugin-name.css`, `plugin_name.py`, `log.py` |

### Template Features

- Boilerplate with TODO comments
- Working examples (settings read, basic hook handler)
- Comments referencing skill's reference files

## Main SKILL.md Content

### Frontmatter

```yaml
name: developing-stash-plugins
description: Use when creating Stash plugins, modifying plugin.yml configuration, writing plugin hooks/tasks, or troubleshooting plugin issues
```

### Sections (~300 words total)

1. **Overview** - What Stash plugins are, three interface types (raw, rpc, js)

2. **Quick Reference Table**
   | Type | Interface | Language | Use Case |
   |------|-----------|----------|----------|
   | UI-only | N/A | JS/CSS | DOM, styling |
   | Backend | raw | Python | Tasks, hooks, APIs |
   | Hybrid | raw | Python+JS | Full-featured |

3. **Plugin.yml Minimal Examples** - One per type (5-10 lines each)

4. **Local Testing** - Symlink to `~/.stash/plugins/`, reload, check logs

5. **Reference Links** - Pointers to reference files

6. **Publishing** - Brief note pointing to publishing-guide.md

## Reference Files

### plugin-yml-syntax.md (~200 lines)
- Complete YAML schema with all fields
- Each field: type, required/optional, example
- Covers: name, description, version, url, interface, exec, ui, settings, tasks, hooks, csp

### hooks-reference.md (~150 lines)
- All hooks from Stash core:
  - Scene, SceneMarker, Image, Gallery, GalleryChapter
  - Performer, Studio, Tag, Group
  - Each with Create.Post, Update.Post, Destroy.Post (Tag also has Merge.Post)
- Hook context structure (ID, Type, Input, InputFields)
- Example hook handler in Python

### settings-reference.md (~80 lines)
- Three types: STRING, NUMBER, BOOLEAN
- Settings structure with displayName, description
- Reading settings in Python and JavaScript

### python-patterns.md (~200 lines)
- stashapi.stashapp.StashInterface usage
- Mode-based execution pattern
- Reading input from stdin
- GraphQL query examples
- Logging patterns
- Error handling

### javascript-patterns.md (~200 lines)
- Accessing stash7dJx1qP / csLib globals
- GraphQL via csLib.callGQL
- Plugin config read/write
- DOM manipulation patterns
- Calling backend operations from JS

### publishing-guide.md (~100 lines)
- Directory structure for stash-plugins repo
- Required files checklist
- Manual copy steps
- Build script behaviour
- GitHub Pages deployment

## Stash Plugin Types Summary

### UI-only (JavaScript/CSS)
- No `exec` section
- Only `ui` block with javascript/css arrays
- Runs in browser, manipulates Stash UI

### Backend-only (Python)
- `exec: [python, "{pluginDir}/script.py"]`
- `interface: raw`
- Defines `tasks` and/or `hooks`
- No `ui` section

### Hybrid (Python + JavaScript)
- Has both `exec` and `ui` sections
- Python handles heavy processing
- JavaScript provides UI controls
- JS can invoke Python via `runPluginOperation`

## Local Testing Workflow

1. Create symlink: `ln -s /path/to/plugin ~/.stash/plugins/plugin-name`
2. In Stash: Settings > Plugins > Reload Plugins
3. Check logs: Settings > Logs (filter by plugin name)
4. For Python: Check stderr output in Stash logs

## Key Research Sources

- Official docs: https://docs.stashapp.cc/plugins/
- Stash core plugin system: `/home/matt/workspace/stashapp/stash/pkg/plugin/`
- CommunityScripts: `/home/matt/workspace/stashapp/CommunityScripts/plugins/`
- Installed plugins: `/mnt/c/stash/plugins/`
