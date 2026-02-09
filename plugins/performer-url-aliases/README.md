# Performer URL Aliases

Extracts usernames from performer social media URLs and adds them as aliases.

## What it does

Scans all performers in your Stash library and:

1. **Extracts usernames** from social media URLs (e.g., `https://x.com/janedoe` → `janedoe`)
2. **Deduplicates aliases** using case-insensitive matching against existing aliases and the performer's name
3. **Cleans up existing duplicates** - removes pre-existing duplicate aliases found in your Stash data

## Supported sites

| Site | Example URL | Extracted alias |
|------|-------------|-----------------|
| OnlyFans | `https://onlyfans.com/janedoe` | `janedoe` |
| X / Twitter | `https://x.com/janedoe` | `janedoe` |
| Instagram | `https://www.instagram.com/janedoe` | `janedoe` |
| Fansly | `https://fansly.com/janedoe` | `janedoe` |

Non-username paths (e.g., `/about`, `/login`, `/explore`) are automatically skipped.

## Tasks

- **Preview Alias Extraction** - Shows what aliases would be extracted without applying them
- **Extract Aliases from URLs** - Extracts usernames and adds them as aliases

## Usage

1. Run **Preview Alias Extraction** first to review proposed changes
2. Check the logs to verify the additions and duplicate removals look correct
3. Run **Extract Aliases from URLs** to apply the changes

## Requirements

- [stashapp-tools](https://pypi.org/project/stashapp-tools/) (bundled with Stash)
