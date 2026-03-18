# Scene Title to Filename

Batch renames scene files on disk to match their Stash title.

## What it does

Finds all scenes under a configurable path prefix and renames the files to match their Stash title. Renames are atomic — the file and Stash's database are updated together, no rescan needed.

## Settings

| Setting | Type | Description |
|---------|------|-------------|
| **Path Filter** | STRING | Only rename scenes whose file path starts with this value (e.g. `/data/import/`) |

## Tasks

- **Preview Renames** — Dry run showing all planned renames and a summary without touching files
- **Rename Scene Files** — Performs the renames

## Behaviour

- Illegal filesystem characters (`/ \ : * ? " < > |`) are stripped from titles
- Multiple spaces (left after stripping) are collapsed to a single space
- Filename conflicts in the same directory get `(1)`, `(2)`, etc. suffixed before the extension
- Aborts after 5 consecutive failures to avoid grinding through systemic errors

## Skipped scenes

The plugin skips scenes and logs a warning when:

- **No title** — nothing to rename to
- **Multiple files** — ambiguous, needs manual resolution
- **Title matches filename** — already correct, no-op
- **Title empty after sanitizing** — title was only illegal characters

## Usage

1. Set **Path Filter** in Settings > Plugins > Scene Title to Filename
2. Run **Preview Renames** to review planned changes
3. Check the logs — verify renames look correct and review any skipped scenes
4. Run **Rename Scene Files** to apply

## Requirements

- [stashapp-tools](https://pypi.org/project/stashapp-tools/) (bundled with Stash)
