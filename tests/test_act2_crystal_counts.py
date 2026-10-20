"""BUG-207 (TASK-064): act 2 keeps exactly 56 bright crystals, and each placed cluster gets at most CRYSTAL_FILLERS
dim buried crystals, and every one of them is placed (exactly CRYSTAL_FILLERS per cluster).

Counts come from the real bake: the two sprite builders are wrapped so the test knows which sprites are bright and
which are buried, and every stamp of one is counted.
Measured on 806a7ce over 64 seeds: 56 bright on every seed; fillers 80-84 of 84 (a filler got 1 + CRYSTAL_REROLLS spots).
BUG-207 (TASK-065): a filler now gets CRYSTAL_FILLER_TRIES (24) spots in its ring before it is dropped: 84 of 84 on all 64.
BUG-225: seed 3012 still dropped one; after the random tries the ring is now scanned (terrain._filler_spot): 0 drops
in 2150 seeds (0-2047, 3000-3099, ...), the scan placed 35 fillers on 30 of them.
"""
import math

import pygame
import pytest

from blob_evolution import config
from blob_evolution.utils import terrain
from blob_evolution.utils.graphics import generate_map_texture

SEEDS = (0, 7, 145, 999, *range(1, 21), 31, 77, 123, 500, 1234, 4242, 2026, 31337, 3012)   # 3012: BUG-225
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


# Seeds where a cluster found no centre after CRYSTAL_REROLLS re-rolls (its 2 bright crystals are re-placed anywhere,
# BUG-184), so that cluster has no filler ring: 27 rings x 3 = 81 fillers, all placed. 1 seed in 2150 (0-2047, 3000-3099).
SHORT_CLUSTER_SEEDS = {888: 27}


@pytest.mark.slow
def test_bug_225_every_filler_is_placed_on_1024_seeds():
    bad = []
    for seed in range(1024):
        with pytest.MonkeyPatch.context() as mp:           # a fresh patch per seed: wrappers must not stack
            calls, real = [], terrain._filler_spot

            def spy(rng, cx, cy, r, placed, real=real, calls=calls):
                calls.append(real(rng, cx, cy, r, placed))
                return calls[-1]

            mp.setattr(terrain, "_filler_spot", spy)
            n = _counts(mp, seed)
        rings = SHORT_CLUSTER_SEEDS.get(seed, CLUSTERS)
        if n != (BRIGHT, rings * terrain.CRYSTAL_FILLERS) or None in calls or len(calls) != rings * terrain.CRYSTAL_FILLERS:
            bad.append((seed, n, len(calls), calls.count(None)))
    assert not bad


# BUG-226: every placed filler is inside its own cluster's 0.6-1.4 x radius ring and clears every bright crystal by the
# spacing rule, including fillers found on late re-roll tries (>= 10) or by the ring scan. Seeds: 13 (22 tries), 3012
# and 74 / 87 (ring scan), 39 (most old drops) and the BUG-207 seeds that used to drop fillers.
RING_SEEDS = (13, 3012, 74, 87, 39, 0, 8, 11, 12, 15, 16, 18, 20, 77, 500, 31337, 22, 24, 26, 28, 29, 37, 42, 43, 48, 49, 52)


def test_bug_226_refilled_fillers_stay_in_the_ring_and_keep_the_spacing(monkeypatch):
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    seen = []
    real = terrain._filler_spot

    def spy(rng, cx, cy, r, placed):
        spot = real(rng, cx, cy, r, placed)
        seen.append((cx, cy, r, list(placed), spot))
        return spot

    monkeypatch.setattr(terrain, "_filler_spot", spy)
    th = config.MAP_THEMES[2]
    R = terrain.CRYSTAL_CLUSTER_RADIUS
    for seed in RING_SEEDS:
        seen.clear()
        generate_map_texture(config.WORLD_WIDTH, config.WORLD_HEIGHT, th["color"], th["accent"], seed, 2)
        assert len(seen) == CLUSTERS * terrain.CRYSTAL_FILLERS
        for cx, cy, r, placed, spot in seen:
            assert spot is not None, seed
            px, py = spot
            d = math.hypot(px - cx, py - cy)
            assert 0.6 * R - 1 <= d <= 1.4 * R + 1, (seed, round(d / R, 3))          # +-1 px: spots are rounded
            assert all(math.hypot(px - x, py - y) >= 2.2 * q + 0.7 * r + 2 for x, y, q in placed), (seed, spot)


