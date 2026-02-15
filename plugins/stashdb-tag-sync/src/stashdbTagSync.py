#!/usr/bin/env python3
"""Stash plugin entry point for StashDB tag synchroniser."""
import sys
import json
import asyncio
import logging
from typing import Dict, Any

import stashapi.log as log

# Silence noisy stash_graphql_client logging
logging.getLogger('stash_graphql_client').setLevel(logging.CRITICAL)

try:
    from graphql_client import StashDBClient
    from stash_client import StashClient
    from core.tag_transfer import transfer_tags_graphql
    from models import Config, StashConnection
except ImportError as e:
    # If imports fail, output error so Stash can display it
    log.error(f"Import error: {str(e)}")
    sys.exit(1)


async def fetch_stashdb_config(stash_client: StashClient) -> tuple[str, str]:
    """Fetch StashDB configuration from Stash's configuration.

    Queries Stash's general configuration to get the StashDB API key and endpoint
    that are already configured in Stash.

    Args:
        stash_client: Connected StashClient instance

    Returns:
        Tuple of (api_key, endpoint). Returns ("", "") if unable to fetch.
    """
    try:
        result = await stash_client.graphql_client.get_configuration()

        if not hasattr(result, 'general') or not result.general:
            log.error("No general configuration found in Stash")
            return ("", "")

        general = result.general

        if not hasattr(general, 'stash_boxes') or not general.stash_boxes:
            log.error("No stash boxes configured in Stash")
            return ("", "")

        # Find StashDB entry
        for box in general.stash_boxes:
            if not isinstance(box, dict):
                continue

            name = box.get('name', '')
            api_key = box.get('api_key', '')
            endpoint = box.get('endpoint', '')

            # Match by endpoint containing '://stashdb.org' (case insensitive)
            if api_key and endpoint and '://stashdb.org' in endpoint.lower():
                log.info(f"Found StashDB configuration: {name}")
                return (api_key, endpoint)

        log.error("No StashDB box found in stash boxes. Configured boxes:")
        for box in general.stash_boxes:
            if isinstance(box, dict):
                log.error(f"  - {box.get('name', 'UNKNOWN')}")

    except Exception as e:
        log.error(f"Failed to fetch StashDB config: {e}")
        import traceback
        log.error(f"Traceback: {traceback.format_exc()}")

    return ("", "")


async def plugin_main(input_data: Dict[str, Any]) -> None:
    """Main plugin execution function.

    Args:
        input_data: JSON input from Stash containing server_connection and args
    """
    # Extract server connection information
    server_conn = input_data.get("server_connection", {})

    # Create Stash connection to query configuration
    stash_conn = StashConnection(
        scheme=server_conn.get("Scheme", "http"),
        host=server_conn.get("Host", "localhost"),
        port=server_conn.get("Port", 9999),
        api_key=server_conn.get("ApiKey")
    )

    # Use defaults for other settings
    use_cache: bool = True
    ignored_aliases: list = []

    try:
        # Fetch StashDB configuration from Stash (no auth needed for config queries)
        log.info("Fetching StashDB configuration from Stash...")

        # Create connection with blank API key for initial config fetch
        # (no API key needed to query Stash configuration)
        config_conn = StashConnection(
            scheme=stash_conn.scheme,
            host=stash_conn.host,
            port=stash_conn.port,
            api_key=""
        )

        # Temporarily suppress stash_graphql_client's noisy warnings during config fetch
        import os
        stderr_fd = os.dup(2)
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_fd, 2)
        try:
            async with StashClient(config_conn) as stash_client:
                stashdb_api_key, stashdb_endpoint = await fetch_stashdb_config(stash_client)
        finally:
            os.close(devnull_fd)
            os.dup2(stderr_fd, 2)
            os.close(stderr_fd)

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
        async with StashClient(stash_conn) as stash_client:
            stats = await transfer_tags_graphql(stash_client, tags, config)

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

    except KeyboardInterrupt:
        log.info("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        log.error(f"Operation failed: {str(e)}")
        import traceback
        log.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)


def main() -> None:
    """Entry point for plugin execution."""
    try:
        input_data = json.load(sys.stdin)
        asyncio.run(plugin_main(input_data))

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
