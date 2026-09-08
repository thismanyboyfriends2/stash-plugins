"""Tests for auto_merge_duplicates plugin logic."""
from unittest.mock import Mock

from auto_merge_duplicates import (
    MAX_CONSECUTIVE_ERRORS,
    _scene_score,
    pick_destination,
    process_duplicates,
)


def _scene(id, title=None, performers=None, tags=None, studio=None,
           galleries=None, urls=None, files=None):
    """Helper to build a scene dict."""
    return {
        "id": id,
        "title": title,
        "performers": performers or [],
        "tags": tags or [],
        "studio": studio,
        "galleries": galleries or [],
        "urls": urls or [],
        "files": files or [],
    }


def _file(width=0, height=0, duration=0.0):
    """Helper to build a file dict."""
    return {"width": width, "height": height, "duration": duration}


# --- _scene_score / pick_destination ---

class TestSceneScore:
    def test_title_increases_score(self):
        with_title = _scene("1", title="Something")
        without_title = _scene("2", title="")
        assert _scene_score(with_title, False) > _scene_score(without_title, False)

    def test_performers_tags_studio_galleries_urls_increase_score(self):
        bare = _scene("1")
        rich = _scene(
            "2",
            performers=[{"id": "p1"}],
            tags=[{"id": "t1"}],
            studio={"id": "s1"},
            galleries=[{"id": "g1"}],
            urls=["http://example.com"],
        )
        assert _scene_score(rich, False) > _scene_score(bare, False)

    def test_resolution_ignored_unless_prefer_higher_res(self):
        low_res = _scene("1", files=[_file(width=100, height=100)])
        high_res = _scene("2", files=[_file(width=1000, height=1000)])
        # Metadata score and resolution component (index 0-1) tie when the
        # setting is off; scene-id (index 3) is excluded since it always differs.
        assert _scene_score(low_res, False)[:2] == _scene_score(high_res, False)[:2]
        assert _scene_score(high_res, True) > _scene_score(low_res, True)

    def test_duration_tiebreak_independent_of_prefer_higher_res(self):
        shorter = _scene("1", files=[_file(duration=100.0)])
        longer = _scene("2", files=[_file(duration=200.0)])
        assert _scene_score(longer, False) > _scene_score(shorter, False)

    def test_scene_id_final_tiebreak(self):
        """When every other field ties, the lowest scene id wins (deterministic)."""
        a = _scene("5")
        b = _scene("10")
        assert _scene_score(a, False) > _scene_score(b, False)


class TestPickDestination:
    def test_picks_highest_metadata_score(self):
        sparse = _scene("1")
        rich = _scene("2", title="Title", performers=[{"id": "p1"}])
        assert pick_destination([sparse, rich], False)["id"] == "2"

    def test_deterministic_regardless_of_order(self):
        a = _scene("5")
        b = _scene("10")
        assert pick_destination([a, b], False)["id"] == "5"
        assert pick_destination([b, a], False)["id"] == "5"


# --- process_duplicates control flow ---

def _make_stash(call_gql_side_effect):
    stash = Mock()
    stash.call_GQL.side_effect = call_gql_side_effect
    return stash


class TestProcessDuplicatesResponseHandling:
    def test_none_response_treated_as_error(self):
        stash = _make_stash([{"findDuplicateScenes": None}])
        # Should not raise, and should not attempt any merge call beyond the query.
        process_duplicates(stash, {}, dry_run=True)
        assert stash.call_GQL.call_count == 1

    def test_empty_list_is_not_an_error(self):
        stash = _make_stash([{"findDuplicateScenes": []}])
        process_duplicates(stash, {}, dry_run=True)
        assert stash.call_GQL.call_count == 1

    def test_groups_with_fewer_than_two_scenes_are_skipped(self):
        stash = _make_stash([{"findDuplicateScenes": [[_scene("1")]]}])
        process_duplicates(stash, {}, dry_run=False)
        # Only the initial query call — no merge mutation should have fired.
        assert stash.call_GQL.call_count == 1


class TestProcessDuplicatesMatchDistance:
    def test_invalid_match_distance_falls_back_to_zero(self):
        stash = _make_stash([{"findDuplicateScenes": []}])
        process_duplicates(stash, {"matchDistance": "not-a-number"}, dry_run=True)
        called_variables = stash.call_GQL.call_args[0][1]
        assert called_variables["distance"] == 0


class TestProcessDuplicatesCircuitBreaker:
    def test_aborts_after_max_consecutive_errors(self):
        group = [_scene("1"), _scene("2")]
        groups = [group] * (MAX_CONSECUTIVE_ERRORS + 2)

        def call_gql(query, variables=None):
            if "findDuplicateScenes" in query:
                return {"findDuplicateScenes": groups}
            raise RuntimeError("merge failed")

        stash = _make_stash(call_gql)
        process_duplicates(stash, {}, dry_run=False)

        # 1 query call + MAX_CONSECUTIVE_ERRORS merge attempts before aborting.
        assert stash.call_GQL.call_count == 1 + MAX_CONSECUTIVE_ERRORS

    def test_consecutive_error_count_resets_on_success(self):
        group = [_scene("1"), _scene("2")]
        groups = [group] * (MAX_CONSECUTIVE_ERRORS + 1)
        calls = {"merge": 0}

        def call_gql(query, variables=None):
            if "findDuplicateScenes" in query:
                return {"findDuplicateScenes": groups}
            calls["merge"] += 1
            # Fail every other merge — never MAX_CONSECUTIVE_ERRORS in a row.
            if calls["merge"] % 2 == 0:
                raise RuntimeError("merge failed")
            return {"sceneMerge": {"id": "1"}}

        stash = _make_stash(call_gql)
        process_duplicates(stash, {}, dry_run=False)

        # All groups attempted — the breaker never trips because failures aren't consecutive.
        assert calls["merge"] == len(groups)
