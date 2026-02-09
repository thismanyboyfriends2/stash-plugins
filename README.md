# Stash Plugins

A collection of plugins for [Stash](https://stashapp.cc/).

## Installation

1. Go to **Settings** > **Plugins**
2. Click **Available Plugins** > **Add Source**
3. Enter the source URL:
   ```
   https://thismanyboyfriends2.github.io/stash-plugins/main/index.yml
   ```
4. Click **Confirm**

The plugins will appear in the Available Plugins list.

## Plugins

| Plugin | Description |
|--------|-------------|
| **Copy StashBox URLs** | Extracts StashBox URLs from StashIDs and adds them to scene and performer URL fields. |
| **Performer URL Aliases** | Extracts usernames from performer social media URLs (OnlyFans, X/Twitter, Instagram, Fansly, TikTok, LoyalFans, Linktree) and adds them as aliases. Case-insensitive deduplication against existing aliases. |
| **Performer URL Cleanup** | Normalises, deduplicates, and sorts performer URLs. Includes preview mode to review changes before applying. |
| **StashDB Tag Synchroniser** | Synchronises tags from StashDB to your local Stash instance. Three-stage matching (stash_id → name → create new), 24-hour caching, case-insensitive matching, configurable alias exclusions. Requires Python 3.12+ and StashDB API key. |

## Licence

[AGPL-3.0](LICENCE)
