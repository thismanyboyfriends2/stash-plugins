"""Performer URL Cleanup Plugin for Stash.

Normalises, deduplicates, and sorts performer URLs.
"""
import json
import sys
from collections import defaultdict
from urllib.parse import urlparse, urlunparse

# Debug output paths (temporary)
DEBUG_DIR = r"C:\stash"
DEBUG_BY_PERFORMER = f"{DEBUG_DIR}\\url_cleanup_by_performer.txt"
DEBUG_BY_DOMAIN = f"{DEBUG_DIR}\\url_cleanup_by_domain.txt"
DEBUG_POTENTIAL = f"{DEBUG_DIR}\\url_cleanup_potential.txt"

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
    'fansly.com',
    'xhamster.com',
}

# Sites that should have www prefix added
ADD_WWW = {
    'instagram.com',
    'pornhub.com',
    'xvideos.com',
}

# Domain aliases - map old domains to canonical ones
DOMAIN_ALIASES = {
    'twitter.com': 'x.com',
}

# Sites where path is case-insensitive (safe to lowercase)
# Default behaviour: preserve original case
LOWERCASE_PATH = {
    'onlyfans.com',
    'instagram.com',
}

# Sites that don't support HTTPS (keep as HTTP)
HTTP_ONLY = {
    'bustybuffy.com',
    'www.bustybuffy.com',
}

# Path transformations - (domain, old_prefix, new_prefix)
PATH_TRANSFORMS = [
    ('eastcoasttalents.com', '/site/talent/', '/talent/'),
]

# Path suffixes to remove - (domain, suffix)
REMOVE_PATH_SUFFIX = [
    ('fansly.com', '/posts'),
]

# Sites that require trailing slashes
KEEP_TRAILING_SLASH = {
    'adultfilmdatabase.com',
    'www.adultfilmdatabase.com',
}


def get_known_domains():
    """Build set of all domains we have explicit rules for."""
    known = set()
    known.update(REMOVE_WWW)
    known.update(ADD_WWW)
    known.update(DOMAIN_ALIASES.keys())
    known.update(LOWERCASE_PATH)
    known.update(HTTP_ONLY)
    known.update(KEEP_TRAILING_SLASH)
    for domain, _, _ in PATH_TRANSFORMS:
        known.add(domain)
    for domain, _ in REMOVE_PATH_SUFFIX:
        known.add(domain)
    # Also add www variants
    www_variants = {f'www.{d}' for d in known if not d.startswith('www.')}
    known.update(www_variants)
    return known


KNOWN_DOMAINS = get_known_domains()


def is_known_domain(domain):
    """Check if domain has explicit rules configured."""
    d = domain.lower()
    if d in KNOWN_DOMAINS:
        return True
    if d.startswith('www.') and d[4:] in KNOWN_DOMAINS:
        return True
    return False


def normalise_url(url):
    """Normalise a URL according to site-specific rules.

    Returns (normalised_url, canonical_domain) tuple.
    """
    # Ensure URL has a scheme before parsing (urlparse needs it to identify netloc)
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Parse the URL
    parsed = urlparse(url)

    # Normalise domain (need this early to check HTTP_ONLY)
    domain = parsed.netloc.lower()

    # Upgrade to HTTPS unless site doesn't support it
    scheme = 'http' if domain in HTTP_ONLY else 'https'

    # Remove www if site doesn't use it
    if domain.startswith('www.'):
        domain_without_www = domain[4:]
        if domain_without_www in REMOVE_WWW:
            domain = domain_without_www

    # Add www if site requires it
    if not domain.startswith('www.') and domain in ADD_WWW:
        domain = 'www.' + domain

    # Apply domain aliases
    if domain in DOMAIN_ALIASES:
        domain = DOMAIN_ALIASES[domain]

    # Handle path
    path = parsed.path

    # Apply path transformations
    for transform_domain, old_prefix, new_prefix in PATH_TRANSFORMS:
        if domain == transform_domain and path.startswith(old_prefix):
            path = new_prefix + path[len(old_prefix):]
            break

    # Remove path suffixes
    for suffix_domain, suffix in REMOVE_PATH_SUFFIX:
        if domain == suffix_domain and path.endswith(suffix):
            path = path[:-len(suffix)]
            break

    # Remove trailing slash (unless site requires it)
    if path.endswith('/') and domain not in KEEP_TRAILING_SLASH:
        path = path.rstrip('/')

    # Case handling - only lowercase if site is known to be case-insensitive
    if domain in LOWERCASE_PATH:
        path = path.lower()

    # Reconstruct URL (preserve query string, drop fragment)
    normalised = urlunparse((scheme, domain, path, parsed.params, parsed.query, ''))

    return normalised, domain


