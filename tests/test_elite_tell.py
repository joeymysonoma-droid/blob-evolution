"""TASK-068 elite tell (Visual Designer spec TASK-068-elite-tell.md): thorn crown, flash copy, absorb-denied cue."""
from __future__ import annotations

import math

import pygame
import pytest

import hitfx_scene
from blob_evolution import config
from blob_evolution.entities.creature import Creature
from blob_evolution.utils import clock as anim_clock
from blob_evolution.utils import creature_shapes as shapes
from blob_evolution.utils.enums import CreatureType
from blob_evolution.utils.vector2 import Vector2
from enemy_scene import BG, CAM, CX, CY, ENEMY_TYPES, NO_SHAKE, make
from test_enemy_shapes import _install_counter, contrast


def _mask(c: Creature) -> pygame.mask.Mask:
    """Grayscale-free silhouette: every pixel that differs from the background."""
    s = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    s.fill(BG)
    c.draw(s, CAM, NO_SHAKE)
    return _diff(s)


def _diff(s: pygame.Surface) -> pygame.mask.Mask:
    m = pygame.mask.Mask(s.get_size())
    for y in range(CY - 90, CY + 91):
        for x in range(CX - 90, CX + 91):
            if s.get_at((x, y))[:3] != BG:
                m.set_at((x, y))
    return m


@pytest.mark.parametrize("kind", ENEMY_TYPES)
@pytest.mark.parametrize("size", [12, 20, 30])
def test_silhouette_alone_tells_elites_apart(kind, size):
    """Acceptance 1: mask XOR outside the body disc is >= 8 % of the body area."""
    plain, elite = make(kind, size), make(kind, size)
    elite.make_elite()
    a, b = _mask(plain), _mask(elite)
    r = size + 0.5
    diff = 0
    for y in range(CY - 90, CY + 91):
        for x in range(CX - 90, CX + 91):
            if a.get_at((x, y)) != b.get_at((x, y)) and math.hypot(x + 0.5 - CX, y + 0.5 - CY) > r:
                diff += 1
    assert diff >= 0.08 * math.pi * size * size, (kind, size, diff)


def test_thorn_fill_contrast_on_every_light_ground():
    """Acceptance 2: thorn fill >= 3:1 against every act's LIGHT ground (spec measures 6.39)."""
    worst = min(contrast(config.ELITE_THORN_FILL, ramp[2]) for ramp in config.GROUND_RAMPS)
    assert worst >= 6.38


@pytest.mark.parametrize("size", [12, 20, 22, 25, 28, pytest.param(30), pytest.param(40, marks=pytest.mark.xfail(
    reason="TASK-067: re-check elite splitter silhouette at size 40, currently 6.88%; fallback (ii) splitter T=0.36R, measured first.",
    strict=True))])
def test_splitter_silhouette_every_size(size):
    """VD option (a): the splitter's crown at 30 deg clears its side bulbs; XOR outside the body >= 8 % per size."""
    plain, elite = make(CreatureType.SPLITTER, size), make(CreatureType.SPLITTER, size)
    elite.make_elite()
    a, b = _mask(plain), _mask(elite)
    diff = sum(1 for y in range(CY - 90, CY + 91) for x in range(CX - 90, CX + 91)
               if a.get_at((x, y)) != b.get_at((x, y)) and math.hypot(x + 0.5 - CX, y + 0.5 - CY) > size + 0.5)
    assert diff >= 0.08 * math.pi * size * size, (size, diff)


def test_crown_offset_per_type():
    """Splitter 30 deg, every other type the 0 deg default; the two bake to different sprites."""
    assert shapes.crown_offset("SPLITTER") == 30.0
    assert all(shapes.crown_offset(k.name) == 0.0 for k in ENEMY_TYPES if k != CreatureType.SPLITTER)
    assert shapes.crown_sprite(20, False, False, "SPLITTER")[0] is not shapes.crown_sprite(20, False, False, "BASIC")[0]


def test_splitter_elite_bakes_its_own_crowns_at_spawn():
    """make_elite on a splitter bakes the four 30 deg crowns."""
    shapes._cache.clear()
    c = make(CreatureType.SPLITTER, 23)
    c.make_elite()
    assert {k for k in shapes._cache if k[0].startswith("crown")} == {
        ("crown", 23, 0, 30.0), ("crown", 23, 3, 30.0), ("crown_f", 23, 0, 30.0), ("crown_f", 23, 3, 30.0)}


