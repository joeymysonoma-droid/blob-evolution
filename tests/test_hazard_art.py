"""TASK-042: hazard redesign. Redraw only: collision, effects and positions are unchanged; art is baked, nothing allocates per frame."""
from __future__ import annotations

import math
import random
import statistics
import time

import pygame
import pytest

from blob_evolution import config
from blob_evolution.maps.generator import MapGenerator
from blob_evolution.systems import hazards as hazards_module
from blob_evolution.systems.hazards import HazardManager, HazardZone
from blob_evolution.utils import layers
from blob_evolution.utils.enums import HazardType
from blob_evolution.utils.graphics import draw_blob
from blob_evolution.utils.vector2 import Vector2

TYPES = list(HazardType)
CAM = Vector2(1000, 1000)
NO_SHAKE = Vector2(0, 0)


@pytest.fixture(scope="module")
def screen():
    pygame.init()
    return pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))


def _zone(kind: HazardType, radius: int = 90, x: float = 1000, y: float = 1000, phase: float = 1.0) -> HazardZone:
    zone = HazardZone(Vector2(x, y), radius, kind)
    zone.phase = phase
    return zone


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb) -> float:
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def _cr(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# --- behaviour untouched -------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind", TYPES)
def test_collision_is_still_distance_below_radius(kind):
    zone = _zone(kind, 90)
    assert zone.contains(Vector2(1089.9, 1000)) and not zone.contains(Vector2(1090, 1000))
    assert zone.contains(Vector2(1000, 910.5)) and not zone.contains(Vector2(1000, 909))


def test_effects_are_unchanged():
    lava = _zone(HazardType.LAVA, phase=math.pi / 2)                   # intensity 1.0
    assert lava.get_effects(0.4) == {"damage": 0.0, "speed_mult": 0.6, "regen_mult": 1.0}
    assert lava.get_effects(0.1) == {"damage": 8.0, "speed_mult": 0.6, "regen_mult": 1.0}
    toxic = _zone(HazardType.TOXIC)
    assert toxic.get_effects(0.9) == {"damage": 0.0, "speed_mult": 0.9, "regen_mult": 0.0}
    assert toxic.get_effects(0.2) == {"damage": 5, "speed_mult": 0.9, "regen_mult": 0.0}
    assert _zone(HazardType.ICE).get_effects(1.0) == {"damage": 0.0, "speed_mult": 1.4, "regen_mult": 1.0}


def test_generation_is_unchanged_and_bakes_the_art_up_front():
    mgr = HazardManager()
    mgr.generate_for_map(["lava"], count=5, seed=7)
    assert [(z.pos.x, z.pos.y, z.radius) for z in mgr.zones][:2] == [(508.0, 1008.0, mgr.zones[0].radius), (348.0, 1297.0, mgr.zones[1].radius)]
    assert all(60 <= z.radius <= 120 for z in mgr.zones)
    assert all(z._sprite is not None for z in mgr.zones)                 # baked at map load, not in the first fight frame
    again = HazardManager()
    again.generate_for_map(["lava"], count=5, seed=7)
    assert [(z.pos.x, z.pos.y, z.radius, z.hazard_type) for z in again.zones] == [(z.pos.x, z.pos.y, z.radius, z.hazard_type) for z in mgr.zones]


def test_player_effects_are_combined_as_before():
    mgr = HazardManager()
    mgr.zones = [_zone(HazardType.TOXIC, 90), _zone(HazardType.ICE, 90)]
    eff = mgr.get_player_effects(Vector2(1000, 1000), 0.016)
    assert eff["speed_mult"] == pytest.approx(0.9 * 1.4) and eff["regen_mult"] == 0.0


# --- caching, determinism, no per-frame allocation --------------------------------------------------------------------

@pytest.mark.parametrize("kind", TYPES)
def test_the_baked_sprite_is_built_once_and_reused(kind, screen):
    zone = _zone(kind)
    assert zone._sprite is None
    zone.draw(screen, CAM, NO_SHAKE)
    sprite, core = zone._sprite, list(zone._core)
    assert sprite is not None and sprite.get_size() == (2 * 90 + 2 * config.HAZARD_SPRITE_PAD,) * 2
    for _ in range(5):
        zone.update(0.1)
        zone.draw(screen, CAM, NO_SHAKE)
    assert zone._sprite is sprite and all(a is b for a, b in zip(zone._core, core))
    assert bool(core) == (kind == HazardType.LAVA)


@pytest.mark.parametrize("kind", TYPES)
def test_drawing_allocates_no_surface_and_scales_nothing(kind, screen, monkeypatch):
    zone = _zone(kind)
    zone.build()
    counts = {"surface": 0, "transform": 0, "sprite": 0}
    real_surface = pygame.Surface

    def counting_surface(*args, **kwargs):
        counts["surface"] += 1
        return real_surface(*args, **kwargs)

    monkeypatch.setattr(pygame, "Surface", counting_surface)
    for name in ("smoothscale", "scale", "rotozoom"):
        real = getattr(pygame.transform, name)
        monkeypatch.setattr(pygame.transform, name, lambda *a, _r=real, **k: (counts.__setitem__("transform", counts["transform"] + 1), _r(*a, **k))[1])
    monkeypatch.setattr(hazards_module, "make_sprite", lambda *a, **k: counts.__setitem__("sprite", counts["sprite"] + 1))
    for _ in range(120):
        zone.update(1 / 60)
        zone.draw(screen, CAM, NO_SHAKE)
    assert counts == {"surface": 0, "transform": 0, "sprite": 0}


@pytest.mark.parametrize("kind", TYPES)
def test_the_art_is_deterministic_per_zone_and_never_touches_the_global_random(kind):
    random.seed(9)
    state = random.getstate()
    a, b = _zone(kind, 77, 400, 650), _zone(kind, 77, 400, 650)
    state_after_init = random.getstate()
    a.build()
    b.build()
    random.setstate(state)
    c = _zone(kind, 77, 400, 650)
    c.build()
    assert random.getstate() != state                                    # the zone phase itself still draws from the global stream (as before)
    random.setstate(state_after_init)
    d = _zone(kind, 77, 401, 650)
    d.build()
    bytes_of = lambda z: pygame.image.tobytes(z._sprite, "RGBA")
    assert bytes_of(a) == bytes_of(b) == bytes_of(c)
    assert (bytes_of(a) != bytes_of(d)) == (kind != HazardType.ICE)      # the regular ice hexagon is the same for every zone
    random.seed(9)
    state = random.getstate()
    zone = _zone(kind)
    random.setstate(state)
    zone.build()
    assert random.getstate() == state                                    # build() itself draws nothing from the global stream


@pytest.mark.parametrize("kind", TYPES)
@pytest.mark.parametrize("radius", [60, 90, 120])
def test_the_art_never_extends_past_the_hit_radius(kind, radius):
    zone = _zone(kind, radius)
    zone.build()
    sprite = zone._sprite
    size = sprite.get_width()
    data = pygame.image.tobytes(sprite, "RGBA")
    far = 0.0
    for y in range(size):
        for x in range(size):
            if data[(y * size + x) * 4 + 3] > 8:
                far = max(far, math.hypot(x + 0.5 - size / 2, y + 0.5 - size / 2))
    assert far <= radius + 0.5, (kind, radius, far)


def test_zones_off_screen_are_skipped_and_never_baked(screen):
    zone = _zone(HazardType.LAVA, 90, 5000, 5000)
    before = pygame.image.tobytes(screen, "RGB")
    zone.draw(screen, CAM, NO_SHAKE)
    assert zone._sprite is None and pygame.image.tobytes(screen, "RGB") == before


def test_a_zone_partly_on_screen_is_drawn(screen):
    screen.fill((0, 0, 0))
    zone = _zone(HazardType.TOXIC, 90, 1000 + 600 + 60, 1000)             # centre 60 px past the right edge
    zone.draw(screen, CAM, NO_SHAKE)
    assert screen.get_at((config.SCREEN_WIDTH - 3, 400))[:3] != (0, 0, 0)


def test_hazard_draw_cost_for_three_zones_guard(screen):
    zones = [_zone(k, 90, 1000 + 100 * i) for i, k in enumerate(TYPES)]
    for z in zones:
        z.build()
    t = time.perf_counter()
    for _ in range(200):
        for z in zones:
            z.update(1 / 60)
            z.draw(screen, CAM, NO_SHAKE)
    assert (time.perf_counter() - t) / 200 * 1000 < 0.5                  # loose default guard (measured ~0.05 ms)


@pytest.mark.slow
def test_hazard_draw_cost_for_three_zones_is_inside_the_plan_budget(screen):
    zones = [_zone(k, 90, 1000 + 100 * i) for i, k in enumerate(TYPES)]
    for z in zones:
        z.build()
    samples = []
    for _ in range(1500):
        for z in zones:
            z.update(1 / 60)
        t = time.perf_counter()
        for z in zones:
            z.draw(screen, CAM, NO_SHAKE)
        samples.append((time.perf_counter() - t) * 1000)
    assert statistics.median(samples) <= 0.06, statistics.median(samples)


def test_at_most_eight_draw_calls_per_zone(screen, monkeypatch):
    calls = {"n": 0}
    for mod, names in ((pygame.draw, ("circle", "line", "polygon", "lines")), (pygame.Surface, ())):
        for name in names:
            real = getattr(mod, name)
            monkeypatch.setattr(mod, name, lambda *a, _r=real, **k: (calls.__setitem__("n", calls["n"] + 1), _r(*a, **k))[1])
    real_blit = screen.blit
    for kind in TYPES:
        zone = _zone(kind)
        zone.build()
        calls["n"] = 0
        zone.draw(screen, CAM, NO_SHAKE)
        assert calls["n"] <= 7, (kind, calls)                           # primitives; the sprite and the lava core are 2 blits more


# --- animation: no flash, shape and motion differ by type ------------------------------------------------------------------

@pytest.mark.parametrize("kind", TYPES)
def test_animation_never_flashes(kind, screen):
    zone = _zone(kind, 90, 1000, 1000, phase=0.0)
    zone.build()
    lumas = []
    for _ in range(240):                                                 # 4 s at 60 fps
        zone.update(1 / 60)
        screen.fill((20, 30, 40))
        zone.draw(screen, CAM, NO_SHAKE)
        sub = screen.subsurface((510, 310, 180, 180))
        lumas.append(sum(pygame.transform.average_color(sub)[:3]))
    steps = [abs(b - a) for a, b in zip(lumas, lumas[1:])]
    assert max(steps) <= 12, max(steps)                                  # a frame never jumps by more than a few percent of the zone's brightness


def test_ice_is_the_still_one_and_lava_and_toxic_move(screen):
    def frame(kind, phase):
        screen.fill((20, 30, 40))
        z = _zone(kind, 90, 1000, 1000, phase)
        z.draw(screen, CAM, NO_SHAKE)
        return pygame.image.tobytes(screen.subsurface((510, 310, 180, 180)), "RGB")
    assert frame(HazardType.LAVA, 0.5) != frame(HazardType.LAVA, 2.5)
    assert frame(HazardType.TOXIC, 0.5) != frame(HazardType.TOXIC, 2.5)
    off = config.HAZARD_SPARKLE[0] * 2 + 0.2                             # phase = 2 x seconds: inside the "off" part of the cycle
    assert frame(HazardType.ICE, off) == frame(HazardType.ICE, off + 0.1)


def test_the_ice_sparkle_is_slower_than_1_hz():
    on, off = config.HAZARD_SPARKLE
    assert 1 / (on + off) < 1.0 and on <= 0.7 and off >= 2.0


# --- distinguishable by shape in grayscale, never by colour alone ---------------------------------------------------------

def _gray_signature(kind: HazardType, screen) -> dict:
    screen.fill((60, 60, 60))
    zone = _zone(kind, 100, 1000, 1000, phase=1.2)
    zone.draw(screen, CAM, NO_SHAKE)
    cx, cy, r = 600, 400, 100
    grey = lambda px: 0.299 * px[0] + 0.587 * px[1] + 0.114 * px[2]
    radial = []
    for k in range(360):
        a = k * math.pi / 180
        edge = 0.0
        for d in range(r + 4, 20, -1):
            px = screen.get_at((round(cx + math.cos(a) * d), round(cy + math.sin(a) * d)))
            if abs(grey(px) - 60) > 14:
                edge = d
                break
        radial.append(edge)
    mean = sum(radial) / len(radial)

    def harmonic(n: int) -> float:
        re = sum((v - mean) * math.cos(n * k * math.pi / 180) for k, v in enumerate(radial)) / len(radial)
        im = sum((v - mean) * math.sin(n * k * math.pi / 180) for k, v in enumerate(radial)) / len(radial)
        return 2 * math.hypot(re, im) / r
    inner = [grey(screen.get_at((cx + dx, cy + dy))) for dx in range(-40, 41, 4) for dy in range(-40, 41, 4)]
    return {"h6": harmonic(6), "h10": harmonic(10), "inner": sum(inner) / len(inner)}


def test_the_three_hazards_have_clearly_different_grayscale_signatures(screen):
    sig = {k: _gray_signature(k, screen) for k in TYPES}
    lava, toxic, ice = sig[HazardType.LAVA], sig[HazardType.TOXIC], sig[HazardType.ICE]
    assert ice["h6"] > 2 * max(ice["h10"], 0.001) and ice["h6"] > 2 * max(lava["h6"], toxic["h6"])          # hexagon: 6 corners
    assert toxic["h10"] > 2 * lava["h10"]                                                                # scalloped (deep) vs spiky (shallow)
    assert toxic["h10"] > 0.03 and lava["h10"] > 0.003
    assert abs(lava["inner"] - toxic["inner"]) > 6 or abs(lava["inner"] - ice["inner"]) > 6              # interiors differ in grey too


def test_outline_colours_keep_5_to_1_against_every_act_ground():
    for kind, key in ((HazardType.LAVA, "lava"), (HazardType.TOXIC, "toxic"), (HazardType.ICE, "ice")):
        edge = config.HAZARD_STYLE[key]["edge"]
        for act, ramp in enumerate(config.GROUND_RAMPS):
            assert _cr(edge, ramp[1]) >= 5.0, (key, act)


# --- contrast: the player, enemy shots and XP stay readable inside a hazard, all layers on ----------------------------------

COMBOS = [(1, HazardType.TOXIC), (3, HazardType.LAVA), (4, HazardType.ICE), (6, HazardType.TOXIC),
          (9, HazardType.LAVA), (9, HazardType.TOXIC), (9, HazardType.ICE)]


def _mean(px):
    return tuple(sum(p[i] for p in px) / len(px) for i in range(3))


@pytest.mark.parametrize("lowhp", [False, True])
@pytest.mark.parametrize("act, kind", COMBOS)
def test_player_enemy_shots_and_xp_keep_3_to_1_inside_a_hazard_with_all_layers(act, kind, lowhp, screen):
    ring = [(dx, dy) for dy in range(-19, 20) for dx in range(-19, 20) if 15 <= math.hypot(dx, dy) <= 19]
    around = [(dx, dy) for dy in range(-30, 31) for dx in range(-30, 31) if 23 <= math.hypot(dx, dy) <= 30]
    disc = [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3) if math.hypot(dx, dy) <= 2]
    dbg = [(dx, dy) for dy in range(-14, 15) for dx in range(-14, 15) if 9 <= math.hypot(dx, dy) <= 14]
    gen = MapGenerator()
    gen.load_map(act, 7)
    depth = layers.DepthLayers(act, 7)
    red = layers.build_overlay(*config.LOW_HP_OVERLAY)
    rng = random.Random(act * 7 + len(kind.value))
    worst = {"body": 99.0, "shot": 99.0, "xp": 99.0}
    for _ in range(10):
        radius = rng.choice((60, 90, 120))
        zone = _zone(kind, radius, 1000, 1000, rng.uniform(0, 6.28))
        a, d = rng.uniform(0, 6.283), math.sqrt(rng.random()) * 0.7 * radius          # inside 70% (the outline band is thin by design)
        px, py = round(600 + math.cos(a) * d), round(400 + math.sin(a) * d)

        def base():
            gen.draw_background(screen, CAM, NO_SHAKE)
            zone.draw(screen, CAM, NO_SHAKE)
            depth.blit_fog(screen, CAM, NO_SHAKE)
            screen.blit(red if lowhp else depth.vignette, (0, 0))

        base()
        bg = _mean([screen.get_at((px + dx, py + dy)) for dx, dy in around])
        bg_small = _mean([screen.get_at((px + dx, py + dy)) for dx, dy in dbg])
        base()
        draw_blob(screen, (px, py), 20, config.COLOR_PLAYER, config.COLOR_PLAYER_CORE, look=(1, 0))
        worst["body"] = min(worst["body"], _cr(_mean([screen.get_at((px + dx, py + dy)) for dx, dy in ring]), bg))
        for key, colour in (("shot", config.COLOR_PROJECTILE_ENEMY), ("xp", config.COLOR_XP)):
            base()
            pygame.draw.circle(screen, colour, (px, py), 5)
            worst[key] = min(worst[key], _cr(_mean([screen.get_at((px + dx, py + dy)) for dx, dy in disc]), bg_small))
    assert min(worst.values()) >= 3.0, worst


# --- minimap: same colours, shape icons -----------------------------------------------------------------------------------------

def test_minimap_uses_the_same_colours_with_a_shape_per_type():
    surf = pygame.Surface((200, 200))
    surf.fill((16, 22, 34))
    mgr = HazardManager()
    mgr.zones = [_zone(HazardType.LAVA, 120, 300, 300), _zone(HazardType.ICE, 120, 1000, 300), _zone(HazardType.TOXIC, 120, 1700, 300)]
    mgr.draw_minimap(surf, (0, 0), 0.1)
    assert surf.get_at((30, 30))[:3] == config.HAZARD_MINIMAP["lava"]
    assert surf.get_at((100, 30))[:3] == config.HAZARD_MINIMAP["ice"]
    assert surf.get_at((170, 30))[:3] == config.HAZARD_MINIMAP["toxic"]
    assert surf.get_at((30 - 11, 30 - 11))[:3] == (16, 22, 34)           # a diamond leaves its bounding-box corner empty
    assert surf.get_at((170 - 11, 30 - 11))[:3] == (16, 22, 34)          # ... and so does a disc
