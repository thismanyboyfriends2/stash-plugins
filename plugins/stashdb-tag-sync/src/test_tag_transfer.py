"""Tests for tag_transfer's core merge/conflict/sync logic."""
from unittest.mock import Mock

import pytest

from models import Tag, Config
from core.tag_transfer import (
    _filter_new_tags,
    _has_alias_conflicts,
    _is_tag_out_of_sync,
    _merge_tag_data,
    _resolve_local_match,
    transfer_tags_graphql,
)
from stash_client import TagFetchError


def _stashdb_tag(name="Debut", description="", aliases=None, stash_id="sdb-1", category=None):
    return Tag(name=name, description=description, stash_id=stash_id, aliases=aliases or [], category=category)


def _existing_tag(name="Debut", description="", aliases=None, stash_ids=None, id="1"):
    return {'id': id, 'name': name, 'description': description, 'aliases': aliases or [], 'stash_ids': stash_ids or []}


class TestMergeTagData:
    def test_unions_aliases_from_both_sides(self):
        stashdb = _stashdb_tag(aliases=["Debutante"])
        existing = _existing_tag(aliases=["First Timer"])

        merged = _merge_tag_data(stashdb, existing)

        assert merged.aliases == ["Debutante", "First Timer"]

    def test_deduplicates_and_sorts_aliases(self):
        stashdb = _stashdb_tag(aliases=["Beta", "Alpha"])
        existing = _existing_tag(aliases=["Alpha", "Gamma"])

        merged = _merge_tag_data(stashdb, existing)

        assert merged.aliases == ["Alpha", "Beta", "Gamma"]

    def test_excludes_ignored_aliases_from_both_sides(self):
        stashdb = _stashdb_tag(aliases=["Debutante", "Ignored One"])
        existing = _existing_tag(aliases=["Ignored Two", "First Timer"])

        merged = _merge_tag_data(stashdb, existing, ignored_aliases=["Ignored One", "Ignored Two"])

        assert merged.aliases == ["Debutante", "First Timer"]

    def test_ignored_aliases_match_case_insensitively(self):
        stashdb = _stashdb_tag(aliases=["Debutante"])
        existing = _existing_tag(aliases=[])

        merged = _merge_tag_data(stashdb, existing, ignored_aliases=["debutante"])

        assert merged.aliases == []

    def test_strips_whitespace_from_aliases(self):
        stashdb = _stashdb_tag(aliases=["  Debutante  "])
        existing = _existing_tag(aliases=[" First Timer "])

        merged = _merge_tag_data(stashdb, existing)

        assert merged.aliases == ["Debutante", "First Timer"]

    def test_skips_non_string_or_blank_aliases(self):
        stashdb = _stashdb_tag(aliases=["Debutante", "", "   "])
        existing = _existing_tag(aliases=[None, 123])

        merged = _merge_tag_data(stashdb, existing)

        assert merged.aliases == ["Debutante"]

    def test_prefers_stashdb_description_when_present(self):
        stashdb = _stashdb_tag(description="StashDB description")
        existing = _existing_tag(description="Stash description")

        merged = _merge_tag_data(stashdb, existing)

        assert merged.description == "StashDB description"

    def test_falls_back_to_existing_description_when_stashdb_blank(self):
        stashdb = _stashdb_tag(description="   ")
        existing = _existing_tag(description="Stash description")

        merged = _merge_tag_data(stashdb, existing)

        assert merged.description == "Stash description"

    def test_carries_over_name_stash_id_and_category(self):
        stashdb = _stashdb_tag(name="Debut", stash_id="sdb-42", category="Scene Type")
        existing = _existing_tag()

        merged = _merge_tag_data(stashdb, existing)

        assert merged.name == "Debut"
        assert merged.stash_id == "sdb-42"
        assert merged.category == "Scene Type"


