"""BUG-207 (TASK-064): act 2 keeps exactly 56 bright crystals, and each placed cluster gets at most CRYSTAL_FILLERS
dim buried crystals, and every one of them is placed (exactly CRYSTAL_FILLERS per cluster).

Counts come from the real bake: the two sprite builders are wrapped so the test knows which sprites are bright and
which are buried, and every stamp of one is counted.
Measured on 806a7ce over 64 seeds: 56 bright on every seed; fillers 80-84 of 84 (a filler got 1 + CRYSTAL_REROLLS spots).
BUG-207 (TASK-065): a filler now gets CRYSTAL_FILLER_TRIES (24) spots in its ring before it is dropped: 84 of 84 on all 64.
"""
import pygame
import pytest

from blob_evolution import config
from blob_evolution.utils import terrain
from blob_evolution.utils.graphics import generate_map_texture

SEEDS = (0, 7, 145, 999, *range(1, 21), 31, 77, 123, 500, 1234, 4242, 2026, 31337)
BRIGHT = 56
CLUSTERS = BRIGHT // terrain.CRYSTALS_PER_CLUSTER


def _counts(monkeypatch, seed: int):
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    bright, buried, keep, n = set(), set(), [], {"bright": 0, "buried": 0}
    real_c, real_b, real_stamp = terrain._crystal_sprite, terrain._buried_crystal_sprite, terrain.stamp

    def crystal(*a, **k):
        s = real_c(*a, **k); bright.add(id(s)); keep.append(s); return s

    def filler(*a, **k):
        s = real_b(*a, **k); buried.add(id(s)); keep.append(s); return s

    def stamp(surface, sprite, *a, **k):
        if id(sprite) in bright:
            n["bright"] += 1
        elif id(sprite) in buried:
            n["buried"] += 1
        return real_stamp(surface, sprite, *a, **k)

    monkeypatch.setattr(terrain, "_crystal_sprite", crystal)
    monkeypatch.setattr(terrain, "_buried_crystal_sprite", filler)
    monkeypatch.setattr(terrain, "stamp", stamp)
    th = config.MAP_THEMES[2]
    generate_map_texture(config.WORLD_WIDTH, config.WORLD_HEIGHT, th["color"], th["accent"], seed, 2)
    return n["bright"], n["buried"]


@pytest.mark.parametrize("seed", SEEDS)
def test_bug_207_act_2_has_exactly_56_bright_crystals(monkeypatch, seed):
    assert _counts(monkeypatch, seed)[0] == BRIGHT


@pytest.mark.parametrize("seed", SEEDS)
def test_bug_207_act_2_places_every_filler_3_per_cluster(monkeypatch, seed):
    fillers = _counts(monkeypatch, seed)[1]
    assert fillers == CLUSTERS * terrain.CRYSTAL_FILLERS, (seed, fillers)


def test_bug_207_the_counted_constants_are_the_ruled_ones():
    assert (terrain.CRYSTALS_PER_CLUSTER, terrain.CRYSTAL_FILLERS, terrain.CRYSTAL_FILLER_TRIES, CLUSTERS) == (2, 3, 24, 28)