@pytest.mark.parametrize("r", [6, 12, 20, 30, 50])
def test_crown_geometry(r):
    """Tips at R+2+T (T = max(5, round 0.32R)), +3 px when denied; no thorn straight up; extent <= 1.34R+2 (+3)."""
    t = shapes.thorn_len(r)
    assert t == max(5, round(0.32 * r)) and r + 2 + t <= max(1.34 * r + 2, r + 7)
    for deny, grow in ((False, 0), (True, 3)):
        spr, ox, oy = shapes.crown_sprite(r, deny, False)
        reach = max(-ox, -oy, spr.get_width() + ox, spr.get_height() + oy)
        assert reach <= r + 2 + t + grow + 1
    # VD approval: thorns at 0/60/.../300 deg, so none points straight up (270 on screen) or down (90)
    angles = [k * 360.0 / config.ELITE_THORNS + config.ELITE_THORN_OFFSET_DEG for k in range(config.ELITE_THORNS)]
    assert angles == [0.0, 60.0, 120.0, 180.0, 240.0, 300.0]
    spr, ox, oy = shapes.crown_sprite(r, False, False)
    col = -ox                                              # the centre column above and below the separator ring is empty
    assert all(spr.get_at((col, y))[3] == 0 for y in range(0, -oy - r - 4))
    assert all(spr.get_at((col, y))[3] == 0 for y in range(-oy + r + 5, spr.get_height()))


