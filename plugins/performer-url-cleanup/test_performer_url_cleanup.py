"""Tests for performer_url_cleanup's URL normalisation logic."""
from performer_url_cleanup import normalise_url, deduplicate_and_sort, has_mixed_case


class TestNormaliseUrl:
    def test_adds_scheme_when_missing(self):
        normalised, domain = normalise_url("onlyfans.com/someone")

        assert normalised == "https://onlyfans.com/someone"
        assert domain == "onlyfans.com"

    def test_removes_www_for_www_stripped_domains(self):
        normalised, domain = normalise_url("https://www.x.com/someone")

        assert domain == "x.com"
        assert normalised == "https://x.com/someone"

    def test_adds_www_for_www_required_domains(self):
        normalised, domain = normalise_url("https://instagram.com/someone")

        assert domain == "www.instagram.com"
        assert normalised == "https://www.instagram.com/someone"

    def test_applies_domain_alias(self):
        normalised, domain = normalise_url("https://twitter.com/someone")

        assert domain == "x.com"
        assert normalised == "https://x.com/someone"

    def test_domain_alias_applies_after_www_removal(self):
        normalised, domain = normalise_url("https://www.twitter.com/someone")

        assert domain == "x.com"
        assert normalised == "https://x.com/someone"

    def test_upgrades_to_https_by_default(self):
        normalised, domain = normalise_url("http://onlyfans.com/someone")

        assert normalised.startswith("https://")

    def test_keeps_http_for_http_only_domains(self):
        normalised, domain = normalise_url("https://bustybuffy.com/someone")

        assert normalised.startswith("http://")

    def test_removes_trailing_slash_by_default(self):
        normalised, domain = normalise_url("https://onlyfans.com/someone/")

        assert normalised == "https://onlyfans.com/someone"

    def test_keeps_trailing_slash_for_configured_domains(self):
        normalised, domain = normalise_url("https://adultfilmdatabase.com/someone/")

        assert normalised == "https://adultfilmdatabase.com/someone/"

    def test_lowercases_path_for_case_insensitive_domains(self):
        normalised, domain = normalise_url("https://onlyfans.com/SomeOne")

        assert normalised == "https://onlyfans.com/someone"

    def test_preserves_path_case_by_default(self):
        normalised, domain = normalise_url("https://fansly.com/SomeOne")

        assert normalised == "https://fansly.com/SomeOne"

    def test_applies_path_transform(self):
        normalised, domain = normalise_url("https://eastcoasttalents.com/site/talent/someone")

        assert normalised == "https://eastcoasttalents.com/talent/someone"

    def test_removes_configured_path_suffix(self):
        normalised, domain = normalise_url("https://fansly.com/someone/posts")

        assert normalised == "https://fansly.com/someone"

    def test_preserves_query_string_and_drops_fragment(self):
        normalised, domain = normalise_url("https://onlyfans.com/someone?ref=abc#section")

        assert normalised == "https://onlyfans.com/someone?ref=abc"

    def test_rules_interact_www_add_then_lowercase_path(self):
        # instagram.com requires www AND is case-insensitive - both rules must apply together
        normalised, domain = normalise_url("https://instagram.com/SomeOne")

        assert domain == "www.instagram.com"
        assert normalised == "https://www.instagram.com/someone"

    def test_unknown_domain_gets_https_upgrade_but_no_other_changes(self):
        normalised, domain = normalise_url("http://example.com/SomePath/")

        assert normalised == "https://example.com/SomePath"
        assert domain == "example.com"


class TestHasMixedCase:
    def test_true_for_mixed_case_path(self):
        assert has_mixed_case("https://example.com/SomeOne") is True

    def test_false_for_lowercase_path(self):
        assert has_mixed_case("https://example.com/someone") is False

    def test_false_for_uppercase_path(self):
        assert has_mixed_case("https://example.com/SOMEONE") is False

    def test_false_for_empty_path(self):
        assert has_mixed_case("https://example.com") is False


class TestDeduplicateAndSort:
    def test_empty_input_returns_empty_results(self):
        result_urls, changes, potential_changes = deduplicate_and_sort([])

        assert result_urls == []
        assert changes == []
        assert potential_changes == []

    def test_normalises_known_domain_url(self):
        result_urls, changes, potential_changes = deduplicate_and_sort(["https://www.x.com/someone"])

        assert result_urls == ["https://x.com/someone"]
        assert len(changes) == 1
        assert not potential_changes

    def test_leaves_unknown_domain_url_unchanged_but_flags_potential(self):
        result_urls, changes, potential_changes = deduplicate_and_sort(["http://example.com/SomePath/"])

        # normalisation not applied (unknown domain) - original URL kept
        assert result_urls == ["http://example.com/SomePath/"]
        assert not changes
        assert len(potential_changes) == 1

    def test_removes_duplicate_after_normalisation(self):
        result_urls, changes, potential_changes = deduplicate_and_sort([
            "https://onlyfans.com/someone",
            "https://onlyfans.com/someone/",
        ])

        assert result_urls == ["https://onlyfans.com/someone"]
        assert any("Remove duplicate" in c for c in changes)

    def test_prefers_mixed_case_original_when_deduplicating(self):
        result_urls, changes, potential_changes = deduplicate_and_sort([
            "https://fansly.com/someone",
            "https://fansly.com/SomeOne",
        ])

        assert result_urls == ["https://fansly.com/SomeOne"]

    def test_sorts_results_by_domain_then_url(self):
        result_urls, changes, potential_changes = deduplicate_and_sort([
            "https://zzz.com/a",
            "https://aaa.com/a",
        ])

        assert result_urls == ["https://aaa.com/a", "https://zzz.com/a"]
        assert "Reordered URLs alphabetically by domain" in changes

    def test_no_reorder_message_when_already_sorted(self):
        result_urls, changes, potential_changes = deduplicate_and_sort([
            "https://aaa.com/a",
            "https://zzz.com/a",
        ])

        assert "Reordered URLs alphabetically by domain" not in changes