def write_debug_files(performers_to_update):
    """Write debug output files for analysis."""
    # Per-performer output (confirmed changes only)
    with open(DEBUG_BY_PERFORMER, 'w', encoding='utf-8') as f:
        for p in performers_to_update:
            if not p['changes']:
                continue
            f.write(f"{'=' * 60}\n")
            f.write(f"Performer: {p['name']} (ID: {p['id']})\n")
            f.write(f"{'=' * 60}\n")
            f.write("Original URLs:\n")
            for url in p['old_urls']:
                f.write(f"  {url}\n")
            f.write("\nChanges:\n")
            for change in p['changes']:
                f.write(f"  - {change}\n")
            f.write("\nFinal URLs:\n")
            for url in p['new_urls']:
                f.write(f"  {url}\n")
            f.write("\n")

    # Per-domain output - group confirmed changes by domain
    domain_changes = defaultdict(list)
    for p in performers_to_update:
        for url in p['old_urls']:
            normalised, domain = normalise_url(url)
            if normalised != url and is_known_domain(domain):
                domain_changes[domain].append({
                    'performer': p['name'],
                    'original': url,
                    'normalised': normalised
                })

    with open(DEBUG_BY_DOMAIN, 'w', encoding='utf-8') as f:
        for domain in sorted(domain_changes.keys()):
            changes = domain_changes[domain]
            f.write(f"{'=' * 60}\n")
            f.write(f"Domain: {domain} ({len(changes)} changes)\n")
            f.write(f"{'=' * 60}\n")
            for c in changes:
                f.write(f"[{c['performer']}]\n")
                f.write(f"  {c['original']}\n")
                f.write(f"  -> {c['normalised']}\n")
            f.write("\n")

    # Potential changes - unknown domains grouped by domain
    potential_by_domain = defaultdict(list)
    for p in performers_to_update:
        for url in p['old_urls']:
            normalised, domain = normalise_url(url)
            if normalised != url and not is_known_domain(domain):
                potential_by_domain[domain].append({
                    'performer': p['name'],
                    'original': url,
                    'normalised': normalised
                })

    with open(DEBUG_POTENTIAL, 'w', encoding='utf-8') as f:
        f.write("POTENTIAL CHANGES - Unknown domains (review and add rules as needed)\n")
        f.write(f"{'=' * 60}\n\n")
        for domain in sorted(potential_by_domain.keys()):
            changes = potential_by_domain[domain]
            f.write(f"{'=' * 60}\n")
            f.write(f"Domain: {domain} ({len(changes)} potential changes)\n")
            f.write(f"{'=' * 60}\n")
            for c in changes:
                f.write(f"[{c['performer']}]\n")
                f.write(f"  {c['original']}\n")
                f.write(f"  -> {c['normalised']}\n")
            f.write("\n")


def has_mixed_case(url):
    """Check if URL path has mixed case (likely from scraper, more accurate)."""
    parsed = urlparse(url)
    path = parsed.path
    return path != path.lower() and path != path.upper()


