"""TASK-053: animation clocks on the game dt (BUG-140, BUG-144) and the 046 mutant gaps (BUG-141).

BUG-140: enemy-shape animation read pygame.time.get_ticks (frames not reproducible, tendrils moving while paused).
BUG-144: menu / story / ambient-background pulses read time.time(). Both now read blob_evolution.utils.clock, advanced
once per frame by Game._update (the game clock only while PLAYING).
BUG-141: shielder plate flipped 180 deg, cull margin cut, leech tendrils at 3 Hz, phantom wisps drawn forward, global RNG
used while drawing (QA harness /workspace/qa/t45/h/mut46.py: m02, m12, m15, m24, m08).
"""
from __future__ import annotations

import hashlib
import math
import random
import time

import pygame
import pytest

from blob_evolution import config
from blob_evolution.entities.creature import Creature
from blob_evolution.utils import clock as anim_clock
from blob_evolution.utils import creature_shapes as shapes
from blob_evolution.utils.enums import CreatureType, GameState
from blob_evolution.utils.vector2 import Vector2
from enemy_scene import BG, CAM, CX, CY, ENEMY_TYPES, NO_SHAKE, make, render

CT = CreatureType


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(config, "GFX_ENEMY_SHAPES", True)
    monkeypatch.setattr(config, "GFX_READABILITY", True)
    pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    saved = (anim_clock.game_time(), anim_clock.ui_time())
    anim_clock.reset()
    yield
    anim_clock.reset(*saved)


