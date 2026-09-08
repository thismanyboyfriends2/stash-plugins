"""Local Stash client wrapping StashInterface for tag operations."""
import logging
from typing import Dict, List, Tuple

from stashapi.stashapp import StashInterface

from models import Tag
from stash_graphql_mutations import UPDATE_TAG_STASH_IDS_MUTATION

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

    def update_tag_stash_ids(self, tag_id: str, stash_id_dicts: list) -> bool:
        """Update only the stash_ids for a tag using a raw GraphQL mutation.

        Args:
            tag_id: Stash tag ID
            stash_id_dicts: List of {'endpoint': '...', 'stash_id': '...'} dicts

        Returns:
            True if successful, False otherwise
        """
        if not stash_id_dicts or not tag_id:
            logger.debug("Skipping stash_ids update: empty dicts or tag_id")
            return False

        input_data = {
            'id': tag_id,
            'stash_ids': stash_id_dicts,
        }

        try:
            result = self.stash.call_GQL(UPDATE_TAG_STASH_IDS_MUTATION, {'input': input_data})
        except Exception as e:
            logger.error(f"Exception updating stash_ids for tag {tag_id}: {e}")
            return False

        if not result or 'tagUpdate' not in result:
            logger.warning(f"stash_ids update missing 'tagUpdate' in response for tag {tag_id}: {result}")
            return False

        return True

    def update_tags_batch(self, tags_with_ids: List[Tuple]) -> int:
        """Update multiple tags individually with stash_ids, returns count of successful updates.

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

            try:
                self.stash.update_tag(tag_update)
            except Exception as e:
                logger.error(f"Failed to update tag '{tag.name}' (ID: {tag_id}): {e}")
                continue

            updated_count += 1
            logger.info(f"Updated tag '{tag.name}' (ID: {tag_id})")

            if stash_id:
                stash_id_dicts = list(existing_stash_ids or [])
                stash_id_set = {item.get('stash_id') for item in stash_id_dicts}
                if stash_id not in stash_id_set:
                    stash_id_dicts.append({
                        'endpoint': 'https://stashdb.org/graphql',
                        'stash_id': stash_id,
                    })
                    if self.update_tag_stash_ids(tag_id, stash_id_dicts):
                        logger.info(f"Added StashDB ID {stash_id} to tag '{tag.name}'")
                    else:
                        logger.warning(f"Failed to add StashDB ID {stash_id} to tag '{tag.name}'")

        logger.info(f"Successfully updated {updated_count} tags")
        return updated_count
