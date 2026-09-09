# Coding Standards

Conventions for plugin code in this repository. These reflect what the existing plugins already do. Follow them for consistency, and update this file if a deliberate departure is agreed on.

## Language and structure

- All plugins are Python, invoked by Stash via `interface: raw` and `exec: [python3, "{pluginDir}/<script>.py"]`.
- One plugin per directory under `plugins/`, containing:
  - `<plugin-id>.yml`: the manifest (see `CONTEXT.md` for `Plugin`/`Task`/`Setting`/`Dependency` vocabulary)
  - the executable script(s)
  - `test_*.py` alongside the code it tests, not in a separate `tests/` directory
  - a `README.md` if the plugin needs usage notes beyond the manifest's `description`
- New scripts use `snake_case.py` filenames (e.g. `auto_merge_duplicates.py`, `performer_url_cleanup.py`). Two older plugins (`copyStashBoxUrls.py`, `stashdbTagSync.py`) use camelCase. Don't rename them without reason, but don't propagate the pattern to new plugins.
- Larger plugins may split logic into a `src/` package (see `stashdb-tag-sync/src/`) with `models.py` for dataclasses and separate client modules for GraphQL access. Small plugins stay as a single script.

## Style

- Module-level docstring at the top of every script describing what the plugin does, e.g.:
  ```python
  """Auto-Merge Duplicates plugin for Stash.

  Queries all phash duplicate groups detected by Stash and merges each group...
  """
  ```
- Function and class docstrings are one-line unless the behaviour is genuinely non-obvious.
- Type hints on function signatures and dataclass fields (see `models.py`'s use of `Optional[str]`, `list[str]`).
- No repo-wide linter/formatter is configured yet. Match the surrounding file's style: 4-space indent, double quotes for docstrings, snake_case for functions/variables.
- British/Australian spelling in user-facing strings and docs (`Synchronise`, `Normalises`, `Cleanup`), matching existing plugin names and descriptions.

## Plugin manifest (`plugin.yml`)

- `name`, `description`, `version` (semver), `url` (this repo's GitHub URL) are required.
- `# requires: other-plugin-id, another-id` as a YAML comment declares dependencies. Parsed by `build_site.sh`, not by Stash itself.
- Every task that mutates data should have a corresponding `preview`/dry-run task (see `performer-url-cleanup`, `scene-title-to-filename`) or a `dryRun` boolean setting (see `auto-merge-duplicates`). Don't ship a destructive task with no way to see what it would do first.
- Settings the user must configure (API keys, thresholds, filters) go under `settings:`, each with `displayName`, `description`, and `type` (`STRING`/`NUMBER`/`BOOLEAN`).
- When adding a new plugin, also add a row to the `## Plugins` table in the root `README.md` (alphabetical by plugin name). It's easy to ship a new plugin directory and forget this — check it before opening the PR.

## Stash interaction

- Fetch plugin settings via `get_configuration()` at runtime. Never expect them on stdin JSON.
- Connection info for reaching the local Stash instance (`server_connection`: scheme/host/port/API key) does arrive via stdin JSON. That's separate from `get_configuration()`.
- When a required credential isn't resolvable (e.g. no Stash API key), log a clear error pointing at where to configure it and `sys.exit(1)`. Don't silently continue or retry.
- `moveFiles` calls need an explicit `destination_folder` even for an in-place rename.
- `INCLUDES`-style filters in Stash's GraphQL API are case-insensitive substring matches, not prefix matches. Post-filter in Python if you need prefix semantics.

## Testing

- `pytest`, using `unittest.mock` (`Mock`, `patch`) for GraphQL/Stash client calls. No live Stash instance in tests.
- Tests live in `test_<module>.py` next to the code, grouped into `TestSomething` classes by the function/behaviour under test (see `test_auto_merge_duplicates.py`'s `TestSceneScore`).
- Small builder helpers (`_scene(...)`, `_file(...)`) construct fixture dicts/objects instead of duplicating literal dicts across tests.
- Run `pytest` from the plugin directory (or repo root, if a shared venv is active) before committing changes to plugin logic.

## Build

- `./build_site.sh [outdir]` zips each plugin and generates `index.yml` with a `version = <yml version>-<git short hash>` scheme and a SHA256 checksum. Don't hand-edit `index.yml` or `_site/`.
