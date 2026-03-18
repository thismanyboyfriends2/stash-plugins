"""Scene Title to Filename Plugin for Stash.

Batch renames scene files on disk to match their Stash title.
"""
import json
import os
import re
import sys

try:
    import stashapi.log as log
    from stashapi.stashapp import StashInterface
except ImportError:
    print(json.dumps({
        "output": "Error: stashapp-tools not installed. Run: pip install stashapp-tools"
    }))
    sys.exit(1)

ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|]')
PAGE_SIZE = 100
MAX_CONSECUTIVE_FAILURES = 5

FIND_SCENES_QUERY = """
query FindScenes($filter: FindFilterType!, $scene_filter: SceneFilterType) {
  findScenes(filter: $filter, scene_filter: $scene_filter) {
    count
    scenes {
      id
      title
      files {
        id
        path
        basename
      }
    }
  }
}
"""

MOVE_FILES_MUTATION = """
mutation MoveFiles($input: MoveFilesInput!) {
  moveFiles(input: $input)
}
"""


def sanitize_filename(title):
    """Remove illegal filesystem characters and trim whitespace."""
    sanitized = ILLEGAL_CHARS.sub('', title)
    sanitized = re.sub(r' {2,}', ' ', sanitized)
    return sanitized.strip()


def find_scenes(stash, path_filter):
    """Fetch all scenes matching the path filter, paginated.

    Uses INCLUDES for the GraphQL query (substring match), then post-filters
    to ensure file paths actually start with the filter value. This avoids
    false positives like '/data/social/dommes_empire' matching '/data/import/Femdom Empire'.
    """
    scenes = []
    page = 1

    while True:
        result = stash.call_GQL(FIND_SCENES_QUERY, {
            "filter": {"page": page, "per_page": PAGE_SIZE},
            "scene_filter": {
                "path": {"value": path_filter, "modifier": "INCLUDES"}
            }
        })

        data = result["findScenes"]
        scenes.extend(data["scenes"])
        total = data["count"]

        if total > PAGE_SIZE:
            log.info(f"Fetching scenes... {len(scenes)}/{total}")

        if len(scenes) >= total:
            break
        page += 1

    # Post-filter: only keep scenes where at least one file starts with the path filter
    filtered = []
    for scene in scenes:
        files = scene.get("files") or []
        if any(f["path"].startswith(path_filter) for f in files):
            filtered.append(scene)

    if len(filtered) < len(scenes):
        log.info(f"Filtered {len(scenes) - len(filtered)} scenes not under {path_filter}")

    return filtered


def plan_renames(scenes):
    """Build a list of planned renames, handling conflicts and edge cases.

    Returns (renames, skipped) where:
      renames: list of {scene_id, file_id, old_path, old_basename, new_basename}
      skipped: list of {scene_id, reason, detail}
    """
    renames = []
    skipped = []
    # Track target basenames per directory to detect conflicts
    targets_by_dir = {}

    for scene in scenes:
        scene_id = scene["id"]
        title = scene.get("title") or ""
        files = scene.get("files") or []

        if not title.strip():
            skipped.append({
                "scene_id": scene_id,
                "reason": "no_title",
                "detail": f"Scene {scene_id} has no title",
            })
            continue

        if len(files) == 0:
            skipped.append({
                "scene_id": scene_id,
                "reason": "no_files",
                "detail": f"Scene {scene_id} ({title}) has no files",
            })
            continue

        if len(files) > 1:
            skipped.append({
                "scene_id": scene_id,
                "reason": "multiple_files",
                "detail": f"Scene {scene_id} ({title}) has {len(files)} files — resolve manually",
            })
            continue

        file_info = files[0]
        old_basename = file_info["basename"]
        old_path = file_info["path"]
        directory = os.path.dirname(old_path)
        _, ext = os.path.splitext(old_basename)

        sanitized = sanitize_filename(title)
        if not sanitized:
            skipped.append({
                "scene_id": scene_id,
                "reason": "empty_after_sanitize",
                "detail": f"Scene {scene_id} title '{title}' is empty after sanitizing",
            })
            continue

        new_basename = sanitized + ext

        # Register existing basename in conflict tracker before checking
        if directory not in targets_by_dir:
            targets_by_dir[directory] = set()
        dir_targets = targets_by_dir[directory]

        if new_basename == old_basename:
            dir_targets.add(old_basename.lower())
            skipped.append({
                "scene_id": scene_id,
                "reason": "already_correct",
                "detail": f"Scene {scene_id} ({title}) already has correct filename",
            })
            continue

        candidate = new_basename
        counter = 1
        base_name = sanitized
        while candidate.lower() in dir_targets:
            candidate = f"{base_name} ({counter}){ext}"
            counter += 1

        dir_targets.add(candidate.lower())
        new_basename = candidate

        renames.append({
            "scene_id": scene_id,
            "file_id": file_info["id"],
            "old_path": old_path,
            "old_basename": old_basename,
            "new_basename": new_basename,
        })

    return renames, skipped


