"""TASK-058 (A1): TASK-045 boss art. Spec section 6 tests 1-4, 7, 8, 12, 13 and 15 (5, 6 and 14 are A2's).

The art is visual only: stats, hitboxes and every scripted fight digest are 057's; GFX_BOSS_ART = False draws
057's (= main's) pixels exactly. Goldens below were recorded on task-057-mini-bosses 3d9e4d7 with tests/boss_trace.py.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import sys
from typing import Dict, List

import pygame
import pytest

from blob_evolution import config
from blob_evolution.entities import boss as boss_module
from blob_evolution.entities.boss import Boss
from blob_evolution.systems.overworld import NodeType, OverworldMap
from blob_evolution.utils import boss_shapes as bs
from blob_evolution.utils.graphics import get_graphics_cache
from blob_evolution.utils.vector2 import Vector2

from boss_trace import ENTITIES, KINDS, SEEDS, fight_digest, make_boss, scene_digest, stats_table
from test_boss_framework import _expected as golden

STATS_057 = "8b74e7cd547f27b5"          # sha1[:16] of the sorted stats_table() on 057
SCENE_057 = "bb82cc221eb61d7c"          # scene_digest() on 057 (the pre-art Boss.draw)
GRAY = (128, 128, 128)
CAM = Vector2(1200, 1100)
NO_SHAKE = Vector2(0, 0)
DT = 1 / 60


@pytest.fixture(autouse=True)
def _art_on(monkeypatch):
    pygame.font.init()                               # the game initialises pygame; plates need the font module
    monkeypatch.setattr(config, "GFX_BOSS_ART", True)
    monkeypatch.setattr(config, "GFX_READABILITY", True)
    bs.clear()
    gc = get_graphics_cache()
    before = (dict(gc._circles), dict(gc._shadows))
    yield
    bs.clear()
    gc._circles.clear(), gc._circles.update(before[0])          # leave the shared caches as found (other test files
    gc._shadows.clear(), gc._shadows.update(before[1])          # bound their size)


def lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(rgb) -> float:
    return 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2])


def contrast(a, b) -> float:
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _all_bosses() -> List[Boss]:
    return [make_boss(act, mini, var) for act, mini, var in ENTITIES]


# ---- 1. stats untouched, no AI diff ----------------------------------------------------------------------------------

def test_stats_are_057_s_for_every_warden_slot_and_anchor():
    st = stats_table()
    assert len(st) == 50
    assert hashlib.sha1(repr(sorted(st.items())).encode()).hexdigest()[:16] == STATS_057


def test_warm_and_draw_change_no_gameplay_field():
    """warm_art() and draw() (art on and off) write only the draw-private _art_* / _flash_* fields."""
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    for flag in (True, False):
        config.GFX_BOSS_ART = flag
        for b in _all_bosses():
            b.take_damage(b.max_hp * 0.6)
            b.update(DT, Vector2(1000, 900), [])

            def snap():
                return {k: ((v.x, v.y) if isinstance(v, Vector2) else v) for k, v in vars(b).items()
                        if not k.startswith(("_art", "_flash"))}
            before = snap()
            b.warm_art()
            b.draw(screen, CAM, NO_SHAKE)
            assert snap() == before, (flag, b.name)


@pytest.mark.parametrize("act", range(10))
def test_fights_drawn_with_the_art_keep_the_recorded_digests(act):
    """Every scripted fight of the layer (seed 3), drawn every 45 frames with the art on: state and RNG per frame equal
    the recorded (undrawn) digests, so drawing perturbs nothing."""
    for kind in KINDS:
        key = f"{act}/{kind}/{SEEDS[0]}"
        assert fight_digest(act, kind, SEEDS[0], draw="blind") == golden(key), key


@pytest.mark.slow
@pytest.mark.parametrize("act", range(10))
def test_all_seeds_drawn_with_the_art_keep_the_recorded_digests(act):
    for kind in KINDS:
        for seed in SEEDS[1:]:
            key = f"{act}/{kind}/{seed}"
            assert fight_digest(act, kind, seed, draw="blind") == golden(key), key


def test_every_warden_and_anchor_has_art_and_out_of_table_acts_keep_main_s_draw():
    keys = [b.art_key for b in _all_bosses()]
    assert keys[0::3] == bs.BOSSES and sorted(k for i, k in enumerate(keys) if i % 3) == sorted(bs.MINIS)
    for b in _all_bosses():
        assert bs.entity(b.art_key)["R"] == b.size or not b.is_miniboss       # anchors: spec radius == hitbox
        assert bs.entity(b.art_key)["layer"] == b.act_index
    assert Boss(Vector2(0, 0), 12, None).art_key is None
    assert Boss(Vector2(0, 0), 12, None, miniboss=True).art_key is None


# ---- 2 / 3. silhouettes distinct, also in grayscale ------------------------------------------------------------------

def _fg(surf: pygame.Surface, bg) -> pygame.mask.Mask:
    """Pixels that differ from the flat background in any channel by more than 8."""
    m = pygame.mask.from_threshold(surf, bg, (9, 9, 9, 255))
    m.invert()
    return m


def _outside_mask(b: Boss, n: int, gray: bool) -> pygame.mask.Mask:
    """b drawn alone (spec 9.2: glow off, pulse 0) on flat gray, centred on an n x n canvas; the body disc
    (R + 2) is erased for blob-bodied entities."""
    s = pygame.Surface((n, n))
    s.fill(GRAY)
    bs.draw_boss(s, b.art_key, 1, n // 2, n // 2, int(b.size), 0.0, math.radians(35), glow=False, pulse=0.0,
                 blob_fn=boss_module.draw_blob_cached)
    bg = GRAY
    if gray:
        s = pygame.transform.grayscale(s)
        bg = s.get_at((0, 0))[:3]
    m = _fg(s, bg)
    if bs._flags(b.art_key, 1)[0]:
        d = pygame.Surface((n, n), pygame.SRCALPHA)
        pygame.draw.circle(d, (255, 255, 255, 255), (n // 2, n // 2), int(b.size) + 2)
        m.erase(pygame.mask.from_surface(d), (0, 0))
    return m


@pytest.mark.parametrize("gray", [False, True], ids=["colour", "grayscale"])
@pytest.mark.parametrize("group", ["wardens", "anchors"])
def test_silhouettes_distinct(group, gray):
    """Pairs within a group differ by >= 40 % of the smaller outside-disc set (colour and grayscale); in colour each
    warden has >= 15 % of its disc area outside it, each anchor >= 10 % (polygon / ring anchors: whole mask).
    Ash sits at 14.99 % (15.0 at the module's 0.1 % rounding): reported to the Visual Designer."""
    bosses = [b for b in _all_bosses() if b.is_miniboss == (group == "anchors")]
    n = int(2 * 1.95 * max(b.size for b in bosses)) + 24
    masks = {b.art_key: _outside_mask(b, n, gray) for b in bosses}
    least = 15.0 if group == "wardens" else 10.0
    for b in bosses if not gray else ():            # area rule in colour; grayscale re-checks the pairs (test 3)
        share = round(100 * masks[b.art_key].count() / (math.pi * b.size ** 2), 1)     # spec 9.6 reports 0.1 %
        assert share >= least, (b.art_key, share)
    for a, c in itertools.combinations(masks, 2):
        A, B = masks[a], masks[c]
        xd = A.count() + B.count() - 2 * A.overlap_area(B, (0, 0))
        assert xd >= 0.40 * min(A.count(), B.count()), (a, c, xd / min(A.count(), B.count()))


# ---- 4. rim / element contrast ---------------------------------------------------------------------------------------

def test_module_ground_tones_are_the_game_s_light_tones():
    assert [tuple(config.GROUND_RAMPS[a][2]) for a in range(10)] == [tuple(g) for g in bs.GROUND]


def test_every_rim_and_element_outline_is_3_to_1_on_its_layer_s_light_ground():
    for key in bs.ALL_KEYS:
        d = bs.entity(key)
        for ph in range(1, d["phases"] + 1):
            assert contrast(bs.pal(key, ph)[2], bs.GROUND[d["layer"]]) >= 3.0, (key, ph)
    for layer, cols in bs.ELEM.items():
        for name, col in cols.items():
            assert contrast(col, bs.GROUND[layer]) >= 3.0, (layer, name)


def test_drawn_rim_pixel_is_the_rim_colour():
    """The 3 px (warden) / 2 px (anchor) rim really lands at R - 1 in the composed frame, over the body."""
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    cx, cy = config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2
    for b in _all_bosses():
        if bs._flags(b.art_key, 1)[2] != "solid" or b.art_key == "last_whole":   # Last Whole's arc band covers its rim
            continue
        screen.fill(bs.GROUND[b.act_index])
        b.pos = CAM.copy()
        b.draw(screen, CAM, NO_SHAKE)
        K = bs.pal(b.art_key, 1)[2]
        hits = sum(tuple(screen.get_at((int(cx + math.cos(a) * (b.size - 1)), int(cy + math.sin(a) * (b.size - 1)))))[:3] == K
                   for a in (i * math.tau / 72 for i in range(72)))
        assert hits >= 24, (b.art_key, hits)          # parts of the front sprite may sit on the rim


# ---- 7. flash limits -------------------------------------------------------------------------------------------------

def _flash_starts(b: Boss, frames: int, hit_every: int) -> List[int]:
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    starts, prev = [], False
    for f in range(frames):
        if f % hit_every == 0:
            b.take_damage(0.001)
        b.update(DT, Vector2(1000, 900), [])
        b.draw(screen, CAM, NO_SHAKE)
        on = b.pulse_time - b._flash_t0 < config.BOSS_FLASH_TIME
        if on and not prev:
            starts.append(f)
        prev = on
    return starts


def test_twenty_hits_in_one_second_start_at_most_three_flashes():
    for act in (0, 3, 9):
        b = make_boss(act, False, 0)
        assert len(_flash_starts(b, 60, 3)) <= 3, act


def test_one_hit_still_flashes_and_hits_inside_the_window_still_deal_damage():
    b = make_boss(0, False, 0)
    hp = b.hp
    starts = _flash_starts(b, 30, 2)
    assert starts and starts[0] == 0 and b.hp < hp - 14 * 0.001 * 0.9


def test_luminance_flips_of_any_8x8_area_stay_at_or_below_3_hz():
    """5 s of a boss hit every 3rd frame. A flip is a jump of an 8 x 8 block's mean luminance by > 40 against the
    direction of that block's previous jump (light -> dark -> light); at most 6 per second (3 Hz)."""
    for act, mini, var in ((0, False, 0), (9, False, 0), (3, True, 0)):
        b = make_boss(act, mini, var)
        R = int(b.size)
        screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        cx, cy = config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2
        blocks = [pygame.Rect(cx + x, cy + y, 8, 8) for x in range(-R, R, 8) for y in range(-R, R, 8)]
        prev: Dict[int, float] = {}
        last_sign: Dict[int, int] = {}
        flips = [0] * len(blocks)
        for f in range(300):
            if f % 3 == 0:
                b.take_damage(0.001)
            b.update(DT, Vector2(1000, 900), [])
            b.pos = CAM.copy()
            screen.fill(bs.GROUND[act])
            b.draw(screen, CAM, NO_SHAKE)
            for i, r in enumerate(blocks):
                c = pygame.transform.average_color(screen, r)
                L = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
                if i in prev and abs(L - prev[i]) > 40:
                    sign = 1 if L > prev[i] else -1
                    if last_sign.get(i, -sign) != sign:
                        flips[i] += 1
                    last_sign[i] = sign
                prev[i] = L
        assert max(flips) <= 6 * 5, (act, mini, max(flips))


# ---- 8. phase change ---------------------------------------------------------------------------------------------------

def _spy(monkeypatch, name):
    calls = []
    real = getattr(bs, name)

    def spy(*a, **k):
        calls.append((a, k))
        return real(*a, **k)
    monkeypatch.setattr(bs, name, spy)
    return calls


def test_phase_change_selects_the_new_set_fades_and_rings_once(monkeypatch):
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    b = make_boss(3, False, 0)                       # Ash, three phases
    b.draw(screen, CAM, NO_SHAKE)
    boss_calls, rings = _spy(monkeypatch, "draw_boss"), _spy(monkeypatch, "ring_out")
    b.take_damage(b.max_hp * 0.55)
    for _ in range(70):
        b.update(DT, Vector2(1000, 900), [])
        b.draw(screen, CAM, NO_SHAKE)
    phases = [a[2] for a, _ in boss_calls]
    fades = [k["fade"] for _, k in boss_calls]
    assert set(phases) == {2} and all(k["fade_from"] == 1 for _, k in boss_calls)
    assert fades == sorted(fades) and fades[0] < 0.1 and fades[-1] == 1.0          # monotonic 0.6 s cross-fade
    ph = [(a[3], a[5]) for a, k in rings if k.get("style") == "phase"]
    alphas = [al for _, al in ph]
    radii = [r for r, _ in ph]
    assert alphas[0] == pytest.approx(config.BOSS_PHASE_RING_ALPHA, abs=5) and alphas[-1] < 10
    assert alphas == sorted(alphas, reverse=True) and radii == sorted(radii)
    assert radii[0] == pytest.approx(b.size, abs=4) and radii[-1] <= bs.phase_ring_end(int(b.size))
    assert len(ph) == round(config.BOSS_PHASE_RING_TIME / DT)                       # one ring, 0.8 s, then none
    assert {k[3] for k in bs._layers if k[:3] == ("ash", 2, int(b.size))} == {"b", "f"}      # phase 2 set baked


def test_faded_layers_are_restored_to_full_alpha():
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    bs.draw_boss(screen, "ash", 2, 600, 400, 80, 0.0, 0.0, blob_fn="cached", fade_from=1, fade=0.4)
    for k, v in bs._layers.items():
        if v is not None:
            assert v[0].get_alpha() in (None, 255), k


@pytest.mark.parametrize("act,names,notches", [
    (8, ("Warden of Ascent", "Warden of Echoes", "Warden of Stillness"), (0.66, 0.33)),
    (9, ("Prime Anchor",) * 3, (0.66, 0.25)),
    (0, ("Warden of Sprouting",) * 2, (0.5,)),
])
def test_plate_name_pips_and_bar_notches_follow_the_phase_table(act, names, notches, monkeypatch):
    """Layer 9 shows its three names; pips light per phase; notches at the roster thresholds (L10 66/25)."""
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    plates, pips, bars = _spy(monkeypatch, "name_plate"), _spy(monkeypatch, "phase_pips"), _spy(monkeypatch, "health_bar")
    b = make_boss(act, False, 0)
    seen = []
    for target in (1.0, notches[0] - 0.01) + ((notches[1] - 0.01,) if len(notches) > 1 else ()):
        b.take_damage(max(0.0, b.hp - b.max_hp * target), 0.0)
        b.update(DT, Vector2(1000, 900), [])
        plates.clear(); pips.clear(); bars.clear()
        b.draw(screen, CAM, NO_SHAKE)
        seen.append((plates[-1][0][0], pips[-1][0][:2], bars[-1][0][6]))
    for i, (name, pip, notch) in enumerate(seen):
        assert name == names[i] and pip == (len(notches) + 1, i + 1) and notch == notches, (act, i, seen)
    assert seen[-1][0] == b.name


# ---- 12. no allocations ------------------------------------------------------------------------------------------------

def _install_counter(monkeypatch):
    counts = {"surface": 0, "font": 0, "callers": {}}
    real_s, real_f, real_font = pygame.Surface, pygame.font.SysFont, pygame.font.Font

    class Counting(real_s):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            counts["surface"] += 1
            name = sys._getframe(1).f_code.co_name
            counts["callers"][name] = counts["callers"].get(name, 0) + 1

    def sysfont(*a, **kw):
        counts["font"] += 1
        return real_f(*a, **kw)

    def font(*a, **kw):
        counts["font"] += 1
        return real_font(*a, **kw)
    monkeypatch.setattr(pygame, "Surface", Counting)
    monkeypatch.setattr(pygame.font, "SysFont", sysfont)
    monkeypatch.setattr(pygame.font, "Font", font)
    return counts


def _fight(b: Boss, screen, f: int, shots: list) -> None:
    if f % 3 == 0:
        b.take_damage(b.max_hp * 0.0015)
    b.update(DT, Vector2(1000 + 300 * math.cos(f / 40), 900 + 200 * math.sin(f / 30)), shots)
    shots.clear()
    screen.fill((40, 40, 60))
    b.draw(screen, CAM + Vector2(40 * math.sin(f / 50), 0), Vector2(f % 3 - 1, 0))


@pytest.mark.parametrize("act,mini,var,start_hp", [
    (3, False, 0, 0.24),      # Layer 4 Ash at phase 3 (Cinder Veil is H1's)
    (5, False, 0, 0.6),       # Layer 6 Thirst crossing into phase 2 / 3 during the count (decoys are B2's)
    (9, False, 0, 0.62),      # Layer 10 phase 2, crossing into phase 3
    (7, True, 1, 1.0), (8, True, 0, 1.0), (3, True, 1, 1.0),     # an anim, an aim and a polygon anchor
])
def test_no_surface_or_font_after_spawn_warm_up(act, mini, var, start_hp, monkeypatch):
    """After warm_art() (what _load_encounter calls at spawn) 300 fight frames, phase changes, flashes, fades and
    rings included, construct no pygame.Surface and no font."""
    b = make_boss(act, mini, var)
    b.take_damage(b.max_hp * (1 - start_hp))
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    shots: list = []
    b.warm_art()
    counts = _install_counter(monkeypatch)
    for f in range(300):
        _fight(b, screen, f, shots)
    assert counts["surface"] == 0 and counts["font"] == 0, counts["callers"]


def test_the_counter_sees_main_s_per_frame_allocations(monkeypatch):
    monkeypatch.setattr(config, "GFX_BOSS_ART", False)
    b = make_boss(5, False, 0)
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    counts = _install_counter(monkeypatch)
    for f in range(10):
        _fight(b, screen, f, [])
    assert counts["font"] >= 10 and counts["surface"] >= 10


# ---- 13. cache bound ----------------------------------------------------------------------------------------------------

def _mib() -> float:
    return sum(bs.cache_bytes().values()) / 2 ** 20


def test_cache_bound_per_map_and_for_all_thirty_in_sequence():
    """Each map (cleared on load, as _load_encounter does) holds <= 24 MB; all 30 entities' sprites (layers + spin
    pieces, the spec 9.10 measure) spawned in sequence without a clear stay <= 24 MB too."""
    peak = 0.0
    for b in _all_bosses():
        bs.clear()
        b.warm_art()
        peak = max(peak, _mib())
    assert peak <= 24.0
    bs.clear()
    for b in _all_bosses():
        b.warm_art()
    c = bs.cache_bytes()
    assert (c["layers"] + c["pieces"]) / 2 ** 20 <= 24.0
    bs.clear()
    assert _mib() == 0.0


def test_load_encounter_clears_the_last_map_and_warms_the_new_bosses(make_game):
    g = make_game()
    g._start_new_run()
    make_boss(9, False, 0).warm_art()
    assert ("anchor", 1, 140, "b") in bs._layers
    for seed in range(8):
        ow = OverworldMap(act_index=2, seed=seed)
        minis = [n for n in ow.nodes.values() if n.node_type == NodeType.MINIBOSS]
        if minis:
            break
    g.overworld = ow
    g._load_encounter(minis[0])
    (m,) = [b for b in g.bosses if b.is_miniboss]
    assert not any(k[0] == "anchor" for k in bs._layers)
    assert m._art_warm and any(k[0] == m.art_key for k in bs._layers)


# ---- 15. toggle ---------------------------------------------------------------------------------------------------------

def test_toggle_off_draws_057_s_pixels(monkeypatch):
    monkeypatch.setattr(config, "GFX_BOSS_ART", False)
    assert scene_digest() == SCENE_057


def test_toggle_off_touches_no_boss_art_cache(monkeypatch):
    monkeypatch.setattr(config, "GFX_BOSS_ART", False)
    for b in _all_bosses()[:6]:
        b.warm_art()
    scene_digest()
    assert _mib() == 0.0


def test_toggle_on_draws_differently_and_repeatably():
    on = scene_digest()
    assert on != SCENE_057 and on == scene_digest()


def test_offscreen_boss_draws_nothing():
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    screen.fill((1, 2, 3))
    b = make_boss(9, False, 0)
    b.pos = CAM + Vector2(config.SCREEN_WIDTH // 2 + 1.9 * b.size + 61, 0)
    b.draw(screen, CAM, NO_SHAKE)
    assert pygame.transform.average_color(screen)[:3] == (1, 2, 3)
