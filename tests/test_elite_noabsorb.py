"""TASK-068: elite_chance is read; elites (no_absorb) are never absorbed at any player size, and take shots as usual."""
from __future__ import annotations

import hashlib
import random

import pytest

import hitfx_scene
from blob_evolution import config
from blob_evolution.entities.creature import Creature
from blob_evolution.maps.generator import MapGenerator
from blob_evolution.utils.enums import CreatureType
from blob_evolution.utils.vector2 import Vector2


def _spawn(chance: float, seed: int, count: int = 30) -> list:
    """Spawn one encounter with the given elite_chance."""
    diff = dict(config.DIFFICULTY_SETTINGS["normal"], elite_chance=chance)
    return MapGenerator().spawn_encounter_creatures(count, diff, seed)


def _digest(creatures: list, flags: bool = True) -> str:
    """Hash of every creature's position, type, size (and elite flag)."""
    rows = [(c.pos.x, c.pos.y, c.ctype.value, round(c.size, 9)) + ((c.no_absorb,) if flags else ()) for c in creatures]
    return hashlib.sha1(repr(rows).encode()).hexdigest()[:16]


@pytest.mark.parametrize("seed", range(20))
def test_elite_rolls_are_deterministic_per_seed(seed):
    """Same seed, same flags and same hash; the rolls never move positions, types or sizes."""
    a, b = _spawn(0.3, seed), _spawn(0.3, seed)
    assert _digest(a) == _digest(b)
    assert _digest(a, flags=False) == _digest(_spawn(0.0, seed), flags=False)


def test_chance_zero_flags_nothing_and_draws_nothing():
    """normal/easy (0.0) leave every creature absorbable, as on main."""
    for seed in range(50):
        assert not any(c.no_absorb for c in _spawn(0.0, seed))


def test_elite_rate_tracks_chance():
    """Over 200 encounters x 30 the flagged share is near elite_chance."""
    for chance in (0.05, 0.15, 0.3):
        flags = [c.no_absorb for s in range(200) for c in _spawn(chance, s)]
        assert abs(sum(flags) / len(flags) - chance) < 0.02


def test_roll_uses_its_own_rng():
    """The flags match a Random(seed ^ ELITE_RNG_SALT) stream."""
    cs = _spawn(0.3, 4242)
    rng = random.Random(4242 ^ config.ELITE_RNG_SALT)
    assert [c.no_absorb for c in cs] == [rng.random() < 0.3 for _ in cs]


@pytest.fixture
def fight(make_game):
    g = hitfx_scene.make_scene_game(0)
    g.creatures, g.bosses, g.projectiles, g.xp_orbs = [], [], [], []
    g.player.max_hp = g.player.hp = 1e9
    return g


@pytest.mark.parametrize("player_size", [25.0, 40.0, 80.0, 500.0])
def test_elite_is_never_absorbed_at_any_size(fight, player_size):
    """A tiny elite touching a huge player stays alive; the same plain creature is absorbed."""
    g = fight
    g.player.size = player_size
    elite = Creature(Vector2(g.player.pos.x + 2, g.player.pos.y), CreatureType.BASIC, 12.0)
    elite.no_absorb = True
    plain = Creature(Vector2(g.player.pos.x - 2, g.player.pos.y), CreatureType.BASIC, 12.0)
    g.creatures = [elite, plain]
    g._update_collisions()
    assert elite.active and not plain.active


def test_elite_contact_hurts_like_a_big_creature(fight):
    """Touching an elite you would otherwise eat deals its contact damage."""
    g = fight
    g.player.size = 60.0
    g.player.invulnerable = 0.0
    elite = Creature(Vector2(g.player.pos.x + 2, g.player.pos.y), CreatureType.BASIC, 12.0)
    elite.no_absorb = True
    g.creatures = [elite]
    hp0 = g.player.hp
    g._update_collisions()
    assert g.player.hp < hp0


def test_elite_takes_damage_normally():
    """take_damage is unchanged for elites: same hp loss and kill as a plain twin."""
    a = Creature(Vector2(100, 100), CreatureType.BASIC, 15.0)
    b = Creature(Vector2(100, 100), CreatureType.BASIC, 15.0)
    b.no_absorb = True
    assert a.take_damage(7.0) == b.take_damage(7.0)
    assert a.hp == b.hp
    assert a.take_damage(1e6) and b.take_damage(1e6)
