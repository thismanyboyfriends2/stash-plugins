#!/usr/bin/env python3

import sys
import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

try:
    from stashapi.stashapp import StashInterface
    import stashapi.log as log
except ImportError:
    print("Error: stashapi library not found. Please ensure Stash is properly installed.", file=sys.stderr)
    sys.exit(1)


@dataclass(frozen=True)
class EntityConfig:
    """Everything that differs between the scene and performer StashBox URL pipelines."""
    entity_type: str        # "scenes" or "performers" - used in the constructed StashBox URL path
    label: str              # "scene" or "performer" - singular, for logging
    filter_key: str         # "scene_filter" or "performer_filter"
    filter_type_name: str   # "SceneFilterType" or "PerformerFilterType"
    find_query_name: str    # "FindScenes" or "FindPerformers"
    find_field: str         # "findScenes" or "findPerformers"
    items_field: str        # "scenes" or "performers"
    update_mutation_name: str  # "SceneUpdate" or "PerformerUpdate"
    update_field: str       # "sceneUpdate" or "performerUpdate"


SCENE_CONFIG = EntityConfig(
    entity_type="scenes",
    label="scene",
    filter_key="scene_filter",
    filter_type_name="SceneFilterType",
    find_query_name="FindScenes",
    find_field="findScenes",
    items_field="scenes",
    update_mutation_name="SceneUpdate",
    update_field="sceneUpdate",
)

PERFORMER_CONFIG = EntityConfig(
    entity_type="performers",
    label="performer",
    filter_key="performer_filter",
    filter_type_name="PerformerFilterType",
    find_query_name="FindPerformers",
    find_field="findPerformers",
    items_field="performers",
    update_mutation_name="PerformerUpdate",
    update_field="performerUpdate",
)


