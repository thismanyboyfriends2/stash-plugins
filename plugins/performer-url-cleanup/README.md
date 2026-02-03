# Performer URL Cleanup

Normalises, deduplicates, and sorts performer URLs with site-specific rules.

## What it does

Cleans up performer URL fields by:

- **Normalising URLs** - Applies site-specific rules for consistent formatting
- **Deduplicating** - Removes duplicate URLs (prefers mixed-case versions from scrapers)
- **Sorting** - Orders URLs alphabetically by domain

## Site-specific rules

| Rule | Sites |
|------|-------|
| Remove `www.` prefix | x.com, twitter.com, onlyfans.com, fansly.com, xhamster.com |
| Add `www.` prefix | instagram.com, pornhub.com, xvideos.com |
| Domain aliases | twitter.com → x.com |
| Lowercase paths | onlyfans.com, instagram.com |
| HTTP only (no HTTPS) | bustybuffy.com |
| Keep trailing slash | adultfilmdatabase.com |

Additional transformations handle path normalisation (e.g., removing `/posts` suffix from Fansly URLs).

## Tasks

- **Preview URL Cleanup** - Shows what changes would be made without applying them
- **Apply URL Cleanup** - Applies all confirmed changes

## Settings

- **Write debug files** - Outputs text files to the plugin directory for reviewing changes in detail:
  - `debug_by_performer.txt` - Changes grouped by performer
  - `debug_by_domain.txt` - Changes grouped by domain
  - `debug_potential.txt` - Potential changes for unknown domains (not applied)

## Usage

1. Run **Preview URL Cleanup** first to review proposed changes
2. Check the logs or debug files to verify the changes look correct
3. Run **Apply URL Cleanup** to apply the changes

Changes are only applied to URLs from known domains. Unknown domains appear in the "potential" list for manual review.

## Requirements

- [stashapp-tools](https://pypi.org/project/stashapp-tools/) (bundled with Stash)
