"""Local Stash client wrapping StashInterface for tag operations."""
import logging
from typing import Dict, List, Optional, Tuple

from stashapi.stashapp import StashInterface

from models import Tag
from stash_graphql_mutations import CREATE_TAG_MUTATION, UPDATE_TAG_MUTATION

logger = logging.getLogger(__name__)

TAG_FRAGMENT = "id name description aliases stash_ids { endpoint stash_id }"


class TagFetchError(Exception):
    """Raised when fetching existing tags from Stash fails.

    Distinguishes a failed fetch from a genuinely empty tag library, so callers
    can abort the sync instead of treating the failure as "Stash has zero tags"
    and mass-creating every StashDB tag as a duplicate.
    """


class StashClient:
    """Wrapper around StashInterface providing tag operations for the sync plugin."""

    def __init__(self, stash: StashInterface):
        """Initialise StashClient with a connected StashInterface instance."""
        self.stash = stash

    def find_stashdb_box(self) -> Tuple[str, str]:
        """Find the configured StashDB stash-box in Stash's stash-box settings.

        Returns:
            Tuple of (api_key, endpoint). Returns ("", "") if none is configured.
        """
        try:
            boxes = self.stash.get_stashbox_connections()
        except Exception as e:
            logger.error(f"Failed to fetch stash-box configuration: {e}")
            return "", ""

        if not boxes:
            logger.error("No stash boxes configured in Stash")
            return "", ""

        # Match by endpoint containing '://stashdb.org' (case insensitive)
        for box in boxes:
            name = box.get('name', '')
            api_key = box.get('api_key', '')
            endpoint = box.get('endpoint', '')
            if api_key and endpoint and '://stashdb.org' in endpoint.lower():
                logger.info(f"Found StashDB configuration: {name}")
                return api_key, endpoint

        logger.error("No StashDB box found in stash boxes. Configured boxes:")
        for box in boxes:
            logger.error(f"  - {box.get('name', 'UNKNOWN')}")

        return "", ""

    def find_existing_tags_with_data(self) -> Tuple[Dict[str, dict], Dict[str, dict]]:
        """Find all existing tags with full data, returns ({name: tag_data}, {stash_id: tag_data})."""
        try:
            tags = self.stash.find_tags(fragment=TAG_FRAGMENT)
        except Exception as e:
            raise TagFetchError(f"Failed to fetch existing tags from Stash: {e}") from e

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

    def _call_mutation(self, query: str, mutation_input: dict, success_key: str, context: str) -> Optional[dict]:
        """Execute a GraphQL mutation, returning its success_key payload, or None on failure.

        Covers both failure shapes the same way: a network-level exception from call_GQL,
        and a GraphQL-level rejection (missing/falsy success_key in an otherwise-successful
        response, e.g. a validation error Stash reports without raising). `context` (e.g.
        "tag 'Foo' (ID: 1)") is folded into the log message so a batch of failures is still
        attributable to specific tags.
        """
        try:
            result = self.stash.call_GQL(query, {'input': mutation_input})
        except Exception as e:
            logger.error(f"Mutation failed for {context}: {e}")
            return None

        payload = result.get(success_key) if result else None
        if not payload:
            logger.warning(f"Mutation rejected for {context}: no '{success_key}' in response")
            return None

        return payload

    def create_tags_batch(self, tags: List[Tag]) -> Tuple[Dict[str, str], int]:
        """Create multiple tags, returns ({lowercase_name: tag_id}, failed_count).

        failed_count is tracked directly rather than derived from the returned dict's size,
        since two source tags whose names differ only by case collapse to one dict entry.
        """
        if not tags:
            return {}, 0

        created_tags: Dict[str, str] = {}
        failed_count = 0

        for tag in tags:
            if not tag.name or not tag.name.strip():
                logger.warning("Skipping tag with empty name")
                continue

            tag_input = {'name': tag.name}
            if tag.description:
                tag_input['description'] = tag.description
            if tag.aliases:
                tag_input['aliases'] = tag.aliases

            created = self._call_mutation(CREATE_TAG_MUTATION, tag_input, 'tagCreate', f"tag '{tag.name}'")
            if created and created.get('id'):
                created_tags[tag.name.lower()] = created['id']
                logger.info(f"Created tag '{tag.name}' with ID {created['id']}")
            else:
                failed_count += 1

        return created_tags, failed_count

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

            updated = self._call_mutation(
                UPDATE_TAG_MUTATION, tag_update, 'tagUpdate', f"tag '{tag.name}' (ID: {tag_id})"
            )
            if not updated:
                continue

            updated_count += 1
            logger.info(f"Updated tag '{tag.name}' (ID: {tag_id})")
            if stash_id_added:
                logger.info(f"Added StashDB ID {stash_id} to tag '{tag.name}'")

        logger.info(f"Successfully updated {updated_count} tags")
        return updated_count
