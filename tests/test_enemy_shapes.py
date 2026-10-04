"""TASK-046 enemy shapes: nine silhouettes, light rim rings, bone-pale LEECH, baked sprites. Visual only.

Covers the eleven acceptance tests of handoffs/TASK-046-enemy-shapes.md (the eleventh, "all existing tests pass", is the rest of
the suite plus the act 0-9 smoke test here) and the toggle: GFX_ENEMY_SHAPES = False draws exactly what 6a65692 (TASK-043) drew.
"""
from __future__ import annotations

import colorsys
import hashlib
import inspect
import math
import random
import sys
from typing import Callable, List, Set, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.entities import creature as creature_module
from blob_evolution.entities.creature import Creature
from blob_evolution.maps.generator import MapGenerator
from blob_evolution.utils import creature_shapes as shapes
from blob_evolution.utils.enums import CreatureType
from blob_evolution.utils.vector2 import Vector2
from enemy_scene import BG, CAM, CX, CY, ENEMY_TYPES, NO_SHAKE, SCENES, make, render, scene_hash

CT = CreatureType
SIZES = (12, 20, 28)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    """Freeze pygame's clock (animations read it) and pin the toggles to their defaults."""
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: 0)
    monkeypatch.setattr(config, "GFX_ENEMY_SHAPES", True)
    monkeypatch.setattr(config, "GFX_READABILITY", True)
    yield


def lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(rgb) -> float:
    return 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2])


def contrast(a, b) -> float:
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _outside(c: Creature) -> Set[Tuple[int, int]]:
    """Non-background pixels farther than size + 3 from the centre (the silhouette's extras; no contact shadow)."""
    s = render(c)
    r = c.size + 3
    out = set()
    for y in range(CY - 70, CY + 71):
        for x in range(CX - 70, CX + 71):
            if s.get_at((x, y))[:3] != BG and math.hypot(x + 0.5 - CX, y + 0.5 - CY) > r:
                out.add((x, y))
    return out


# ---- 1. stats table and AI untouched ------------------------------------------------------------------------------------------

STATS = {CT.BASIC: (30, 10, 100), CT.SHOOTER: (40, 8, 80), CT.SPLITTER: (60, 12, 70), CT.CHARGER: (50, 25, 120),
         CT.SHIELDER: (55, 12, 70), CT.ORBITER: (35, 9, 90), CT.BOMBER: (28, 18, 110), CT.PHANTOM: (45, 11, 95),
         CT.LEECH: (38, 7, 105)}
# sha256[:16] of inspect.getsource() of every stat / AI / damage method at 6a65692; any behaviour edit changes one
LOGIC_HASHES = {
    "_base_hp": "bd924fcb0943d1fa", "_base_damage": "2159433ec6fbfcdc", "_base_speed": "5ba12aba89a79e9c",
    "take_damage": "f8b1fbf84d6b8c59", "update": "afafe92e662b23d2", "_ai_basic": "58db22245694305f",
    "_ai_shooter": "6d67985f84ed68d0", "_ai_charger": "79ee17a1c4db226d", "_ai_shielder": "6212824a12b51301",
    "_ai_orbiter": "bc4468bbc8fb45c7", "_ai_bomber": "7130e66a241d0411", "_ai_phantom": "0ad824a01449c89f",
    "_ai_leech": "e57bd215c78be755", "can_split": "a527d5805af5e6a3", "create_splits": "2e883e3fed58fb0f",
}


@pytest.mark.parametrize("size", [12, 28])
def test_stats_table_untouched(size):
    """Hp / damage / speed / size / radius / explosion radius are the table of 6a65692 at both sizes, for every type."""
    for kind, (hp, dmg, spd) in STATS.items():
        c = Creature(Vector2(0, 0), kind, size)
        assert (c.max_hp, c.damage, c.speed) == (hp, dmg, spd), kind
        assert c.size == size and c.radius == size and c.explosion_radius == 3.5 * size
        assert c.shield_hp == (40.0 if kind == CT.SHIELDER else 0.0)


def test_logic_methods_are_byte_identical_to_043():
    """No AI, stat, damage or split code changed: the source of each is hashed against the 6a65692 source."""
    for name, want in LOGIC_HASHES.items():
        f = Creature.__dict__[name]
        f = f.fget if isinstance(f, property) else f
        assert hashlib.sha256(inspect.getsource(f).encode()).hexdigest()[:16] == want, name


