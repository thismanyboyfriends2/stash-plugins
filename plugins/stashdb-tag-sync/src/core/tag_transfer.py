"""Core tag transfer logic for plugin."""
import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from models import Tag, Config
from stash_client import StashClient


log = logging.getLogger(__name__)


def _merge_tag_data(stashdb_tag: Tag, existing_tag: dict, ignored_aliases: list[str] = None) -> Tag:
    """Merge StashDB tag with existing Stash tag, combining aliases and keeping best description.

    Args:
        stashdb_tag: Tag from StashDB
        existing_tag: Tag dict from local Stash
        ignored_aliases: List of aliases to exclude from merge
    """
    if ignored_aliases is None:
        ignored_aliases = []

    ignored_set = set(a.lower() for a in ignored_aliases)

    # Merge aliases: union of both sets, excluding ignored aliases
    existing_aliases = set(a.strip() for a in (existing_tag.get('aliases') or [])
                          if isinstance(a, str) and a.strip() and a.strip().lower() not in ignored_set)
    stashdb_aliases = set(a.strip() for a in (stashdb_tag.aliases or [])
                         if isinstance(a, str) and a.strip() and a.strip().lower() not in ignored_set)
    merged_aliases = sorted(list(existing_aliases | stashdb_aliases))

    # For description: prefer StashDB if non-empty, otherwise keep Stash's
    existing_desc = (existing_tag.get('description') or "").strip()
    stashdb_desc = (stashdb_tag.description or "").strip()
    merged_desc = stashdb_desc if stashdb_desc else existing_desc

    return Tag(
        name=stashdb_tag.name,
        description=merged_desc,
        stash_id=stashdb_tag.stash_id,
        aliases=merged_aliases,
        category=stashdb_tag.category
    )


def _has_alias_conflicts(merged_tag: Tag, existing_tags_by_name: dict, ignored_aliases: list[str] = None) -> list[str]:
    """Check if merged tag's aliases conflict with existing tag names.

    Returns list of conflicting aliases that already exist as tag names.
    """
    if ignored_aliases is None:
        ignored_aliases = []

    ignored_set = set(a.lower() for a in ignored_aliases)
    conflicts = []

    for alias in merged_tag.aliases:
        alias_lower = alias.lower().strip()
        if alias_lower and alias_lower not in ignored_set and alias_lower in existing_tags_by_name:
            conflicts.append(alias)

    return conflicts


def _is_tag_out_of_sync(stashdb_tag: Tag, existing_tag: dict, ignored_aliases: list[str] = None) -> bool:
    """Check if a tag differs from Stash after merging (compares merged description, aliases, and stash_ids)."""
    merged = _merge_tag_data(stashdb_tag, existing_tag, ignored_aliases)

    existing_desc = (existing_tag.get('description') or "").strip()
    merged_desc = (merged.description or "").strip()
    if existing_desc != merged_desc:
        log.debug(f"  Description differs for '{stashdb_tag.name}':")
        log.debug(f"    Stash: '{existing_desc}'")
        log.debug(f"    Merged: '{merged_desc}'")
        return True

    # Normalise aliases: strip whitespace and deduplicate
    existing_aliases = set(a.strip() for a in (existing_tag.get('aliases') or []) if isinstance(a, str) and a.strip())
    merged_aliases = set(merged.aliases)
    if existing_aliases != merged_aliases:
        log.debug(f"  Aliases differ for '{stashdb_tag.name}':")
        log.debug(f"    Stash: {existing_aliases}")
        log.debug(f"    Merged: {merged_aliases}")
        return True

    # Check if StashDB stash_id needs to be added
    if stashdb_tag.stash_id:
        existing_stash_ids = existing_tag.get('stash_ids', []) or []
        existing_stash_id_set = {item.get('stash_id') if isinstance(item, dict) else getattr(item, 'stash_id', None)
                                for item in existing_stash_ids}
        if stashdb_tag.stash_id not in existing_stash_id_set:
            log.debug(f"  StashDB ID {stashdb_tag.stash_id} missing from '{stashdb_tag.name}'")
            return True

    return False


@dataclass
class _MatchState:
    """Shared, mutated-in-place state threaded through both matching stages."""
    existing_tags_by_name: dict
    ignored_aliases: list
    matched_tags: set
    tags_to_update: list