def deduplicate_and_sort(urls):
    """Normalise, deduplicate, and sort URLs.

    Only applies changes to known domains. Unknown domain changes go to potential list.
    Returns (new_urls, changes, potential_changes).
    """
    if not urls:
        return [], [], []

    changes = []
    potential_changes = []
    seen = {}  # normalised_lower -> (normalised_url, original_url, domain, is_known)

    for url in urls:
        normalised, domain = normalise_url(url)
        normalised_lower = normalised.lower()
        known = is_known_domain(domain)

        if normalised_lower in seen:
            # Duplicate found - prefer mixed case version (likely from scraper)
            existing_normalised, existing_original, existing_domain, existing_known = seen[normalised_lower]
            if has_mixed_case(normalised) and not has_mixed_case(existing_normalised):
                seen[normalised_lower] = (normalised, url, domain, known)
                msg = f"Remove duplicate: {existing_original} (prefer mixed-case {url})"
                if known or existing_known:
                    changes.append(msg)
                else:
                    potential_changes.append(msg)
            else:
                msg = f"Remove duplicate: {url} (same as {existing_original})"
                if known or existing_known:
                    changes.append(msg)
                else:
                    potential_changes.append(msg)
        else:
            seen[normalised_lower] = (normalised, url, domain, known)
            if normalised != url:
                msg = f"Normalise: {url} -> {normalised}"
                if known:
                    changes.append(msg)
                else:
                    potential_changes.append(msg)

    # Build result - only apply normalisations for known domains
    result_urls = []
    for normalised, original, domain, known in seen.values():
        if known:
            result_urls.append(normalised)
        else:
            result_urls.append(original)  # Keep original for unknown domains

    # Sort by domain, then full URL
    def sort_key(url):
        parsed = urlparse(url)
        return (parsed.netloc.lower(), url.lower())

    sorted_urls = sorted(result_urls, key=sort_key)

    # Check if order changed (result_urls preserves original order after dedup)
    if result_urls != sorted_urls:
        changes.append("Reordered URLs alphabetically by domain")

    return sorted_urls, changes, potential_changes


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

        new_urls, changes, potential_changes = deduplicate_and_sort(urls)

        if changes or potential_changes:
            performers_to_update.append({
                'id': performer['id'],
                'name': performer['name'],
                'old_urls': urls,
                'new_urls': new_urls,
                'changes': changes,
                'potential_changes': potential_changes,
            })

        # Update progress
        if count > 0:
            log.progress((idx + 1) / count)

    # Report results
    if not performers_to_update:
        log.info("No URL changes needed - all performers are already clean")
        return

    # Write debug files
    write_debug_files(performers_to_update)
    log.info(f"Debug files written to {DEBUG_DIR}")

    # Filter to only performers with confirmed changes
    performers_with_changes = [p for p in performers_to_update if p['changes']]
    performers_with_potential = [p for p in performers_to_update if p['potential_changes']]

    log.info(f"Found {len(performers_with_changes)} performers with confirmed changes")
    log.info(f"Found {len(performers_with_potential)} performers with potential changes (see {DEBUG_POTENTIAL})")

    if performers_with_changes:
        log.info(f"\n{'=' * 60}")
        log.info(f"Confirmed changes:")
        log.info(f"{'=' * 60}\n")

        for p in performers_with_changes:
            log.info(f"Performer: {p['name']} (ID: {p['id']})")
            for change in p['changes']:
                log.info(f"  - {change}")
            log.info(f"  Final URLs:")
            for url in p['new_urls']:
                log.info(f"    - {url}")

    if dry_run:
        log.info(f"{'=' * 60}")
        log.info(f"PREVIEW MODE - No changes applied")
        if performers_with_changes:
            log.info(f"Run 'Apply URL Cleanup' to apply {len(performers_with_changes)} confirmed changes")
        log.info(f"{'=' * 60}")
    else:
        if not performers_with_changes:
            log.info("No confirmed changes to apply")
            return

        log.info(f"Applying changes to {len(performers_with_changes)} performers...")

        for idx, p in enumerate(performers_with_changes):
            try:
                stash.update_performer({
                    'id': p['id'],
                    'urls': p['new_urls']
                })
                log.debug(f"Updated {p['name']}")
            except Exception as e:
                log.error(f"Failed to update {p['name']}: {e}")

            log.progress((idx + 1) / len(performers_with_changes))

        log.info(f"{'=' * 60}")
        log.info(f"Applied URL cleanup to {len(performers_with_changes)} performers")
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