class TestHasAliasConflicts:
    def test_flags_alias_that_matches_an_existing_tag_name(self):
        merged = Tag(name="Debut", description="", stash_id="", aliases=["Anal"])
        existing_tags_by_name = {"anal": {"id": "99"}}

        conflicts = _has_alias_conflicts(merged, existing_tags_by_name)

        assert conflicts == ["Anal"]

    def test_no_conflicts_when_aliases_dont_match_any_tag_name(self):
        merged = Tag(name="Debut", description="", stash_id="", aliases=["Debutante"])
        existing_tags_by_name = {"anal": {"id": "99"}}

        conflicts = _has_alias_conflicts(merged, existing_tags_by_name)

        assert conflicts == []

    def test_ignored_aliases_are_never_reported_as_conflicts(self):
        merged = Tag(name="Debut", description="", stash_id="", aliases=["Anal"])
        existing_tags_by_name = {"anal": {"id": "99"}}

        conflicts = _has_alias_conflicts(merged, existing_tags_by_name, ignored_aliases=["Anal"])

        assert conflicts == []

    def test_matches_case_insensitively(self):
        merged = Tag(name="Debut", description="", stash_id="", aliases=["ANAL"])
        existing_tags_by_name = {"anal": {"id": "99"}}

        conflicts = _has_alias_conflicts(merged, existing_tags_by_name)

        assert conflicts == ["ANAL"]

    def test_alias_equal_to_own_tags_former_name_is_not_a_conflict(self):
        # Regression (#53): renaming "Old" to "New" and adding "Old" as an
        # alias must not be rejected just because "Old" still resolves to
        # this same tag in existing_tags_by_name.
        merged = Tag(name="New", description="", stash_id="", aliases=["Old"])
        existing_tags_by_name = {"old": {"id": "1"}}

        conflicts = _has_alias_conflicts(merged, existing_tags_by_name, own_tag_id="1")

        assert conflicts == []

    def test_alias_matching_a_different_tags_name_is_still_a_conflict(self):
        merged = Tag(name="New", description="", stash_id="", aliases=["Anal"])
        existing_tags_by_name = {"anal": {"id": "99"}}

        conflicts = _has_alias_conflicts(merged, existing_tags_by_name, own_tag_id="1")

        assert conflicts == ["Anal"]


class TestIsTagOutOfSync:
    def test_false_when_merged_result_matches_existing_tag_exactly(self):
        stashdb = _stashdb_tag(name="Debut", description="", aliases=["Debutante"], stash_id="")
        existing = _existing_tag(name="Debut", description="", aliases=["Debutante"])

        assert _is_tag_out_of_sync(stashdb, existing) is False

    def test_true_when_name_would_change(self):
        # Regression (#48): a tag renamed on StashDB (matched via stash_id,
        # so name never entered the lookup key) must still be detected as
        # out of sync so the rename reaches Stash.
        stashdb = _stashdb_tag(name="New Name", description="", aliases=[], stash_id="sdb-1")
        existing = _existing_tag(name="Old Name", description="", aliases=[], stash_ids=[{"stash_id": "sdb-1"}])

        assert _is_tag_out_of_sync(stashdb, existing) is True

    def test_true_when_description_would_change(self):
        stashdb = _stashdb_tag(description="New description")
        existing = _existing_tag(description="Old description")

        assert _is_tag_out_of_sync(stashdb, existing) is True

    def test_true_when_aliases_would_change(self):
        stashdb = _stashdb_tag(aliases=["New Alias"])
        existing = _existing_tag(aliases=[])

        assert _is_tag_out_of_sync(stashdb, existing) is True

    def test_true_when_stashdb_id_is_missing_from_existing_stash_ids(self):
        stashdb = _stashdb_tag(stash_id="sdb-1")
        existing = _existing_tag(stash_ids=[{"stash_id": "sdb-2"}])

        assert _is_tag_out_of_sync(stashdb, existing) is True

    def test_false_when_stashdb_id_already_present_as_dict(self):
        stashdb = _stashdb_tag(stash_id="sdb-1")
        existing = _existing_tag(stash_ids=[{"stash_id": "sdb-1"}])

        assert _is_tag_out_of_sync(stashdb, existing) is False

    def test_false_when_stashdb_id_already_present_as_object(self):
        class _StashId:
            stash_id = "sdb-1"

        stashdb = _stashdb_tag(stash_id="sdb-1")
        existing = _existing_tag()
        existing['stash_ids'] = [_StashId()]

        assert _is_tag_out_of_sync(stashdb, existing) is False

    def test_false_when_stashdb_tag_has_no_stash_id_to_check(self):
        stashdb = _stashdb_tag(stash_id="")
        existing = _existing_tag()

        assert _is_tag_out_of_sync(stashdb, existing) is False


