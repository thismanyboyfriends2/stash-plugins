"""Tests for the stdlib-logging -> stashapi.log bridge installed at plugin startup."""
import io
import logging

import pytest

import stashapi.log as stashapi_log
from stashapi.log import StashLogHandler
from stashdbTagSync import configure_logging


@pytest.fixture(autouse=True)
def _reset_logging_state():
    root = logging.getLogger()
    original_root_handlers = list(root.handlers)
    original_root_level = root.level
    stash_logger = logging.getLogger("StashLogger")
    original_stash_propagate = stash_logger.propagate
    original_module_levels = {
        name: logging.getLogger(name).level
        for name in ("stash_client", "graphql_client", "core.tag_transfer")
    }
    yield
    root.handlers = original_root_handlers
    root.setLevel(original_root_level)
    stash_logger.propagate = original_stash_propagate
    for name, level in original_module_levels.items():
        logging.getLogger(name).setLevel(level)


class TestConfigureLogging:
    def test_installs_a_stash_log_handler_on_the_root_logger(self):
        configure_logging()

        root = logging.getLogger()
        assert any(isinstance(h, StashLogHandler) for h in root.handlers)

    def test_bridged_module_loggers_allow_debug_records_through(self):
        configure_logging()

        for name in ("stash_client", "graphql_client", "core.tag_transfer"):
            assert logging.getLogger(name).getEffectiveLevel() <= logging.DEBUG

    def test_unrelated_third_party_loggers_are_not_dropped_to_debug(self):
        configure_logging()

        assert logging.getLogger("urllib3.connectionpool").getEffectiveLevel() == logging.WARNING

    def test_module_logger_record_reaches_the_bridge_handler(self):
        buf = io.StringIO()
        configure_logging(stream=buf)
        module_logger = logging.getLogger("stash_client")

        module_logger.info("Using cached tags")

        output = buf.getvalue()
        assert "Using cached tags" in output
        assert "\x01i\x02" in output

    def test_warning_and_error_records_are_bridged_not_left_to_default_stderr(self):
        buf = io.StringIO()
        configure_logging(stream=buf)
        module_logger = logging.getLogger("tag_transfer")

        module_logger.warning("alias conflict for tag X")
        module_logger.error("fetch failed")

        lines = [line for line in buf.getvalue().splitlines() if line]
        assert len(lines) == 2
        assert lines[0].startswith("\x01w\x02")
        assert lines[1].startswith("\x01e\x02")

    def test_calling_configure_logging_twice_does_not_duplicate_the_handler(self):
        buf = io.StringIO()
        configure_logging(stream=buf)
        configure_logging(stream=buf)
        module_logger = logging.getLogger("graphql_client")

        module_logger.info("Fetched 42 tags")

        assert buf.getvalue().count("Fetched 42 tags") == 1

    def test_stashapi_log_calls_are_not_duplicated_by_the_new_root_handler(self):
        buf = io.StringIO()
        configure_logging(stream=buf)

        stashapi_log.info("Fetching tags from StashDB GraphQL API...")

        assert buf.getvalue().count("Fetching tags from StashDB GraphQL API...") == 0