def _match(
    tags: List[Tag],
    lookup: dict,
    key_fn: Callable[[Tag], Optional[str]],
    state: _MatchState,
    reject_blank_name: bool = False,
) -> tuple[int, int, int]:
    """Match tags against `lookup` by `key_fn(tag)`, merging/updating/marking matched as needed.

    Shared by the stash_id and name matching stages - only the lookup dict,
    key function, and `reject_blank_name` differ between them. A tag already
    present in `state.matched_tags` (from an earlier stage) is skipped so
    it's never re-matched. `state.matched_tags` and `state.tags_to_update`
    are mutated in place.

    `reject_blank_name` preserves a pre-existing asymmetry between the two
    original stages: the stash_id stage validated the matched tag's name
    before updating it (its own outer condition never checked `tag.name`,
    so a stash_id match could still carry a blank name), while the name
    stage never needed to - its outer condition already required a
    non-blank `tag.name` to compute the lookup key in the first place, so a
    tag with a whitespace-only name was matched and updated same as any
    other. Passing `reject_blank_name=True` only for the stash_id stage
    keeps that original difference intact.

    Returns (matches, skipped, failed) counts for this stage:
    - matches: matched and needs an update
    - skipped: matched but rejected for a blank name (stash_id stage only)
    - failed: matched but the merge would create an alias conflict
    """
    matches = 0
    skipped = 0
    failed = 0

    for tag in tags:
        name_key = tag.name.lower() if tag.name else None
        if name_key is not None and name_key in state.matched_tags:
            continue

        key = key_fn(tag)
        if key is None or key not in lookup:
            continue

        if reject_blank_name and (not tag.name or not tag.name.strip()):
            log.warning(f"Tag with key {key!r} has no name - skipping to prevent invalid update")
            skipped += 1
            continue

        existing_tag = lookup[key]
        if _is_tag_out_of_sync(tag, existing_tag, state.ignored_aliases):
            merged_tag = _merge_tag_data(tag, existing_tag, state.ignored_aliases)

            conflicts = _has_alias_conflicts(merged_tag, state.existing_tags_by_name, state.ignored_aliases)
            if conflicts:
                log.warning(f"Cannot update '{tag.name}' - aliases {conflicts} already exist as tag names")
                failed += 1
            else:
                state.tags_to_update.append(
                    (existing_tag['id'], merged_tag, existing_tag.get('stash_ids', []), tag.stash_id)
                )
                log.debug(f"  Matched '{tag.name}' - needs update")
                matches += 1
        else:
            log.debug(f"  Matched '{tag.name}' - in sync")

        state.matched_tags.add(name_key)

    return matches, skipped, failed


def _filter_new_tags(new_tags: List[Tag], existing_tags_by_name: dict) -> List[Tag]:
    """Drop any tag that already exists by name - an idempotency safety net.

    Should be a no-op in practice, since the name-match stage already covers
    everything in existing_tags_by_name. Builds a new list rather than
    mutating `new_tags` while iterating it, so consecutive matches are never
    silently skipped.
    """
    filtered = []
    for tag in new_tags:
        if tag.name.lower() in existing_tags_by_name:
            log.warning(f"Tag '{tag.name}' already exists but wasn't matched - skipping to prevent duplicate")
        else:
            filtered.append(tag)
    return filtered


def transfer_tags_graphql(
    client: StashClient,
    tags: List[Tag],
    config: Config
) -> dict:
    """Transfer tags via three-stage matching: stash_id, then name, then create new.

    Returns:
        Dictionary with transfer statistics (created, updated, skipped, failed)
    """
    log.info(f"Starting transfer of {len(tags)} tags to Stash")

    existing_tags_by_name, existing_tags_by_stash_id = client.find_existing_tags_with_data()
    log.info(f"Found {len(existing_tags_by_name)} existing tags in Stash")

    state = _MatchState(
        existing_tags_by_name=existing_tags_by_name,
        ignored_aliases=config.ignored_aliases,
        matched_tags=set(),
        tags_to_update=[],
    )

    # Stage 1: Match by stash_id (most reliable)
    log.info("Stage 1: Matching tags by stash_id...")
    stage1_matches, skipped_tags, stage1_failed = _match(
        tags, existing_tags_by_stash_id, lambda t: t.stash_id or None,
        state, reject_blank_name=True,
    )
    log.info(f"Stage 1: Found {stage1_matches} tags to update by stash_id")

    # Stage 2: Match remaining tags by name (case-insensitive)
    log.info("Stage 2: Matching remaining tags by name...")
    stage2_matches, _, stage2_failed = _match(
        tags, existing_tags_by_name, lambda t: t.name.lower() if t.name else None,
        state,
    )
    log.info(f"Stage 2: Found {stage2_matches} tags to update by name")

    matched_tags = state.matched_tags
    tags_to_update = state.tags_to_update

    failed_tags = stage1_failed + stage2_failed

    new_tags = [
        tag for tag in tags
        if tag.name and tag.name.lower() not in matched_tags
    ]

    created_count = 0
    create_failed_count = 0
    log.info(f"Stage 3: Creating {len(new_tags)} new tags")
    if new_tags:
        new_tags = _filter_new_tags(new_tags, existing_tags_by_name)

        if new_tags:
            created_ids, create_failed_count = client.create_tags_batch(new_tags)
            # Not len(created_ids): two source tags whose names differ only by case
            # collapse to one dict entry there, which would undercount real successes.
            created_count = len(new_tags) - create_failed_count
            if create_failed_count == 0:
                log.info(f"Successfully created {created_count} new tags")
            else:
                log.warning(f"Created {created_count} of {len(new_tags)} tags ({create_failed_count} failed)")
        else:
            log.info("All new tags already exist")
    else:
        log.info("No new tags to create")

    updated_count = 0
    update_failed_count = 0
    if tags_to_update:
        log.info(f"Updating {len(tags_to_update)} matched tags...")
        updated_count = client.update_tags_batch(tags_to_update)
        update_failed_count = len(tags_to_update) - updated_count

        if updated_count == len(tags_to_update):
            log.info(f"Successfully updated {updated_count} tags")
        else:
            log.warning(f"Updated {updated_count} of {len(tags_to_update)} tags ({update_failed_count} failed)")
    else:
        log.info("No tags to update")

    log.info("Tag transfer completed successfully")

    # Total failed = alias conflicts + tags that failed to create + tags that failed to update
    total_failed = failed_tags + create_failed_count + update_failed_count

    return {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_tags,
        "failed": total_failed,
        "total": len(tags)
    }
