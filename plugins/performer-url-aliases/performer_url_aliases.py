"""Performer URL Aliases Plugin for Stash.

Extracts usernames from performer social media URLs and adds them as aliases.
"""
import json
import sys
from urllib.parse import urlparse

try:
    import stashapi.log as log
    from stashapi.stashapp import StashInterface
except ModuleNotFoundError:
    print(json.dumps({
        "output": "Error: stashapp-tools not installed. Run: pip install stashapp-tools"
    }))
    sys.exit(1)

# Domains to extract usernames from
EXTRACT_DOMAINS = {
    'onlyfans.com',
    'x.com',
    'twitter.com',
    'instagram.com',
    'fansly.com',
}

# Non-username path segments to skip
SKIP_PATHS = {
    'about', 'help', 'login', 'signup', 'settings', 'explore', 'search',
    'home', 'i', 'hashtag', 'compose', 'notifications', 'messages',
    'privacy', 'terms', 'tos', 'support', 'download', 'features',
}


def extract_username_from_url(url):
    """Parse a single URL and return the extracted username, or None."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix('www.')

    if domain not in EXTRACT_DOMAINS:
        return None

    # Take first path segment
    path = parsed.path.strip('/')
    if not path:
        return None

    username = path.split('/')[0]

    if not username or username.lower() in SKIP_PATHS:
        return None

    return username


def extract_usernames(urls):
    """Extract usernames from a list of URLs."""
    usernames = []
    for url in urls:
        username = extract_username_from_url(url)
        if username:
            usernames.append(username)
    return usernames


def deduplicate_aliases(extracted, existing_aliases, performer_name):
    """Case-insensitive dedup against existing aliases, performer name, and self."""
    seen = set()

    if performer_name:
        seen.add(performer_name.lower())

    # Dedup existing aliases (handles pre-existing duplicates in Stash data)
    clean_existing = []
    removed_duplicates = []
    for alias in existing_aliases:
        lower = alias.lower()
        if lower not in seen:
            seen.add(lower)
            clean_existing.append(alias)
        else:
            removed_duplicates.append(alias)

    new_aliases = []
    for username in extracted:
        lower = username.lower()
        if lower not in seen:
            seen.add(lower)
            new_aliases.append(username)

    return clean_existing, new_aliases, removed_duplicates


def process_performers(stash, dry_run=True):
    """Fetch all performers, extract usernames from URLs, and add as aliases."""
    log.info("Fetching performers...")

    result = stash.find_performers(
        f={},
        fragment="id name urls alias_list",
        get_count=True
    )

    if not result:
        log.info("No performers found")
        return

    count, performers = result
    log.info(f"Found {count} performers to check")

    performers_to_update = []

    for idx, performer in enumerate(performers):
        urls = performer.get('urls') or []
        existing_aliases = performer.get('alias_list') or []
        name = performer.get('name', '')

        if not urls:
            if count > 0:
                log.progress((idx + 1) / count)
            continue

        extracted = extract_usernames(urls)
        clean_existing, new_aliases, removed_dupes = deduplicate_aliases(
            extracted, existing_aliases, name
        )

        if new_aliases or removed_dupes:
            performers_to_update.append({
                'id': performer['id'],
                'name': name,
                'existing_aliases': clean_existing,
                'new_aliases': new_aliases,
                'removed_duplicates': removed_dupes,
            })

        if count > 0:
            log.progress((idx + 1) / count)

    if not performers_to_update:
        log.info("No changes needed - all usernames already present")
        return

    log.info(f"Found {len(performers_to_update)} performers to update")

    log.info(f"\n{'=' * 60}")
    log.info("Changes:")
    log.info(f"{'=' * 60}\n")

    for p in performers_to_update:
        log.info(f"Performer: {p['name']} (ID: {p['id']})")
        for alias in p.get('removed_duplicates', []):
            log.info(f"  - {alias} (duplicate removed)")
        for alias in p['new_aliases']:
            log.info(f"  + {alias}")

    total_new = sum(len(p['new_aliases']) for p in performers_to_update)
    total_deduped = sum(len(p.get('removed_duplicates', [])) for p in performers_to_update)

    if dry_run:
        log.info(f"\n{'=' * 60}")
        log.info("PREVIEW MODE - No changes applied")
        parts = []
        if total_new:
            parts.append(f"add {total_new} aliases")
        if total_deduped:
            parts.append(f"remove {total_deduped} duplicates")
        log.info(f"Run 'Extract Aliases from URLs' to {', '.join(parts)} across {len(performers_to_update)} performers")
        log.info(f"{'=' * 60}")
    else:
        log.info(f"\nApplying aliases to {len(performers_to_update)} performers...")

        completed = 0
        failed = 0
        total = len(performers_to_update)

        for p in performers_to_update:
            try:
                full_list = p['existing_aliases'] + p['new_aliases']
                stash.update_performer({
                    'id': p['id'],
                    'alias_list': full_list,
                })
                completed += 1
            except Exception as e:
                log.error(f"Failed to update {p['name']}: {e}")
                failed += 1
            log.progress((completed + failed) / total)

        log.info(f"{'=' * 60}")
        log.info(f"Added aliases to {completed} performers ({failed} failed)")
        log.info(f"{'=' * 60}")


def main():
    """Main entry point."""
    json_input = json.loads(sys.stdin.read())

    server_connection = json_input["server_connection"]
    stash = StashInterface(server_connection)

    mode = json_input.get("args", {}).get("mode", "preview")

    log.info(f"Performer URL Aliases - Mode: {mode}")

    if mode == "preview":
        process_performers(stash, dry_run=True)
    elif mode == "apply":
        process_performers(stash, dry_run=False)
    else:
        log.error(f"Unknown mode: {mode}")


if __name__ == "__main__":
    main()
