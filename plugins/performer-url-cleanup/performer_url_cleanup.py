"""Performer URL Cleanup Plugin for Stash.

Normalises, deduplicates, and sorts performer URLs.
"""
import json
import sys
from urllib.parse import urlparse, urlunparse

try:
    import stashapi.log as log
    from stashapi.stashapp import StashInterface
except ModuleNotFoundError:
    print(json.dumps({
        "output": "Error: stashapp-tools not installed. Run: pip install stashapp-tools"
    }))
    sys.exit(1)

# Sites that should not have www prefix
REMOVE_WWW = {
    'x.com',
    'twitter.com',
    'onlyfans.com',
    'instagram.com',
    'fansly.com',
    'pornhub.com',
    'xvideos.com',
    'xhamster.com',
}

# Domain aliases - map old domains to canonical ones
DOMAIN_ALIASES = {
    'twitter.com': 'x.com',
}

# Sites that preserve user's chosen capitalisation in the path
PRESERVE_CASE = {'x.com', 'twitter.com'}


def normalise_url(url):
    """Normalise a URL according to site-specific rules.

    Returns (normalised_url, canonical_domain) tuple.
    """
    # Parse the URL
    parsed = urlparse(url)

    # Upgrade to HTTPS
    scheme = 'https'

    # Normalise domain
    domain = parsed.netloc.lower()

    # Remove www if site doesn't use it
    if domain.startswith('www.'):
        domain_without_www = domain[4:]
        if domain_without_www in REMOVE_WWW:
            domain = domain_without_www

    # Apply domain aliases
    if domain in DOMAIN_ALIASES:
        domain = DOMAIN_ALIASES[domain]

    # Handle path
    path = parsed.path

    # Remove trailing slash
    if path.endswith('/') and len(path) > 1:
        path = path.rstrip('/')

    # Case handling - lowercase path unless site preserves case
    if domain not in PRESERVE_CASE:
        path = path.lower()

    # Reconstruct URL
    normalised = urlunparse((scheme, domain, path, '', '', ''))

    return normalised, domain


def deduplicate_and_sort(urls):
    """Normalise, deduplicate, and sort URLs.

    Returns (new_urls, changes) where changes is a list of change descriptions.
    """
    if not urls:
        return [], []

    changes = []
    seen = {}  # normalised_lower -> (normalised_url, original_url)

    for url in urls:
        normalised, domain = normalise_url(url)
        normalised_lower = normalised.lower()

        if normalised_lower in seen:
            # Duplicate found
            existing_normalised, existing_original = seen[normalised_lower]
            changes.append(f"Remove duplicate: {url} (same as {existing_original})")
        else:
            seen[normalised_lower] = (normalised, url)
            if normalised != url:
                changes.append(f"Normalise: {url} -> {normalised}")

    # Extract normalised URLs and sort by domain
    result_urls = []
    for normalised, original in seen.values():
        result_urls.append(normalised)

    # Sort by domain, then full URL
    def sort_key(url):
        parsed = urlparse(url)
        return (parsed.netloc.lower(), url.lower())

    sorted_urls = sorted(result_urls, key=sort_key)

    # Check if order changed (result_urls preserves original order after dedup)
    if result_urls != sorted_urls:
        changes.append("Reordered URLs alphabetically by domain")

    return sorted_urls, changes


def process_performers(stash, dry_run=True):
    """Process all performers and clean up their URLs."""
    # Fetch all performers with URLs
    log.info("Fetching performers with URLs...")

    result = stash.find_performers(
        f={},
        fragment="id name urls",
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

        if not urls:
            continue

        new_urls, changes = deduplicate_and_sort(urls)

        if changes:
            performers_to_update.append({
                'id': performer['id'],
                'name': performer['name'],
                'old_urls': urls,
                'new_urls': new_urls,
                'changes': changes
            })

        # Update progress
        if count > 0:
            log.progress((idx + 1) / count)

    # Report results
    if not performers_to_update:
        log.info("No URL changes needed - all performers are already clean")
        return

    log.info(f"\n{'=' * 60}")
    log.info(f"Found {len(performers_to_update)} performers with URL changes:")
    log.info(f"{'=' * 60}\n")

    for p in performers_to_update:
        log.info(f"Performer: {p['name']} (ID: {p['id']})")
        for change in p['changes']:
            log.info(f"  - {change}")
        log.info(f"  Final URLs:")
        for url in p['new_urls']:
            log.info(f"    - {url}")
        log.info("")

    if dry_run:
        log.info(f"{'=' * 60}")
        log.info(f"PREVIEW MODE - No changes applied")
        log.info(f"Run 'Apply URL Cleanup' to apply these changes")
        log.info(f"{'=' * 60}")
    else:
        log.info(f"Applying changes to {len(performers_to_update)} performers...")

        for idx, p in enumerate(performers_to_update):
            try:
                stash.update_performer({
                    'id': p['id'],
                    'urls': p['new_urls']
                })
                log.debug(f"Updated {p['name']}")
            except Exception as e:
                log.error(f"Failed to update {p['name']}: {e}")

            log.progress((idx + 1) / len(performers_to_update))

        log.info(f"{'=' * 60}")
        log.info(f"Applied URL cleanup to {len(performers_to_update)} performers")
        log.info(f"{'=' * 60}")


def main():
    """Main entry point."""
    # Read JSON input from Stash
    json_input = json.loads(sys.stdin.read())

    # Extract connection info and initialise client
    server_connection = json_input["server_connection"]
    stash = StashInterface(server_connection)

    # Get mode from args
    mode = json_input.get("args", {}).get("mode", "preview")

    log.info(f"Performer URL Cleanup - Mode: {mode}")
    log.info("")

    if mode == "preview":
        process_performers(stash, dry_run=True)
    elif mode == "apply":
        process_performers(stash, dry_run=False)
    else:
        log.error(f"Unknown mode: {mode}")


if __name__ == "__main__":
    main()
