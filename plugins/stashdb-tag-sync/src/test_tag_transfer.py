"""Tests for tag_transfer's core merge/conflict/sync logic."""
from unittest.mock import Mock

from models import Tag, Config
from core.tag_transfer import (
    _filter_new_tags,
    _has_alias_conflicts,
    _is_tag_out_of_sync,
    _match,
    _MatchState,
    _merge_tag_data,
    transfer_tags_graphql,
)


def _stashdb_tag(name="Debut", description="", aliases=None, stash_id="sdb-1", category=None):
    return Tag(name=name, description=description, stash_id=stash_id, aliases=aliases or [], category=category)


def _existing_tag(description="", aliases=None, stash_ids=None):
    return {'description': description, 'aliases': aliases or [], 'stash_ids': stash_ids or []}


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


class TestIsTagOutOfSync:
    def test_false_when_merged_result_matches_existing_tag_exactly(self):
        stashdb = _stashdb_tag(description="", aliases=["Debutante"], stash_id="")
        existing = _existing_tag(description="", aliases=["Debutante"])

        assert _is_tag_out_of_sync(stashdb, existing) is False

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


def _match_state(existing_tags_by_name=None, ignored_aliases=None, matched_tags=None, tags_to_update=None):
    return _MatchState(
        existing_tags_by_name=existing_tags_by_name or {},
        ignored_aliases=ignored_aliases or [],
        matched_tags=matched_tags if matched_tags is not None else set(),
        tags_to_update=tags_to_update if tags_to_update is not None else [],
    )


STASH_ID_KEY_FN = lambda t: t.stash_id or None  # noqa: E731
NAME_KEY_FN = lambda t: t.name.lower() if t.name else None  # noqa: E731


