# Copy StashBox URLs

Extracts StashBox URLs from StashIDs and adds them to scene and performer URL fields.

## What it does

When you match scenes or performers to StashDB (or other StashBox instances), Stash stores the StashID internally but doesn't add the corresponding URL to the entity's URL list. This plugin bridges that gap by:

1. Finding all scenes/performers that have StashIDs attached
2. Constructing the full StashBox URL from each StashID (e.g., `https://stashdb.org/scenes/abc-123`)
3. Adding the URL to the entity's URL field (without duplicating existing URLs)

## Tasks

- **Copy StashBox URLs to Scenes** - Processes all scenes with StashIDs
- **Copy StashBox URLs to Performers** - Processes all performers with StashIDs

## Usage

1. Go to **Settings** → **Tasks**
2. Under **Plugin Tasks**, find **Copy StashBox URLs**
3. Run either task to process scenes or performers

The plugin processes in batches and shows progress. It skips entities that already have the StashBox URL present.

## Requirements

- [stashapp-tools](https://pypi.org/project/stashapp-tools/) (bundled with Stash)
