"""TASK-037: ground rebuild (tone ramps, three-octave macro noise, grit, clustered scatter, stamping framework).

Pins the plan's 37.3 acceptance: readability (p99/p95 luma, nothing darker than 0.6 x DARK outside the vignette),
bake time, determinism, and that creature and hazard positions for a seed are unchanged. Everything is
deterministic; the strict timing check is slow-marked.
"""
from __future__ import annotations

import functools
import hashlib
import math
import random
import time
from typing import Dict, List, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.maps.generator import MapGenerator
from blob_evolution.systems.hazards import HazardManager
from blob_evolution.utils import graphics, terrain
from blob_evolution.utils.graphics import generate_map_texture

ACTS = range(len(config.MAP_THEMES))
SEEDS = (0, 7, 145, 999)
W, H = config.WORLD_WIDTH, config.WORLD_HEIGHT
PLAYER_BODY = config.COLOR_PLAYER


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb) -> float:
    """WCAG relative luminance (the 'luma' of the plan's rule R1)."""
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def _cr(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _bake(act: int, seed: int = 7) -> pygame.Surface:
    th = config.MAP_THEMES[act]
    return generate_map_texture(W, H, th["color"], th["accent"], seed, act)


@pytest.fixture
def no_vignette(monkeypatch):
    """Bake without the world-edge vignette, so 'darker than 0.6 x DARK' can be checked on every pixel."""
    monkeypatch.setattr(graphics, "_make_vignette", lambda w, h: pygame.Surface((w, h), pygame.SRCALPHA))


def _all_at_least(surf: pygame.Surface, floor) -> bool:
    """True when every channel of every pixel is >= floor (C-speed mask test; from_threshold is exclusive)."""
    m = [math.ceil((255 - f) / 2) for f in floor]
    centre = (floor[0] + m[0], floor[1] + m[1], floor[2] + m[2], 255)
    return pygame.mask.from_threshold(surf, centre, (m[0] + 1, m[1] + 1, m[2] + 1, 255)).count() == surf.get_width() * surf.get_height()


def _all_at_most(surf: pygame.Surface, ceiling) -> bool:
    """True when every channel of every pixel is <= ceiling."""
    m = [math.ceil(c / 2) for c in ceiling]
    centre = (ceiling[0] - m[0], ceiling[1] - m[1], ceiling[2] - m[2], 255)
    return pygame.mask.from_threshold(surf, centre, (m[0] + 1, m[1] + 1, m[2] + 1, 255)).count() == surf.get_width() * surf.get_height()


@functools.lru_cache(maxsize=None)
def _ground_stats(act: int, seed: int) -> Dict[str, object]:
    """Luma percentiles (sampled every 101st pixel) and ramp-bound checks of the pre-vignette bake, cached."""
    orig = graphics._make_vignette
    graphics._make_vignette = lambda w, h: pygame.Surface((w, h), pygame.SRCALPHA)
    try:
        surf = _bake(act, seed)
    finally:
        graphics._make_vignette = orig
    dark, mid, light = config.GROUND_RAMPS[act]
    data = pygame.image.tobytes(surf, "RGB")
    step = 3 * 101
    lums = sorted(_lum(px) for px in zip(data[0::step], data[1::step], data[2::step]))
    n = len(lums)
    floor = tuple(math.ceil(c * 0.6) for c in dark)
    ceiling = tuple(max(light[c], mid[c] + config.GROUND_GRIT_SPREAD) + 1 for c in range(3))
    return {
        "p95": lums[int(n * 0.95)], "p99": lums[int(n * 0.99)],
        "above_floor": _all_at_least(surf, floor), "below_ceiling": _all_at_most(surf, ceiling),
    }


# --- 37.1 ramps ---------------------------------------------------------------------------------------------

def test_ten_ramps_in_act_order_each_dark_to_light():
    assert len(config.GROUND_RAMPS) == len(config.MAP_THEMES) == 10
    for dark, mid, light in config.GROUND_RAMPS:
        for c in range(3):
            assert 0 <= dark[c] <= light[c] <= 255
        assert _lum(dark) < _lum(mid) < _lum(light)


@pytest.mark.parametrize("act", ACTS)
def test_theme_colour_is_the_mid_tone(act):
    assert config.MAP_THEMES[act]["color"] == config.GROUND_RAMPS[act][1]


def test_exact_plan_ramp_values_for_the_changed_acts():
    assert config.GROUND_RAMPS[4] == ((22, 40, 56), (32, 56, 76), (48, 80, 104))     # Still Expanse
    assert config.GROUND_RAMPS[5] == ((58, 43, 26), (80, 60, 36), (104, 80, 48))     # Mirage Basin
    assert [config.MAP_THEMES[i]["color"] for i in (1, 2, 3, 8)] == [(42, 50, 28), (26, 34, 74), (48, 24, 20), (16, 22, 48)]
    assert config.MAP_THEMES[0]["accent"] == (58, 150, 75)    # accents are untouched


@pytest.mark.parametrize("act, expected", list(enumerate([3.2, 4.4, 5.0, 5.7, 3.7, 3.3, 5.2, 7.6, 6.6, 6.1])))
def test_player_body_contrast_against_the_light_tone_matches_the_plan_table(act, expected):
    cr = _cr(PLAYER_BODY, config.GROUND_RAMPS[act][2])
    assert cr == pytest.approx(expected, abs=0.06)
    assert cr >= 3.0


def test_acts_2_4_8_have_clearly_different_hues():
    def hue(c):
        r, g, b = c
        return math.degrees(math.atan2(math.sqrt(3) * (g - b), 2 * r - g - b)) % 360
    vaults, expanse = hue(config.GROUND_RAMPS[2][1]), hue(config.GROUND_RAMPS[4][1])
    assert vaults - expanse > 15                       # indigo (blue-violet) vs teal-steel (blue-cyan)
    assert _lum(config.GROUND_RAMPS[8][1]) < _lum(config.GROUND_RAMPS[2][1])   # Strata is the navy-black one


# --- 37.3 acceptance 1: readability ----------------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("act", ACTS)
def test_ground_luma_stays_readable(act, seed):
    st = _ground_stats(act, seed)
    assert st["p99"] <= 0.104, st
    assert st["p95"] <= 0.09, st


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("act", ACTS)
def test_no_pixel_darker_than_06_dark_or_outside_the_ramp(act, seed):
    st = _ground_stats(act, seed)
    assert st["above_floor"], "a pixel is darker than 0.6 x DARK (before the vignette)"
    assert st["below_ceiling"], "a pixel is brighter than LIGHT (or MID + grit step)"


def test_mask_helpers_really_detect_a_single_bad_pixel():
    surf = pygame.Surface((20, 20))
    surf.fill((30, 40, 50))
    assert _all_at_least(surf, (30, 40, 50)) and _all_at_most(surf, (30, 40, 50))
    assert not _all_at_least(surf, (31, 40, 50)) and not _all_at_most(surf, (30, 40, 49))
    surf.set_at((7, 7), (30, 39, 50))
    assert not _all_at_least(surf, (30, 40, 50))


def test_vignette_is_the_only_thing_darker_than_the_floor(no_vignette):
    surf = _bake(7)
    dark = config.GROUND_RAMPS[7][0]
    floor = tuple(math.ceil(c * 0.6) for c in dark)
    assert _all_at_least(surf, floor)


# --- 37.2 pipeline pieces ---------------------------------------------------------------------------------

def test_noise_layer_uses_only_tones_between_dark_and_light():
    ramp = config.GROUND_RAMPS[2]
    layer = terrain.noise_layer(120, 80, 9, 0.0, 1.0, ramp, random.Random(1))
    assert layer.get_size() == (120, 80)
    data = pygame.image.tobytes(layer, "RGB")
    for c in range(3):
        assert min(data[c::3]) >= ramp[0][c] - 1 and max(data[c::3]) <= ramp[2][c] + 1


def test_noise_layer_ramp_position_limits_narrow_the_range():
    ramp = ((0, 0, 0), (100, 100, 100), (200, 200, 200))
    layer = terrain.noise_layer(60, 60, 20, 0.3, 0.7, ramp, random.Random(2))
    data = pygame.image.tobytes(layer, "RGB")
    assert 58 <= min(data) and max(data) <= 142


def test_macro_noise_stacks_the_three_configured_octaves(monkeypatch):
    calls: List[Tuple[int, float, float]] = []
    real = terrain.noise_layer

    def spy(width, height, cells, lo, hi, ramp, rng):
        calls.append((cells, lo, hi))
        return real(width, height, cells, lo, hi, ramp, rng)

    monkeypatch.setattr(terrain, "noise_layer", spy)
    ground = terrain.macro_noise_ground(100, 100, config.GROUND_RAMPS[0], random.Random(3))
    assert calls == [(9, 0.0, 1.0), (22, 0.05, 0.95), (60, 0.25, 0.75)]
    assert config.GROUND_NOISE_OCTAVES[1][3] == 90 and config.GROUND_NOISE_OCTAVES[2][3] == 50
    assert ground.get_size() == (100, 100) and ground.get_at((5, 5))[3] == 255


def test_grit_count_range_and_brightness_step():
    ramp = config.GROUND_RAMPS[0]
    mid = ramp[1]
    surf = pygame.Surface((400, 400))
    surf.fill(mid)
    terrain.add_grit(surf, ramp, random.Random(4))
    changed = [(x, y) for x in range(400) for y in range(400) if surf.get_at((x, y))[:3] != mid]
    assert 400 <= len(changed) <= config.GROUND_GRIT_COUNT[1]
    for x, y in changed:
        px = surf.get_at((x, y))[:3]
        assert all(abs(px[i] - mid[i]) <= config.GROUND_GRIT_SPREAD for i in range(3))


def test_grit_never_goes_below_06_dark_even_on_the_darkest_acts():
    ramp = config.GROUND_RAMPS[7]
    surf = pygame.Surface((300, 300))
    surf.fill(ramp[1])
    terrain.add_grit(surf, ramp, random.Random(5))
    floor = tuple(math.ceil(c * 0.6) for c in ramp[0])
    assert _all_at_least(surf, floor)


def test_scatter_stays_in_the_world_is_deterministic_and_clusters():
    a = terrain.make_scatter(W, H, random.Random(11))
    b = terrain.make_scatter(W, H, random.Random(11))
    pts = a(3000, 140)
    assert pts == b(3000, 140)
    assert len(pts) == 3000 and a.total == 3000
    assert all(0 <= x < W and 0 <= y < H for x, y in pts)
    cells: Dict[Tuple[int, int], int] = {}
    for x, y in pts:
        cells[(x // 200, y // 200)] = cells.get((x // 200, y // 200), 0) + 1
    uniform_expect = 3000 / 100
    assert max(cells.values()) >= 2 * uniform_expect          # patches, not confetti
    assert len(cells) >= 20                                   # the 30% uniform share still reaches most of the map


def test_scatter_total_tracks_the_stamp_budget():
    scatter = terrain.make_scatter(W, H, random.Random(12))
    scatter(120)
    scatter(30, 100)
    assert scatter.total == 150 <= config.MAX_STAMPS_PER_ACT == 500


def test_make_sprite_is_supersampled_and_antialiased():
    def draw(big):
        pygame.draw.circle(big, (255, 255, 255, 255), (big.get_width() // 2, big.get_height() // 2), 9)

    sprite = terrain.make_sprite(10, 10, draw)
    assert sprite.get_size() == (10, 10) and sprite.get_flags() & pygame.SRCALPHA
    alphas = {sprite.get_at((x, y))[3] for x in range(10) for y in range(10)}
    assert any(0 < a < 255 for a in alphas)                   # soft edge from the 2x -> 1x smoothscale


def test_stamp_centres_rotates_scales_and_fades_without_touching_the_sprite():
    sprite = pygame.Surface((10, 4), pygame.SRCALPHA)
    sprite.fill((200, 0, 0, 255))
    ground = pygame.Surface((100, 100))
    ground.fill((0, 0, 100))
    terrain.stamp(ground, sprite, (50, 50))
    assert ground.get_at((50, 50))[:3] == (200, 0, 0) and ground.get_at((46, 50))[:3] == (200, 0, 0)
    assert ground.get_at((50, 56))[:3] == (0, 0, 100)
    ground.fill((0, 0, 100))
    terrain.stamp(ground, sprite, (50, 50), angle=90)          # a long bar turned upright
    assert ground.get_at((50, 46))[:3] == (200, 0, 0) and ground.get_at((46, 50))[:3] == (0, 0, 100)
    ground.fill((0, 0, 100))
    terrain.stamp(ground, sprite, (50, 50), scale=2.0)
    assert ground.get_at((50, 53))[:3] == (200, 0, 0) and ground.get_at((41, 50))[:3] == (200, 0, 0)
    ground.fill((0, 0, 100))
    terrain.stamp(ground, sprite, (50, 50), alpha=128)
    px = ground.get_at((50, 50))[:3]
    assert 90 <= px[0] <= 110 and 40 <= px[2] <= 60
    assert sprite.get_alpha() in (None, 255) and sprite.get_at((0, 0))[3] == 255


def test_placeholder_decals_exist_for_every_act_and_draw_nothing():
    assert len(terrain.ACT_DECALS) == 10
    assert [getattr(terrain, f"decals_act_{i}") for i in range(10)] == list(terrain.ACT_DECALS)
    surf = pygame.Surface((50, 50))
    surf.fill((9, 9, 9))
    before = pygame.image.tobytes(surf, "RGB")
    for decals in terrain.ACT_DECALS:
        decals(surf, random.Random(1), terrain.make_scatter(50, 50, random.Random(1)))
    assert pygame.image.tobytes(surf, "RGB") == before


def test_old_theme_flourishes_and_membrane_blobs_are_gone():
    assert not hasattr(graphics, "_draw_theme_details")


# --- 37.3 acceptance 4: determinism, positions unchanged ----------------------------------------------------

def _digest(act: int, seed: int) -> str:
    return hashlib.sha1(pygame.image.tobytes(_bake(act, seed), "RGB")).hexdigest()


@pytest.mark.parametrize("act", [0, 4, 9])
def test_same_seed_same_texture(act):
    assert _digest(act, 145) == _digest(act, 145)


def test_different_seed_or_act_gives_a_different_texture():
    assert _digest(2, 7) != _digest(2, 999)
    assert _digest(2, 7) != _digest(6, 7)


def test_bake_does_not_consume_the_global_random_stream():
    random.seed(5)
    state = random.getstate()
    _bake(3, 0)
    assert random.getstate() == state


def test_creature_and_hazard_positions_for_a_seed_are_unchanged_from_main():
    """Pinned from origin/main (a27dffc) for seed 7: the new bake draws only from its own random streams."""
    diff = {"hp": 1.0, "damage": 1.0, "speed": 1.0, "xp": 1.0, "elite_chance": 0.0}
    gen = MapGenerator()
    gen.load_map(3, 7)
    creatures = gen.spawn_encounter_creatures(6, diff, 7)
    assert [(c.pos.x, c.pos.y) for c in creatures] == [
        (763.0, 408.0), (248.0, 1781.0), (1293.0, 218.0), (276.0, 988.0), (285.0, 1228.0), (1258.0, 353.0)]
    hazards = HazardManager()
    hazards.generate_for_map(gen.hazard_types, count=5, seed=7)
    assert [(z.pos.x, z.pos.y) for z in hazards.zones][:4] == [
        (508.0, 1008.0), (348.0, 1297.0), (1393.0, 318.0), (276.0, 376.0)]


# --- timing -------------------------------------------------------------------------------------------------

@pytest.mark.slow
def test_whole_ground_bake_median_across_acts_is_well_inside_the_budgets():
    """037 alone: every act <= 90 ms (median of 5); ceiling 130 ms for the whole pipeline after 038/039."""
    for act in ACTS:
        times = []
        for _ in range(5):
            t = time.perf_counter()
            _bake(act)
            times.append((time.perf_counter() - t) * 1000)
        times.sort()
        assert times[2] <= 90, (act, times)
