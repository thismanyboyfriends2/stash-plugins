# Scene Title Cleanup

Strips trailing resolution/quality suffixes that some scrapers append to scene titles, e.g.:

> Gwen - Whole Strawberry Cream Cake Food Splosh (1080 HD)

becomes:

> Gwen - Whole Strawberry Cream Cake Food Splosh

## What it does

Removes a trailing `(...)` suffix when it matches a resolution/quality shape:

- Resolution: `(720 HD)`, `(1080 HD)`, `(720p)`, `(2160p)`
- Quality only: `(4K)`, `(UHD)`, `(HD)`, `(SD)`

Matching is deliberately narrow and trailing-only. Many studios use legitimate
parenthetical genre tags at the end of titles (e.g. `(Ass Worship)`, `(Foot
Worship)`) — these are never touched, since they don't match the
resolution/quality shape above.

Chained suffixes (e.g. `(1080 HD) (WEB-DL)`) are stripped fully, one tag at a
time from the end, as long as each one matches the built-in pattern or the
**Extra Suffixes** setting.

A title is never emptied out — if stripping would leave nothing behind, the
original title is kept.

## Tasks

- **Preview Title Cleanup** - Shows what title changes would be made without applying them
- **Apply Title Cleanup** - Applies all confirmed changes

## Settings

- **Studio Filter** - Only clean titles for scenes whose studio name contains this value (case-insensitive substring). Leave blank to clean titles across all studios.
- **Extra Suffixes** - Comma-separated additional literal suffixes to strip, matched case-insensitively at the end of the title, e.g. `(WEB-DL),(Remux)`. Useful for scraper-added tags beyond resolution/quality.

## Usage

1. Run **Preview Title Cleanup** first to review proposed changes
2. Check the logs to verify the changes look correct
3. Run **Apply Title Cleanup** to apply the changes

## Requirements

- [stashapp-tools](https://pypi.org/project/stashapp-tools/) (bundled with Stash)