def execute_renames(stash, renames):
    """Execute renames via moveFiles mutation. Returns (succeeded, failed) counts."""
    succeeded = 0
    failed = 0
    consecutive_failures = 0
    total = len(renames)

    for idx, rename in enumerate(renames):
        try:
            stash.call_GQL(MOVE_FILES_MUTATION, {
                "input": {
                    "ids": [rename["file_id"]],
                    "destination_folder": os.path.dirname(rename["old_path"]),
                    "destination_basename": rename["new_basename"],
                }
            })
            log.info(f"  Renamed: {rename['old_basename']} -> {rename['new_basename']}")
            succeeded += 1
            consecutive_failures = 0
        except Exception as e:
            log.error(f"  Failed: {rename['old_basename']} -> {rename['new_basename']}: {e}")
            failed += 1
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                remaining = total - idx - 1
                log.error(f"Aborting: {MAX_CONSECUTIVE_FAILURES} consecutive failures — likely a systemic issue ({remaining} renames skipped)")
                break

        log.progress((idx + 1) / total)

    return succeeded, failed


def process_scenes(stash, path_filter, dry_run=True):
    """Main processing pipeline."""
    log.info(f"Fetching scenes matching path: {path_filter}")

    scenes = find_scenes(stash, path_filter)
    log.info(f"Found {len(scenes)} scenes matching filter")

    if not scenes:
        log.info("No scenes found — nothing to do")
        return

    renames, skipped = plan_renames(scenes)

    # Log skipped scenes by category
    skip_reasons = {}
    for s in skipped:
        reason = s["reason"]
        skip_reasons.setdefault(reason, []).append(s)

    reason_labels = {
        "no_title": "no title",
        "no_files": "no files",
        "multiple_files": "multiple files (resolve manually)",
        "empty_after_sanitize": "title empty after sanitizing",
        "already_correct": "already correctly named",
    }
    for reason, items in skip_reasons.items():
        label = reason_labels.get(reason, reason)
        if reason == "already_correct":
            log.info(f"Skipping {len(items)} scenes: {label}")
        else:
            log.warning(f"Skipping {len(items)} scenes: {label}")

    if not renames:
        log.info("No renames needed")
        return

    log.info(f"\n{'=' * 60}")
    log.info(f"Planned renames: {len(renames)}")
    log.info(f"{'=' * 60}\n")

    for rename in renames:
        log.info(f"  {rename['old_basename']} -> {rename['new_basename']}")

    if dry_run:
        log.info(f"\n{'=' * 60}")
        log.info("PREVIEW MODE — No changes applied")
        log.info(f"{'=' * 60}")
        log.info(f"  Would rename: {len(renames)} files")
        for reason, items in skip_reasons.items():
            label = reason_labels.get(reason, reason)
            log.info(f"  Skipped:      {len(items)} ({label})")
        log.info(f"  Total scenes: {len(scenes)}")
        log.info(f"{'=' * 60}")
        log.info(f"Run 'Rename Scene Files' to apply")
    else:
        log.info(f"\nRenaming {len(renames)} files...")
        succeeded, failed = execute_renames(stash, renames)
        log.info(f"\n{'=' * 60}")
        log.info(f"Renamed {succeeded} files ({failed} failed)")
        log.info(f"{'=' * 60}")


def main():
    """Main entry point."""
    json_input = json.loads(sys.stdin.read())

    server_connection = json_input["server_connection"]
    stash = StashInterface(server_connection)

    plugin_settings = stash.get_configuration().get("plugins", {}).get("scene-title-to-filename", {})
    path_filter = (plugin_settings.get("pathFilter") or "").strip()

    mode = json_input.get("args", {}).get("mode", "preview")

    log.info(f"Scene Title to Filename — Mode: {mode}")

    if not path_filter:
        log.error("pathFilter setting is empty. Configure it in Settings > Plugins > Scene Title to Filename")
        return

    if mode == "preview":
        process_scenes(stash, path_filter, dry_run=True)
    elif mode == "apply":
        process_scenes(stash, path_filter, dry_run=False)
    else:
        log.error(f"Unknown mode: {mode}")


if __name__ == "__main__":
    main()
