"""Scene Title Cleanup plugin for Stash.

Strips trailing resolution/quality suffixes (e.g. "(720 HD)", "(1080 HD)",
"(4K)") that some scrapers append to scene titles.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import stashapi.log as log
    from stashapi.stashapp import StashInterface
except ModuleNotFoundError:
    print(json.dumps({
        "output": "Error: stashapp-tools not installed. Run: pip install stashapp-tools"
    }))
    sys.exit(1)

# Number of parallel threads for updates
PARALLEL_WORKERS = 10

PAGE_SIZE = 1000

# Matches a single trailing "(...)" resolution/quality tag, e.g.
# "(720 HD)", "(1080 HD)", "(720p)", "(2160p)", "(4K)", "(HD)", "(SD)".
# Digits are only treated as a resolution when paired with "p" or an HD/SD
# keyword - bare digits alone (e.g. a "(2008)" release year) never match,
# since a bare 3-4 digit number in parens is indistinguishable from one.
DEFAULT_SUFFIX_RE = re.compile(
    r'\s*\(\s*(?:4K|UHD|\d{3,4}p(?:\s*(?:HD|SD))?|\d{3,4}\s+(?:HD|SD)|HD|SD)\s*\)\s*$',
    re.IGNORECASE,
)

# Safety cap on repeated suffix stripping (chained tags like "(1080 HD) (WEB-DL)")
MAX_STRIP_ITERATIONS = 10

FIND_SCENES_QUERY = """
query FindScenes($filter: FindFilterType!) {
  findScenes(filter: $filter) {
    count
    scenes {
      id
      title
      studio {
        name
      }
    }
  }
}
"""


def parse_extra_suffixes(raw):
    """Parse a comma-separated setting string into a list of regexes.

    Each extra suffix is matched literally (case-insensitive) when it appears
    at the end of the title, with any preceding whitespace.
    """
    if not raw:
        return []
    patterns = []
    for part in raw.split(','):
        suffix = part.strip()
        if not suffix:
            continue
        patterns.append(re.compile(r'\s*' + re.escape(suffix) + r'\s*$', re.IGNORECASE))
    return patterns


def clean_title(title, extra_patterns=None):
    """Strip trailing resolution/quality suffixes from a title.

    Returns (new_title, changed). Repeatedly strips so chained suffixes
    (e.g. "(1080 HD) (WEB-DL)") are fully removed. Never returns an empty
    title - if stripping would empty it out, the original is kept.
    """
    patterns = [DEFAULT_SUFFIX_RE] + list(extra_patterns or [])
    current = title

    for _ in range(MAX_STRIP_ITERATIONS):
        stripped = current
        for pattern in patterns:
            match = pattern.search(stripped)
            if match:
                stripped = stripped[:match.start()]
                break
        if stripped == current:
            break
        current = stripped

    if not current.strip():
        return title, False

    return current, current != title


def find_scenes(stash):
    """Fetch all scenes with a title, paginated."""
    scenes = []
    page = 1

    while True:
        result = stash.call_GQL(FIND_SCENES_QUERY, {
            "filter": {"page": page, "per_page": PAGE_SIZE}
        })

        data = result["findScenes"]
        scenes.extend(data["scenes"])
        total = data["count"]

        if total > PAGE_SIZE:
            log.info(f"Fetching scenes... {min(len(scenes), total)}/{total}")

        if len(scenes) >= total:
            break
        page += 1

    return [s for s in scenes if (s.get("title") or "").strip()]


def plan_changes(scenes, studio_filter, extra_patterns):
    """Build a list of planned title changes."""
    changes = []

    for scene in scenes:
        if studio_filter:
            studio_name = (scene.get("studio") or {}).get("name") or ""
            if studio_filter.lower() not in studio_name.lower():
                continue

        title = scene["title"]
        new_title, changed = clean_title(title, extra_patterns)
        if changed:
            changes.append({
                "id": scene["id"],
                "old_title": title,
                "new_title": new_title,
            })

    return changes


def process_scenes(stash, studio_filter, extra_patterns, dry_run=True):
    """Main processing pipeline."""
    log.info("Fetching scenes...")
    scenes = find_scenes(stash)
    log.info(f"Found {len(scenes)} scenes with a title")

    changes = plan_changes(scenes, studio_filter, extra_patterns)

    if not changes:
        log.info("No title changes needed")
        return

    log.info(f"\n{'=' * 60}")
    log.info(f"Planned title changes: {len(changes)}")
    log.info(f"{'=' * 60}\n")

    for change in changes:
        log.info(f"  {change['old_title']!r} -> {change['new_title']!r}")

    if dry_run:
        log.info(f"\n{'=' * 60}")
        log.info("PREVIEW MODE — No changes applied")
        log.info(f"Run 'Apply Title Cleanup' to apply {len(changes)} changes")
        log.info(f"{'=' * 60}")
        return

    log.info(f"\nApplying {len(changes)} title changes using {PARALLEL_WORKERS} workers...")

    completed = 0
    failed = 0
    total = len(changes)

    def update_scene(change):
        stash.update_scene({"id": change["id"], "title": change["new_title"]})
        return change["old_title"]

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {executor.submit(update_scene, c): c for c in changes}
        for future in as_completed(futures):
            change = futures[future]
            try:
                future.result()
                completed += 1
            except Exception as e:
                log.error(f"Failed to update {change['old_title']!r}: {e}")
                failed += 1
            log.progress((completed + failed) / total)

    log.info(f"{'=' * 60}")
    log.info(f"Applied title cleanup to {completed} scenes ({failed} failed)")
    log.info(f"{'=' * 60}")


def main():
    """Main entry point."""
    json_input = json.loads(sys.stdin.read())

    server_connection = json_input["server_connection"]
    stash = StashInterface(server_connection)

    plugin_settings = stash.get_configuration().get("plugins", {}).get("scene-title-cleanup", {})
    studio_filter = (plugin_settings.get("studioFilter") or "").strip()
    extra_patterns = parse_extra_suffixes(plugin_settings.get("extraSuffixes") or "")

    mode = json_input.get("args", {}).get("mode", "preview")

    log.info(f"Scene Title Cleanup — Mode: {mode}")
    if studio_filter:
        log.info(f"Studio filter: {studio_filter}")

    if mode == "preview":
        process_scenes(stash, studio_filter, extra_patterns, dry_run=True)
    elif mode == "apply":
        process_scenes(stash, studio_filter, extra_patterns, dry_run=False)
    else:
        log.error(f"Unknown mode: {mode}")


if __name__ == "__main__":
    main()
