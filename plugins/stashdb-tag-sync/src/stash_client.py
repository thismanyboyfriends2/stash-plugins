"""Stash GraphQL Client wrapper providing async interface for tag operations."""
import logging
from typing import Dict, List, Optional, Tuple

from stash_graphql_client import StashContext
from stash_graphql_client.types import Tag as GraphQLTag

from models import StashConnection, Tag
from stash_graphql_mutations import UPDATE_TAG_STASH_IDS_MUTATION

logger = logging.getLogger(__name__)


class StashClient:
    """Wrapper around stash-graphql-client providing clean async interface for tag operations."""

    def __init__(self, connection: Optional[StashConnection] = None):
        """Initialize StashClient with optional Stash connection details."""
        if connection is None:
            connection = StashConnection()

        self.connection = connection
        self.context = StashContext(conn=connection.to_connection_dict())
        self.graphql_client = None

    async def __aenter__(self):
        """Enter async context manager."""
        try:
            self.graphql_client = await self.context.__aenter__()
            return self
        except Exception as e:
            logger.error(f"Failed to initialise GraphQL client: {e}")
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        try:
            await self.context.__aexit__(exc_type, exc_val, exc_tb)
        except Exception as e:
            logger.error(f"Error during context exit: {e}")
            raise
        finally:
            self.graphql_client = None

    async def find_existing_tags(self) -> Dict[str, str]:
        """Find all existing tags in Stash, returns {lowercase_name: tag_id}."""
        try:
            if self.graphql_client is None:
                raise RuntimeError("GraphQL client not initialised. Did you forget async context manager?")

            # Fetch all tags from Stash
            result = await self.graphql_client.find_tags(
                filter_={"per_page": -1}  # Get all tags
            )

            # Convert to lowercase name -> ID mapping
            tag_map: Dict[str, str] = {}
            for tag in result.tags:
                if hasattr(tag, 'name') and hasattr(tag, 'id'):
                    tag_map[tag.name.lower()] = tag.id

            return tag_map

        except Exception as e:
            logger.error(f"Failed to find existing tags: {e}")
            return {}

    async def find_existing_tags_with_data(self):
        """Find all existing tags with full data, returns ({name: tag_data}, {stash_id: tag_data})."""
        try:
            if self.graphql_client is None:
                raise RuntimeError("GraphQL client not initialised. Did you forget async context manager?")

            # Fetch all tags from Stash
            result = await self.graphql_client.find_tags(
                filter_={"per_page": -1}  # Get all tags
            )

            # Convert to lowercase name -> tag data mapping, also build stash_id index
            tag_map: Dict[str, Dict] = {}
            stash_id_map: Dict[str, Dict] = {}

            for tag in result.tags:
                if hasattr(tag, 'name') and hasattr(tag, 'id'):
                    tag_data = {
                        'id': tag.id,
                        'name': tag.name,
                        'description': getattr(tag, 'description', None),
                        'aliases': getattr(tag, 'aliases', []) or [],
                        'stash_ids': getattr(tag, 'stash_ids', []) or []
                    }
                    tag_map[tag.name.lower()] = tag_data

                    # Also index by stash_ids if they exist
                    stash_ids = getattr(tag, 'stash_ids', []) or []
                    for stash_id_obj in stash_ids:
                        if hasattr(stash_id_obj, 'stash_id') and stash_id_obj.stash_id:
                            stash_id_map[stash_id_obj.stash_id] = tag_data

            return tag_map, stash_id_map

        except Exception as e:
            logger.error(f"Failed to find existing tags with data: {e}")
            return {}, {}

    async def create_tags_batch(self, tags: List[Tag]) -> Dict[str, str]:
        """Create multiple tags, returns {lowercase_name: tag_id}."""
        try:
            if self.graphql_client is None:
                raise RuntimeError("GraphQL client not initialised. Did you forget async context manager?")

            if not tags:
                return {}

            created_tags: Dict[str, str] = {}

            for tag in tags:
                try:
                    if not tag.name or not tag.name.strip():
                        logger.warning(f"Skipping tag with empty name")
                        continue

                    graphql_tag = GraphQLTag(name=tag.name)

                    if tag.description:
                        graphql_tag.description = tag.description
                    if tag.aliases:
                        graphql_tag.aliases = tag.aliases

                    created = await self.graphql_client.create_tag(graphql_tag)

                    if hasattr(created, 'id') and created.id:
                        created_tags[tag.name.lower()] = created.id
                        logger.info(f"Created tag '{tag.name}' with ID {created.id}")
                    else:
                        logger.warning(f"Created tag '{tag.name}' but no ID returned")

                except Exception as e:
                    logger.error(f"Failed to create tag '{tag.name}': {e}")
                    continue

            return created_tags

        except Exception as e:
            logger.error(f"Failed in create_tags_batch: {e}")
            return {}

    async def bulk_update_tags(
        self,
        tag_ids: List[str],
        description: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        parent_ids: Optional[List[str]] = None,
        child_ids: Optional[List[str]] = None,
    ) -> bool:
        """Update multiple tags with the same properties."""
        try:
            if self.graphql_client is None:
                raise RuntimeError("GraphQL client not initialised. Did you forget async context manager?")

            if not tag_ids:
                logger.warning("No tag IDs provided for bulk update")
                return False

            # Call the GraphQL client's bulk update method
            await self.graphql_client.bulk_tag_update(
                ids=tag_ids,
                description=description,
                aliases=aliases,
                parent_ids=parent_ids,
                child_ids=child_ids,
            )

            logger.info(f"Successfully updated {len(tag_ids)} tags")
            return True

        except Exception as e:
            logger.error(f"Failed to bulk update tags: {e}")
            return False

    async def update_tag_stash_ids(self, tag_id: str, stash_id_dicts: list) -> bool:
        """Update only the stash_ids for a tag using raw GraphQL mutation.

        Args:
            tag_id: Stash tag ID
            stash_id_dicts: List of {'endpoint': '...', 'stash_id': '...'} dicts

        Returns:
            True if successful, False otherwise
        """
        try:
            if not stash_id_dicts or not tag_id:
                logger.debug(f"Skipping stash_ids update: empty dicts or tag_id")
                return False

            input_data = {
                'id': tag_id,
                'stash_ids': stash_id_dicts
            }

            logger.debug(f"Updating stash_ids for tag {tag_id} with data: {input_data}")
            result = await self.graphql_client.execute(UPDATE_TAG_STASH_IDS_MUTATION, {'input': input_data})

            if result is None:
                logger.warning(f"stash_ids update returned None for tag {tag_id}")
                return False

            if 'tagUpdate' in result:
                tag_update = result['tagUpdate']
                stored_stash_ids = tag_update.get('stash_ids', [])
                logger.debug(f"stash_ids update successful for tag {tag_id}")
                logger.debug(f"  Sent stash_ids: {stash_id_dicts}")
                logger.debug(f"  Returned stash_ids from mutation: {stored_stash_ids}")

                # Verify what we got back matches what we sent
                if stored_stash_ids != stash_id_dicts:
                    logger.warning(f"  WARNING: Returned stash_ids differ from sent data!")
                    logger.warning(f"    Expected: {stash_id_dicts}")
                    logger.warning(f"    Got: {stored_stash_ids}")

                # Query the tag to verify what's actually persisted in the database
                logger.debug(f"Querying tag {tag_id} to verify database persistence...")
                query_result = await self.graphql_client.find_tags(
                    filter_={'id': tag_id}
                )
                if query_result and query_result.tags:
                    queried_tag = query_result.tags[0]
                    if hasattr(queried_tag, 'stash_ids'):
                        logger.debug(f"  Database stash_ids: {queried_tag.stash_ids}")
                        for sid in queried_tag.stash_ids:
                            logger.debug(f"    - endpoint='{getattr(sid, 'endpoint', 'MISSING')}' stash_id='{getattr(sid, 'stash_id', 'MISSING')}'")

                return True
            else:
                logger.warning(f"stash_ids update missing 'tagUpdate' in response for tag {tag_id}: {result}")
                return False

        except Exception as e:
            logger.error(f"Exception updating stash_ids for tag {tag_id}: {e}")
            return False

    async def update_tags_batch(
        self,
        tags_with_ids: List[Tuple],
        progress: Optional[object] = None,
        task_id: Optional[int] = None
    ) -> int:
        """Update multiple tags individually with stash_ids, returns count of successful updates.

        Args:
            tags_with_ids: List of (tag_id, tag, existing_stash_ids, stash_id) tuples
                - tag_id: Stash tag ID
                - tag: Tag object with name, description, aliases
                - existing_stash_ids: List of existing stash_id dicts
                - stash_id: StashDB ID to add (if not already present)
        """
        try:
            if self.graphql_client is None:
                raise RuntimeError("GraphQL client not initialised. Did you forget async context manager?")

            if not tags_with_ids:
                return 0

            updated_count = 0

            # Suppress stash_graphql_client logs during progress bar to avoid interruptions
            graphql_logger = logging.getLogger('stash_graphql_client')
            original_level = graphql_logger.level if progress else None
            if progress:
                graphql_logger.setLevel(logging.CRITICAL)

            for idx, (tag_id, tag, existing_stash_ids, stash_id) in enumerate(tags_with_ids, 1):
                try:
                    graphql_tag = GraphQLTag.model_construct(id=tag_id)

                    graphql_tag.name = tag.name
                    if tag.description:
                        graphql_tag.description = tag.description
                    if tag.aliases:
                        graphql_tag.aliases = tag.aliases

                    result = await self.graphql_client.update_tag(graphql_tag)
                    if result:
                        updated_count += 1
                        if progress is None:
                            logger.info(f"Updated tag '{tag.name}' (ID: {tag_id})")

                        # Update stash_ids if we have a new one to add
                        if stash_id:
                            # Convert existing stash_ids to plain dicts (may be pydantic objects)
                            stash_id_dicts = []
                            if existing_stash_ids:
                                for item in existing_stash_ids:
                                    if isinstance(item, dict):
                                        stash_id_dicts.append(item)
                                    else:
                                        # Handle pydantic model
                                        stash_id_dicts.append({
                                            'endpoint': getattr(item, 'endpoint', ''),
                                            'stash_id': getattr(item, 'stash_id', '')
                                        })

                            # Check if this stash_id is already present
                            stash_id_set = {item.get('stash_id') for item in stash_id_dicts}
                            if stash_id not in stash_id_set:
                                stash_id_dicts.append({
                                    'endpoint': 'https://stashdb.org/graphql',
                                    'stash_id': stash_id
                                })
                                stash_ids_success = await self.update_tag_stash_ids(tag_id, stash_id_dicts)
                                if stash_ids_success:
                                    if progress is None:
                                        logger.info(f"Added StashDB ID {stash_id} to tag '{tag.name}'")
                                else:
                                    msg = f"Failed to add StashDB ID {stash_id} to tag '{tag.name}'"
                                    if progress is not None:
                                        progress.console.print(f"[yellow]Warning[/yellow] {msg}")
                                    else:
                                        logger.warning(msg)
                    else:
                        msg = f"Update returned no result for tag '{tag.name}' (ID: {tag_id})"
                        if progress is not None:
                            progress.console.print(f"[yellow]Warning[/yellow] {msg}")
                        else:
                            logger.error(msg)

                    if progress is not None and task_id is not None:
                        progress.update(task_id, completed=idx)

                except Exception as e:
                    msg = f"Failed to update tag '{tag.name}' (ID: {tag_id}): {e}"
                    if progress is not None:
                        progress.console.print(f"[red]Error[/red] {msg}")
                    else:
                        logger.error(msg)
                        logger.debug(f"  Tag data: name={tag.name}, desc={tag.description}, aliases={tag.aliases}")

                    if progress is not None and task_id is not None:
                        progress.update(task_id, completed=idx)
                    continue

            logger.info(f"Successfully updated {updated_count} tags")
            return updated_count

        except Exception as e:
            logger.error(f"Failed in update_tags_batch: {e}")
            return 0
        finally:
            # Restore original log level
            if progress and original_level is not None:
                graphql_logger = logging.getLogger('stash_graphql_client')
                graphql_logger.setLevel(original_level)
