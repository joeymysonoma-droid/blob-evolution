"""(c) Regression tests for save-loading bugs BUG-001..BUG-004 (fix owner: TASK-007).

Each is xfail(strict=True) with raises=<the exception the bug produces>, so:
  * today they XFAIL only if they fail for the bug's reason (any other exception
    is reported as a real failure);
  * once TASK-007 fixes a bug the test XPASSes, which strict mode turns into a
    suite failure -- the xfail marker must then be removed.
"""

from __future__ import annotations

import json

import pytest


@pytest.mark.xfail(
    strict=True,
    raises=UnicodeDecodeError,
    reason="BUG-001: save with non-UTF-8 bytes crashes Game() on load",
)
def test_bug001_non_utf8_save_does_not_crash(make_game, isolated_save):
    isolated_save.write_bytes(b"\xff\xfe\x00\x81garbage\x9c")
    make_game()


@pytest.mark.xfail(
    strict=True,
    raises=AttributeError,
    reason="BUG-002: save whose top level is [] crashes Game() on load",
)
def test_bug002_top_level_list_save_does_not_crash(make_game, isolated_save):
    isolated_save.write_text("[]")
    make_game()


@pytest.mark.xfail(
    strict=True,
    raises=AttributeError,
    reason='BUG-003: save with "ng_plus": null crashes Game() on load',
)
def test_bug003_null_ng_plus_section_does_not_crash(make_game, isolated_save, fixture_data):
    data = dict(fixture_data)
    data["ng_plus"] = None
    isolated_save.write_text(json.dumps(data, indent=2))
    make_game()


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="BUG-004: unreadable (truncated) save is overwritten with defaults on next save",
)
def test_bug004_truncated_save_progress_not_destroyed(make_game, isolated_save, fixture_bytes, tmp_path):
    original = fixture_bytes[: len(fixture_bytes) // 2]
    isolated_save.write_bytes(original)
    game = make_game()  # load fails silently today (no crash)
    game._save_game()  # the same call the game makes on exit / purchases / run end
    survivors = [p for p in tmp_path.rglob("*") if p.is_file() and p.read_bytes() == original]
    assert survivors, (
        "original save bytes no longer exist anywhere in the save directory "
        "(neither left in place nor backed up)"
    )
