"""Tests for StashClient's tag-write failure detection."""
from unittest.mock import Mock

import pytest

from models import Tag
from stash_client import StashClient, TagFetchError


def _tag(name="Debut", description="", aliases=None):
    return Tag(name=name, description=description, stash_id="", aliases=aliases or [])


class TestCreateTagsBatch:
    def test_counts_successful_create(self):
        stash = Mock()
        stash.call_GQL.return_value = {'tagCreate': {'id': '1'}}
        client = StashClient(stash)

        created, failed_count = client.create_tags_batch([_tag()])

        assert created == {"debut": "1"}
        assert failed_count == 0

    def test_does_not_count_create_rejected_at_graphql_level(self):
        stash = Mock()
        stash.call_GQL.return_value = {'tagCreate': None}
        client = StashClient(stash)

        created, failed_count = client.create_tags_batch([_tag()])

        assert created == {}
        assert failed_count == 1

    def test_does_not_count_create_when_call_GQL_raises(self):
        stash = Mock()
        stash.call_GQL.side_effect = Exception("GRAPHQL_ERROR:['tagCreate'] name conflict")
        client = StashClient(stash)

        created, failed_count = client.create_tags_batch([_tag()])

        assert created == {}
        assert failed_count == 1

    def test_only_successful_creates_count_in_a_mixed_batch(self):
        stash = Mock()
        stash.call_GQL.side_effect = [
            {'tagCreate': {'id': '1'}},
            {'tagCreate': None},
            {'tagCreate': {'id': '3'}},
        ]
        client = StashClient(stash)

        created, failed_count = client.create_tags_batch([_tag("Alpha"), _tag("Beta"), _tag("Gamma")])

        assert created == {"alpha": "1", "gamma": "3"}
        assert failed_count == 1

    def test_case_variant_names_are_both_counted_as_successes_not_collapsed(self):
        stash = Mock()
        stash.call_GQL.side_effect = [
            {'tagCreate': {'id': '1'}},
            {'tagCreate': {'id': '2'}},
        ]
        client = StashClient(stash)

        created, failed_count = client.create_tags_batch([_tag("Foo"), _tag("foo")])

        assert failed_count == 0
        assert len(created) == 1  # dict collapses case-variant names to one entry...
        # ...which is exactly why failed_count is tracked separately, not derived from len(created)

    def test_sends_name_description_and_aliases_in_the_mutation_input(self):
        stash = Mock()
        stash.call_GQL.return_value = {'tagCreate': {'id': '1'}}
        client = StashClient(stash)

        client.create_tags_batch([_tag(description="A debut scene", aliases=["First Timer"])])

        _, variables = stash.call_GQL.call_args[0]
        assert variables['input'] == {
            'name': 'Debut',
            'description': 'A debut scene',
            'aliases': ['First Timer'],
        }


class TestFindStashdbBox:
    def test_returns_key_and_endpoint_for_stashdb_box(self):
        stash = Mock()
        stash.get_stashbox_connections.return_value = [
            {"name": "StashDB", "endpoint": "https://stashdb.org/graphql", "api_key": "sdb-key"},
        ]
        client = StashClient(stash)

        result = client.find_stashdb_box()

        assert result == ("sdb-key", "https://stashdb.org/graphql")

    def test_ignores_non_stashdb_boxes(self):
        stash = Mock()
        stash.get_stashbox_connections.return_value = [
            {"name": "FansDB", "endpoint": "https://fansdb.cc/graphql", "api_key": "fdb-key"},
            {"name": "StashDB", "endpoint": "https://stashdb.org/graphql", "api_key": "sdb-key"},
        ]
        client = StashClient(stash)

        result = client.find_stashdb_box()

        assert result == ("sdb-key", "https://stashdb.org/graphql")

    def test_matches_endpoint_case_insensitively(self):
        stash = Mock()
        stash.get_stashbox_connections.return_value = [
            {"name": "StashDB", "endpoint": "https://StashDB.org/graphql", "api_key": "sdb-key"},
        ]
        client = StashClient(stash)

        result = client.find_stashdb_box()

        assert result == ("sdb-key", "https://StashDB.org/graphql")

    def test_returns_empty_strings_when_no_boxes_configured(self):
        stash = Mock()
        stash.get_stashbox_connections.return_value = []
        client = StashClient(stash)

        result = client.find_stashdb_box()

        assert result == ("", "")

    def test_returns_empty_strings_when_no_stashdb_box_present(self):
        stash = Mock()
        stash.get_stashbox_connections.return_value = [
            {"name": "FansDB", "endpoint": "https://fansdb.cc/graphql", "api_key": "fdb-key"},
        ]
        client = StashClient(stash)

        result = client.find_stashdb_box()

        assert result == ("", "")

    def test_returns_empty_strings_when_box_missing_api_key(self):
        stash = Mock()
        stash.get_stashbox_connections.return_value = [
            {"name": "StashDB", "endpoint": "https://stashdb.org/graphql", "api_key": ""},
        ]
        client = StashClient(stash)

        result = client.find_stashdb_box()

        assert result == ("", "")

    def test_returns_empty_strings_when_fetch_raises(self):
        stash = Mock()
        stash.get_stashbox_connections.side_effect = Exception("connection refused")
        client = StashClient(stash)

        result = client.find_stashdb_box()

        assert result == ("", "")