def test_draw_does_not_change_state():
    """Drawing (both toggle states) never writes any gameplay field."""
    for flag in (True, False):
        config.GFX_ENEMY_SHAPES = flag
        for kind in ENEMY_TYPES:
            c = make(kind, 20, charging=True, phased=kind == CT.PHANTOM)
            def snap():
                return {k: ((v.x, v.y) if isinstance(v, Vector2) else v) for k, v in vars(c).items()}
            before = snap()
            render(c)
            assert snap() == before, (flag, kind)


# ---- 2. distinct silhouettes --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("size", SIZES)
def test_silhouettes_distinct(size, monkeypatch):
    """BASIC is a plain disc (<= 2% outside size+3); every other type has >= 5%; pairs differ by >= 50% of the smaller set."""
    monkeypatch.setattr(config, "GFX_READABILITY", False)       # the contact shadow is not part of the silhouette
    disc = math.pi * size * size
    sets = {k: _outside(make(k, size)) for k in ENEMY_TYPES}
    assert len(sets[CT.BASIC]) <= 0.02 * disc
    for k, s in sets.items():
        if k != CT.BASIC:
            assert len(s) >= 0.05 * disc, (k, len(s) / disc)
    others = [k for k in ENEMY_TYPES if k != CT.BASIC]
    for i, a in enumerate(others):
        for b in others[i + 1:]:
            diff = len(sets[a] ^ sets[b])
            assert diff >= 0.5 * min(len(sets[a]), len(sets[b])), (a, b, diff, len(sets[a]), len(sets[b]))


@pytest.mark.parametrize("kind", [k for k in ENEMY_TYPES])
def test_extras_stay_within_1_9_radii(kind, monkeypatch):
    """Nothing of the silhouette strays farther than ~1.9 r from the centre (spec limit), over aim / orbit / phase sweeps."""
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    size = 20
    far = 0.0
    for i in range(0, 32, 3):
        ang = i * math.tau / 32
        for tick in (0, 350, 700, 1050):
            monkeypatch.setattr(pygame.time, "get_ticks", lambda t=tick: t)
            c = make(kind, size, face=(math.cos(ang), math.sin(ang)), orbit=ang, fuse=1.5)
            s = render(c)
            for y in range(CY - 60, CY + 61):
                for x in range(CX - 60, CX + 61):
                    if s.get_at((x, y))[:3] != BG:
                        far = max(far, math.hypot(x + 0.5 - CX, y + 0.5 - CY))
    assert far <= 1.95 * size + 1, far


def test_light_rim_ring_on_every_type(monkeypatch):
    """Every enemy has a 2 px RIM-coloured ring at its body edge."""
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    for kind in ENEMY_TYPES:
        c = make(kind, 20)
        s = render(c)
        # sample the ring on the side opposite to face_dir where no extra covers it (BASIC / all types have a clear back)
        x, y = int(CX - 0.96 * 19), int(CY - 0.29 * 19)
        hits = sum(tuple(s.get_at((x + dx, y + dy)))[:3] == shapes.RIM[kind.name] for dx in (-1, 0, 1) for dy in (-1, 0, 1))
        assert hits >= 2, kind


# ---- 3. rim contrast + LEECH recolour -----------------------------------------------------------------------------------------

def test_rim_contrast_against_each_acts_light_ground():
    """RIM colour vs the LIGHT tone of each of the 10 act ramps >= 3:1 for all nine types (the ground never gets lighter)."""
    assert len(config.GROUND_RAMPS) == 10
    for act, ramp in enumerate(config.GROUND_RAMPS):
        for kind in ENEMY_TYPES:
            assert contrast(shapes.RIM[kind.name], ramp[2]) >= 3.0, (act, kind)


def test_leech_is_bone_pale_not_green():
    """LEECH body saturation <= 0.20 (player 0.83); the old green (60,160,100) / (120,230,160) is gone from the draw path."""
    body, core = Creature.COLORS[CT.LEECH]
    for col in (body, core):
        assert colorsys.rgb_to_hsv(*(v / 255 for v in col))[1] <= 0.20
    assert colorsys.rgb_to_hsv(*(v / 255 for v in config.COLOR_PLAYER))[1] > 0.7
    assert Creature.COLORS[CT.LEECH] != Creature.LEGACY_LEECH_COLORS
    s = render(make(CT.LEECH, 20))
    px = [s.get_at((CX + dx, CY + dy))[:3] for dx in range(-8, 9, 4) for dy in range(4, 12, 4)]
    assert all(colorsys.rgb_to_hsv(*(v / 255 for v in p))[1] <= 0.25 for p in px), px