def test_bug_225_226_a_fully_blocked_ring_drops_and_never_spills_outside_it():
    import random
    R = terrain.CRYSTAL_CLUSTER_RADIUS
    blocker = [(500.0, 500.0, 30)]                      # clears 2.2 * 30 + 0.7 * 8 + 2 = 73.6 px > 1.4 * R (67.2 px)
    assert terrain._filler_spot(random.Random(1), 500.0, 500.0, 8, blocker) is None


def test_bug_225_the_ring_scan_finds_the_last_clear_band_at_the_ring_edge():
    import random
    R = terrain.CRYSTAL_CLUSTER_RADIUS
    blocker = [(500.0, 500.0, 27)]                      # clears 2.2 * 27 + 0.7 * 8 + 2 = 67.0 px: only 67.0-67.2 px is free
    for seed in range(40):
        spot = terrain._filler_spot(random.Random(seed), 500.0, 500.0, 8, blocker)
        assert spot is not None, seed
        d = math.hypot(spot[0] - 500, spot[1] - 500)
        assert 0.6 * R - 1 <= d <= 1.4 * R + 1, (seed, round(d / R, 3))
        assert d >= 2.2 * 27 + 0.7 * 8 + 2, (seed, d)


# --- BUG-236: the ring scan never draws from the rng ------------------------------------------------------------------

def test_bug_236_the_ring_scan_draws_nothing_from_the_rng(monkeypatch):
    import random
    blocker = [(500.0, 500.0, 27)]                      # only the 67.0-67.2 px band is clear: the scan has to find it
    monkeypatch.setattr(terrain, "CRYSTAL_FILLER_TRIES", 0)       # straight to the scan
    for seed in range(20):
        rng = random.Random(seed)
        before = rng.getstate()
        assert terrain._filler_spot(rng, 500.0, 500.0, 8, blocker) is not None, seed
        assert rng.getstate() == before, seed


def test_bug_236_after_the_random_tries_the_scan_leaves_the_rng_where_the_tries_left_it():
    import random
    blocker = [(500.0, 500.0, 27)]
    R, scanned = terrain.CRYSTAL_CLUSTER_RADIUS, 0
    for seed in range(40):
        rng, ref = random.Random(seed), random.Random(seed)
        spot = terrain._filler_spot(rng, 500.0, 500.0, 8, blocker)
        assert spot is not None, seed
        hit = False
        for _ in range(terrain.CRYSTAL_FILLER_TRIES):   # replay the random tries: two draws each
            d, a = ref.uniform(0.6, 1.4) * R, ref.uniform(0, terrain.TAU)
            if terrain._filler_fits(round(500.0 + d * math.cos(a)), round(500.0 + d * math.sin(a)), 8, blocker):
                hit = True
                break
        if hit:                                         # a random try landed in the band: no scan on this seed
            continue
        scanned += 1
        assert rng.getstate() == ref.getstate(), seed   # the scan added no draws
    assert scanned >= 20, scanned


def test_bug_236_act_2_pin_on_a_seed_that_uses_the_scan():
    """Seed 3012 places one filler by the ring scan (BUG-225); measured on 0beba4b, re-pinned for BUG-235 (hashed start, outer radius first: was 0da8691c13f571ca)."""
    import hashlib
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    th = config.MAP_THEMES[2]
    t = generate_map_texture(config.WORLD_WIDTH, config.WORLD_HEIGHT, th["color"], th["accent"], 3012, 2)
    assert hashlib.sha256(pygame.image.tobytes(t, "RGB")).hexdigest()[:16] == "7d71347eb9373f20"
