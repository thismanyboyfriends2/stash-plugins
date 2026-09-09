"""Tests for StashClient's tag-write failure detection."""
from unittest.mock import Mock

from models import Tag
from stash_client import StashClient


def _tag(name="Debut", description="", aliases=None):
    return Tag(name=name, description=description, stash_id="", aliases=aliases or [])


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