class TestMatch:
    """Covers the shared matching helper by both key shapes: stash_id and name."""

    def test_matches_and_updates_by_stash_id_when_out_of_sync(self):
        tag = _stashdb_tag(name="Debut", stash_id="sdb-1", description="New")
        lookup = {"sdb-1": {"id": "1", "description": "Old", "aliases": []}}
        state = _match_state()

        matches, skipped, failed = _match(tags=[tag], lookup=lookup, key_fn=STASH_ID_KEY_FN, state=state)

        assert (matches, skipped, failed) == (1, 0, 0)
        assert state.matched_tags == {"debut"}
        assert len(state.tags_to_update) == 1
        assert state.tags_to_update[0][0] == "1"

    def test_matches_and_updates_by_name_when_out_of_sync(self):
        tag = _stashdb_tag(name="Debut", stash_id="", description="New")
        lookup = {"debut": {"id": "1", "description": "Old", "aliases": []}}
        state = _match_state()

        matches, skipped, failed = _match(tags=[tag], lookup=lookup, key_fn=NAME_KEY_FN, state=state)

        assert (matches, skipped, failed) == (1, 0, 0)
        assert state.matched_tags == {"debut"}
        assert len(state.tags_to_update) == 1

    def test_marks_matched_without_update_when_already_in_sync(self):
        tag = _stashdb_tag(name="Debut", stash_id="sdb-1", description="")
        lookup = {"sdb-1": {"id": "1", "description": "", "aliases": [], "stash_ids": [{"stash_id": "sdb-1"}]}}
        state = _match_state()

        matches, skipped, failed = _match(tags=[tag], lookup=lookup, key_fn=STASH_ID_KEY_FN, state=state)

        assert (matches, skipped, failed) == (0, 0, 0)
        assert state.matched_tags == {"debut"}
        assert state.tags_to_update == []

    def test_skips_tags_already_present_in_matched_tags(self):
        tag = _stashdb_tag(name="Debut", stash_id="sdb-1")
        lookup = {"sdb-1": {"id": "1", "description": "", "aliases": []}}
        state = _match_state(matched_tags={"debut"})

        matches, skipped, failed = _match(tags=[tag], lookup=lookup, key_fn=STASH_ID_KEY_FN, state=state)

        assert (matches, skipped, failed) == (0, 0, 0)
        assert state.tags_to_update == []

    def test_ignores_tags_whose_key_is_not_in_lookup(self):
        tag = _stashdb_tag(name="Debut", stash_id="sdb-missing")
        state = _match_state()

        matches, skipped, failed = _match(tags=[tag], lookup={}, key_fn=STASH_ID_KEY_FN, state=state)

        assert (matches, skipped, failed) == (0, 0, 0)
        assert state.matched_tags == set()

    def test_counts_alias_conflict_as_failed_not_matched(self):
        tag = _stashdb_tag(name="Debut", stash_id="sdb-1", aliases=["Anal"])
        lookup = {"sdb-1": {"id": "1", "description": "", "aliases": []}}
        state = _match_state(existing_tags_by_name={"anal": {"id": "99"}})

        matches, skipped, failed = _match(tags=[tag], lookup=lookup, key_fn=STASH_ID_KEY_FN, state=state)

        assert (matches, skipped, failed) == (0, 0, 1)
        assert state.tags_to_update == []
        # A failed (conflicted) tag is still marked matched, so stage 2 doesn't re-attempt it.
        assert state.matched_tags == {"debut"}

    def test_reject_blank_name_skips_and_counts_a_matched_tag_with_no_name(self):
        tag = Tag(name="", description="", stash_id="sdb-1", aliases=[])
        lookup = {"sdb-1": {"id": "1", "description": "", "aliases": []}}
        state = _match_state()

        matches, skipped, failed = _match(
            tags=[tag], lookup=lookup, key_fn=STASH_ID_KEY_FN, state=state, reject_blank_name=True,
        )

        assert (matches, skipped, failed) == (0, 1, 0)
        assert state.matched_tags == set()

    def test_reject_blank_name_skips_a_matched_tag_with_a_whitespace_only_name(self):
        tag = Tag(name="   ", description="", stash_id="sdb-1", aliases=[])
        lookup = {"sdb-1": {"id": "1", "description": "", "aliases": []}}
        state = _match_state()

        matches, skipped, failed = _match(
            tags=[tag], lookup=lookup, key_fn=STASH_ID_KEY_FN, state=state, reject_blank_name=True,
        )

        assert (matches, skipped, failed) == (0, 1, 0)

    def test_without_reject_blank_name_a_whitespace_only_name_is_processed_normally(self):
        # Regression: the original name-match stage never rejected a blank
        # name (its own outer condition already required a truthy name to
        # compute the lookup key), so a whitespace-only name was matched and
        # updated like any other. reject_blank_name defaults to False so the
        # collapsed helper preserves that per-stage difference.
        tag = Tag(name="   ", description="New", stash_id="", aliases=[])
        lookup = {"   ": {"id": "1", "description": "Old", "aliases": []}}
        state = _match_state()

        matches, skipped, failed = _match(tags=[tag], lookup=lookup, key_fn=NAME_KEY_FN, state=state)

        assert (matches, skipped, failed) == (1, 0, 0)
        assert len(state.tags_to_update) == 1


class TestTransferTagsGraphql:
    """Integration-style coverage for the full three-stage pipeline via a mocked StashClient."""

    def _client(self, existing_by_name=None, existing_by_stash_id=None):
        client = Mock()
        client.find_existing_tags_with_data.return_value = (existing_by_name or {}, existing_by_stash_id or {})
        client.create_tags_batch.return_value = ({}, 0)
        client.update_tags_batch.return_value = 0
        return client

    def test_stash_id_match_takes_priority_over_name_match(self):
        # Tag matches an existing tag by stash_id; a *different* existing tag
        # happens to share its name. stash_id should win (stage 1 runs first).
        tag = _stashdb_tag(name="Debut", stash_id="sdb-1", description="New")
        by_stash_id = {"sdb-1": {"id": "1", "description": "Old", "aliases": []}}
        by_name = {"debut": {"id": "2", "description": "Old", "aliases": []}}
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

class TestFilterNewTags:
    """Covers the stage-3 idempotency filter directly.

    In the full pipeline stage 2 already matches everything in
    existing_tags_by_name, so this filter is a defensive no-op in practice -
    but it used to mutate `new_tags` via list.remove() while iterating it,
    which silently skipped every other consecutive match. Testing it in
    isolation (rather than via the full pipeline, where stage 2 would mask
    the bug entirely) is what actually regression-tests the fix.
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
