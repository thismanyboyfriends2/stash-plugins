# Contributing

Thanks for considering a contribution to this Stash plugin repository.

## Reporting a bug or requesting a feature

Open a [GitHub issue](https://github.com/thismanyboyfriends2/stash-plugins/issues) describing:

- Which plugin is affected
- What you expected vs. what happened
- Your Stash version, and the plugin version (shown in Settings → Plugins)
- Steps to reproduce, if it's a bug

## Submitting a pull request

1. Fork the repo and branch off `main`.
2. Make your change following [`CODING_STANDARDS.md`](CODING_STANDARDS.md).
3. If you touched plugin logic, add or update tests (`pytest`) and confirm they pass.
4. If you touched a `plugin.yml`, bump its `version` (semver). The published version string combines this with the commit hash automatically.
5. Open a pull request against `main` describing what changed and why. Link any related issue.

External pull requests are welcome and are reviewed the same way incoming feature requests are. Don't be surprised if a maintainer asks a clarifying question or requests changes before merging.

## Adding a new plugin

- Create a new directory under `plugins/<plugin-id>/`.
- Add a `<plugin-id>.yml` manifest. See any existing plugin for the shape, and [`CODING_STANDARDS.md`](CODING_STANDARDS.md) for what's expected in it (preview/dry-run tasks for anything destructive, settings for anything configurable).
- If your plugin depends on another plugin in this repo, declare it with a `# requires: other-plugin-id` comment in the manifest.
- Add tests alongside the code (`test_<module>.py`).
- Add your plugin to the table in [`README.md`](README.md).

## Local development

- Plugins require no build step to run inside Stash directly from a checkout — point Stash's plugin directory at your local `plugins/<plugin-id>/` folder to iterate.
- `./build_site.sh` builds the full publishable index locally into `_site/` if you want to verify packaging before opening a PR.
- `stashdb-tag-sync` needs `pip install -r plugins/stashdb-tag-sync/requirements.txt` in a venv for its extra dependencies; other plugins have none beyond the Python standard library and what Stash provides at runtime.

## Licence

By contributing, you agree your contribution is licensed under this repo's [AGPL-3.0 licence](LICENCE).
