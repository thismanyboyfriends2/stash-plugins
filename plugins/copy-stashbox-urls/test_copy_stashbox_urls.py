"""Verification that scene and performer StashBox URL processing behave identically
through the shared StashBoxURLProcessor pipeline (aside from entity-type data)."""
from unittest.mock import Mock

from copyStashBoxUrls import StashBoxURLProcessor, SCENE_CONFIG, PERFORMER_CONFIG


def _stash_id(endpoint="https://stashdb.org/graphql", stash_id="abc-123"):
    return {"endpoint": endpoint, "stash_id": stash_id}


class TestSceneAndPerformerPipelinesShareBehaviour:
    def test_scene_and_performer_processors_construct_analogous_urls(self):
        stash = Mock()
        scene_processor = StashBoxURLProcessor(stash, SCENE_CONFIG)
        performer_processor = StashBoxURLProcessor(stash, PERFORMER_CONFIG)

        scene_url = scene_processor.construct_stashbox_url("https://stashdb.org/graphql", "abc-123")
        performer_url = performer_processor.construct_stashbox_url("https://stashdb.org/graphql", "abc-123")

        assert scene_url == "https://stashdb.org/scenes/abc-123"
        assert performer_url == "https://stashdb.org/performers/abc-123"

    def test_get_count_reads_the_right_field_for_each_config(self):
        stash = Mock()
        stash.callGQL.return_value = {"findScenes": {"count": 5}}
        scene_processor = StashBoxURLProcessor(stash, SCENE_CONFIG)
        assert scene_processor.get_count_with_stashids() == 5

        stash.callGQL.return_value = {"findPerformers": {"count": 7}}
        performer_processor = StashBoxURLProcessor(stash, PERFORMER_CONFIG)
        assert performer_processor.get_count_with_stashids() == 7

    def test_query_page_reads_the_right_items_field_for_each_config(self):
        stash = Mock()
        stash.callGQL.return_value = {"findScenes": {"scenes": [{"id": "1"}]}}
        scene_processor = StashBoxURLProcessor(stash, SCENE_CONFIG)
        assert scene_processor.query_page_with_stashids(1, 100) == [{"id": "1"}]

        stash.callGQL.return_value = {"findPerformers": {"performers": [{"id": "2"}]}}
        performer_processor = StashBoxURLProcessor(stash, PERFORMER_CONFIG)
        assert performer_processor.query_page_with_stashids(1, 100) == [{"id": "2"}]

    def test_update_entity_urls_calls_the_right_mutation_field(self):
        stash = Mock()

        scene_processor = StashBoxURLProcessor(stash, SCENE_CONFIG)
        scene_processor.update_entity_urls("1", ["https://x.com/a"])
        scene_mutation = stash.callGQL.call_args[0][0]
        assert "sceneUpdate" in scene_mutation
        assert "SceneUpdateInput" in scene_mutation

        performer_processor = StashBoxURLProcessor(stash, PERFORMER_CONFIG)
        performer_processor.update_entity_urls("2", ["https://x.com/b"])
        performer_mutation = stash.callGQL.call_args[0][0]
        assert "performerUpdate" in performer_mutation
        assert "PerformerUpdateInput" in performer_mutation

    def test_process_entity_merges_urls_and_updates_when_changed(self):
        stash = Mock()
        processor = StashBoxURLProcessor(stash, SCENE_CONFIG)

        entity = {
            "id": "1",
            "urls": ["https://existing.com/a"],
            "stash_ids": [_stash_id()],
        }

        processor.process_entity(entity)

        assert processor.updated_count == 1
        assert processor.skipped_count == 0
        update_call = stash.callGQL.call_args
        assert update_call[0][1]["input"]["urls"] == [
            "https://existing.com/a",
            "https://stashdb.org/scenes/abc-123",
        ]

    def test_process_entity_skips_when_no_changes_needed(self):
        stash = Mock()
        processor = StashBoxURLProcessor(stash, PERFORMER_CONFIG)

        entity = {
            "id": "1",
            "urls": ["https://stashdb.org/performers/abc-123"],
            "stash_ids": [_stash_id()],
        }

        processor.process_entity(entity)

        assert processor.updated_count == 0
        assert processor.skipped_count == 1
        stash.callGQL.assert_not_called()

    def test_process_entity_skips_when_missing_id(self):
        stash = Mock()
        processor = StashBoxURLProcessor(stash, SCENE_CONFIG)

        processor.process_entity({"stash_ids": [_stash_id()], "urls": []})

        assert processor.skipped_count == 1
        assert processor.processed_count == 1

    def test_process_all_end_to_end_for_scenes_and_performers(self):
        for config, find_field, items_field in (
            (SCENE_CONFIG, "findScenes", "scenes"),
            (PERFORMER_CONFIG, "findPerformers", "performers"),
        ):
            stash = Mock()
            stash.callGQL.side_effect = [
                {find_field: {"count": 1}},
                {find_field: {items_field: [{"id": "1", "urls": [], "stash_ids": [_stash_id()]}]}},
                {},  # update mutation response
            ]

            processor = StashBoxURLProcessor(stash, config)
            processor.process_all()

            assert processor.get_summary() == {
                "processed": 1,
                "updated": 1,
                "skipped": 0,
                "errors": 0,
            }
