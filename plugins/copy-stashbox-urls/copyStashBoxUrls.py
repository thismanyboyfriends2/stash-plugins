#!/usr/bin/env python3

import sys
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

try:
    from stashapi.stashapp import StashInterface
    import stashapi.log as log
except ImportError:
    print("Error: stashapi library not found. Please ensure Stash is properly installed.", file=sys.stderr)
    sys.exit(1)


class StashBoxURLProcessor(ABC):
    """Base class for processing StashBox URLs and adding them to Stash entities."""

    def __init__(self, stash: StashInterface):
        """
        Initialize the processor with a Stash interface.

        Args:
            stash: StashInterface instance for API communication
        """
        self.stash = stash
        self.processed_count = 0
        self.updated_count = 0
        self.skipped_count = 0
        self.error_count = 0

    def construct_stashbox_url(self, endpoint: str, stash_id: str, entity_type: str) -> str:
        """
        Construct a StashBox URL from endpoint and stash_id.

        Args:
            endpoint: GraphQL endpoint (e.g., "https://stashdb.org/graphql")
            stash_id: Entity ID in StashBox (e.g., UUID)
            entity_type: Type of entity ("scenes" or "performers")

        Returns:
            Complete StashBox URL (e.g., "https://stashdb.org/scenes/abc-123")
        """
        if not endpoint or not stash_id:
            log.warning(f"Invalid endpoint or stash_id: endpoint={endpoint}, stash_id={stash_id}")
            return None

        try:
            # Remove /graphql suffix if present
            base_url = endpoint.replace("/graphql", "").rstrip("/")
            url = f"{base_url}/{entity_type}/{stash_id}"
            return url
        except Exception as e:
            log.error(f"Error constructing StashBox URL: {str(e)}")
            return None

    def extract_urls_from_stashids(self, stash_ids: List[Dict[str, str]], entity_type: str) -> List[str]:
        """
        Extract StashBox URLs from a list of stash_id objects.

        Args:
            stash_ids: List of {"endpoint": "...", "stash_id": "..."} dicts
            entity_type: Type of entity ("scenes" or "performers")

        Returns:
            List of constructed StashBox URLs
        """
        urls = []

        if not stash_ids:
            return urls

        for stash_id_obj in stash_ids:
            endpoint = stash_id_obj.get("endpoint")
            stash_id = stash_id_obj.get("stash_id")

            url = self.construct_stashbox_url(endpoint, stash_id, entity_type)
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

    @abstractmethod
    def process_all(self) -> None:
        """Process all entities. Must be implemented by subclasses."""
        pass


