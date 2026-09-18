"""Tests for scene_title_cleanup's title suffix-stripping logic."""
from unittest.mock import Mock

from scene_title_cleanup import (
    build_scene_filter,
    clean_title,
    find_scenes,
    parse_extra_suffixes,
    plan_changes,
)


class TestCleanTitle:
    def test_strips_resolution_and_hd(self):
        new_title, changed = clean_title("Whole Strawberry Cream Cake Food Splosh (1080 HD)")

        assert new_title == "Whole Strawberry Cream Cake Food Splosh"
        assert changed is True

    def test_strips_720_hd(self):
        new_title, changed = clean_title("Some Title (720 HD)")

        assert new_title == "Some Title"
        assert changed is True

    def test_strips_bare_resolution(self):
        new_title, changed = clean_title("Some Title (720p)")

        assert new_title == "Some Title"

    def test_strips_4k(self):
        new_title, changed = clean_title("Some Title (4K)")

        assert new_title == "Some Title"

    def test_strips_bare_hd(self):
        new_title, changed = clean_title("Some Title (HD)")

        assert new_title == "Some Title"

    def test_case_insensitive(self):
        new_title, changed = clean_title("Some Title (1080 hd)")

        assert new_title == "Some Title"

    def test_leaves_genre_suffix_untouched(self):
        # Studios legitimately use trailing parenthetical genre tags -
        # these must never be treated as scraper noise.
        new_title, changed = clean_title("Lick My Fresh Young Asshole (Ass Worship)")

        assert new_title == "Lick My Fresh Young Asshole (Ass Worship)"
        assert changed is False

    def test_leaves_release_year_untouched(self):
        # A bare 3-4 digit number in parens (a year) has the same shape as a
        # resolution number with its qualifier stripped - must not match.
        new_title, changed = clean_title("Rico Strong & Annette Schwarz: Butthole Whores (2008)")

        assert new_title == "Rico Strong & Annette Schwarz: Butthole Whores (2008)"
        assert changed is False

    def test_leaves_other_bare_years_untouched(self):
        for year in ("1999", "2160", "720", "480"):
            new_title, changed = clean_title(f"Some Title ({year})")

            assert new_title == f"Some Title ({year})"
            assert changed is False

    def test_leaves_title_with_no_suffix_untouched(self):
        new_title, changed = clean_title("Plain Title")

        assert new_title == "Plain Title"
        assert changed is False

    def test_only_strips_trailing_suffix_not_mid_title(self):
        title = "Scene (1080 HD) Part Two"
        new_title, changed = clean_title(title)

        assert new_title == title
        assert changed is False

    def test_strips_chained_suffixes(self):
        new_title, changed = clean_title("Some Title (1080 HD) (4K)")

        assert new_title == "Some Title"
        assert changed is True

    def test_strips_chained_suffix_with_extra_pattern(self):
        extra = parse_extra_suffixes("(WEB-DL)")
        new_title, changed = clean_title("Some Title (1080 HD) (WEB-DL)", extra)

        assert new_title == "Some Title"
        assert changed is True

    def test_never_returns_empty_title(self):
        new_title, changed = clean_title("(1080 HD)")

        assert new_title == "(1080 HD)"
        assert changed is False

    def test_no_change_when_no_extra_patterns_match(self):
        new_title, changed = clean_title("Some Title (WEB-DL)")

        assert new_title == "Some Title (WEB-DL)"
        assert changed is False


class TestParseExtraSuffixes:
    def test_empty_string_returns_no_patterns(self):
        assert parse_extra_suffixes("") == []
        assert parse_extra_suffixes(None) == []

    def test_splits_comma_separated_values(self):
        patterns = parse_extra_suffixes("(WEB-DL),(Remux)")

        assert len(patterns) == 2

    def test_strips_whitespace_around_entries(self):
        patterns = parse_extra_suffixes(" (WEB-DL) , (Remux) ")

        assert len(patterns) == 2

    def test_skips_empty_entries(self):
        patterns = parse_extra_suffixes("(WEB-DL),,")

        assert len(patterns) == 1


