"""TASK-013c: best-progress tracking in NewGamePlus.complete_run and game-over run_stats."""

from __future__ import annotations

import json
from types import SimpleNamespace

from blob_evolution.systems.newgameplus import NewGamePlus


def _best_layer(ng: NewGamePlus) -> int:
    """Best layer reached as the screens show it (best_map_reached is 0-based)."""
    return ng.best_map_reached + 1


def test_death_records_layer_reached_and_never_lowers_best() -> None:
    """Dying on Layer 5 (4 cleared) records Layer 5; a later shallower death keeps it."""
    ng = NewGamePlus()
    ng.complete_run(4)
    assert _best_layer(ng) == 5
    assert ng.total_runs == 1 and ng.ng_plus_level == 0
    ng.complete_run(1)
    assert _best_layer(ng) == 5
    assert ng.total_runs == 2


def test_death_sets_new_best() -> None:
    """A deeper death raises the best."""
    ng = NewGamePlus()
    ng.best_map_reached = 2
    ng.complete_run(6)
    assert _best_layer(ng) == 7


def test_full_clear_records_layer_10() -> None:
    """A full clear records Layer 10 as best (never 11) and unlocks the next NG+ level."""
    ng = NewGamePlus()
    ng.best_map_reached = 3
    ng.complete_run(10)
    assert _best_layer(ng) == 10
    assert ng.ng_plus_level == 1
    ng.complete_run(10)
    assert _best_layer(ng) == 10
    assert ng.ng_plus_level == 2


def test_full_clear_message_unchanged() -> None:
    """The victory notification text is not part of this task."""
    assert NewGamePlus().complete_run(10) == "New Game Plus 1 unlocked!"


def test_ng_plus_save_with_low_best_loads_as_layer_10(fixture_data) -> None:
    """The QA fixture (NG+ 2, best Layer 2) loads as best Layer 10; nothing else changes."""
    data = json.loads(json.dumps(fixture_data["ng_plus"]))
    assert data["ng_plus_level"] == 2 and data["best_map_reached"] == 1
    ng = NewGamePlus()
    ng.from_dict(data)
    assert _best_layer(ng) == 10
    assert ng.to_dict() == {**fixture_data["ng_plus"], "best_map_reached": 9}


def test_ng_plus_zero_save_loads_unchanged(fixture_data) -> None:
    """A save that never cleared the game keeps its stored best exactly."""
    data = {**json.loads(json.dumps(fixture_data["ng_plus"])), "ng_plus_level": 0, "best_map_reached": 3}
    ng = NewGamePlus()
    ng.from_dict(json.loads(json.dumps(data)))
    assert ng.to_dict() == data


def _ng_section(fixture_data, **overrides) -> dict:
    """Copy of the fixture's ng_plus section with some fields replaced."""
    return {**json.loads(json.dumps(fixture_data["ng_plus"])), **overrides}


def test_ng_plus_one_save_with_low_best_raised_to_layer_10(fixture_data) -> None:
    """An NG+ 1 save with a low best loads with best Layer 10."""
    data = _ng_section(fixture_data, ng_plus_level=1, best_map_reached=2)
    ng = NewGamePlus()
    ng.from_dict(json.loads(json.dumps(data)))
    assert ng.to_dict() == {**data, "best_map_reached": 9}


def test_ng_plus_save_with_best_above_9_is_kept(fixture_data) -> None:
    """An NG+ 1+ save whose best is already above 9 is never lowered."""
    for level in (1, 2):
        data = _ng_section(fixture_data, ng_plus_level=level, best_map_reached=12)
        ng = NewGamePlus()
        ng.from_dict(json.loads(json.dumps(data)))
        assert ng.to_dict() == data


def test_string_ng_plus_level_loads_without_clamp(make_game, isolated_save, fixture_data) -> None:
    """BUG-019: "ng_plus_level": "2" loads without a TypeError; values stay as saved."""
    save = {**fixture_data, "ng_plus": _ng_section(fixture_data, ng_plus_level="2")}
    isolated_save.write_text(json.dumps(save), encoding="utf-8")
    game = make_game()
    assert game.ng_plus.to_dict() == save["ng_plus"]


def test_null_best_at_ng_plus_2_loads_without_clamp(make_game, isolated_save, fixture_data) -> None:
    """BUG-019: "best_map_reached": null at NG+ 2 loads without a TypeError; values stay as saved."""
    save = {**fixture_data, "ng_plus": _ng_section(fixture_data, ng_plus_level=2, best_map_reached=None)}
    isolated_save.write_text(json.dumps(save), encoding="utf-8")
    game = make_game()
    assert game.ng_plus.to_dict() == save["ng_plus"]


def test_game_over_captures_best_before_complete_run(make_game, isolated_save) -> None:
    """_trigger_game_over stores the best layer from before this run updates it."""
    game = make_game()
    game.ng_plus.best_map_reached = 2  # best so far: Layer 3
    game.maps_cleared = 5  # died on Layer 6
    game.player = SimpleNamespace(level=7, kills=40, total_xp=900, artifacts=SimpleNamespace(collected=[]))
    game._trigger_game_over()
    assert game.run_stats["best_layer_before"] == 3
    assert game.run_stats["maps_cleared"] == 5
    assert game.ng_plus.best_map_reached + 1 == 6
    saved = json.loads(isolated_save.read_text(encoding="utf-8"))
    assert set(saved) == {"ng_plus", "permanent", "economy", "audio_enabled"}
    assert set(saved["ng_plus"]) == {"ng_plus_level", "total_runs", "best_map_reached", "permanent_bonuses"}

