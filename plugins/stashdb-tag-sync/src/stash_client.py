"""Local Stash client wrapping StashInterface for tag operations."""
import logging
from typing import Dict, List, Tuple

from stashapi.stashapp import StashInterface

from models import Tag
from stash_graphql_mutations import UPDATE_TAG_MUTATION

logger = logging.getLogger(__name__)

TAG_FRAGMENT = "id name description aliases stash_ids { endpoint stash_id }"


class StashClient:
    """Wrapper around StashInterface providing tag operations for the sync plugin."""

    def __init__(self, stash: StashInterface):
        """Initialise StashClient with a connected StashInterface instance."""
        self.stash = stash

    def find_existing_tags_with_data(self) -> Tuple[Dict[str, dict], Dict[str, dict]]:
        """Find all existing tags with full data, returns ({name: tag_data}, {stash_id: tag_data})."""
        try:
            tags = self.stash.find_tags(fragment=TAG_FRAGMENT)
        except Exception as e:
            logger.error(f"Failed to find existing tags with data: {e}")
            return {}, {}

        tag_map: Dict[str, dict] = {}
        stash_id_map: Dict[str, dict] = {}

        for tag in tags:
            name = tag.get('name')
            if not name:
                continue
            tag_map[name.lower()] = tag

            for stash_id_entry in tag.get('stash_ids') or []:
                stash_id = stash_id_entry.get('stash_id')
                if stash_id:
                    stash_id_map[stash_id] = tag

        return tag_map, stash_id_map

    def create_tags_batch(self, tags: List[Tag]) -> Dict[str, str]:
        """Create multiple tags, returns {lowercase_name: tag_id}."""
        if not tags:
            return {}

        created_tags: Dict[str, str] = {}

        for tag in tags:
            if not tag.name or not tag.name.strip():
                logger.warning("Skipping tag with empty name")
                continue

            tag_input = {'name': tag.name}
            if tag.description:
                tag_input['description'] = tag.description
            if tag.aliases:
                tag_input['aliases'] = tag.aliases

            try:
                created = self.stash.create_tag(tag_input)
            except Exception as e:
                logger.error(f"Failed to create tag '{tag.name}': {e}")
                continue

            if created and created.get('id'):
                created_tags[tag.name.lower()] = created['id']
                logger.info(f"Created tag '{tag.name}' with ID {created['id']}")
            else:
                logger.warning(f"Created tag '{tag.name}' but no ID returned")

        return created_tags

    def update_tags_batch(self, tags_with_ids: List[Tuple]) -> int:
        """Update multiple tags, returns count of successful updates.

        Each tag's name/description/aliases and (if a new one needs adding)
        stash_ids are sent together in a single tagUpdate mutation.

        Args:
            tags_with_ids: List of (tag_id, tag, existing_stash_ids, stash_id) tuples
                - tag_id: Stash tag ID
                - tag: Tag object with name, description, aliases
                - existing_stash_ids: List of existing stash_id dicts
                - stash_id: StashDB ID to add (if not already present)
        """
        if not tags_with_ids:
            return 0

        updated_count = 0

        for tag_id, tag, existing_stash_ids, stash_id in tags_with_ids:
            tag_update = {'id': tag_id, 'name': tag.name}
            if tag.description:
                tag_update['description'] = tag.description
            if tag.aliases:
                tag_update['aliases'] = tag.aliases

            stash_id_added = False
            if stash_id:
                existing_stash_id_set = {item.get('stash_id') for item in (existing_stash_ids or [])}
                if stash_id not in existing_stash_id_set:
                    tag_update['stash_ids'] = list(existing_stash_ids or []) + [{
                        'endpoint': 'https://stashdb.org/graphql',
                        'stash_id': stash_id,
                    }]
                    stash_id_added = True

            try:
                result = self.stash.call_GQL(UPDATE_TAG_MUTATION, {'input': tag_update})
            except Exception as e:
                logger.error(f"Failed to update tag '{tag.name}' (ID: {tag_id}): {e}")
                continue

            if not result or not result.get('tagUpdate'):
                logger.warning(f"Update returned no result for tag '{tag.name}' (ID: {tag_id})")
                continue

            updated_count += 1
            logger.info(f"Updated tag '{tag.name}' (ID: {tag_id})")
            if stash_id_added:
                logger.info(f"Added StashDB ID {stash_id} to tag '{tag.name}'")

        logger.info(f"Successfully updated {updated_count} tags")
        return updated_count
