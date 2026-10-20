"""TASK-067: enemy size grows ENEMY_SIZE_PER_LAYER per layer (act index); the rng stream is unchanged."""
from __future__ import annotations

import random

import pytest

from blob_evolution import config
from blob_evolution.maps.generator import MapGenerator
from blob_evolution.systems.skills import SKILL_DEFINITIONS

LAYERS = range(len(config.MAP_THEMES))
ABSORB_RATIO = 1.1                       # game.py: player.size > creature.size * 1.1 absorbs
SIZE_MAXED = config.PLAYER_BASE_SIZE * (1 + config.MAX_SKILL_LEVEL * SKILL_DEFINITIONS["size"]["multiplier_per_level"])
# Size-heavy bot (TASK-066 sim, 30 seeds): median size entering each layer = end of the layer before
SIM_SIZE_ENTERING = {0: 20.0, 1: 32.0, 2: 32.9, 3: 36.1}


def _gen(layer: int) -> MapGenerator:
    """A generator set to one layer without baking its map."""
    gen = MapGenerator()
    gen.current_map_index = layer
    return gen


@pytest.mark.parametrize("layer", LAYERS)
def test_size_table_per_layer(layer):
    """Layer k rolls 12+2.5k .. 25+2.5k (elite nodes 28+2.5k)."""
    gen = _gen(layer)
    assert gen.enemy_size_range() == pytest.approx((12 + 2.5 * layer, 25 + 2.5 * layer))
    assert gen.enemy_size_range(elite=True) == pytest.approx((12 + 2.5 * layer, 28 + 2.5 * layer))


@pytest.mark.parametrize("layer", LAYERS)
def test_size_roll_is_the_old_roll_shifted(layer):
    """One draw per enemy as on main: same rng position, size = old size + 2.5k."""
    for seed in range(50):
        a, b = random.Random(seed), random.Random(seed)
        new = _gen(layer).enemy_size(a)
        assert new == pytest.approx(b.uniform(12, 25) + 2.5 * layer)
        assert a.random() == b.random()


@pytest.mark.parametrize("layer", [2])
def test_size_heavy_player_cannot_absorb_everything_from_layer_3(layer):
    """The sim's size-heavy player entering layer 3 (index 2) meets enemies too big to absorb (layer 4 at 36.1 does not)."""
    top = _gen(layer).enemy_size_range()[1]
    assert SIM_SIZE_ENTERING[layer] <= top * ABSORB_RATIO


@pytest.mark.parametrize("layer", LAYERS)
def test_skill_maxed_player_absorb_layer(layer):
    """Size skill 10 (40): absorbs every normal enemy through layer 5 (index 4), not from layer 6 on."""
    top = _gen(layer).enemy_size_range()[1]
    assert (SIZE_MAXED > top * ABSORB_RATIO) == (layer <= 4)


def test_spawned_encounter_sizes_shift_and_keep_positions():
    """A spawned encounter at layer 3 has layer 1's positions (types follow the act weights), sizes +5."""
    diff = config.DIFFICULTY_SETTINGS["normal"]
    g0, g2 = _gen(0), _gen(2)
    a = g0.spawn_encounter_creatures(12, diff, seed=77)
    b = g2.spawn_encounter_creatures(12, diff, seed=77)
    assert [(c.pos.x, c.pos.y) for c in a] == [(c.pos.x, c.pos.y) for c in b]
    assert [c.size + 5 for c in a] == pytest.approx([c.size for c in b])
