"""Core tag transfer logic for plugin."""
import logging
from typing import List

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
        category=stashdb_tag.category,
        url=stashdb_tag.url
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


async def transfer_tags_graphql(
    client: StashClient,
    tags: List[Tag],
    config: Config
) -> dict:
    """Transfer tags via three-stage matching: stash_id, then name, then create new.

    Returns:
        Dictionary with transfer statistics (created, updated, skipped, failed)
    """
    log.info(f"Starting transfer of {len(tags)} tags to Stash")

    existing_tags_by_name, existing_tags_by_stash_id = await client.find_existing_tags_with_data()
    log.info(f"Found {len(existing_tags_by_name)} existing tags in Stash")

    matched_tags: set = set()
    tags_to_update = []
    skipped_tags = 0
    failed_tags = 0

    # Stage 1: Match by stash_id (most reliable)
    log.info("Stage 1: Matching tags by stash_id...")
    stage1_matches = 0
    for tag in tags:
        if tag.stash_id and tag.stash_id in existing_tags_by_stash_id:
            if not tag.name or not tag.name.strip():
                log.warning(f"Tag with stash_id {tag.stash_id} has no name - skipping to prevent invalid update")
                skipped_tags += 1
                continue

            existing_tag = existing_tags_by_stash_id[tag.stash_id]
            if _is_tag_out_of_sync(tag, existing_tag, config.ignored_aliases):
                merged_tag = _merge_tag_data(tag, existing_tag, config.ignored_aliases)

                # Check for alias conflicts before updating
                conflicts = _has_alias_conflicts(merged_tag, existing_tags_by_name, config.ignored_aliases)
                if conflicts:
                    log.warning(f"Cannot update '{tag.name}' - aliases {conflicts} already exist as tag names")
                    failed_tags += 1
                else:
                    tags_to_update.append((existing_tag['id'], merged_tag, existing_tag.get('stash_ids', []), tag.stash_id))
                    log.debug(f"  Matched '{tag.name}' by stash_id {tag.stash_id} - needs update")
                    stage1_matches += 1
            else:
                log.debug(f"  Matched '{tag.name}' by stash_id {tag.stash_id} - in sync")
            matched_tags.add(tag.name.lower())

    log.info(f"Stage 1: Found {stage1_matches} tags to update by stash_id")

    # Stage 2: Match remaining tags by name and description/aliases (case-insensitive)
    log.info("Stage 2: Matching remaining tags by name...")
    stage2_matches = 0
    for tag in tags:
        if tag.name and tag.name.lower() not in matched_tags:
            if tag.name.lower() in existing_tags_by_name:
                existing_tag = existing_tags_by_name[tag.name.lower()]
                if _is_tag_out_of_sync(tag, existing_tag, config.ignored_aliases):
                    merged_tag = _merge_tag_data(tag, existing_tag, config.ignored_aliases)

                    # Check for alias conflicts before updating
                    conflicts = _has_alias_conflicts(merged_tag, existing_tags_by_name, config.ignored_aliases)
                    if conflicts:
                        log.warning(f"Cannot update '{tag.name}' - aliases {conflicts} already exist as tag names")
                        failed_tags += 1
                    else:
                        tags_to_update.append((existing_tag['id'], merged_tag, existing_tag.get('stash_ids', []), tag.stash_id))
                        log.debug(f"  Matched '{tag.name}' by name - needs update")
                        stage2_matches += 1
                else:
                    log.debug(f"  Matched '{tag.name}' by name - in sync")
                matched_tags.add(tag.name.lower())

    log.info(f"Stage 2: Found {stage2_matches} tags to update by name")

    new_tags = [
        tag for tag in tags
        if tag.name and tag.name.lower() not in matched_tags
    ]

    created_count = 0
    log.info(f"Stage 3: Creating {len(new_tags)} new tags")
    if new_tags:
        # Idempotency check: warn if any new tag names already exist (shouldn't happen, but safety check)
        for tag in new_tags:
            if tag.name.lower() in existing_tags_by_name:
                log.warning(f"Tag '{tag.name}' already exists but wasn't matched - skipping to prevent duplicate")
                new_tags.remove(tag)

        if new_tags:
            created_ids = await client.create_tags_batch(new_tags)
            created_count = len(created_ids)
            log.info(f"Successfully created {created_count} new tags")
        else:
            log.info("All new tags already exist")
    else:
        log.info("No new tags to create")

    updated_count = 0
    update_failed_count = 0
    if tags_to_update:
        log.info(f"Updating {len(tags_to_update)} matched tags...")
        updated_count = await client.update_tags_batch(tags_to_update, progress=None, task_id=None)
        update_failed_count = len(tags_to_update) - updated_count

        if updated_count == len(tags_to_update):
            log.info(f"Successfully updated {updated_count} tags")
        else:
            log.warning(f"Updated {updated_count} of {len(tags_to_update)} tags ({update_failed_count} failed)")
    else:
        log.info("No tags to update")

    log.info("Tag transfer completed successfully")

    # Total failed = tags with alias conflicts + tags that failed to update
    total_failed = failed_tags + update_failed_count

    return {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_tags,
        "failed": total_failed,
        "total": len(tags)
    }