class SceneProcessor(StashBoxURLProcessor):
    """Processor for adding StashBox URLs to Stash scenes."""

    def __init__(self, stash: StashInterface):
        """Initialize with Stash interface."""
        super().__init__(stash)
        self.total_scenes_with_stashids = 0

    def process_all(self) -> None:
        """
        Main batch job: Query scenes with StashIDs (filtered server-side) and add StashBox URLs.
        """
        log.info("Starting StashBox URL processing for scenes...")

        try:
            # Get total count of scenes with StashIDs
            total_with_stashids = self.get_scene_count_with_stashids()
            log.info(f"Found {total_with_stashids} scenes with StashIDs")

            if total_with_stashids == 0:
                log.info("No scenes with StashIDs found.")
                return

            # Process in batches (10000 scenes per request for maximum efficiency)
            per_page = 10000
            page = 1

            while self.processed_count < total_with_stashids:
                try:
                    scenes = self.query_scenes_with_stashids(page, per_page)

                    if not scenes:
                        break

                    for scene in scenes:
                        self.process_scene(scene)

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
                f"Complete! Processed {summary['processed']} scenes, "
                f"updated {summary['updated']}, skipped {summary['skipped']}, "
                f"errors {summary['errors']}"
            )

        except Exception as e:
            log.error(f"Fatal error during scene processing: {str(e)}")
            self.error_count += 1

    def get_scene_count_with_stashids(self) -> int:
        """
        Get the total count of scenes with StashIDs using GraphQL filter.

        Returns:
            Total count of scenes with StashIDs
        """
        query = """
            query FindScenes($scene_filter: SceneFilterType) {
                findScenes(scene_filter: $scene_filter) {
                    count
                }
            }
        """

        variables = {
            "scene_filter": {
                "stash_id_endpoint": {
                    "modifier": "NOT_NULL"
                }
            }
        }

        try:
            result = self.stash.callGQL(query, variables)

            if result:
                count = result.get("findScenes", {}).get("count", 0)
                log.info(f"Scenes with StashIDs count: {count}")
                return count

            return 0
        except Exception as e:
            log.error(f"Error getting scene count with stashids: {str(e)}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return 0

    def query_scenes_with_stashids(self, page: int, per_page: int) -> List[Dict[str, Any]]:
        """
        Query scenes that have StashIDs attached using GraphQL filter.

        Args:
            page: Page number (1-indexed)
            per_page: Results per page

        Returns:
            List of scene objects with id, urls, and stash_ids
        """
        query = """
            query FindScenes($scene_filter: SceneFilterType, $filter: FindFilterType) {
                findScenes(scene_filter: $scene_filter, filter: $filter) {
                    scenes {
                        id
                        urls
                        stash_ids {
                            endpoint
                            stash_id
                        }
                    }
                }
            }
        """

        variables = {
            "scene_filter": {
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
                scenes = result.get("findScenes", {}).get("scenes", [])
                log.info(f"Found {len(scenes)} scenes with StashIDs on page {page}")
                return scenes if scenes else []

            return []
        except Exception as e:
            log.error(f"Error querying scenes on page {page}: {str(e)}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            raise

    def update_scene_urls(self, scene_id: str, urls: List[str]) -> None:
        """
        Update a scene's URLs using a custom GraphQL mutation.

        Args:
            scene_id: ID of the scene to update
            urls: List of URLs to set
        """
        mutation = """
            mutation SceneUpdate($input: SceneUpdateInput!) {
                sceneUpdate(input: $input) {
                    id
                }
            }
        """

        variables = {
            "input": {
                "id": scene_id,
                "urls": urls
            }
        }

        try:
            self.stash.callGQL(mutation, variables)
        except Exception as e:
            log.error(f"Error updating scene {scene_id} URLs: {str(e)}")
            raise

    def process_scene(self, scene: Dict[str, Any]) -> None:
        """
        Process a single scene: extract StashBox URLs and add them to the scene.

        Args:
            scene: Scene object from Stash API
        """
        self.processed_count += 1

        try:
            scene_id = scene.get("id")
            stash_ids = scene.get("stash_ids", [])
            existing_urls = scene.get("urls", [])

            if not scene_id:
                log.warning("Scene missing ID")
                self.skipped_count += 1
                return

            if not stash_ids:
                log.debug(f"Scene {scene_id} has no StashIDs")
                self.skipped_count += 1
                return

            # Extract URLs from StashIDs
            new_urls = self.extract_urls_from_stashids(stash_ids, "scenes")

            if not new_urls:
                log.debug(f"Scene {scene_id} has StashIDs but no valid URLs could be constructed")
                self.skipped_count += 1
                return

            # Merge with existing URLs
            merged_urls = self.merge_urls(existing_urls, new_urls)

            # Check if anything changed
            if merged_urls == existing_urls:
                log.debug(f"Scene {scene_id} already has all StashBox URLs")
                self.skipped_count += 1
                return

            # Update scene with merged URLs using custom GraphQL mutation
            self.update_scene_urls(scene_id, merged_urls)

            self.updated_count += 1
            log.debug(f"Updated scene {scene_id} with {len(new_urls)} StashBox URL(s)")

        except Exception as e:
            log.error(f"Error processing scene {scene.get('id', 'unknown')}: {str(e)}")
            self.error_count += 1


class PerformerProcessor(StashBoxURLProcessor):
    """Processor for adding StashBox URLs to Stash performers."""

    def __init__(self, stash: StashInterface):
        """Initialize with Stash interface."""
        super().__init__(stash)

    def process_all(self) -> None:
        """
        Main batch job: Query performers with StashIDs (filtered server-side) and add StashBox URLs.
        """
        log.info("Starting StashBox URL processing for performers...")

        try:
            # Get total count of performers with StashIDs
            total_with_stashids = self.get_performer_count_with_stashids()
            log.info(f"Found {total_with_stashids} performers with StashIDs")

            if total_with_stashids == 0:
                log.info("No performers with StashIDs found.")
                return

            # Process in batches (10000 performers per request for maximum efficiency)
            per_page = 10000
            page = 1

            while self.processed_count < total_with_stashids:
                try:
                    performers = self.query_performers_with_stashids(page, per_page)

                    if not performers:
                        break

                    for performer in performers:
                        self.process_performer(performer)

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
                f"Complete! Processed {summary['processed']} performers, "
                f"updated {summary['updated']}, skipped {summary['skipped']}, "
                f"errors {summary['errors']}"
            )

        except Exception as e:
            log.error(f"Fatal error during performer processing: {str(e)}")
            self.error_count += 1

    def get_performer_count_with_stashids(self) -> int:
        """
        Get the total count of performers with StashIDs using GraphQL filter.

        Returns:
            Total count of performers with StashIDs
        """
        query = """
            query FindPerformers($performer_filter: PerformerFilterType) {
                findPerformers(performer_filter: $performer_filter) {
                    count
                }
            }
        """

        variables = {
            "performer_filter": {
                "stash_id_endpoint": {
                    "modifier": "NOT_NULL"
                }
            }
        }

        try:
            result = self.stash.callGQL(query, variables)

            if result:
                count = result.get("findPerformers", {}).get("count", 0)
                log.info(f"Performers with StashIDs count: {count}")
                return count

            return 0
        except Exception as e:
            log.error(f"Error getting performer count with stashids: {str(e)}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return 0

    def query_performers_with_stashids(self, page: int, per_page: int) -> List[Dict[str, Any]]:
        """
        Query performers that have StashIDs attached using GraphQL filter.

        Args:
            page: Page number (1-indexed)
            per_page: Results per page

        Returns:
            List of performer objects with id, urls, and stash_ids
        """
        query = """
            query FindPerformers($performer_filter: PerformerFilterType, $filter: FindFilterType) {
                findPerformers(performer_filter: $performer_filter, filter: $filter) {
                    performers {
                        id
                        urls
                        stash_ids {
                            endpoint
                            stash_id
                        }
                    }
                }
            }
        """

        variables = {
            "performer_filter": {
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
                performers = result.get("findPerformers", {}).get("performers", [])
                log.info(f"Found {len(performers)} performers with StashIDs on page {page}")
                return performers if performers else []

            return []
        except Exception as e:
            log.error(f"Error querying performers on page {page}: {str(e)}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            raise

    def update_performer_urls(self, performer_id: str, urls: List[str]) -> None:
        """
        Update a performer's URLs using a custom GraphQL mutation.

        Args:
            performer_id: ID of the performer to update
            urls: List of URLs to set
        """
        mutation = """
            mutation PerformerUpdate($input: PerformerUpdateInput!) {
                performerUpdate(input: $input) {
                    id
                }
            }
        """

        variables = {
            "input": {
                "id": performer_id,
                "urls": urls
            }
        }

        try:
            self.stash.callGQL(mutation, variables)
        except Exception as e:
            log.error(f"Error updating performer {performer_id} URLs: {str(e)}")
            raise

    def process_performer(self, performer: Dict[str, Any]) -> None:
        """
        Process a single performer: extract StashBox URLs and add them to the performer.

        Args:
            performer: Performer object from Stash API
        """
        self.processed_count += 1

        try:
            performer_id = performer.get("id")
            stash_ids = performer.get("stash_ids", [])
            existing_urls = performer.get("urls", [])

            if not performer_id:
                log.warning("Performer missing ID")
                self.skipped_count += 1
                return

            if not stash_ids:
                log.debug(f"Performer {performer_id} has no StashIDs")
                self.skipped_count += 1
                return

            # Extract URLs from StashIDs
            new_urls = self.extract_urls_from_stashids(stash_ids, "performers")

            if not new_urls:
                log.debug(f"Performer {performer_id} has StashIDs but no valid URLs could be constructed")
                self.skipped_count += 1
                return

            # Merge with existing URLs
            merged_urls = self.merge_urls(existing_urls, new_urls)

            # Check if anything changed
            if merged_urls == existing_urls:
                log.debug(f"Performer {performer_id} already has all StashBox URLs")
                self.skipped_count += 1
                return

            # Update performer with merged URLs using custom GraphQL mutation
            self.update_performer_urls(performer_id, merged_urls)

            self.updated_count += 1
            log.debug(f"Updated performer {performer_id} with {len(new_urls)} StashBox URL(s)")

        except Exception as e:
            log.error(f"Error processing performer {performer.get('id', 'unknown')}: {str(e)}")
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
            processor = SceneProcessor(stash)
            processor.process_all()
        elif mode == "process_performers":
            processor = PerformerProcessor(stash)
            processor.process_all()
        else:
            log.error(f"Unknown mode: {mode}")

    except json.JSONDecodeError as e:
        log.error(f"Failed to parse input JSON: {str(e)}")
    except Exception as e:
        log.error(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    main()