# ---- 4. phased phantom --------------------------------------------------------------------------------------------------------

def test_phased_phantom_is_translucent_and_eyeless(monkeypatch):
    """Phased: the body blends over the ground at about 110/255 and draw_blob is asked for no eyes; solid keeps eyes."""
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    calls: List[bool] = []
    real = creature_module.draw_blob

    def spy(*a, **kw):
        calls.append(kw.get("eyes", True))
        return real(*a, **kw)

    monkeypatch.setattr(creature_module, "draw_blob", spy)
    solid = render(make(CT.PHANTOM, 28))
    solid_eyes = calls[-1]
    phased = render(make(CT.PHANTOM, 28, phased=True))
    assert solid_eyes is True and calls[-1] is False
    ests = []
    for dx, dy in ((0, 12), (6, 10), (-6, 10)):
        p, q = solid.get_at((CX + dx, CY + dy))[:3], phased.get_at((CX + dx, CY + dy))[:3]
        ests += [(q[i] - BG[i]) / (p[i] - BG[i]) for i in range(3) if abs(p[i] - BG[i]) > 30]
    assert ests and all(abs(e - config.ENEMY_PHASED_ALPHA / 255) < 0.12 for e in ests), ests
    assert config.ENEMY_PHASED_ALPHA == 110


def _lit(s: pygame.Surface) -> dict:
    """{(x, y): rgb} of the non-background pixels farther than 29 px from the centre."""
    return {(x, y): tuple(s.get_at((x, y)))[:3] for x in range(CX - 60, CX + 61) for y in range(CY - 60, CY + 61)
            if s.get_at((x, y))[:3] != BG and math.hypot(x + 0.5 - CX, y + 0.5 - CY) > 29}


# ---- 5. hit flash -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ENEMY_TYPES)
def test_flash_whitens_body_rim_and_extras_then_recovers(kind, monkeypatch):
    """hit_flash > 0: rim pixels are pure white and the body is near-white; after 0.15 s of update() the normal look returns."""
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    normal = render(make(kind, 28))
    flash = render(make(kind, 28, flash=True))
    x, y = int(CX - 0.96 * 27), int(CY - 0.29 * 27)
    assert tuple(flash.get_at((x, y)))[:3] == (255, 255, 255)
    body = [flash.get_at((CX + dx, CY + dy))[:3] for dx in (-10, 10) for dy in (6, 12)]
    assert all(min(p) >= 200 for p in body), body
    # extras outside the body (minus the membrane glow every type shares): mostly white when flashing, not when idle.
    # PHANTOM's wisps are a translucent trail, not part of the body: like the reference sprites they do not flash.
    glow = _lit(render(make(CT.BASIC, 28, flash=True)))

    def bright_share(s):
        pts = [p for xy, p in _lit(s).items() if xy not in glow]
        return (sum(min(p) >= 200 for p in pts) / len(pts)) if pts else 1.0
    if kind not in (CT.BASIC, CT.PHANTOM):
        assert bright_share(flash) >= 0.45, (kind, bright_share(flash))
        assert bright_share(flash) >= bright_share(normal) + (0.0 if kind == CT.LEECH else 0.2)    # bone-pale tendrils are near-white anyway
    c = make(kind, 28)
    assert c.take_damage(1.0) in (False, True)
    assert c.hit_flash == pytest.approx(0.15)
    c.update(0.16, Vector2(CX + 900, CY), 15.0, [])
    assert c.hit_flash <= 0
    c2 = render(c)
    assert not (tuple(c2.get_at((x, y)))[:3] == (255, 255, 255))


# ---- 6. no per-frame surface allocation ---------------------------------------------------------------------------------------

def _install_counter(monkeypatch):
    """Count pygame.Surface constructions, split into 'inside draw_blob' (untouched pre-existing membrane ring) and the rest."""
    counts = {"blob": 0, "other": 0, "callers": {}}
    real = pygame.Surface

    class Counting(real):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            f = sys._getframe(1)
            name = f.f_code.co_name
            if name == "draw_blob":
                counts["blob"] += 1
            else:
                counts["other"] += 1
                counts["callers"][name] = counts["callers"].get(name, 0) + 1

    monkeypatch.setattr(pygame, "Surface", Counting)
    return counts


