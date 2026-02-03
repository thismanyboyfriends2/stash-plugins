# StashDB Tag Synchroniser

Synchronises tags from StashDB to your local Stash instance via GraphQL.

## What it does

Fetches all tags from StashDB and synchronises them to your local Stash:

1. **Fetches tags** from StashDB's GraphQL API (with 24-hour caching)
2. **Matches existing tags** using a three-stage process:
   - Match by StashID (exact match)
   - Match by name (case-insensitive)
   - Create new tag if no match found
3. **Updates tag metadata** including description and aliases

## Features

- **Smart matching** - Finds existing tags by StashID or name to avoid creating duplicate entries
- **24-hour cache** - Avoids repeated API calls to StashDB
- **Case-insensitive matching** - Handles variations in tag names
- **Alias synchronisation** - Keeps tag aliases in sync with StashDB
- **Progress reporting** - Shows detailed progress and summary statistics

## Tasks

- **Synchronise Tags from StashDB** - Runs the full synchronisation

## Usage

1. Configure StashDB in **Settings** → **Metadata Providers** → **Stash-boxes**
2. Go to **Settings** → **Tasks**
3. Under **Plugin Tasks**, find **StashDB Tag Synchroniser**
4. Run **Synchronise Tags from StashDB**

The plugin automatically reads your StashDB API key from Stash's configuration.

## Requirements

- Python 3.12+
- StashDB API key configured in Stash
- [stashapp-tools](https://pypi.org/project/stashapp-tools/) (bundled with Stash)
