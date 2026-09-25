"""(a) The committed sample save loads, keeps its values, and round-trips."""

from __future__ import annotations

import json


def _loaded_state(game) -> dict:
    """Snapshot of everything Game._load_save restores."""
    return {
        "ng_plus": game.ng_plus.to_dict(),
        "permanent": game.permanent.to_dict(),
        "total_earned": game.economy.total_earned,
        "audio_enabled": game.audio.enabled,
    }


def test_fixture_is_not_default_state(make_game, isolated_save, fixture_data):
    """Guard: the fixture must differ from a fresh no-save game, or test (a) proves nothing."""
    assert not isolated_save.exists()
    default = _loaded_state(make_game())
    assert fixture_data["ng_plus"] != default["ng_plus"]
    assert fixture_data["permanent"] != default["permanent"]
    assert fixture_data["economy"]["total_earned"] != default["total_earned"]


def test_fixture_values_survive_load(make_game, isolated_save, fixture_bytes, fixture_data):
    """Loading the fixture the way the game does restores every saved value."""
    isolated_save.write_bytes(fixture_bytes)
    game = make_game()

    ng = fixture_data["ng_plus"]
    assert game.ng_plus.ng_plus_level == ng["ng_plus_level"]
    assert game.ng_plus.total_runs == ng["total_runs"]
    assert game.ng_plus.best_map_reached == ng["best_map_reached"]
    assert game.ng_plus.permanent_bonuses == ng["permanent_bonuses"]

    perm = fixture_data["permanent"]
    assert game.permanent.shards == perm["shards"]
    assert game.permanent.total_shards_earned == perm["total_shards_earned"]
    for key, level in perm["upgrade_levels"].items():
        assert game.permanent.upgrade_levels[key] == level, key
    assert game.permanent.unlocked_skins == perm["unlocked_skins"]
    assert game.permanent.equipped_skin == perm["equipped_skin"]
    assert game.permanent.unlocked_wardens == perm["unlocked_wardens"]
    assert game.permanent.unlocked_artifacts == perm["unlocked_artifacts"]
    assert game.permanent.endings_seen == perm["endings_seen"]

    assert game.economy.total_earned == fixture_data["economy"]["total_earned"]
    assert game.audio.enabled is fixture_data["audio_enabled"]


def test_fixture_round_trips_through_save(make_game, isolated_save, fixture_bytes, fixture_data, tmp_path):
    """Load fixture, then Game._save_game(); the written JSON equals the fixture."""
    isolated_save.write_bytes(fixture_bytes)
    game = make_game()
    isolated_save.unlink()  # prove _save_game really writes a new file
    game._save_game()
    assert isolated_save.exists()
    assert json.loads(isolated_save.read_text()) == fixture_data
    # Nothing else written next to the save.
    assert sorted(p.name for p in tmp_path.iterdir()) == [isolated_save.name]