class TestResolveLocalMatch:
    """Covers the single-decision resolver: stash_id first, then name, then nothing."""

    def test_matches_by_stash_id_when_present(self):
        tag = _stashdb_tag(name="Debut", stash_id="sdb-1")
        by_stash_id = {"sdb-1": _existing_tag(id="1")}
        by_name = {"debut": _existing_tag(id="2")}

        existing_tag, source, already_claimed = _resolve_local_match(tag, by_stash_id, by_name, claimed_ids=set())

        assert source == "stash_id"
        assert existing_tag["id"] == "1"
        assert already_claimed is False

    def test_falls_back_to_name_when_no_stash_id_match(self):
        tag = _stashdb_tag(name="Debut", stash_id="sdb-missing")
        by_name = {"debut": _existing_tag(id="2")}

        existing_tag, source, already_claimed = _resolve_local_match(tag, {}, by_name, claimed_ids=set())

        assert source == "name"
        assert existing_tag["id"] == "2"
        assert already_claimed is False

    def test_returns_none_when_nothing_matches(self):
        tag = _stashdb_tag(name="Brand New", stash_id="sdb-missing")

        existing_tag, source, already_claimed = _resolve_local_match(tag, {}, {}, claimed_ids=set())

        assert existing_tag is None
        assert source is None
        assert already_claimed is False

    def test_claimed_local_tag_is_never_matched_again(self):
        # Regression (#57): once a local tag id has been claimed by an
        # earlier StashDB tag this run, neither a stash_id nor a name match
        # against it should succeed for a later tag.
        by_stash_id = {"sdb-1": _existing_tag(id="1")}
        by_name = {"debut": _existing_tag(id="1")}

        existing_tag, source, already_claimed = _resolve_local_match(
            _stashdb_tag(name="Debut", stash_id="sdb-1"), by_stash_id, by_name, claimed_ids={"1"},
        )

        assert existing_tag is None
        assert source == "stash_id"
        assert already_claimed is True

    def test_stash_id_match_takes_priority_over_a_different_names_match(self):
        tag = _stashdb_tag(name="Debut", stash_id="sdb-1")
        by_stash_id = {"sdb-1": _existing_tag(id="1")}
        by_name = {"debut": _existing_tag(id="2")}

        existing_tag, source, already_claimed = _resolve_local_match(tag, by_stash_id, by_name, claimed_ids=set())

        assert source == "stash_id"
        assert existing_tag["id"] == "1"
        assert already_claimed is False

    def test_claimed_stash_id_candidate_does_not_fall_back_to_an_unrelated_name_match(self):
        # A stash_id candidate that's already claimed reports already_claimed
        # rather than silently falling through to a name lookup that would
        # resolve to a *different* local tag - that would attach this
        # StashDB tag's identity to the wrong local tag.
        by_stash_id = {"sdb-1": _existing_tag(id="1")}
        by_name = {"debut": _existing_tag(id="2")}

        existing_tag, source, already_claimed = _resolve_local_match(
            _stashdb_tag(name="Debut", stash_id="sdb-1"), by_stash_id, by_name, claimed_ids={"1"},
        )

        assert existing_tag is None
        assert source == "stash_id"
        assert already_claimed is True