def _no_wall_clock(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("drawing read the wall clock")
    monkeypatch.setattr(pygame.time, "get_ticks", boom)
    monkeypatch.setattr(time, "time", boom)


def _digest(s: pygame.Surface) -> str:
    return hashlib.md5(pygame.image.tobytes(s, "RGB")).hexdigest()


# --- BUG-140: enemy animation on the game clock ------------------------------------------------------------------------------

def test_enemy_draw_reads_the_game_clock_not_the_wall_clock(monkeypatch):
    _no_wall_clock(monkeypatch)
    for kind in ENEMY_TYPES:
        render(make(kind, 20))


@pytest.mark.parametrize("kind", [CT.LEECH, CT.PHANTOM])
def test_same_game_time_same_frame_and_time_moves_the_animation(kind, monkeypatch):
    _no_wall_clock(monkeypatch)
    c = make(kind, 22)
    frames = {}
    for t in (0.25, 0.25, 0.6):
        anim_clock.reset(game=t)
        frames.setdefault(t, set()).add(_digest(render(c)))
    assert len(frames[0.25]) == 1
    assert frames[0.6] != frames[0.25]


def test_game_clock_freezes_outside_gameplay_and_the_ui_clock_keeps_going(make_game):
    g = make_game()
    for state, _moves in ((GameState.PAUSED, False), (GameState.SKILLS, False), (GameState.MAIN_MENU, False)):
        g.state = state
        before = (anim_clock.game_time(), anim_clock.ui_time())
        for _ in range(30):
            g._update(1 / 60)
        assert anim_clock.game_time() == before[0], state
        assert anim_clock.ui_time() == pytest.approx(before[1] + 0.5), state
    anim_clock.reset()
    anim_clock.advance(0.5, gameplay=True)
    assert (anim_clock.game_time(), anim_clock.game_ms()) == (0.5, 500)


def test_paused_leech_keeps_its_frame(make_game):
    g = make_game()
    g.state = GameState.PAUSED
    c = make(CT.LEECH, 22)
    anim_clock.reset(game=0.3)
    first = _digest(render(c))
    for _ in range(45):
        g._update(1 / 60)
        assert _digest(render(c)) == first


# --- BUG-144: UI pulses on the UI clock ----------------------------------------------------------------------------------------

def test_ui_pulse_and_ambient_background_follow_the_ui_clock(monkeypatch):
    from blob_evolution.ui import style
    _no_wall_clock(monkeypatch)
    anim_clock.reset(ui=1.0)
    a = style.pulse(2.0)
    assert a == pytest.approx((math.sin(2.0) + 1) / 2)
    s1, s2 = pygame.Surface((320, 200)), pygame.Surface((320, 200))
    style.draw_ambient_bg(s1, seed_offset=2.0)
    style.draw_ambient_bg(s2, seed_offset=2.0)
    assert _digest(s1) == _digest(s2)
    anim_clock.reset(ui=3.0)
    style.draw_ambient_bg(s2, seed_offset=2.0)
    assert _digest(s1) != _digest(s2)


def test_no_wall_clock_left_in_ui_drawing_sources():
    import inspect
    from blob_evolution.ui import cinematic, menus, style
    for mod in (style, menus, cinematic):
        src = inspect.getsource(mod)
        assert "time.time(" not in src and "get_ticks(" not in src, mod.__name__


# --- BUG-141: the four surviving 046 mutants and the global-RNG draw mutant ---------------------------------------------------

def _sprite_centroid_angle(spr) -> float:
    surf, ox, oy = spr
    sx = sy = n = 0.0
    for y in range(surf.get_height()):
        for x in range(surf.get_width()):
            a = surf.get_at((x, y)).a
            if a:
                sx += (x + ox) * a
                sy += (y + oy) * a
                n += a
    return math.atan2(sy / n, sx / n)


@pytest.mark.parametrize("deg", [0, 50, 135, 200, 290])
def test_shielder_plate_faces_where_the_shielder_faces(deg, monkeypatch):
    got = []
    real = shapes._get
    monkeypatch.setattr(shapes, "_get", lambda key, fn, *a: got.append((key, real(key, fn, *a))) or got[-1][1])
    ang = math.radians(deg)
    render(make(CT.SHIELDER, 22, face=(math.cos(ang), math.sin(ang))))
    plates = [spr for key, spr in got if key[0] == "crescent"]
    assert len(plates) == 1
    off = (_sprite_centroid_angle(plates[0]) - ang + math.pi) % math.tau - math.pi
    assert abs(off) <= math.tau / config.ENEMY_SHIELD_STEPS, (deg, math.degrees(off))


def test_bomber_blast_just_off_screen_is_still_drawn():
    """A lit bomber whose centre is 3 radii left of the screen still shows the edge of its 3.5 radius blast disc."""
    c = make(CT.BOMBER, 20, fuse=0.5)
    c.pos = Vector2(CX - config.SCREEN_WIDTH // 2 - 3 * 20, CY)       # screen x = -60
    s = render(c)
    assert any(s.get_at((x, CY))[:3] != BG for x in range(0, 6))


def test_leech_tendrils_loop_at_0_7_hz():
    keys = []
    real = shapes._get
    c = make(CT.LEECH, 22)
    s = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    orig = shapes._get
    try:
        shapes._get = lambda key, fn, *a: (keys.append(key) if key[0] == "leech" else None) or real(key, fn, *a)
        for ms in range(0, 2858, 10):                              # two 0.7 Hz loops (1.4286 s each)
            anim_clock.reset(game=ms / 1000)
            c.draw(s, CAM, NO_SHAKE)
    finally:
        shapes._get = orig
    phases = [k[2] for k in keys]
    changes = sum(a != b for a, b in zip(phases, phases[1:]))
    assert set(phases) == set(range(config.ENEMY_TENDRIL_PHASES))
    assert 2 * config.ENEMY_TENDRIL_PHASES - 1 <= changes <= 2 * config.ENEMY_TENDRIL_PHASES


@pytest.mark.parametrize("vel", [(150, 0), (0, -150), (-100, 100)])
def test_phantom_wisps_trail_behind_its_motion(vel, monkeypatch):
    spots = []
    real = shapes._blit_c

    def spy(dst, spr, x, y):
        spots.append((x, y))
        real(dst, spr, x, y)
    monkeypatch.setattr(shapes, "_blit_c", spy)
    c = make(CT.PHANTOM, 22)
    c.vel = Vector2(*vel)
    render(c)
    n = math.hypot(*vel)
    wisps = spots[:3]
    assert len(wisps) == 3
    for x, y in wisps:
        assert ((x - CX) * vel[0] + (y - CY) * vel[1]) / n < -0.5 * 22    # behind the body, opposite the velocity


def test_drawing_enemies_never_touches_the_global_rng():
    creatures = [make(k, 20, phased=k == CT.PHANTOM, flash=True, fuse=0.8) for k in ENEMY_TYPES]
    s = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    random.seed(1234)
    before = random.getstate()
    for n in range(20):
        anim_clock.reset(game=n / 60)
        for c in creatures:
            c.draw(s, CAM, NO_SHAKE)
    assert random.getstate() == before