def _workload(clock: List[int]) -> Callable[[pygame.Surface, int], None]:
    """All nine types incl. a charging CHARGER, a phased PHANTOM and a fuse-lit BOMBER with different aims, drawn one frame."""
    creatures: List[Creature] = []
    for i, kind in enumerate(ENEMY_TYPES):
        for j, size in enumerate((12, 22)):
            ang = (i * 2 + j) * math.tau / 32
            creatures.append(make(kind, size, face=(math.cos(ang), math.sin(ang)), orbit=ang, fuse=1.5 if j else 0.8,
                                  phased=kind == CT.PHANTOM and j == 1, charging=kind == CT.CHARGER and j == 1))
            creatures[-1].pos = Vector2(CX - 400 + 90 * i, CY - 100 + 160 * j)
    creatures[-1].hit_flash = 0.1

    def frame(surface: pygame.Surface, n: int) -> None:
        clock[0] = int(n * 1000 / 60)
        for c in creatures:
            c.draw(surface, CAM, NO_SHAKE)
    return frame


def test_no_surface_allocation_per_frame(monkeypatch):
    """After a warm-up, 300 frames of all nine types allocate no Surface in the enemy drawing code (the baked cache covers it).

    draw_blob's own membrane ring (pre-existing, outside this task: draw_blob is not to be edited) is counted apart.
    """
    clock = [0]
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: clock[0])
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    frame = _workload(clock)
    for n in range(150):                         # longer than the slowest loop (LEECH tendrils: 8 phases at ~5.6 Hz -> 1.43 s)
        frame(screen, n)
    counts = _install_counter(monkeypatch)
    for n in range(150, 450):
        frame(screen, n)
    assert counts["other"] == 0, counts["callers"]
    assert shapes.cache_size() <= config.ENEMY_SPRITE_CACHE_MAX


def test_surface_counter_sees_the_legacy_allocations(monkeypatch):
    """Sanity check of the counter: the old path (toggle False) allocates a telegraph Surface per charging charger per frame."""
    config.GFX_ENEMY_SHAPES = False
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    c = make(CT.CHARGER, 20, charging=True)
    counts = _install_counter(monkeypatch)
    for _ in range(10):
        c.draw(screen, CAM, NO_SHAKE)
    assert counts["other"] >= 10 and "_draw_legacy" in counts["callers"]


# ---- 7. bounded cache ---------------------------------------------------------------------------------------------------------

def test_sprite_cache_bounded_over_every_size_and_aim_step():
    """Drawing every type at every int size 6..30 and all aim steps (flash on and off) never lets the cache pass 1500."""
    peak = 0
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    for size in range(6, 31):
        for kind in ENEMY_TYPES:
            for step in range(0, 32, 1):
                ang = step * math.tau / 32
                c = make(kind, size, face=(math.cos(ang), math.sin(ang)), orbit=ang, fuse=0.7 + (step % 2),
                         flash=step % 7 == 0, shield_frac=(step % 3) / 2.0)
                c.draw(screen, CAM, NO_SHAKE)
                peak = max(peak, shapes.cache_size())
    assert peak <= config.ENEMY_SPRITE_CACHE_MAX == 1500


# ---- 8. cull ------------------------------------------------------------------------------------------------------------------