class TestFindExistingTagsWithData:
    def test_raises_tag_fetch_error_when_find_tags_raises(self):
        stash = Mock()
        stash.find_tags.side_effect = Exception("connection refused")
        client = StashClient(stash)

        with pytest.raises(TagFetchError):
            client.find_existing_tags_with_data()

    def test_returns_empty_maps_when_stash_genuinely_has_no_tags(self):
        stash = Mock()
        stash.find_tags.return_value = []
        client = StashClient(stash)

        tag_map, stash_id_map = client.find_existing_tags_with_data()

        assert tag_map == {}
        assert stash_id_map == {}

    def test_builds_name_and_stash_id_maps_from_returned_tags(self):
        stash = Mock()
        stash.find_tags.return_value = [
            {"name": "Debut", "stash_ids": [{"endpoint": "https://stashdb.org/graphql", "stash_id": "sdb-1"}]},
        ]
        client = StashClient(stash)

        tag_map, stash_id_map = client.find_existing_tags_with_data()

        assert tag_map == {"debut": stash.find_tags.return_value[0]}
        assert stash_id_map == {"sdb-1": stash.find_tags.return_value[0]}


class TestUpdateTagsBatch:
    def test_counts_successful_update(self):
        stash = Mock()
        stash.call_GQL.return_value = {'tagUpdate': {'id': '1'}}
        client = StashClient(stash)

        result = client.update_tags_batch([("1", _tag(), [], None)])

        assert result == 1

    def test_does_not_count_update_rejected_at_graphql_level(self):
        stash = Mock()
        stash.call_GQL.return_value = {'tagUpdate': None}
        client = StashClient(stash)

        result = client.update_tags_batch([("1", _tag(), [], None)])

        assert result == 0

    def test_does_not_count_update_when_call_GQL_raises(self):
        stash = Mock()
        stash.call_GQL.side_effect = Exception("GRAPHQL_ERROR:['tagUpdate'] name conflict")
        client = StashClient(stash)

        result = client.update_tags_batch([("1", _tag(), [], None)])

        assert result == 0

    def test_only_successful_updates_count_in_a_mixed_batch(self):
        stash = Mock()
        stash.call_GQL.side_effect = [
            {'tagUpdate': {'id': '1'}},
            {'tagUpdate': None},
            {'tagUpdate': {'id': '3'}},
        ]
        client = StashClient(stash)

        result = client.update_tags_batch([
            ("1", _tag("Alpha"), [], None),
            ("2", _tag("Beta"), [], None),
            ("3", _tag("Gamma"), [], None),
        ])

        assert result == 2

    def test_does_not_attempt_stash_id_update_after_a_rejected_update(self):
        stash = Mock()
        stash.call_GQL.return_value = {'tagUpdate': None}
        client = StashClient(stash)

        client.update_tags_batch([("1", _tag(), [], "stashdb-id-123")])

        stash.call_GQL.assert_called_once()

    def test_sends_name_and_new_stash_id_in_a_single_mutation_call(self):
        stash = Mock()
        stash.call_GQL.return_value = {'tagUpdate': {'id': '1'}}
        client = StashClient(stash)

        client.update_tags_batch([("1", _tag(), [], "stashdb-id-123")])

        stash.call_GQL.assert_called_once()
        _, variables = stash.call_GQL.call_args[0]
        assert variables['input']['stash_ids'] == [
            {'endpoint': 'https://stashdb.org/graphql', 'stash_id': 'stashdb-id-123'}
        ]

    def test_does_not_resend_a_stash_id_already_present(self):
        stash = Mock()
        stash.call_GQL.return_value = {'tagUpdate': {'id': '1'}}
        client = StashClient(stash)
        existing = [{'endpoint': 'https://stashdb.org/graphql', 'stash_id': 'stashdb-id-123'}]

        client.update_tags_batch([("1", _tag(), existing, "stashdb-id-123")])

        _, variables = stash.call_GQL.call_args[0]
        assert 'stash_ids' not in variables['input']

    def test_omits_stash_ids_entirely_when_no_stash_id_to_add(self):
        stash = Mock()
        stash.call_GQL.return_value = {'tagUpdate': {'id': '1'}}
        client = StashClient(stash)

        client.update_tags_batch([("1", _tag(), [], None)])

        _, variables = stash.call_GQL.call_args[0]
        assert 'stash_ids' not in variables['input']
