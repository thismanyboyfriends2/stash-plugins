"""Tests for stashdbTagSync plugin logic."""
from unittest.mock import Mock, patch

from stashdbTagSync import resolve_api_key


class TestResolveApiKey:
    def test_returns_api_key_from_connection_fragment_without_fetching(self):
        with patch("stashdbTagSync.StashInterface") as mock_stash_interface:
            result = resolve_api_key({"ApiKey": "fragment-key", "Host": "localhost"})

        assert result == "fragment-key"
        mock_stash_interface.assert_not_called()

    def test_falls_back_to_stash_configuration_when_fragment_has_no_key(self):
        mock_client = Mock()
        mock_client.get_configuration.return_value = {"general": {"apiKey": "configured-key"}}
        with patch("stashdbTagSync.StashInterface", return_value=mock_client) as mock_stash_interface:
            result = resolve_api_key({"Host": "localhost", "SessionCookie": {"Value": "abc"}})

        assert result == "configured-key"
        mock_stash_interface.assert_called_once_with({"Host": "localhost", "SessionCookie": {"Value": "abc"}})

    def test_returns_empty_string_when_stash_configuration_has_no_api_key(self):
        mock_client = Mock()
        mock_client.get_configuration.return_value = {"general": {"apiKey": ""}}
        with patch("stashdbTagSync.StashInterface", return_value=mock_client):
            result = resolve_api_key({"Host": "localhost"})

        assert result == ""

    def test_returns_empty_string_when_stash_configuration_missing_general_section(self):
        mock_client = Mock()
        mock_client.get_configuration.return_value = {}
        with patch("stashdbTagSync.StashInterface", return_value=mock_client):
            result = resolve_api_key({"Host": "localhost"})

        assert result == ""

    def test_returns_empty_string_when_stash_interface_raises(self):
        with patch("stashdbTagSync.StashInterface", side_effect=Exception("connection refused")):
            result = resolve_api_key({"Host": "localhost"})

        assert result == ""

    def test_never_logs_api_key_material(self):
        mock_client = Mock()
        mock_client.get_configuration.return_value = {"general": {"apiKey": "super-secret-key"}}
        with patch("stashdbTagSync.StashInterface", return_value=mock_client), \
             patch("stashdbTagSync.log") as mock_log:
            resolve_api_key({"Host": "localhost"})

        for mock_call in mock_log.mock_calls:
            for arg in list(mock_call.args) + list(mock_call.kwargs.values()):
                assert "super-secret-key" not in str(arg)