def test_offscreen_creature_draws_nothing(monkeypatch):
    """A creature 5000 px away touches no pixel and does not even call the baked-sprite layer."""
    calls = []
    monkeypatch.setattr(shapes, "draw_under", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(shapes, "draw_over", lambda *a, **k: calls.append(1))
    for kind in ENEMY_TYPES:
        s = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        s.fill(BG)
        before = pygame.image.tobytes(s, "RGB")
        c = make(kind, 28)
        c.pos = Vector2(CX + 5000, CY + 5000)
        c.draw(s, CAM, NO_SHAKE)
        assert pygame.image.tobytes(s, "RGB") == before and not calls, kind
    # just inside the margin the creature is still drawn
    c = make(CT.BASIC, 20)
    c.pos = Vector2(1, CY - CY + CY)                              # screen x = 1 - CX + CX = 1: half visible
    s = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    s.fill(BG)
    c.draw(s, CAM, NO_SHAKE)
    assert s.get_at((5, CY))[:3] != BG


# ---- 9. bomber blast disc -----------------------------------------------------------------------------------------------------

def _right_edge(s: pygame.Surface) -> float:
    """Distance from the creature centre to the farthest non-background pixel along the +x axis (rows CY-1..CY+1)."""
    best = 0
    for y in (CY - 1, CY, CY + 1):
        for x in range(CX, CX + 200):
            if s.get_at((x, y))[:3] != BG:
                best = max(best, x + 1 - CX)
    return best


def test_bomber_blast_disc_only_when_fuse_under_one_second(monkeypatch):
    """fuse 1.1: nothing near the blast radius; fuse 0.9: a disc whose edge is within 2 px of explosion_radius."""
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    for size in (12, 20, 28):
        far = _right_edge(render(make(CT.BOMBER, size, fuse=1.1)))
        assert far < 2.0 * size
        c = make(CT.BOMBER, size, fuse=0.9)
        near = _right_edge(render(c))
        assert abs(near - c.explosion_radius) <= 2, (size, near, c.explosion_radius)
        assert near > 3 * size


# ---- 10. shielder crescent ----------------------------------------------------------------------------------------------------

def test_shielder_crescent_thick_thin_none(monkeypatch):
    """shield_hp = max: thick crescent; 0.4 max: clearly thinner; 0: none (no shield-coloured pixel at all)."""
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    def count(frac):
        s = render(make(CT.SHIELDER, 28, shield_frac=frac))
        return sum(tuple(s.get_at((x, y)))[:3] == shapes.SHIELD_FILL for x in range(CX - 70, CX + 71) for y in range(CY - 70, CY + 71))
    full, thin, none = count(1.0), count(0.4), count(0.0)
    assert full > 40 and 0 < thin < 0.8 * full and none == 0, (full, thin, none)


# ---- toggle: False = exactly 6a65692 ------------------------------------------------------------------------------------------

LEGACY_HASHES = {      # md5 over {plain, flash, phased, charging, fuse1, shield_half} x sizes 12/28 of enemy_scene.scene_hash, taken at 6a65692
    "BASIC": "5dad15c1fde23bcb376d11e4069b57da", "BOMBER": "32c3fd59dea90228230582af41fdbcd8",
    "CHARGER": "c03a6088503a361aa495ad8b279d0a0a", "LEECH": "4e192386bbc156bc36280bb3c8749fb2",
    "ORBITER": "a66cc90d37a19d06b6eb9ad5b0aca28e", "PHANTOM": "19e5aa38e6fe52cd25a8807b064cff3b",
    "SHIELDER": "718e7304e6662c41e35b5ff843d6726b", "SHOOTER": "f0ae7bbf33093f024e1abb3539a74b20",
    "SPLITTER": "719399e07337d0b1c2eec7d9cab66599",
}


@pytest.mark.parametrize("kind", ENEMY_TYPES)
def test_toggle_false_reproduces_the_pre_046_pixels(kind):
    """GFX_ENEMY_SHAPES = False: byte-identical pixels to the 6a65692 build (incl. the old green LEECH, shield circle, darkened phase)."""
    config.GFX_ENEMY_SHAPES = False
    # the baseline order is the sorted keys "KIND/scene/size"
    keys = sorted(f"{kind.name}/{name}/{size}" for name in SCENES for size in (12, 28))
    order = [(k.split("/")[1], int(k.split("/")[2])) for k in keys]
    hashes = [scene_hash(make(kind, size, **SCENES[name])) for name, size in order]
    assert hashlib.md5("".join(hashes).encode()).hexdigest() == LEGACY_HASHES[kind.name]


def test_toggle_true_differs_from_false_for_every_type():
    """The new look is really different from the old one for each of the nine types."""
    for kind in ENEMY_TYPES:
        config.GFX_ENEMY_SHAPES = True
        a = scene_hash(make(kind, 20))
        config.GFX_ENEMY_SHAPES = False
        assert scene_hash(make(kind, 20)) != a, kind


# ---- 11. smoke: acts 0-9 ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("act", range(10))
def test_act_smoke_update_and_draw_every_enemy(act):
    """A real encounter population of the act, every type forced in, updates 60 frames and draws on the real ground without error."""
    random.seed(act)
    mg = MapGenerator()
    mg.load_map(act, 7)
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    player_pos = Vector2(1000, 1000)
    creatures = [Creature(Vector2(1000 + 70 * (i - 4), 1060), kind, random.choice((10, 15, 24))) for i, kind in enumerate(ENEMY_TYPES)]
    creatures[0].phased = creatures[7].phased = True
    cam = Vector2(1000, 1000)
    for n in range(60):
        for c in creatures:
            c.update(1 / 60, player_pos, 15.0, [])
        mg.draw_background(screen, cam, NO_SHAKE)
        for c in creatures:
            c.draw(screen, cam, NO_SHAKE)
    assert shapes.cache_size() <= config.ENEMY_SPRITE_CACHE_MAX
