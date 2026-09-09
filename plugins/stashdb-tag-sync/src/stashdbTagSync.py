#!/usr/bin/env python3
"""Stash plugin entry point for StashDB tag synchroniser."""
import os
import sys
import json
from typing import Dict, Any

import stashapi.log as log

try:
    from stashapi.stashapp import StashInterface
    from graphql_client import StashDBClient
    from stash_client import StashClient
    from core.tag_transfer import transfer_tags_graphql
    from models import Config
except ImportError as e:
    # If imports fail, output error so Stash can display it
    log.error(f"Import error: {str(e)}")
    sys.exit(1)


def find_stashdb_box(stash: StashInterface) -> tuple[str, str]:
    """Find the configured StashDB stash-box in Stash's stash-box settings.

    Args:
        stash: Connected StashInterface instance

    Returns:
        Tuple of (api_key, endpoint). Returns ("", "") if none is configured.
    """
    try:
        boxes = stash.get_stashbox_connections()
    except Exception as e:
        log.error(f"Failed to fetch stash-box configuration: {e}")
        return ("", "")

    if not boxes:
        log.error("No stash boxes configured in Stash")
        return ("", "")

    # Match by endpoint containing '://stashdb.org' (case insensitive)
    for box in boxes:
        name = box.get('name', '')
        api_key = box.get('api_key', '')
        endpoint = box.get('endpoint', '')
        if api_key and endpoint and '://stashdb.org' in endpoint.lower():
            log.info(f"Found StashDB configuration: {name}")
            return (api_key, endpoint)

    log.error("No StashDB box found in stash boxes. Configured boxes:")
    for box in boxes:
        log.error(f"  - {box.get('name', 'UNKNOWN')}")

    return ("", "")


def plugin_main(input_data: Dict[str, Any]) -> None:
    """Main plugin execution function.

    Args:
        input_data: JSON input from Stash containing server_connection and args
    """
    server_conn = input_data.get("server_connection", {})

    try:
        stash = StashInterface(server_conn)
    except Exception as e:
        log.error(f"Failed to connect to Stash: {e}")
        sys.exit(1)

    # Use defaults for other settings
    use_cache: bool = True
    ignored_aliases: list = []

    log.info("Fetching StashDB configuration from Stash...")
    stashdb_api_key, stashdb_endpoint = find_stashdb_box(stash)

    # Validate configuration
    if not stashdb_api_key:
        log.error("StashDB not configured in Stash. Configure it in Settings → Metadata Providers → StashDB")
        sys.exit(1)

    # Create configuration
    config = Config(
        stashdb_api_key=stashdb_api_key,
        ignored_aliases=ignored_aliases
    )

    # Fetch tags from StashDB
    log.info("Fetching tags from StashDB GraphQL API...")
    stashdb_client = StashDBClient(endpoint=stashdb_endpoint, api_key=stashdb_api_key)
    tags = stashdb_client.query_all_tags(use_cache=use_cache)
    log.info(f"Fetched {len(tags)} tags from StashDB")

    # Transfer tags to Stash
    log.info("Transferring tags to Stash...")
    stash_client = StashClient(stash)
    stats = transfer_tags_graphql(stash_client, tags, config)

    # Display transfer summary
    log.info("=" * 50)
    log.info("Transfer Summary")
    log.info("=" * 50)
    log.info(f"Created:  {stats['created']} new tags")
    log.info(f"Updated:  {stats['updated']} existing tags")
    if stats['failed'] > 0:
        log.info(f"Failed:   {stats['failed']} tags (update errors)")
    if stats['skipped'] > 0:
        log.info(f"Skipped:  {stats['skipped']} tags (invalid data)")
    log.info(f"Total:    {stats['total']} tags from StashDB")
    log.info("=" * 50)


def main() -> None:
    """Entry point for plugin execution.

    Sole error boundary for the plugin: catches everything from JSON
    input parsing through tag transfer, logs it via Stash's log protocol,
    and exits non-zero.
    """
    log.debug(f"Plugin starting - CWD: {os.getcwd()}, Python: {sys.executable}, Args: {sys.argv}")
    log.debug(f"stdin isatty: {sys.stdin.isatty()}")

    try:
        input_data = json.load(sys.stdin)
        plugin_main(input_data)

    except KeyboardInterrupt:
        log.info("Operation cancelled by user")
        sys.exit(130)
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON input: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Plugin error: {str(e)}")
        import traceback
        log.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == '__main__':
    main()