class StashBoxURLProcessor:
    """Adds StashBox URLs to Stash scenes or performers, per the given EntityConfig."""

    def __init__(self, stash: StashInterface, config: EntityConfig):
        """
        Initialize the processor with a Stash interface and entity configuration.

        Args:
            stash: StashInterface instance for API communication
            config: EntityConfig describing which entity type to process
        """
        self.stash = stash
        self.config = config
        self.processed_count = 0
        self.updated_count = 0
        self.skipped_count = 0
        self.error_count = 0

    def construct_stashbox_url(self, endpoint: str, stash_id: str) -> Optional[str]:
        """
        Construct a StashBox URL from endpoint and stash_id.

        Args:
            endpoint: GraphQL endpoint (e.g., "https://stashdb.org/graphql")
            stash_id: Entity ID in StashBox (e.g., UUID)

        Returns:
            Complete StashBox URL (e.g., "https://stashdb.org/scenes/abc-123")
        """
        if not endpoint or not stash_id:
            log.warning(f"Invalid endpoint or stash_id: endpoint={endpoint}, stash_id={stash_id}")
            return None

        try:
            # Remove /graphql suffix if present
            base_url = endpoint.replace("/graphql", "").rstrip("/")
            return f"{base_url}/{self.config.entity_type}/{stash_id}"
        except Exception as e:
            log.error(f"Error constructing StashBox URL: {str(e)}")
            return None

    def extract_urls_from_stashids(self, stash_ids: List[Dict[str, str]]) -> List[str]:
        """
        Extract StashBox URLs from a list of stash_id objects.

        Args:
            stash_ids: List of {"endpoint": "...", "stash_id": "..."} dicts

        Returns:
            List of constructed StashBox URLs
        """
        urls = []

        if not stash_ids:
            return urls

        for stash_id_obj in stash_ids:
            endpoint = stash_id_obj.get("endpoint")
            stash_id = stash_id_obj.get("stash_id")

            url = self.construct_stashbox_url(endpoint, stash_id)
            if url:
                urls.append(url)

        return urls

    def merge_urls(self, existing_urls: Optional[List[str]], new_urls: List[str]) -> List[str]:
        """
        Merge existing URLs with new URLs, removing duplicates.

        Args:
            existing_urls: Current list of URLs (can be None or empty)
            new_urls: New URLs to add

        Returns:
            Combined list with duplicates removed
        """
        if existing_urls is None:
            existing_urls = []

        # Combine and deduplicate while preserving relative order
        # Keep existing URLs first, then add new URLs
        combined = existing_urls.copy()
        for url in new_urls:
            if url not in combined:
                combined.append(url)

        return combined

    def get_summary(self) -> Dict[str, int]:
        """Return processing summary statistics."""
        return {
            "processed": self.processed_count,
            "updated": self.updated_count,
            "skipped": self.skipped_count,
            "errors": self.error_count
        }

    def get_count_with_stashids(self) -> int:
        """
        Get the total count of entities with StashIDs using a GraphQL filter.

        Returns:
            Total count of entities with StashIDs
        """
        query = f"""
            query {self.config.find_query_name}(${self.config.filter_key}: {self.config.filter_type_name}) {{
                {self.config.find_field}({self.config.filter_key}: ${self.config.filter_key}) {{
                    count
                }}
            }}
        """

        variables = {
            self.config.filter_key: {
                "stash_id_endpoint": {
                    "modifier": "NOT_NULL"
                }
            }
        }

        try:
            result = self.stash.callGQL(query, variables)

            if result:
                count = result.get(self.config.find_field, {}).get("count", 0)
                log.info(f"{self.config.entity_type.capitalize()} with StashIDs count: {count}")
                return count

            return 0
        except Exception as e:
            log.error(f"Error getting {self.config.label} count with stashids: {str(e)}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return 0

    def query_page_with_stashids(self, page: int, per_page: int) -> List[Dict[str, Any]]:
        """
        Query a page of entities that have StashIDs attached using a GraphQL filter.

        Args:
            page: Page number (1-indexed)
            per_page: Results per page

        Returns:
            List of entity objects with id, urls, and stash_ids
        """
        query = f"""
            query {self.config.find_query_name}(${self.config.filter_key}: {self.config.filter_type_name}, $filter: FindFilterType) {{
                {self.config.find_field}({self.config.filter_key}: ${self.config.filter_key}, filter: $filter) {{
                    {self.config.items_field} {{
                        id
                        urls
                        stash_ids {{
                            endpoint
                            stash_id
                        }}
                    }}
                }}
            }}
        """

        variables = {
            self.config.filter_key: {
                "stash_id_endpoint": {
                    "modifier": "NOT_NULL"
                }
            },
            "filter": {
                "page": page,
                "per_page": per_page
            }
        }

        try:
            result = self.stash.callGQL(query, variables)

            if result:
                items = result.get(self.config.find_field, {}).get(self.config.items_field, [])
                log.info(f"Found {len(items)} {self.config.entity_type} with StashIDs on page {page}")
                return items if items else []

            return []
        except Exception as e:
            log.error(f"Error querying {self.config.entity_type} on page {page}: {str(e)}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            raise

    def update_entity_urls(self, entity_id: str, urls: List[str]) -> None:
        """
        Update an entity's URLs using a custom GraphQL mutation.

        Args:
            entity_id: ID of the scene or performer to update
            urls: List of URLs to set
        """
        mutation = f"""
            mutation {self.config.update_mutation_name}($input: {self.config.update_mutation_name}Input!) {{
                {self.config.update_field}(input: $input) {{
                    id
                }}
            }}
        """

        variables = {
            "input": {
                "id": entity_id,
                "urls": urls
            }
        }

        try:
            self.stash.callGQL(mutation, variables)
        except Exception as e:
            log.error(f"Error updating {self.config.label} {entity_id} URLs: {str(e)}")
            raise

    def process_entity(self, entity: Dict[str, Any]) -> None:
        """
        Process a single entity: extract StashBox URLs and add them to it.

        Args:
            entity: Scene or performer object from Stash API
        """
        self.processed_count += 1

        try:
            entity_id = entity.get("id")
            stash_ids = entity.get("stash_ids", [])
            existing_urls = entity.get("urls", [])

            if not entity_id:
                log.warning(f"{self.config.label.capitalize()} missing ID")
                self.skipped_count += 1
                return

            if not stash_ids:
                log.debug(f"{self.config.label.capitalize()} {entity_id} has no StashIDs")
                self.skipped_count += 1
                return

            # Extract URLs from StashIDs
            new_urls = self.extract_urls_from_stashids(stash_ids)

            if not new_urls:
                log.debug(f"{self.config.label.capitalize()} {entity_id} has StashIDs but no valid URLs could be constructed")
                self.skipped_count += 1
                return

            # Merge with existing URLs
            merged_urls = self.merge_urls(existing_urls, new_urls)

            # Check if anything changed
            if merged_urls == existing_urls:
                log.debug(f"{self.config.label.capitalize()} {entity_id} already has all StashBox URLs")
                self.skipped_count += 1
                return

            # Update entity with merged URLs using custom GraphQL mutation
            self.update_entity_urls(entity_id, merged_urls)

            self.updated_count += 1
            log.debug(f"Updated {self.config.label} {entity_id} with {len(new_urls)} StashBox URL(s)")

        except Exception as e:
            log.error(f"Error processing {self.config.label} {entity.get('id', 'unknown')}: {str(e)}")
            self.error_count += 1

    def process_all(self) -> None:
        """
        Main batch job: query entities with StashIDs (filtered server-side) and add StashBox URLs.
        """
        log.info(f"Starting StashBox URL processing for {self.config.entity_type}...")

        try:
            # Get total count of entities with StashIDs
            total_with_stashids = self.get_count_with_stashids()
            log.info(f"Found {total_with_stashids} {self.config.entity_type} with StashIDs")

            if total_with_stashids == 0:
                log.info(f"No {self.config.entity_type} with StashIDs found.")
                return

            # Process in batches (10000 per request for maximum efficiency)
            per_page = 10000
            page = 1

            while self.processed_count < total_with_stashids:
                try:
                    items = self.query_page_with_stashids(page, per_page)

                    if not items:
                        break

                    for item in items:
                        self.process_entity(item)

                    page += 1

                    # Update progress bar
                    log.progress(self.processed_count / total_with_stashids)

                except Exception as e:
                    log.error(f"Error processing batch on page {page}: {str(e)}")
                    self.error_count += 1
                    break

            # Print final summary
            summary = self.get_summary()
            log.info(
                f"Complete! Processed {summary['processed']} {self.config.entity_type}, "
                f"updated {summary['updated']}, skipped {summary['skipped']}, "
                f"errors {summary['errors']}"
            )

        except Exception as e:
            log.error(f"Fatal error during {self.config.label} processing: {str(e)}")
            self.error_count += 1


def main():
    """Main entry point for the plugin."""
    try:
        # Read input from Stash
        json_input = json.loads(sys.stdin.read())

        # Extract server connection and arguments
        server_connection = json_input.get("server_connection")
        args = json_input.get("args", {})
        mode = args.get("mode", "process_scenes")

        if not server_connection:
            log.error("No server connection provided")
            return

        # Initialize Stash interface
        stash = StashInterface(server_connection)

        # Route to appropriate handler
        if mode == "process_scenes":
            processor = StashBoxURLProcessor(stash, SCENE_CONFIG)
            processor.process_all()
        elif mode == "process_performers":
            processor = StashBoxURLProcessor(stash, PERFORMER_CONFIG)
            processor.process_all()
        else:
            log.error(f"Unknown mode: {mode}")

    except json.JSONDecodeError as e:
        log.error(f"Failed to parse input JSON: {str(e)}")
    except Exception as e:
        log.error(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    main()
