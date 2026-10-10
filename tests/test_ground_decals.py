"""TASK-038 / TASK-039 acceptance: act decals + landmarks, all ten acts (baked into the ground texture: no per-frame cost)."""
from __future__ import annotations

import functools
import hashlib
import math
import random
import statistics
import time
from typing import Dict, List, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.maps.generator import MapGenerator
from blob_evolution.utils import graphics, layers, terrain
from blob_evolution.utils.graphics import draw_blob, generate_map_texture
from blob_evolution.utils.vector2 import Vector2

W, H = config.WORLD_WIDTH, config.WORLD_HEIGHT
DECAL_ACTS = range(10)
SEEDS = (0, 7, 145, 999)
LUMA_LIMIT = 0.104


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


LIN = [_lin(i) for i in range(256)]


def _lum(r, g, b) -> float:
    return 0.2126 * LIN[int(r + 0.5)] + 0.7152 * LIN[int(g + 0.5)] + 0.0722 * LIN[int(b + 0.5)]


def _bake(act: int, seed: int = 7) -> pygame.Surface:
    th = config.MAP_THEMES[act]
    return generate_map_texture(W, H, th["color"], th["accent"], seed, act)


def _ground() -> pygame.Surface:
    return pygame.Surface((W, H))


def _run_decals(act: int, seed: int = 7, surface: pygame.Surface = None) -> Tuple[pygame.Surface, object, random.Random]:
    """The decal pass alone on a flat MID ground, with the bake's own stamp stream."""
    surf = surface or _ground()
    if surface is None:
        surf.fill(config.GROUND_RAMPS[act][1])
    rng = random.Random(seed ^ 0x5EED)
    scatter = terrain.make_scatter(W, H, rng)
    terrain.ACT_DECALS[act](surf, rng, scatter)
    return surf, scatter, rng


@pytest.fixture
def no_vignette(monkeypatch):
    monkeypatch.setattr(graphics, "_make_vignette", lambda w, h: pygame.Surface((w, h), pygame.SRCALPHA))


def _bare(act: int, seed: int) -> pygame.Surface:
    orig = graphics._make_vignette
    graphics._make_vignette = lambda w, h: pygame.Surface((w, h), pygame.SRCALPHA)
    try:
        return _bake(act, seed)
    finally:
        graphics._make_vignette = orig


# --- 38 acceptance 2: stamps <= 500 and decal time <= 25 ms ------------------------------------------------------

class _StampSpy:
    def __init__(self, monkeypatch):
        self.calls: List[tuple] = []
        real = terrain.stamp

        def spy(surface, sprite, pos, angle=0.0, scale=1.0, alpha=255):
            self.calls.append((sprite, pos, angle, scale, alpha))
            return real(surface, sprite, pos, angle, scale, alpha)

        monkeypatch.setattr(terrain, "stamp", spy)


@pytest.mark.parametrize("act", DECAL_ACTS)
def test_stamps_per_act_stay_inside_the_500_cap(act, monkeypatch):
    spy = _StampSpy(monkeypatch)
    _, scatter, _ = _run_decals(act)
    assert len(spy.calls) > 10                                    # the act really is decorated (act 5 draws its ripples directly)
    assert len(spy.calls) <= config.MAX_STAMPS_PER_ACT == 500
    assert scatter.total <= config.MAX_STAMPS_PER_ACT


@pytest.mark.parametrize("act", DECAL_ACTS)
def test_decal_pass_time_guard(act):
    """Loose guard in the default suite (measured 4-17 ms); the strict 25 ms cap is in the slow suite."""
    t = time.process_time()
    _run_decals(act)
    assert (time.process_time() - t) * 1000 <= 100


@pytest.mark.slow
@pytest.mark.parametrize("act", DECAL_ACTS)
def test_decal_pass_time_is_inside_25_ms(act):
    times = []
    for _ in range(7):
        t = time.process_time()
        _run_decals(act)
        times.append((time.process_time() - t) * 1000)
    assert statistics.median(times) <= 25, times


@pytest.mark.parametrize("act", DECAL_ACTS)
def test_bake_time_guard(act):
    t = time.process_time()
    _bake(act)
    assert (time.process_time() - t) * 1000 <= 400                # loose; strict budget in the slow suite


@pytest.mark.slow
@pytest.mark.parametrize("act", DECAL_ACTS)
def test_full_ground_bake_median_of_7_is_inside_130_ms(act):
    times = []
    for _ in range(7):
        t = time.process_time()
        _bake(act)
        times.append((time.process_time() - t) * 1000)
    assert statistics.median(times) <= 130, times