class TestTransferTagsGraphql:
    """Integration-style coverage for the full resolve/create/update pipeline via a mocked StashClient."""

    def _client(self, existing_by_name=None, existing_by_stash_id=None):
        client = Mock()
        client.find_existing_tags_with_data.return_value = (existing_by_name or {}, existing_by_stash_id or {})
        client.create_tags_batch.return_value = ({}, 0)
        client.update_tags_batch.return_value = 0
        return client

    def test_stash_id_match_takes_priority_over_name_match(self):
        # Tag matches an existing tag by stash_id; a *different* existing tag
        # happens to share its name. stash_id should win.
        tag = _stashdb_tag(name="Debut", stash_id="sdb-1", description="New")
        by_stash_id = {"sdb-1": _existing_tag(id="1", name="Debut", description="Old")}
        by_name = {"debut": _existing_tag(id="2", name="Debut", description="Old")}
        client = self._client(existing_by_name=by_name, existing_by_stash_id=by_stash_id)
        client.update_tags_batch.return_value = 1

        transfer_tags_graphql(client, [tag], Config(stashdb_api_key="key"))

        (tags_with_ids,), _ = client.update_tags_batch.call_args
        assert tags_with_ids[0][0] == "1"  # matched by stash_id's tag id, not name's

    def test_unmatched_tag_is_created(self):
        tag = _stashdb_tag(name="New Tag", stash_id="")
        client = self._client()
        client.create_tags_batch.return_value = ({"new tag": "1"}, 0)

        stats = transfer_tags_graphql(client, [tag], Config(stashdb_api_key="key"))

        client.create_tags_batch.assert_called_once_with([tag])
        assert stats["created"] == 1

    def test_fetch_failure_aborts_before_any_create_or_update(self):
        tag = _stashdb_tag(name="Debut", stash_id="sdb-1")
        client = self._client()
        client.find_existing_tags_with_data.side_effect = TagFetchError("connection refused")

        with pytest.raises(TagFetchError):
            transfer_tags_graphql(client, [tag], Config(stashdb_api_key="key"))

        client.create_tags_batch.assert_not_called()
        client.update_tags_batch.assert_not_called()

    def test_rename_on_stashdb_reaches_stash(self):
        # Fixes #48: matched by stash_id, same description/aliases, new name.
        tag = _stashdb_tag(name="New Name", stash_id="sdb-1", description="", aliases=[])
        by_stash_id = {"sdb-1": _existing_tag(id="1", name="Old Name", description="", aliases=[])}
        client = self._client(existing_by_stash_id=by_stash_id)
        client.update_tags_batch.return_value = 1

        transfer_tags_graphql(client, [tag], Config(stashdb_api_key="key"))

        (tags_with_ids,), _ = client.update_tags_batch.call_args
        assert len(tags_with_ids) == 1
        assert tags_with_ids[0][1].name == "New Name"

    def test_rename_reusing_own_former_name_as_alias_is_not_a_conflict(self):
        # Fixes #53: StashDB renames "Old" to "New" and adds "Old" as an
        # alias. "Old" resolves to this same local tag in
        # existing_tags_by_name, so it must not be treated as a conflict.
        tag = _stashdb_tag(name="New", stash_id="sdb-1", description="", aliases=["Old"])
        existing = _existing_tag(id="1", name="Old", description="", aliases=[])
        by_stash_id = {"sdb-1": existing}
        by_name = {"old": existing}
        client = self._client(existing_by_name=by_name, existing_by_stash_id=by_stash_id)
        client.update_tags_batch.return_value = 1

        stats = transfer_tags_graphql(client, [tag], Config(stashdb_api_key="key"))

        assert stats["failed"] == 0
        client.update_tags_batch.assert_called_once()

    def test_a_local_tag_is_never_updated_twice_in_one_run(self):
        # Fixes #57: one local tag has a stash_id set, and its current name
        # also happens to match a different incoming StashDB tag by name.
        # That local tag must be reached by exactly one of the two -
        # whichever comes first - never both.
        existing = _existing_tag(id="1", name="Debut", description="", aliases=[], stash_ids=[{"stash_id": "sdb-1"}])
        by_stash_id = {"sdb-1": existing}
        by_name = {"debut": existing}

        tag_by_stash_id = _stashdb_tag(name="Debut", stash_id="sdb-1", description="New via stash_id")
        tag_by_name = _stashdb_tag(name="Debut", stash_id="sdb-other", description="New via name")

        client = self._client(existing_by_name=by_name, existing_by_stash_id=by_stash_id)
        client.update_tags_batch.return_value = 1
        client.create_tags_batch.return_value = ({}, 0)

        transfer_tags_graphql(client, [tag_by_stash_id, tag_by_name], Config(stashdb_api_key="key"))

        (tags_with_ids,), _ = client.update_tags_batch.call_args
        ids = [entry[0] for entry in tags_with_ids]
        assert ids.count("1") == 1

    def test_second_stash_id_pointing_at_an_already_claimed_tag_is_not_created_as_a_duplicate(self):
        # A local tag carrying two StashDB stash_ids (e.g. from an earlier
        # StashDB-side merge). Two incoming StashDB tags each resolve to it
        # by a different stash_id, with different names. The first claims
        # it; the second must recognise it as already handled and not fall
        # through to name lookup (miss) and then get created as a duplicate.
        existing = _existing_tag(
            id="1", name="Anal Sex", description="", aliases=[],
            stash_ids=[{"stash_id": "sdb-1"}, {"stash_id": "sdb-2"}],
        )
        by_stash_id = {"sdb-1": existing, "sdb-2": existing}
        by_name = {"anal sex": existing}

        tag_one = _stashdb_tag(name="Anal Sex", stash_id="sdb-1", description="", aliases=[])
        tag_two = _stashdb_tag(name="Anal", stash_id="sdb-2", description="", aliases=[])

        client = self._client(existing_by_name=by_name, existing_by_stash_id=by_stash_id)
        client.update_tags_batch.return_value = 0

        stats = transfer_tags_graphql(client, [tag_one, tag_two], Config(stashdb_api_key="key"))

        client.create_tags_batch.assert_not_called()
        assert stats["created"] == 0


class TestFilterNewTags:
    """Covers the stage-3 idempotency filter directly.

    In the full pipeline the resolver already matches everything in
    existing_tags_by_name, so this filter is a defensive no-op in practice -
    but it used to mutate `new_tags` via list.remove() while iterating it,
    which silently skipped every other consecutive match. Testing it in
    isolation (rather than via the full pipeline, where the resolver would
    mask the bug entirely) is what actually regression-tests the fix.
    """

    def test_drops_every_tag_that_already_exists_by_name_even_when_consecutive(self):
        dup1 = _stashdb_tag(name="Dup One", stash_id="")
        dup2 = _stashdb_tag(name="Dup Two", stash_id="")
        fresh = _stashdb_tag(name="Fresh", stash_id="")
        existing_tags_by_name = {
            "dup one": {"id": "1"},
            "dup two": {"id": "2"},
        }

        result = _filter_new_tags([dup1, dup2, fresh], existing_tags_by_name)

        assert result == [fresh]

    def test_keeps_all_tags_when_none_already_exist(self):
        tags = [_stashdb_tag(name="A", stash_id=""), _stashdb_tag(name="B", stash_id="")]

        result = _filter_new_tags(tags, {})

        assert result == tags
