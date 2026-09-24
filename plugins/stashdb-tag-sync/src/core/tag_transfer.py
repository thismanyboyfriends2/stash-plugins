"""Core tag transfer logic for plugin."""
import logging
from typing import List, Optional

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


def _has_alias_conflicts(
    merged_tag: Tag,
    existing_tags_by_name: dict,
    ignored_aliases: list[str] = None,
    own_tag_id: str = None,
) -> list[str]:
    """Check if merged tag's aliases conflict with existing tag names.

    `own_tag_id`, when given, is the id of the local tag being updated: an
    alias that resolves to that same tag (its own current name, or a former
    name it's being renamed away from) is its own identity, not a conflict.

    Returns list of conflicting aliases that already exist as tag names.
    """
    if ignored_aliases is None:
        ignored_aliases = []

    ignored_set = set(a.lower() for a in ignored_aliases)
    conflicts = []

    for alias in merged_tag.aliases:
        alias_lower = alias.lower().strip()
        if not alias_lower or alias_lower in ignored_set:
            continue

        match = existing_tags_by_name.get(alias_lower)
        if match is None:
            continue
        if own_tag_id is not None and match.get('id') == own_tag_id:
            continue

        conflicts.append(alias)

    return conflicts


def _is_tag_out_of_sync(stashdb_tag: Tag, existing_tag: dict, ignored_aliases: list[str] = None) -> bool:
    """Check if a tag differs from Stash after merging (compares every merged field against the existing tag)."""
    merged = _merge_tag_data(stashdb_tag, existing_tag, ignored_aliases)

    existing_name = (existing_tag.get('name') or "").strip()
    merged_name = (merged.name or "").strip()
    if existing_name != merged_name:
        log.debug(f"  Name differs for '{stashdb_tag.name}':")
        log.debug(f"    Stash: '{existing_name}'")
        log.debug(f"    Merged: '{merged_name}'")
        return True

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


def _resolve_local_match(
    tag: Tag,
    existing_tags_by_stash_id: dict,
    existing_tags_by_name: dict,
    claimed_ids: set,
) -> tuple[Optional[dict], Optional[str], bool]:
    """Find the one local tag this StashDB tag owns, trying stash_id then name.

    A local tag id already in `claimed_ids` (claimed by an earlier StashDB
    tag this run) is never matched again, so a single local tag can only be
    reached once per run - via stash_id or name, never both.

    Returns (existing_tag, match_source, already_claimed):
    - A resolved match: (existing_tag, 'stash_id' | 'name', False)
    - A candidate exists but its local tag was already claimed this run
      (e.g. a local tag carrying two StashDB stash_ids, both present in this
      batch): (None, 'stash_id' | 'name', True). This is not "no match" -
      creating a new tag for it would duplicate a tag that's already been
      resolved.
    - No candidate at all: (None, None, False)
    """
    if tag.stash_id:
        candidate = existing_tags_by_stash_id.get(tag.stash_id)
        if candidate is not None:
            if candidate['id'] in claimed_ids:
                return None, 'stash_id', True
            return candidate, 'stash_id', False

    if tag.name:
        candidate = existing_tags_by_name.get(tag.name.lower())
        if candidate is not None:
            if candidate['id'] in claimed_ids:
                return None, 'name', True
            return candidate, 'name', False

    return None, None, False


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
    """Transfer tags: resolve each StashDB tag to exactly one local match, then create/update.

    Each StashDB tag is resolved to at most one local tag - tried by
    stash_id first, then by name - so a single local tag can never be
    matched twice in the same run and never gets two conflicting update
    entries. A tag with no local match is queued for creation.

    Returns:
        Dictionary with transfer statistics (created, updated, skipped, failed)
    """
    log.info(f"Starting transfer of {len(tags)} tags to Stash")

    existing_tags_by_name, existing_tags_by_stash_id = client.find_existing_tags_with_data()
    log.info(f"Found {len(existing_tags_by_name)} existing tags in Stash")

    claimed_ids: set = set()
    tags_to_update = []
    new_tags = []
    matched_count = 0
    skipped_tags = 0
    failed_tags = 0

    log.info("Resolving each StashDB tag to its local match...")
    for tag in tags:
        existing_tag, match_source, already_claimed = _resolve_local_match(
            tag, existing_tags_by_stash_id, existing_tags_by_name, claimed_ids,
        )

        if existing_tag is None:
            if already_claimed:
                log.debug(f"  '{tag.name}' resolves to a local tag already handled this run via {match_source}")
            elif tag.name:
                new_tags.append(tag)
            continue

        if match_source == 'stash_id' and (not tag.name or not tag.name.strip()):
            log.warning(f"Tag with stash_id {tag.stash_id!r} has no name - skipping to prevent invalid update")
            skipped_tags += 1
            continue

        claimed_ids.add(existing_tag['id'])

        if _is_tag_out_of_sync(tag, existing_tag, config.ignored_aliases):
            merged_tag = _merge_tag_data(tag, existing_tag, config.ignored_aliases)

            conflicts = _has_alias_conflicts(
                merged_tag, existing_tags_by_name, config.ignored_aliases, own_tag_id=existing_tag['id'],
            )
            if conflicts:
                log.warning(f"Cannot update '{tag.name}' - aliases {conflicts} already exist as tag names")
                failed_tags += 1
            else:
                tags_to_update.append(
                    (existing_tag['id'], merged_tag, existing_tag.get('stash_ids', []), tag.stash_id)
                )
                log.debug(f"  Matched '{tag.name}' via {match_source} - needs update")
                matched_count += 1
        else:
            log.debug(f"  Matched '{tag.name}' via {match_source} - in sync")

    log.info(f"Resolved {matched_count} tags to update by stash_id/name")

    created_count = 0
    create_failed_count = 0
    log.info(f"Creating {len(new_tags)} new tags")
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