# --- determinism, global random, positions unchanged ------------------------------------------------------------

def _digest(act: int, seed: int) -> str:
    return hashlib.sha1(pygame.image.tobytes(_bake(act, seed), "RGB")).hexdigest()


@pytest.mark.parametrize("act", DECAL_ACTS)
def test_decals_are_deterministic_per_seed_and_differ_between_seeds(act):
    assert _digest(act, 145) == _digest(act, 145)
    assert _digest(act, 145) != _digest(act, 999)


@pytest.mark.parametrize("act", DECAL_ACTS)
def test_decals_use_only_the_stamp_stream_and_never_the_global_random(act):
    random.seed(11)
    state = random.getstate()
    _run_decals(act, 3)
    assert random.getstate() == state


@pytest.mark.parametrize("act", DECAL_ACTS)
def test_decals_are_a_pure_overlay_on_the_same_ground(act, monkeypatch):
    """Swapping the decal pass for the placeholder gives the same ground (the decals use their own random stream)."""
    decorated = pygame.image.tobytes(_bare(act, 7), "RGB")
    monkeypatch.setattr(terrain, "ACT_DECALS", terrain.ACT_DECALS[:act] + (terrain._no_decals,) + terrain.ACT_DECALS[act + 1:])
    bare = pygame.image.tobytes(_bare(act, 7), "RGB")
    assert bare != decorated
    idx = range(0, len(bare), 3 * 97)
    mean_diff = sum(abs(bare[i + c] - decorated[i + c]) for i in idx for c in range(3)) / (3 * len(idx))
    assert mean_diff < 6                                          # same macro layout; decals only touch a few pixels


def test_creature_and_hazard_positions_are_unchanged_by_the_decals():
    """Pinned values from origin/main (also pinned in test_ground_terrain.py): decals draw nothing but pixels."""
    diff = {"hp": 1.0, "damage": 1.0, "speed": 1.0, "xp": 1.0, "elite_chance": 0.0}
    gen = MapGenerator()
    gen.load_map(3, 7)
    creatures = gen.spawn_encounter_creatures(6, diff, 7)
    assert [(c.pos.x, c.pos.y) for c in creatures][:2] == [(763.0, 408.0), (248.0, 1781.0)]
    from blob_evolution.systems.hazards import HazardManager
    hazards = HazardManager()
    hazards.generate_for_map(gen.hazard_types, count=5, seed=7)
    assert [(z.pos.x, z.pos.y) for z in hazards.zones][:2] == [(508.0, 1008.0), (348.0, 1297.0)]


# --- 38 acceptance 1: the 037 luma rules still hold for every decorated act ---------------------------------------

@functools.lru_cache(maxsize=None)
def _luma_sample(act: int, seed: int) -> Tuple[float, float, float, float]:
    """(p95, p99, share of pixels > 0.104, share in the central 1200 x 800) of the pre-vignette bake."""
    surf = _bare(act, seed)
    data = pygame.image.tobytes(surf, "RGB")
    lums = []
    central = []
    for p in range(0, W * H, 101):
        i = p * 3
        v = _lum(data[i], data[i + 1], data[i + 2])
        lums.append(v)
        if 400 <= p % W < 1600 and 600 <= p // W < 1400:
            central.append(v)
    lums.sort()
    n = len(lums)
    return (lums[int(n * 0.95)], lums[int(n * 0.99)], sum(1 for v in lums if v > LUMA_LIMIT) / n,
            sum(1 for v in central if v > LUMA_LIMIT) / len(central))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("act", DECAL_ACTS)
def test_decorated_ground_keeps_the_037_luma_limits_and_highlights_stay_thin(act, seed):
    p95, p99, bright, central = _luma_sample(act, seed)
    assert p99 <= LUMA_LIMIT and p95 <= 0.09, (p95, p99)
    assert bright < 0.01, bright                                  # R1: thin highlights cover < 1% of the pixels
    assert central < 0.025, central                               # ... the central band holds the lake/dais landmarks (<= 1.8% measured)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("act", DECAL_ACTS)
def test_no_decal_pixel_is_darker_than_06_dark(act, seed, no_vignette):
    dark = config.GROUND_RAMPS[act][0]
    floor = tuple(math.ceil(c * 0.6) for c in dark)
    data = pygame.image.tobytes(_bake(act, seed), "RGB")
    for c in range(3):
        assert min(data[c::3]) >= floor[c], (c, min(data[c::3]), floor)


