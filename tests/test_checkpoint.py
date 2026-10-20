"""TASK-070: the optional "checkpoint" save field; old saves load unchanged; resume restores the layer start."""
from __future__ import annotations

import json

import pytest

from blob_evolution.systems import checkpoint
from blob_evolution.utils.enums import Difficulty, GameState

EXPECTED_FIXTURE = lambda fx: {**fx, "ng_plus": {**fx["ng_plus"], "best_map_reached": 9}}   # as test_save_fixture


def test_old_fixture_has_no_checkpoint_and_round_trips_unchanged(make_game, isolated_save, fixture_bytes, fixture_data):
    """The committed fixture (no checkpoint key) loads with checkpoint None and re-saves exactly as on main."""
    assert "checkpoint" not in fixture_data
    isolated_save.write_bytes(fixture_bytes)
    game = make_game()
    assert game.checkpoint is None and game.save_notice is None
    game._save_game()
    assert json.loads(isolated_save.read_text()) == EXPECTED_FIXTURE(fixture_data)
    second = make_game()                                  # and again: load -> save is stable
    second._save_game()
    assert json.loads(isolated_save.read_text()) == EXPECTED_FIXTURE(fixture_data)


def test_new_run_writes_a_layer_1_checkpoint(make_game, isolated_save, fixture_bytes, fixture_data):
    """Starting a run saves a checkpoint for layer 1; every other field is the fixture's."""
    isolated_save.write_bytes(fixture_bytes)
    game = make_game()
    game._start_new_run()
    data = json.loads(isolated_save.read_text())
    cp = data.pop("checkpoint")
    assert cp["version"] == checkpoint.VERSION and cp["act_index"] == 0
    assert cp["overworld_seed"] == game.overworld.seed
    assert data == EXPECTED_FIXTURE(fixture_data)


def _advance_to_layer(game, act: int) -> dict:
    """Give the run a mid-game state and write its checkpoint at layer `act`."""
    from blob_evolution.systems.overworld import OverworldMap
    p = game.player
    p.level, p.xp, p.total_xp, p.skill_points, p.kills = 9, 33, 1200, 3, 140
    p.skills.levels["size"], p.skills.levels["damage"] = 4, 2
    p.artifacts.collected = ["thick_skin", "growth_catalyst"]
    p.artifacts.upgrade_levels = {"thick_skin": 1}
    p.shop_size_boost = 0.12
    p.has_shield = True
    p._update_stats()
    p.hp = p.max_hp * 0.6
    game.economy.essence, game.economy.run_xp_boost, game.economy.run_piercing = 210, 0.2, True
    game.maps_cleared, game.run_shards_earned = act, 55
    game._seen_acts = set(range(act + 1))
    game.difficulty = Difficulty.HARD
    game.overworld = OverworldMap(act_index=act, seed=4321)
    game._write_checkpoint()
    return checkpoint.capture(game)


@pytest.mark.parametrize("act", [0, 2, 5, 9])
def test_resume_restores_the_layer_start(make_game, isolated_save, act):
    """Play on past the checkpoint, quit; a new Game resumes with exactly the layer-start state and a fresh map."""
    game = make_game()
    game._start_new_run()
    at_start = _advance_to_layer(game, act)
    node = game.overworld.get_available_nodes()[0]
    game.overworld.select_node(node.id)
    game.overworld.complete_current_node()
    game.player.hp, game.economy.essence, game.player.kills = 1.0, 0, 999
    game.player.skills.levels["speed"] = 5

    later = make_game()
    assert later.checkpoint is not None
    later.difficulty = Difficulty.EASY
    assert later._resume_checkpoint()
    assert later.state == GameState.OVERWORLD
    assert checkpoint.capture(later) == at_start
    assert later.player.size == pytest.approx(game.player.size)    # same skills/artifacts/shop: same stats
    assert not any(n.completed for n in later.overworld.nodes.values() if n.layer > 0)
    assert later.overworld.current_node_id == "n_0_0"


def test_no_checkpoint_means_no_resume(make_game):
    """A fresh game has nothing to resume."""
    game = make_game()
    assert game.checkpoint is None and not game._resume_checkpoint()


def test_core_choice_clears_the_checkpoint(make_game, isolated_save):
    """Finishing the last layer ends the run: the next save has no checkpoint."""
    game = make_game()
    game._start_new_run()
    game._trigger_core_choice()
    game._save_game()
    assert "checkpoint" not in json.loads(isolated_save.read_text())


@pytest.mark.parametrize("bad", [
    5, "x", [], {}, {"version": 2}, {"version": 1, "act_index": 99, "difficulty": "normal", "player": {}},
    {"version": 1, "act_index": 0, "difficulty": "nope", "player": {}},
    {"version": 1, "act_index": 0, "difficulty": "normal", "player": {"level": "9"}},
    {"version": 1, "act_index": 0, "difficulty": "normal", "player": {}, "seen_acts": 3},
])
def test_bad_checkpoint_is_ignored_and_the_rest_loads(make_game, isolated_save, fixture_data, bad):
    """An unusable checkpoint is dropped; the save's other fields still load, no backup and no notice."""
    isolated_save.write_text(json.dumps({**fixture_data, "checkpoint": bad}))
    game = make_game()
    assert game.checkpoint is None and game.save_notice is None
    assert game.permanent.shards == fixture_data["permanent"]["shards"]
    assert not list(isolated_save.parent.glob("*.bak*"))


def test_checkpoint_survives_its_own_round_trip(make_game):
    """read(capture()) is the identity once JSON-encoded."""
    game = make_game()
    game._start_new_run()
    cp = _advance_to_layer(game, 3)
    assert checkpoint.read(json.loads(json.dumps(cp))) == cp
