"""Auto-Merge Duplicates plugin for Stash.

Queries all phash duplicate groups detected by Stash and merges each group
into a single scene, keeping the one with the most metadata as the destination.
"""
import json
import sys

try:
    import stashapi.log as log
    from stashapi.stashapp import StashInterface
except ImportError:
    print(json.dumps({"output": "Error: stashapp-tools not installed. Run: pip install stashapp-tools"}))
    sys.exit(1)

PLUGIN_ID = "auto-merge-duplicates"
MAX_CONSECUTIVE_ERRORS = 5

FIND_DUPLICATES_QUERY = """
query FindDuplicateScenes($distance: Int) {
  findDuplicateScenes(distance: $distance) {
    id
    title
    performers { id }
    tags { id }
    studio { id }
    galleries { id }
    urls
    files {
      width
      height
      duration
    }
  }
}
"""

SCENE_MERGE_MUTATION = """
mutation SceneMerge($input: SceneMergeInput!) {
  sceneMerge(input: $input) {
    id
  }
}
"""


def _scene_score(scene, prefer_higher_res):
    """Return a (metadata_score, resolution, duration) tuple for ranking.

    Higher metadata score = more reasons to keep this scene. Resolution and
    duration are used as tiebreakers when scores are equal.
    """
    metadata_score = 0
    if scene.get("title"):
        metadata_score += 3
    metadata_score += len(scene.get("performers") or [])
    metadata_score += len(scene.get("tags") or [])
    if scene.get("studio"):
        metadata_score += 1
    metadata_score += len(scene.get("galleries") or [])
    metadata_score += len(scene.get("urls") or [])

    resolution = 0
    duration = 0.0
    files = scene.get("files") or []
    if files:
        resolution = max((f.get("width", 0) * f.get("height", 0)) for f in files)
        duration = max((f.get("duration") or 0.0) for f in files)

    res_key = resolution if prefer_higher_res else 0
    # scene id as final tiebreaker so destination selection is deterministic
    # across repeated runs regardless of API return order
    return (metadata_score, res_key, duration, -int(scene.get("id", 0)))


def pick_destination(group, prefer_higher_res):
    """Return the scene from the group that should be kept as the destination."""
    return max(group, key=lambda s: _scene_score(s, prefer_higher_res))


def process_duplicates(stash, settings, dry_run):
    try:
        distance = int(float(settings.get("matchDistance") or 0))
    except (ValueError, TypeError):
        log.warning("Invalid matchDistance setting — defaulting to 0 (exact match).")
        distance = 0
    prefer_higher_res = bool(settings.get("preferHigherRes", False))
    merge_play_history = bool(settings.get("mergePlayHistory", False))
    merge_o_history = bool(settings.get("mergeOHistory", False))

    log.info(
        f"Auto-Merge Duplicates — dryRun={dry_run} distance={distance}"
        f" preferHigherRes={prefer_higher_res} mergePlayHistory={merge_play_history}"
        f" mergeOHistory={merge_o_history}"
    )

    try:
        result = stash.call_GQL(FIND_DUPLICATES_QUERY, {"distance": distance})
    except Exception as e:
        log.error(f"Failed to fetch duplicate groups: {e}")
        return

    raw_groups = result.get("findDuplicateScenes")
    if raw_groups is None:
        log.error("Empty response from findDuplicateScenes — possible GraphQL error.")
        return
    groups = raw_groups

    if not groups:
        log.info("No duplicate groups found.")
        return

    log.info(f"Found {len(groups)} duplicate group(s).")

    merged = 0
    skipped = 0
    errors = 0
    consecutive_errors = 0

    for idx, group in enumerate(groups):
        log.progress((idx + 1) / len(groups))

        if len(group) < 2:
            skipped += 1
            continue

        destination = pick_destination(group, prefer_higher_res)
        sources = [s["id"] for s in group if s["id"] != destination["id"]]
        dest_title = destination.get("title") or "(no title)"

        log.info(
            f"Group {idx + 1}/{len(groups)}: keeping scene {destination['id']} '{dest_title}'"
            f" | merging {len(sources)} source(s): {sources}"
        )

        if dry_run:
            continue

        try:
            stash.call_GQL(SCENE_MERGE_MUTATION, {
                "input": {
                    "destination": destination["id"],
                    "source": sources,
                    "play_history": merge_play_history,
                    "o_history": merge_o_history,
                }
            })
            merged += 1
            consecutive_errors = 0
        except Exception as e:
            log.error(f"Failed to merge group {idx + 1}: {e}")
            errors += 1
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log.error(f"Aborting: {MAX_CONSECUTIVE_ERRORS} consecutive merge failures.")
                break

    if dry_run:
        log.info(f"Dry run complete. {len(groups) - skipped} group(s) would be merged, {skipped} skipped.")
    else:
        log.info(f"Done. {merged} group(s) merged, {skipped} skipped, {errors} error(s).")


def main():
    json_input = json.loads(sys.stdin.read())
    stash = StashInterface(json_input["server_connection"])

    plugin_settings = stash.get_configuration().get("plugins", {}).get(PLUGIN_ID, {})
    global_dry_run = bool(plugin_settings.get("dryRun", False))
    mode = json_input.get("args", {}).get("mode", "preview")

    dry_run = global_dry_run or (mode == "preview")

    if mode in ("preview", "apply"):
        process_duplicates(stash, plugin_settings, dry_run)
    else:
        log.error(f"Unknown mode: {mode}")


if __name__ == "__main__":
    main()