# --- 38 acceptance 3: no decal wider than 3 px has luma > 0.104 --------------------------------------------------

def _wide_bright(sprite: pygame.Surface, alpha: int, mid: tuple) -> bool:
    """True when some 4 x 4 block of the sprite, composited over MID, is brighter than 0.104."""
    w, h = sprite.get_size()
    data = pygame.image.tobytes(sprite, "RGBA")
    bright = []
    for y in range(h):
        row = []
        for x in range(w):
            i = (y * w + x) * 4
            k = data[i + 3] / 255 * alpha / 255
            row.append(_lum(*(mid[c] * (1 - k) + data[i + c] * k for c in range(3))) > LUMA_LIMIT)
        bright.append(row)
    run = [[all(r[x:x + 4]) for x in range(w - 3)] for r in bright]
    return any(all(run[y + j][x] for j in range(4)) for y in range(h - 3) for x in range(w - 3))


@pytest.mark.parametrize("act", DECAL_ACTS)
def test_no_stamped_sprite_has_a_bright_part_wider_than_3_px(act, monkeypatch):
    spy = _StampSpy(monkeypatch)
    _run_decals(act)
    mid = config.GROUND_RAMPS[act][1]
    seen: Dict[tuple, tuple] = {}
    for sprite, _, _, _, alpha in spy.calls:
        seen[(id(sprite), alpha)] = (sprite, alpha)
    assert seen
    bad = [(s.get_size(), a) for s, a in seen.values() if _wide_bright(s, a, mid)]
    assert not bad, bad


def test_the_wide_bright_check_detects_a_wide_bright_sprite():
    mid = config.GROUND_RAMPS[0][1]
    wide = pygame.Surface((8, 8), pygame.SRCALPHA)
    wide.fill((255, 255, 255, 255))
    thin = pygame.Surface((8, 8), pygame.SRCALPHA)
    pygame.draw.rect(thin, (255, 255, 255, 255), (0, 3, 8, 3))        # 3 px wide
    assert _wide_bright(wide, 255, mid) and not _wide_bright(thin, 255, mid)


# --- 38 acceptance 4: no rigid parallel stripe pattern -----------------------------------------------------------

