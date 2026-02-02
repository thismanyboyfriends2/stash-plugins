"""
GraphQL client for StashDB API.
Fetches tag information directly from the StashDB.org GraphQL endpoint.
"""
import logging
import requests
import time
import json
from pathlib import Path
from typing import List, Dict, Optional

from models import Tag

logger = logging.getLogger(__name__)


class StashDBClient:
    """Client for interacting with StashDB GraphQL API."""

    CACHE_EXPIRY_HOURS = 24
    CACHE_DIR = Path.home() / '.cache' / 'stash-tag-scraper'
    CACHE_FILE = CACHE_DIR / 'tags.json'

    def __init__(self, endpoint: str = "https://stashdb.org/graphql", api_key: str = None):
        """Initialize StashDB client with endpoint and API key."""
        self.endpoint = endpoint
        self.api_key = api_key

        if not self.api_key:
            raise ValueError(
                "StashDB API key is required. "
                "Configure StashDB in Stash Settings → Metadata Providers → StashDB."
            )

        self.headers = {
            'ApiKey': self.api_key,
            'Content-Type': 'application/json'
        }

    def _get_cache_file(self) -> Optional[dict]:
        """Load tags from cache if valid (not expired)."""
        if not self.CACHE_FILE.exists():
            return None

        try:
            with open(self.CACHE_FILE, 'r') as f:
                cache = json.load(f)

            # Check if cache is expired
            cache_time = cache.get('timestamp', 0)
            age_hours = (time.time() - cache_time) / 3600
            if age_hours > self.CACHE_EXPIRY_HOURS:
                logger.debug(f"Cache expired ({age_hours:.1f}h old)")
                return None

            logger.info(f"Using cached tags ({age_hours:.1f}h old)")
            return cache.get('tags', [])

        except Exception as e:
            logger.warning(f"Failed to read cache: {e}")
            return None

    def _save_cache_file(self, tags: List[dict]) -> None:
        """Save tags to cache with timestamp."""
        try:
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache = {
                'timestamp': time.time(),
                'tags': tags
            }
            with open(self.CACHE_FILE, 'w') as f:
                json.dump(cache, f)
            logger.debug(f"Saved {len(tags)} tags to cache")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    @staticmethod
    def clear_cache() -> None:
        """Remove cache file."""
        try:
            StashDBClient.CACHE_FILE.unlink()
            logger.info("Cache cleared")
        except FileNotFoundError:
            logger.debug("Cache file not found")

    def _execute_query(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute a GraphQL query with retry logic for transient errors."""
        payload = {'query': query}
        if variables:
            payload['variables'] = variables

        max_retries = 3
        base_delay = 1

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.endpoint,
                    json=payload,
                    headers=self.headers,
                    timeout=60
                )
                response.raise_for_status()

                result = response.json()

                if 'errors' in result:
                    error_messages = [err.get('message', str(err)) for err in result['errors']]
                    raise ValueError(f"GraphQL errors: {', '.join(error_messages)}")

                return result.get('data', {})

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Transient error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"Request failed after {max_retries} attempts: {e}")
                    raise
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                raise

    def query_all_tags(self, use_cache: bool = True) -> List[Tag]:
        """Fetch all tags from StashDB using pagination.

        Args:
            use_cache: If True, use cached tags if available and not expired.
        """
        # Check cache first
        if use_cache:
            cached_tag_dicts = self._get_cache_file()
            if cached_tag_dicts is not None:
                tags = [self._tag_from_graphql_dict(tag_dict) for tag_dict in cached_tag_dicts]
                logger.info(f"Loaded {len(tags)} tags from cache")
                return tags

        query = """
        query QueryTags($input: TagQueryInput!) {
            queryTags(input: $input) {
                count
                tags {
                    id
                    name
                    description
                    aliases
                    deleted
                    category {
                        id
                        name
                        group
                        description
                    }
                }
            }
        }
        """

        per_page: int = 100
        all_tags = []
        all_tag_dicts = []  # Store raw dicts for caching
        page = 1
        total_count = None

        logger.info("Fetching tags from StashDB")

        while True:
            variables = {
                'input': {
                    'page': page,
                    'per_page': per_page,
                    'sort': 'NAME',
                    'direction': 'ASC'
                }
            }

            try:
                data = self._execute_query(query, variables)

                if 'queryTags' not in data:
                    raise ValueError("Invalid StashDB response: missing 'queryTags' field")

                result = data['queryTags']

                if 'tags' not in result or 'count' not in result:
                    raise ValueError("Invalid StashDB response: missing 'tags' or 'count' in queryTags")

                tags = result['tags']
                if total_count is None:
                    total_count = result['count']
                    logger.debug(f"Fetching {total_count} tags total")

                # Filter out deleted tags and convert to Tag objects
                active_tags = [
                    self._tag_from_graphql(tag)
                    for tag in tags
                    if not tag.get('deleted', False)
                ]
                # Store non-deleted dicts for caching
                all_tag_dicts.extend([tag for tag in tags if not tag.get('deleted', False)])
                all_tags.extend(active_tags)
                logger.debug(f"Fetched {len(all_tags)} tags so far")

                # Check if we've fetched all tags (last page has fewer items)
                if len(tags) < per_page:
                    break

                page += 1

            except Exception as e:
                logger.error(f"Failed to fetch page {page}: {e}")
                raise

        logger.info(f"Successfully fetched {len(all_tags)} active tags")
        # Save to cache
        self._save_cache_file(all_tag_dicts)
        return all_tags

    def _tag_from_graphql(self, tag_data: Dict) -> Tag:
        """Convert GraphQL tag response to Tag object."""
        category_name = None
        if tag_data.get('category'):
            category_name = tag_data['category'].get('name')

        stash_id = tag_data['id']

        return Tag(
            name=tag_data['name'],
            description=tag_data.get('description') or '',
            stash_id=stash_id,
            aliases=tag_data.get('aliases', []),
            category=category_name,
            url=f"https://stashdb.org/tags/{stash_id}"
        )

    def _tag_from_graphql_dict(self, tag_data: Dict) -> Tag:
        """Convert cached or GraphQL tag dict to Tag object. Alias for _tag_from_graphql."""
        return self._tag_from_graphql(tag_data)

    def find_tag(self, name: Optional[str] = None, tag_id: Optional[str] = None) -> Optional[Tag]:
        """Find a tag by name or ID."""
        query = """
        query FindTag($name: String, $id: ID) {
            findTag(name: $name, id: $id) {
                id
                name
                description
                aliases
                deleted
                category {
                    id
                    name
                    group
                    description
                }
            }
        }
        """

        variables = {}
        if name:
            variables['name'] = name
        if tag_id:
            variables['id'] = tag_id

        if not variables:
            raise ValueError("Either name or tag_id must be provided")

        try:
            data = self._execute_query(query, variables)
            tag = data.get('findTag')

            if tag and not tag.get('deleted', False):
                return self._tag_from_graphql(tag)

            return None

        except Exception as e:
            logger.error(f"Failed to find tag: {e}")
            return None
