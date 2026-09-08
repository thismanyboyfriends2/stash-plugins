# Stash Plugins

A source repository of Stash plugins: each plugin is built, zipped, and published as an index that Stash instances can install from.

## Language

**Plugin**:
A directory under `plugins/` containing a `plugin.yml` manifest plus its executable source; the unit `build_site.sh` zips and lists in `index.yml`.

**Task**:
A user-facing action a plugin exposes, declared under its `plugin.yml`'s `tasks:` list and shown as a clickable action in Stash's UI. Invoking a Task passes a `mode` string (via `defaultArgs.mode`) that the plugin's script switches on internally. Task and mode are the same concept; `mode` is just its wire representation as a script argument.
_Avoid_: Mode (as a standalone term), Action, Command

**Setting**:
A user-configurable value declared under a plugin's `settings:` block (e.g. `matchDistance`, `dryRun`), surfaced in Stash's plugin settings UI. Read via `get_configuration()`, never passed via stdin JSON.
_Avoid_: Option, Config value (the latter overloads with **Config**, below)

**Dependency**:
Another plugin ID that must be installed alongside this one, declared as a comma-separated `# requires:` YAML comment in `plugin.yml` and surfaced in the published `index.yml` as a `requires:` list.
_Avoid_: Requirement, prerequisite

**Interface**:
The `interface:` field in `plugin.yml` declaring how Stash invokes the plugin's executable (every plugin in this repo currently uses `raw`).

**Endpoint**:
Connection details (base URL and optional API key) for a remote GraphQL source a plugin talks to: a local Stash instance or StashDB. Deliberately not called "Connection", since Stash's own GraphQL schema already uses `Connection` for paginated result types and the two would collide when discussed together.
_Avoid_: Connection, StashConnection (as the conceptual name; the `StashConnection` dataclass is an implementation detail, not the glossary term)

**Config**:
Runtime values a plugin resolves at execution time from Stash's own configuration, for example `stashdb-tag-sync` fetching the StashDB API key from Stash's Settings → Metadata Providers via GraphQL. Distinct from a **Setting**, which the plugin author defines and the user fills in through Stash's plugin settings UI.
_Avoid_: Settings (reserve that word for the plugin-author-defined concept above)