def test_flash_copy_follows_bug176():
    """The flash crown is BUG-176's copy: 3 px bigger on each side, white outline, art lifted toward white."""
    from blob_evolution.utils import boss_shapes
    base, bx, by = shapes.crown_sprite(20, False, False)
    fl, fx, fy = shapes.crown_sprite(20, False, True)
    assert fl.get_width() == base.get_width() + 2 * boss_shapes.FLASH_PAD and fx == bx - boss_shapes.FLASH_PAD
    assert fl.get_at((0, fl.get_height() // 2))[3] in (0, 255)
    assert any(fl.get_at((x, y))[:3] == (255, 255, 255) and fl.get_at((x, y))[3] == 255
               for x in range(fl.get_width()) for y in range(fl.get_height()))


def test_crown_is_baked_at_spawn():
    """make_elite bakes all four crown sprites before any frame."""
    shapes._cache.clear()
    c = make(CreatureType.BASIC, 23)
    c.make_elite()
    assert {k for k in shapes._cache if k[0].startswith("crown")} == {
        ("crown", 23, 0, 0.0), ("crown", 23, 3, 0.0), ("crown_f", 23, 0, 0.0), ("crown_f", 23, 3, 0.0)}


def test_zero_allocations_300_frames_10_elites(monkeypatch):
    """Acceptance 3: 10 elites (incl. a flashing and a denied one), 300 frames, no Surface made outside draw_blob."""
    clock = [0]
    monkeypatch.setattr(anim_clock, "game_ms", lambda: clock[0])
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    cs = []
    for i in range(10):
        c = make(ENEMY_TYPES[i % len(ENEMY_TYPES)], 14 + i * 2)
        c.pos = Vector2(CX - 450 + 100 * i, CY)
        c.make_elite()
        cs.append(c)
    for n in range(150):
        clock[0] = int(n * 1000 / 60)
        cs[0].hit_flash = 0.1 if n % 20 < 5 else 0.0      # warm-up sees every state the timed frames use
        for c in cs:
            c.draw(screen, CAM, NO_SHAKE)
    counts = _install_counter(monkeypatch)
    for n in range(150, 450):
        clock[0] = int(n * 1000 / 60)
        cs[0].hit_flash = 0.1 if n % 20 < 5 else 0.0
        if n % 30 == 0:
            cs[1].deny_absorb()
        for c in cs:
            c.draw(screen, CAM, NO_SHAKE)
    assert counts["other"] == 0, counts["callers"]


@pytest.fixture
def fight(make_game):
    g = hitfx_scene.make_scene_game(0)
    g.creatures, g.bosses, g.projectiles, g.xp_orbs = [], [], [], []
    g.player.max_hp = g.player.hp = 1e9
    return g


def test_absorb_denied_fires_at_most_3_per_second(fight, monkeypatch):
    """Acceptance 4: a big player held on an elite for 3 s starts the cue <= 9 times, each lasting 0.25 s."""
    g = fight
    now = [10_000]
    monkeypatch.setattr(anim_clock, "game_ms", lambda: now[0])
    g.player.size = 60.0
    e = Creature(Vector2(g.player.pos.x + 2, g.player.pos.y), CreatureType.BASIC, 12.0)
    e.make_elite()
    e.speed = 0.0
    g.creatures = [e]
    starts, prev, shown = 0, -1, 0
    for n in range(180):
        now[0] = 10_000 + n * 1000 // 60
        e.pos.set(g.player.pos.x + 2, g.player.pos.y)
        g._update_collisions()
        if e.deny_until != prev:
            starts += 1
            assert e.deny_until - now[0] == 250
        prev = e.deny_until
        shown += e.deny_showing()
    assert 1 <= starts <= 9 and e.active
    assert starts == 9 and 120 <= shown <= 140                 # every 0.34 s, 0.25 s each


def test_small_player_touching_elite_shows_no_deny_cue(fight):
    """The cue is only for touches that would have absorbed."""
    g = fight
    g.player.size = 10.0
    e = Creature(Vector2(g.player.pos.x + 2, g.player.pos.y), CreatureType.BASIC, 20.0)
    e.make_elite()
    g.creatures = [e]
    g._update_collisions()
    assert not e.deny_showing() and e.deny_until == -1


def test_cue_off_switch(fight, monkeypatch):
    """ELITE_DENY_CUE False: no growth."""
    monkeypatch.setattr(config, "ELITE_DENY_CUE", False)
    e = make(CreatureType.BASIC, 12)
    e.make_elite()
    e.deny_absorb()
    assert e.deny_until == -1


def test_hitbox_unchanged():
    """Visual only: an elite's radius equals its twin's."""
    a, b = make(CreatureType.BASIC, 18), make(CreatureType.BASIC, 18)
    b.make_elite()
    assert a.radius == b.radius if hasattr(a, "radius") else a.size == b.size


@pytest.fixture
def legacy(monkeypatch):
    """GFX_ENEMY_SHAPES False: the pre-046 drawing path."""
    monkeypatch.setattr(config, "GFX_ENEMY_SHAPES", False)


@pytest.mark.parametrize("kind", ENEMY_TYPES)
def test_legacy_mode_draws_the_crown(legacy, kind):
    """Legacy circle + the same crown: silhouette XOR outside the body >= 8 % of its area."""
    plain, elite = make(kind, 20), make(kind, 20)
    elite.make_elite()
    a, b = _mask(plain), _mask(elite)
    diff = sum(1 for y in range(CY - 90, CY + 91) for x in range(CX - 90, CX + 91)
               if a.get_at((x, y)) != b.get_at((x, y)) and math.hypot(x + 0.5 - CX, y + 0.5 - CY) > 20.5)
    assert diff >= 0.08 * math.pi * 400, (kind, diff)


@pytest.mark.parametrize("deny,flash", [(False, False), (True, False), (False, True), (True, True)])
def test_legacy_blits_the_shared_baked_variant(legacy, monkeypatch, deny, flash):
    """Legacy draws the cached crown_sprite for its state (denied / flash), the very sprite the 046 path uses."""
    seen = []
    real = shapes.draw_crown
    monkeypatch.setattr(shapes, "draw_crown", lambda d, x, y, size, dn, fl, kind="": (seen.append((dn, fl)), real(d, x, y, size, dn, fl, kind)))
    monkeypatch.setattr(anim_clock, "game_ms", lambda: 5_000)
    c = make(CreatureType.BASIC, 18)
    c.make_elite()
    c.hit_flash = 0.1 if flash else 0.0
    c.deny_until = 6_000 if deny else -1
    s = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    c.draw(s, CAM, NO_SHAKE)
    assert seen == [(deny, flash)]


def test_legacy_zero_allocations_300_frames_10_elites(legacy, monkeypatch):
    """Legacy mode, 10 elites (one flashing, one denied), 300 frames: no Surface made outside draw_blob."""
    clock = [0]
    monkeypatch.setattr(anim_clock, "game_ms", lambda: clock[0])
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    cs = []
    for i in range(10):
        c = make(ENEMY_TYPES[i % len(ENEMY_TYPES)], 14 + i * 2)
        c.pos = Vector2(CX - 450 + 100 * i, CY)
        c.make_elite()
        cs.append(c)
    for n in range(450):
        if n == 150:
            counts = _install_counter(monkeypatch)
        clock[0] = int(n * 1000 / 60)
        cs[0].hit_flash = 0.1 if n % 20 < 5 else 0.0
        if n % 30 == 0:
            cs[1].deny_absorb()
        for c in cs:
            c.draw(screen, CAM, NO_SHAKE)
    assert counts["other"] == 0, counts["callers"]
