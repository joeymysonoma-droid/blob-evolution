"""(c) Regression tests for save-loading bugs BUG-001..BUG-004 (fixed in TASK-007).

These were strict xfails until TASK-007 landed; they must now pass outright.
"""

from __future__ import annotations

import json


def test_bug001_non_utf8_save_does_not_crash(make_game, isolated_save):
    isolated_save.write_bytes(b"\xff\xfe\x00\x81garbage\x9c")
    make_game()


def test_bug002_top_level_list_save_does_not_crash(make_game, isolated_save):
    isolated_save.write_text("[]")
    make_game()


def test_bug003_null_ng_plus_section_does_not_crash(make_game, isolated_save, fixture_data):
    data = dict(fixture_data)
    data["ng_plus"] = None
    isolated_save.write_text(json.dumps(data, indent=2))
    make_game()


def test_bug004_truncated_save_progress_not_destroyed(make_game, isolated_save, fixture_bytes, tmp_path):
    original = fixture_bytes[: len(fixture_bytes) // 2]
    isolated_save.write_bytes(original)
    game = make_game()  # unreadable save must load without crashing
    game._save_game()  # the same call the game makes on exit / purchases / run end
    survivors = [p for p in tmp_path.rglob("*") if p.is_file() and p.read_bytes() == original]
    assert survivors, (
        "original save bytes no longer exist anywhere in the save directory "
        "(neither left in place nor backed up)"
    )