def _periodic_spike(signal: List[float], dec: int = 4, lo: int = 10, hi: int = 200) -> float:
    """Strongest autocorrelation at a lag that repeats: max over L of min(ac(L), ac(2L)) of the high-passed row.

    A stripe pattern correlates with itself at L, 2L, 3L...; two isolated features (a ring, a pair of crystals)
    correlate at one lag only and are not a 'pattern'."""
    n = len(signal) // dec
    x = [sum(signal[i * dec:(i + 1) * dec]) / dec for i in range(n)]
    k = 4
    hp = [x[i] - sum(x[max(0, i - k):i + k + 1]) / len(x[max(0, i - k):i + k + 1]) for i in range(n)]
    energy = sum(v * v for v in hp)
    if energy <= 1e-12:
        return 0.0
    ac = {}
    for lag in range(lo // dec, min(2 * hi // dec, n - 5)):
        ac[lag] = sum(hp[i] * hp[i + lag] for i in range(n - lag)) / (energy * (n - lag) / n)
    best = 0.0
    for lag in range(lo // dec, hi // dec):
        if lag in ac and 2 * lag in ac:
            best = max(best, min(ac[lag], ac[2 * lag]))
    return best


def _worst_row_spike(surf: pygame.Surface, step: int = 32) -> float:
    crop = surf.subsurface((400, 600, 1200, 800))
    data = pygame.image.tobytes(crop, "RGB")
    luma = [0.2126 * LIN[data[i]] + 0.7152 * LIN[data[i + 1]] + 0.0722 * LIN[data[i + 2]] for i in range(0, len(data), 3)]
    return max(_periodic_spike(luma[y * 1200:(y + 1) * 1200]) for y in range(0, 800, step))


def test_038_follow_up_act_2_alphas():
    assert terrain.FACET_ALPHA == 100 and terrain.RUNE_DOT_ALPHA == 150 and terrain.CRYSTAL_GLOW_ALPHA == 8


def test_the_stripe_metric_flags_real_stripes_and_not_feature_pairs():
    n = 1200
    stripes = [0.05 + (0.04 if (x % 160) < 2 else 0.0) for x in range(n)]
    pair = [0.05] * n
    for x in (500, 800):
        pair[x:x + 12] = [0.09] * 12
    assert _periodic_spike(stripes) > 0.5
    assert _periodic_spike(pair) < 0.5


def test_the_regular_160_px_flagstone_grid_would_fail_so_it_is_jittered(monkeypatch):
    monkeypatch.setattr(terrain, "GRID_JITTER", 0)
    assert _worst_row_spike(_bake(2, 7)) > 0.5                    # the plan's perfectly regular grid is a stripe pattern
    monkeypatch.setattr(terrain, "GRID_JITTER", 18)
    assert _worst_row_spike(_bake(2, 7)) < 0.5


@pytest.mark.parametrize("seed", (7, 999))
@pytest.mark.parametrize("act", DECAL_ACTS)
def test_no_rigid_stripe_pattern_in_a_1200x800_crop(act, seed):
    assert _worst_row_spike(_bake(act, seed)) < 0.5


@pytest.mark.slow
@pytest.mark.parametrize("seed", (0, 145))
@pytest.mark.parametrize("act", DECAL_ACTS)
def test_no_rigid_stripe_pattern_in_the_other_two_seeds(act, seed):
    assert _worst_row_spike(_bake(act, seed), step=16) < 0.5


# --- landmarks and layout ---------------------------------------------------------------------------------------

def test_the_great_seam_stays_at_least_250_px_from_the_centre(monkeypatch):
    strokes = []
    real = terrain._stroke
    monkeypatch.setattr(terrain, "_stroke", lambda target, segs, width, rgba, *a: (strokes.append((width, segs)), real(target, segs, width, rgba, *a))[1])
    for seed in SEEDS:
        strokes.clear()
        _run_decals(3, seed)
        seams = [segs for width, segs in strokes if width == 14]
        assert len(seams) == 1
        dist = min(math.hypot(x0 - W / 2, y0 - H / 2) for x0, y0, _, _ in seams[0])
        assert dist >= 250, (seed, dist)


def test_the_act_4_lake_stays_in_the_middle_band_and_the_act_2_dais_is_at_the_centre(monkeypatch):
    spy = _StampSpy(monkeypatch)
    _run_decals(2)
    assert spy.calls[-1][1] == (W // 2, H // 2)                    # the dais is stamped last, at the world centre
    for seed in SEEDS:
        spy.calls.clear()
        _run_decals(4, seed)
        x, y = spy.calls[-1][1]
        assert 650 <= x <= 1350 and 650 <= y <= 1350


# sha1[:16] of the full texture (vignette included) at seeds 7 and 145, taken at the TASK-038 tip (dd4bccd);
# act 2 was re-pinned by the 038 follow-up commit
ACTS_0_4_PINNED = {
    0: ("4a24928a7812698e", "3633e2338e8b0ed4"),
    1: ("0876fe1889b74a4b", "6819ae4040346e30"),
    2: ("c3b4a43e961ea082", "0fde6e336c1aa062"),     # re-pinned by the 038 follow-up (dimmer crystals / rune dots / glow)
    3: ("00a6c0bd10a543d6", "e1954e966d9b1e7c"),
    4: ("4ab7d877fc9f2bc7", "fcda2a7ad4125437"),     # BUG-119: re-pinned (dimmer frost ferns, crack highlight 110, drift fill 56)
}


# BUG-117: the same pins for pygame-ce's GENERIC smoothscale backend (the one non-x86 machines use; SSE2 and MMX give the
# digests above). Taken at the same commits (dd4bccd, act 2 at 050ad5a) with set_smoothscale_backend("GENERIC"); at those
# commits SSE2 reproduced ACTS_0_4_PINNED exactly, so both tables pin the same 038-tip textures.
ACTS_0_4_PINNED_GENERIC = {
    0: ("0c11e40a71b9d526", "6913b43c22536ca5"),
    1: ("4c5940a07e15512b", "c1c793aafd402973"),
    2: ("ce2acd5b2c0fb1bf", "cee61ec92976ad7b"),
    3: ("2e3cb86c153aa32e", "f1c39bdddc647fdf"),
    4: ("fa578000d8850d32", "1d93800a6f1f915a"),     # BUG-119 re-pin, as above
}
PINS_BY_BACKEND = {"SSE2": ACTS_0_4_PINNED, "MMX": ACTS_0_4_PINNED, "GENERIC": ACTS_0_4_PINNED_GENERIC}


@pytest.fixture
def smoothscale_backend(request):
    """Run under the requested smoothscale backend (skip where the CPU lacks it), then restore the default."""
    before = pygame.transform.get_smoothscale_backend()
    try:
        pygame.transform.set_smoothscale_backend(request.param)
    except ValueError:
        pytest.skip(f"smoothscale backend {request.param} not available here")
    yield request.param
    pygame.transform.set_smoothscale_backend(before)


@pytest.mark.parametrize("smoothscale_backend", ["GENERIC", "SSE2"], indirect=True)
@pytest.mark.parametrize("act", sorted(ACTS_0_4_PINNED))
def test_acts_0_to_4_ground_is_pixel_identical_to_the_038_tip(act, smoothscale_backend):
    """TASK-039 only adds acts 5-9: the acts 0-4 textures of a seed must not move by a single pixel (on every backend)."""
    pins = PINS_BY_BACKEND[smoothscale_backend]
    assert (_digest(act, 7)[:16], _digest(act, 145)[:16]) == pins[act]


# --- 38 acceptance: decals must not hide gameplay-critical visuals (contrast with everything on) -------------------

def _contrast(a, b) -> float:
    la, lb = _lum(*a), _lum(*b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _mean(px) -> tuple:
    return tuple(sum(p[i] for p in px) / len(px) for i in range(3))


@pytest.fixture(scope="module")
def _screen():
    pygame.init()
    return pygame.display.set_mode((1200, 800))


@pytest.mark.parametrize("lowhp", (False, True))
@pytest.mark.parametrize("act", DECAL_ACTS)
def test_player_enemy_shots_and_xp_orbs_keep_contrast_over_ground_decals_fog_and_overlay(act, lowhp, _screen):
    sw, sh = 1200, 800
    ring = [(dx, dy) for dy in range(-19, 20) for dx in range(-19, 20) if 15 <= math.hypot(dx, dy) <= 19]
    bg = [(dx, dy) for dy in range(-30, 31) for dx in range(-30, 31) if 23 <= math.hypot(dx, dy) <= 30]
    disc = [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3) if math.hypot(dx, dy) <= 2]
    dbg = [(dx, dy) for dy in range(-14, 15) for dx in range(-14, 15) if 9 <= math.hypot(dx, dy) <= 14]
    gen = MapGenerator()
    gen.load_map(act, 7)
    depth = layers.DepthLayers(act, 7)
    red = layers.build_overlay(*config.LOW_HP_OVERLAY)
    rng = random.Random(100 + act)
    samples = [(rng.randint(500, 1500), rng.randint(500, 1500), rng.randint(70, sw - 70), rng.randint(70, sh - 70)) for _ in range(14)]
    samples[0] = (1000, 1000, sw // 2, sh // 2)
    samples[1] = (1000, 1000, 80, 80)
    samples[2] = (1000, 1000, sw - 80, sh - 80)

    def base(cam):
        gen.draw_background(_screen, cam, Vector2(0, 0))
        depth.blit_fog(_screen, cam, Vector2(0, 0))
        _screen.blit(red if lowhp else depth.vignette, (0, 0))

    worst = {"body": 99.0, "shot": 99.0, "xp": 99.0}
    for cx, cy, px, py in samples:
        cam = Vector2(cx, cy)
        base(cam)
        around = _mean([_screen.get_at((px + dx, py + dy)) for dx, dy in bg])
        base(cam)
        draw_blob(_screen, (px, py), 20, config.COLOR_PLAYER, config.COLOR_PLAYER_CORE, look=(1, 0))
        worst["body"] = min(worst["body"], _contrast(_mean([_screen.get_at((px + dx, py + dy)) for dx, dy in ring]), around))
        for key, colour in (("shot", config.COLOR_PROJECTILE_ENEMY), ("xp", config.COLOR_XP)):
            base(cam)
            around_d = _mean([_screen.get_at((px + dx, py + dy)) for dx, dy in dbg])
            pygame.draw.circle(_screen, colour, (px, py), 5)
            worst[key] = min(worst[key], _contrast(_mean([_screen.get_at((px + dx, py + dy)) for dx, dy in disc]), around_d))
    assert worst["body"] >= 3.0, worst
    assert worst["shot"] >= (3.4 if act == 2 else 3.0) and worst["xp"] >= 3.0, worst      # act 2: 038 follow-up target 3.4