class TestPlanChanges:
    def _scene(self, scene_id, title, studio_name=None):
        return {
            "id": scene_id,
            "title": title,
            "studio": {"name": studio_name} if studio_name else None,
        }

    def test_includes_only_changed_titles(self):
        scenes = [
            self._scene("1", "Title A (1080 HD)"),
            self._scene("2", "Title B"),
        ]

        changes = plan_changes(scenes, studio_filter="", extra_patterns=[])

        assert len(changes) == 1
        assert changes[0]["id"] == "1"
        assert changes[0]["new_title"] == "Title A"

    def test_filters_by_studio_case_insensitive_substring(self):
        scenes = [
            self._scene("1", "Title A (1080 HD)", studio_name="Brat Princess"),
            self._scene("2", "Title B (1080 HD)", studio_name="Other Studio"),
        ]

        changes = plan_changes(scenes, studio_filter="brat princess", extra_patterns=[])

        assert len(changes) == 1
        assert changes[0]["id"] == "1"

    def test_no_studio_filter_applies_to_all_studios(self):
        scenes = [
            self._scene("1", "Title A (1080 HD)", studio_name="Brat Princess"),
            self._scene("2", "Title B (1080 HD)", studio_name="Other Studio"),
        ]

        changes = plan_changes(scenes, studio_filter="", extra_patterns=[])

        assert len(changes) == 2

    def test_scene_with_no_studio_skipped_when_filter_set(self):
        scenes = [self._scene("1", "Title A (1080 HD)", studio_name=None)]

        changes = plan_changes(scenes, studio_filter="brat princess", extra_patterns=[])

        assert changes == []


class TestBuildSceneFilter:
    def test_no_studio_filter_all_paren_extras_is_title_only(self):
        scene_filter = build_scene_filter([], ["(WEB-DL)", "(Remux)"])

        assert scene_filter == {"title": {"value": ")", "modifier": "INCLUDES"}}

    def test_studio_filter_set_all_paren_extras_has_both_criteria(self):
        scene_filter = build_scene_filter(["1", "2"], ["(WEB-DL)"])

        assert scene_filter == {
            "studios": {"value": ["1", "2"], "modifier": "INCLUDES", "depth": 0},
            "title": {"value": ")", "modifier": "INCLUDES"},
        }

    def test_no_studio_filter_one_non_paren_extra_has_no_title_criterion(self):
        scene_filter = build_scene_filter([], ["(WEB-DL)", "WEB-DL"])

        assert scene_filter == {}

    def test_studio_filter_set_one_non_paren_extra_has_only_studios_criterion(self):
        scene_filter = build_scene_filter(["1"], ["WEB-DL"])

        assert scene_filter == {
            "studios": {"value": ["1"], "modifier": "INCLUDES", "depth": 0},
        }

    def test_no_extras_defaults_to_title_only_superset(self):
        scene_filter = build_scene_filter([], [])

        assert scene_filter == {"title": {"value": ")", "modifier": "INCLUDES"}}


class TestFindScenes:
    def _scenes_page(self, scenes, total=None):
        return {"findScenes": {"count": total if total is not None else len(scenes), "scenes": scenes}}

    def test_no_studio_filter_skips_find_studios_call(self):
        stash = Mock()
        stash.call_GQL.side_effect = [self._scenes_page([{"id": "1", "title": "A", "studio": None}])]

        result = find_scenes(stash, studio_filter="", extra_suffixes=[])

        assert stash.call_GQL.call_count == 1
        query = stash.call_GQL.call_args[0][0]
        assert "findScenes" in query
        assert len(result) == 1

    def test_studio_filter_resolves_to_one_id_and_is_passed_to_scene_query(self):
        stash = Mock()
        stash.call_GQL.side_effect = [
            {"findStudios": {"studios": [{"id": "42"}]}},
            self._scenes_page([{"id": "1", "title": "A", "studio": {"name": "Brat Princess"}}]),
        ]

        result = find_scenes(stash, studio_filter="brat princess", extra_suffixes=[])

        assert stash.call_GQL.call_count == 2
        find_studios_variables = stash.call_GQL.call_args_list[0][0][1]
        assert find_studios_variables["studio_filter"] == {
            "name": {"value": "brat princess", "modifier": "INCLUDES"}
        }
        scene_query_variables = stash.call_GQL.call_args_list[1][0][1]
        assert scene_query_variables["scene_filter"]["studios"] == {
            "value": ["42"], "modifier": "INCLUDES", "depth": 0,
        }
        assert len(result) == 1

    def test_studio_filter_matching_zero_studios_returns_empty_without_crashing(self):
        stash = Mock()
        stash.call_GQL.side_effect = [{"findStudios": {"studios": []}}]

        result = find_scenes(stash, studio_filter="nonexistent studio", extra_suffixes=[])

        assert result == []
        # No scene query fired once we know zero studios can match.
        assert stash.call_GQL.call_count == 1

    def test_non_paren_extra_suffix_falls_back_to_no_title_criterion(self):
        stash = Mock()
        stash.call_GQL.side_effect = [self._scenes_page([{"id": "1", "title": "A", "studio": None}])]

        find_scenes(stash, studio_filter="", extra_suffixes=["WEB-DL"])

        scene_query_variables = stash.call_GQL.call_args_list[0][0][1]
        assert "title" not in scene_query_variables["scene_filter"]
