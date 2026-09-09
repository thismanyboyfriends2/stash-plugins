"""Tests for scene_title_cleanup's title suffix-stripping logic."""
from scene_title_cleanup import clean_title, parse_extra_suffixes, plan_changes


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
