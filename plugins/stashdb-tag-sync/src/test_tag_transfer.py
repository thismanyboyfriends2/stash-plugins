"""Tests for tag_transfer's core merge/conflict/sync logic."""
from models import Tag
from core.tag_transfer import _merge_tag_data, _has_alias_conflicts, _is_tag_out_of_sync


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
