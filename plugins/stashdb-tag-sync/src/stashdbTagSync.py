#!/usr/bin/env python3
"""Stash plugin entry point for StashDB tag synchroniser."""
import os
import sys
import json
import logging
from typing import Dict, Any

import stashapi.log as log
from stashapi.log import StashLogHandler

try:
    from stashapi.stashapp import StashInterface
    from graphql_client import StashDBClient
    from stash_client import StashClient, TagFetchError
    from core.tag_transfer import transfer_tags_graphql
    from models import Config
except ImportError as e:
    # If imports fail, output error so Stash can display it
    log.error(f"Import error: {str(e)}")
    sys.exit(1)


# stdlib loggers used by the modules this bridge targets - kept explicit rather than
# bridging root wholesale, so third-party loggers (e.g. requests/urllib3, used by
# graphql_client) don't also start emitting DEBUG noise into Stash's plugin log.
_BRIDGED_LOGGER_NAMES = ("stash_client", "graphql_client", "core.tag_transfer")


def configure_logging(stream=None) -> None:
    """Bridge stdlib `logging` (used by tag_transfer/stash_client/graphql_client) into
    stashapi.log's wire protocol, so their records reach Stash's plugin log UI instead
    of falling through to Python's default stderr handler or being dropped below WARNING.

    `stream` is exposed only so tests can point the handler at an in-memory buffer instead
    of `StashLogHandler`'s early-bound default (its `stream=sys.stderr` default argument is
    resolved once, at import time, so it can't be swapped later via capsys/capfd).
    """
    root = logging.getLogger()
    if not any(isinstance(h, StashLogHandler) for h in root.handlers):
        handler = StashLogHandler(stream) if stream is not None else StashLogHandler()
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        root.addHandler(handler)

    # stashapi.log's own 'StashLogger' logger already has its own StashLogHandler bound
    # directly to sys.stderr; it also has no dots, so it too propagates to root by default.
    # Without this, every stashapi.log.* call (used throughout this file) would now emit
    # twice - once via its own handler, once via the one just added to root.
    logging.getLogger("StashLogger").propagate = False

    for name in _BRIDGED_LOGGER_NAMES:
        logging.getLogger(name).setLevel(logging.DEBUG)


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

    stash_client = StashClient(stash)

    log.info("Fetching StashDB configuration from Stash...")
    stashdb_api_key, stashdb_endpoint = stash_client.find_stashdb_box()

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
    try:
        stats = transfer_tags_graphql(stash_client, tags, config)
    except TagFetchError as e:
        log.error(f"Aborting sync: {e}")
        log.error("No tags were created or updated - a fetch failure was not treated as an empty tag library")
        sys.exit(1)

    # Display transfer summary
    log.info("=" * 50)
    log.info("Transfer Summary")
    log.info("=" * 50)
    log.info(f"Created:  {stats['created']} new tags")
    log.info(f"Updated:  {stats['updated']} existing tags")
    if stats['failed'] > 0:
        log.info(f"Failed:   {stats['failed']} tags (create/update errors)")
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
    configure_logging()
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
