"""Tests for scene_title_to_filename plugin logic."""
import pytest
from scene_title_to_filename import sanitize_filename, plan_renames


def _scene(id, title, files):
    """Helper to build a scene dict."""
    return {"id": id, "title": title, "files": files}


def _file(id, path):
    """Helper to build a file dict."""
    import os
    return {"id": id, "path": path, "basename": os.path.basename(path)}


# --- sanitize_filename ---

class TestSanitizeFilename:
    def test_basic(self):
        assert sanitize_filename("My Scene Title") == "My Scene Title"

    def test_strips_illegal_chars(self):
        assert sanitize_filename('Scene: "The Best" 2024') == "Scene The Best 2024"

    def test_strips_all_illegal_chars(self):
        for char in r'/\:*?"<>|':
            assert char not in sanitize_filename(f"before{char}after")

    def test_trims_whitespace(self):
        assert sanitize_filename("  padded  ") == "padded"

    def test_empty_after_sanitize(self):
        assert sanitize_filename('???') == ""

    def test_collapses_multiple_spaces(self):
        assert sanitize_filename('Scene:  "The"  Best') == "Scene The Best"

    def test_preserves_normal_punctuation(self):
        assert sanitize_filename("Scene - Part 1 (2024)") == "Scene - Part 1 (2024)"


# --- plan_renames ---

class TestPlanRenames:
    def test_basic_rename(self):
        scenes = [_scene("1", "New Title", [_file("f1", "/data/import/old_name.mp4")])]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 1
        assert renames[0]["new_basename"] == "New Title.mp4"
        assert renames[0]["old_basename"] == "old_name.mp4"

    def test_skip_no_title(self):
        scenes = [_scene("1", "", [_file("f1", "/data/import/file.mp4")])]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 0
        assert any(s["reason"] == "no_title" for s in skipped)

    def test_skip_none_title(self):
        scenes = [_scene("1", None, [_file("f1", "/data/import/file.mp4")])]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 0
        assert any(s["reason"] == "no_title" for s in skipped)

    def test_skip_no_files(self):
        scenes = [_scene("1", "Title", [])]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 0
        assert any(s["reason"] == "no_files" for s in skipped)

    def test_skip_multiple_files(self):
        scenes = [_scene("1", "Title", [
            _file("f1", "/data/import/a.mp4"),
            _file("f2", "/data/import/b.mp4"),
        ])]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 0
        assert any(s["reason"] == "multiple_files" for s in skipped)

    def test_skip_already_correct(self):
        scenes = [_scene("1", "My Scene", [_file("f1", "/data/import/My Scene.mp4")])]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 0
        assert any(s["reason"] == "already_correct" for s in skipped)

    def test_skip_empty_after_sanitize(self):
        scenes = [_scene("1", "???", [_file("f1", "/data/import/file.mp4")])]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 0
        assert any(s["reason"] == "empty_after_sanitize" for s in skipped)

    def test_preserves_extension(self):
        scenes = [_scene("1", "New Name", [_file("f1", "/data/import/old.mkv")])]
        renames, skipped = plan_renames(scenes)
        assert renames[0]["new_basename"] == "New Name.mkv"

    def test_sanitizes_illegal_chars_in_title(self):
        scenes = [_scene("1", 'Title: "Subtitle"', [_file("f1", "/data/import/old.mp4")])]
        renames, skipped = plan_renames(scenes)
        assert renames[0]["new_basename"] == "Title Subtitle.mp4"

    def test_conflict_same_directory(self):
        scenes = [
            _scene("1", "Same Title", [_file("f1", "/data/import/a.mp4")]),
            _scene("2", "Same Title", [_file("f2", "/data/import/b.mp4")]),
        ]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 2
        basenames = {r["new_basename"] for r in renames}
        assert "Same Title.mp4" in basenames
        assert "Same Title (1).mp4" in basenames

    def test_conflict_different_directories(self):
        scenes = [
            _scene("1", "Same Title", [_file("f1", "/data/dir1/a.mp4")]),
            _scene("2", "Same Title", [_file("f2", "/data/dir2/b.mp4")]),
        ]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 2
        # No conflict — different directories, both get the clean name
        assert all(r["new_basename"] == "Same Title.mp4" for r in renames)

    def test_triple_conflict(self):
        scenes = [
            _scene("1", "Title", [_file("f1", "/data/import/a.mp4")]),
            _scene("2", "Title", [_file("f2", "/data/import/b.mp4")]),
            _scene("3", "Title", [_file("f3", "/data/import/c.mp4")]),
        ]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 3
        basenames = sorted(r["new_basename"] for r in renames)
        assert basenames == ["Title (1).mp4", "Title (2).mp4", "Title.mp4"]

    def test_mixed_skip_and_rename(self):
        scenes = [
            _scene("1", "Good Title", [_file("f1", "/data/import/old.mp4")]),
            _scene("2", "", [_file("f2", "/data/import/notitle.mp4")]),
            _scene("3", "Another", [
                _file("f3", "/data/import/multi1.mp4"),
                _file("f4", "/data/import/multi2.mp4"),
            ]),
        ]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 1
        assert len(skipped) == 2
        assert renames[0]["new_basename"] == "Good Title.mp4"

    def test_case_insensitive_conflict(self):
        scenes = [
            _scene("1", "My Scene", [_file("f1", "/data/import/a.mp4")]),
            _scene("2", "my scene", [_file("f2", "/data/import/b.mp4")]),
        ]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 2
        basenames = sorted(r["new_basename"] for r in renames)
        assert basenames == ["My Scene.mp4", "my scene (1).mp4"]

    def test_already_correct_blocks_conflict(self):
        """A file already named correctly should prevent another scene from taking that name."""
        scenes = [
            _scene("1", "Foo", [_file("f1", "/data/import/Foo.mp4")]),  # already correct
            _scene("2", "Foo", [_file("f2", "/data/import/old.mp4")]),  # wants same name
        ]
        renames, skipped = plan_renames(scenes)
        assert len(skipped) == 1
        assert skipped[0]["reason"] == "already_correct"
        assert len(renames) == 1
        assert renames[0]["new_basename"] == "Foo (1).mp4"

    def test_whitespace_only_title(self):
        scenes = [_scene("1", "   ", [_file("f1", "/data/import/file.mp4")])]
        renames, skipped = plan_renames(scenes)
        assert len(renames) == 0
        assert any(s["reason"] == "no_title" for s in skipped)
