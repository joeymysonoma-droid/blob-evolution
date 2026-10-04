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
from blob_evolution.systems.ambient import AmbientField
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


# --- TASK-042 r2 (QA hold): extents over the whole animation, dense contrast in all ten acts, fills, pulse -----------------------------

ALL_RADII = list(range(40, 121, 5))                                      # generation uses 60..120; 40..55 are checked as a margin
SURFACE = 320                                                            # the zone is drawn at (160, 160) of a transparent surface
_circle_masks: dict = {}


def _circle_mask(radius: int) -> pygame.mask.Mask:
    """Mask of every pixel whose centre is within radius + 0.5 of the zone centre (the zone centre sits on a pixel corner)."""
    if radius not in _circle_masks:
        mask = pygame.mask.Mask((SURFACE, SURFACE))
        for y in range(SURFACE):
            for x in range(SURFACE):
                if math.hypot(x + 0.5 - SURFACE // 2, y + 0.5 - SURFACE // 2) <= radius + 0.5:
                    mask.set_at((x, y), 1)
        _circle_masks[radius] = mask
    return _circle_masks[radius]


def _pixels_outside_the_radius(zone: HazardZone, surface: pygame.Surface, camera: Vector2) -> int:
    surface.fill((0, 0, 0, 0))
    zone.draw(surface, camera, NO_SHAKE)
    drawn = pygame.mask.from_surface(surface, 8)
    return drawn.count() - drawn.overlap_area(_circle_mask(int(zone.radius)), (0, 0))


def _extent_sweep(kind: HazardType, radii, seeds: int, seconds: float, step: float) -> None:
    surface = pygame.Surface((SURFACE, SURFACE), pygame.SRCALPHA)
    for radius in radii:
        for seed in range(seeds):
            zone = _zone(kind, radius, 400 + 97 * seed + radius, 300 + 61 * seed)
            zone.build()
            camera = Vector2(zone.pos.x + config.SCREEN_WIDTH // 2 - SURFACE // 2, zone.pos.y + config.SCREEN_HEIGHT // 2 - SURFACE // 2)
            for k in range(int(seconds / step)):
                zone.phase = 2.0 * k * step                              # phase = 2 x seconds
                outside = _pixels_outside_the_radius(zone, surface, camera)
                assert outside == 0, (kind, radius, seed, round(k * step, 2), outside)


@pytest.mark.parametrize("kind", TYPES)
def test_every_animated_part_stays_inside_the_hit_radius_over_the_whole_cycle(kind):
    """Bubbles, sparkle arms, lava bubbles and every core frame: nothing drawn beyond r + 0.5 px at any moment (BUG-123 / BUG-126)."""
    _extent_sweep(kind, ALL_RADII, 3, 8.0, 0.1)


@pytest.mark.slow
@pytest.mark.parametrize("kind", TYPES)
def test_every_animated_part_stays_inside_the_hit_radius_every_radius_every_frame(kind):
    _extent_sweep(kind, range(40, 121), 4, 12.0, 1 / 30)


@pytest.mark.parametrize("radius", range(40, 121))
def test_toxic_bubbles_stay_inside_the_green_body_with_their_whole_rise(radius):
    for seed in range(12):
        zone = _zone(HazardType.TOXIC, radius, 300 + 53 * seed, 500 + 29 * seed)
        zone.build()
        for angle, dist, rad, _period, _offset, rise in zone._anim:
            assert 0 < rise <= config.HAZARD_BUBBLE_RISE
            for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
                x, y = math.cos(angle) * dist * radius, math.sin(angle) * dist * radius - rise * frac
                assert math.hypot(x, y) + rad <= radius - 1, (radius, seed, frac)    # centre + bubble radius never reaches the hit circle


def test_every_core_frame_and_lava_bubble_fits_the_hit_circle_and_the_core_is_dimmer_than_the_fill_glow_cap():
    for radius in (40, 60, 90, 120):
        zone = _zone(HazardType.LAVA, radius)
        zone.build()
        for core in zone._core:
            data = pygame.image.tobytes(core, "RGBA")
            w = core.get_width()
            far = max((math.hypot(x + 0.5 - w / 2, y + 0.5 - w / 2) for y in range(w) for x in range(w) if data[(y * w + x) * 4 + 3] > 8), default=0.0)
            assert far <= radius + 0.5, (radius, far)
        for _angle, dist, big, _period, _offset in zone._anim:
            assert dist * radius + big <= radius - 1
    assert config.HAZARD_STYLE["lava"]["core"][3] <= 40                  # BUG-125: the glow stays a faint warm tint, not a bright centre


# --- fills: dark and opaque enough to read a shot, an XP orb and the player on top of them -------------------------------------

def _inner_fill(kind: HazardType) -> tuple:
    zone = _zone(kind, 100)
    zone.build()
    sprite = zone._sprite
    c = sprite.get_width() // 2
    px = [sprite.get_at((c + dx, c + dy)) for dy in range(-30, 31, 2) for dx in range(-30, 31, 2) if math.hypot(dx, dy) <= 30]
    n = len(px)
    return tuple(sum(p[i] for p in px) / n for i in range(4))


@pytest.mark.parametrize("kind", TYPES)
def test_hazard_fills_are_dark_and_mostly_opaque(kind):
    """Catches a bright fill (e.g. the plan's (100,180,255)) and facets/rings that punch holes through the fill (BUG-126)."""
    r, g, b, a = _inner_fill(kind)
    assert a >= 170, (kind, a)                                           # the ground only shows through a little
    assert _lum((r, g, b)) <= 0.03, (kind, (r, g, b), _lum((r, g, b)))


def test_ice_fill_is_the_configured_dark_blue_under_the_facets():
    r, g, b, a = _inner_fill(HazardType.ICE)
    fill = config.HAZARD_STYLE["ice"]["fill"]
    assert abs(a - fill[3]) <= 8 and max(abs(r - fill[0]), abs(g - fill[1]), abs(b - fill[2])) <= 12, ((r, g, b, a), fill)


def test_the_ice_edge_is_dimmed_and_the_outline_still_reads_against_every_ground():
    edge = config.HAZARD_STYLE["ice"]["edge"]
    assert _lum(edge) <= 0.70                                            # BUG-124: no near-white rim behind an enemy shot
    assert min(_cr(edge, ramp[1]) for ramp in config.GROUND_RAMPS) >= 5.0


# --- lava core: slow pulse, no flash -------------------------------------------------------------------------------------------

def test_the_lava_core_pulses_at_most_once_a_second_and_never_flashes(screen):
    zone = _zone(HazardType.LAVA, 90, 1000, 1000, phase=0.0)
    zone.build()
    seen = []
    for _ in range(60 * 20):                                             # 20 s at 60 fps
        zone.update(1 / 60)
        screen.fill((20, 30, 40))
        zone.draw(screen, CAM, NO_SHAKE)
        seen.append(sum(pygame.transform.average_color(screen.subsurface((570, 370, 60, 60)))[:3]))
    steps = [abs(b - a) for a, b in zip(seen, seen[1:])]
    assert max(steps) <= 4, max(steps)                                   # a pulse step is a few % of the centre brightness at most
    levels = [v for k, v in enumerate(seen) if k == 0 or v != seen[k - 1]]       # collapse the held frames, then count the peaks
    peaks = sum(1 for k in range(1, len(levels) - 1) if levels[k] > levels[k - 1] and levels[k] > levels[k + 1])
    assert 0 < peaks <= 20, peaks                                        # <= 1 pulse per second over 20 s


def test_the_lava_core_frame_follows_the_slow_phase_not_the_frame_rate():
    assert config.HAZARD_CORE_FRAMES >= 2
    phase_speed = 2.0                                                    # HazardZone.update advances the phase by 2 rad/s
    assert phase_speed / math.tau <= 1.0                                 # one core pulse per 2*pi/2 = 3.14 s


# --- contrast, dense: every position from the centre to the rim, ten acts, three hazards, normal and low HP ----------------------

RMIN = {HazardType.LAVA: 0.93, HazardType.TOXIC: 0.80, HazardType.ICE: 0.84}      # smallest outline radius / R of each shape
SHOT_TARGET, SHOT_RIM_FLOOR, PLAYER_XP_FLOOR = 3.3, 2.7, 3.0


def _ring(r0: float, r1: float, step: int = 1):
    n = int(r1) + 1
    return [(dx, dy) for dy in range(-n, n + 1) for dx in range(-n, n + 1) if r0 <= math.hypot(dx, dy) <= r1][::step]


def _dense_contrast(act: int, kind: HazardType, lowhp: bool, screen, radii, angles: int, phases, step: float = 0.05) -> dict:
    """Contrast of the player body, an enemy shot and an XP orb at fractions 0..1 of the radius, real ground, zone, fog, ambient and
    overlay. Items inside the outline band (further from the outline than the 14 px sampling ring + 3 px) must reach 3.3 (shots) or 3.0,
    items in the band 2.7 (shots) or 3.0; where even the bare ground (no zone) is below that, the zone must not be worse than the
    bare ground. Returns the worst value per item and band and the smallest margin over the requirement."""
    ring, around, body, bg_small = _ring(15, 19), _ring(23, 30, 3), _ring(0, 2), _ring(9, 14, 2)
    gen = MapGenerator()
    gen.load_map(act, 7)
    depth = layers.DepthLayers(act, 7)
    red = layers.build_overlay(*config.LOW_HP_OVERLAY)
    ambient = AmbientField(act, 5)
    for _ in range(180):
        ambient.update(1 / 60, CAM)
    rng = random.Random(f"{act}-{kind.value}-{lowhp}")
    worst = {"body": [99.0, 99.0], "shot": [99.0, 99.0], "xp": [99.0, 99.0], "margin": (99.0, None)}          # [inside, rim band]
    for radius in radii:
        limit = RMIN[kind] * radius - (1.5 if kind == HazardType.ICE else 0.0) - 17
        for phase in phases:
            for a_i in range(angles):
                angle = a_i * math.tau / angles
                for k in range(int(round(1 / step)) + 1):
                    frac = k * step
                    if k == 0 and a_i > 0:
                        continue
                    sx, sy = rng.uniform(-200, 200), rng.uniform(-150, 150)
                    px, py = round(600 + sx), round(400 + sy)
                    world = Vector2(rng.uniform(400, 1600), rng.uniform(400, 1600))
                    cam = Vector2(world.x - sx, world.y - sy)
                    zone = _zone(kind, radius, world.x - math.cos(angle) * frac * radius, world.y - math.sin(angle) * frac * radius,
                                 phase + 0.35 * a_i)
                    band = 0 if frac * radius <= limit else 1

                    def base(with_zone: bool = True):
                        gen.draw_background(screen, cam, NO_SHAKE)
                        if with_zone:
                            zone.draw(screen, cam, NO_SHAKE)
                        depth.blit_fog(screen, cam, NO_SHAKE)
                        ambient.draw_back(screen, cam, NO_SHAKE)
                        screen.blit(red if lowhp else depth.vignette, (0, 0))

                    def measure(item: str, with_zone: bool) -> float:
                        base(with_zone)
                        if item == "body":
                            draw_blob(screen, (px, py), 20, config.COLOR_PLAYER, config.COLOR_PLAYER_CORE, look=(1, 0))
                        else:
                            pygame.draw.circle(screen, config.COLOR_PROJECTILE_ENEMY if item == "shot" else config.COLOR_XP, (px, py), 5)
                        ambient.draw_front(screen, cam, NO_SHAKE)
                        got = _mean([screen.get_at((px + dx, py + dy)) for dx, dy in (ring if item == "body" else body)])
                        base(with_zone)
                        ambient.draw_front(screen, cam, NO_SHAKE)
                        return _cr(got, _mean([screen.get_at((px + dx, py + dy)) for dx, dy in (around if item == "body" else bg_small)]))
                    screen.set_clip(pygame.Rect(px - 40, py - 40, 80, 80))
                    try:
                        for item in ("body", "shot", "xp"):
                            need = SHOT_TARGET if item == "shot" and band == 0 else SHOT_RIM_FLOOR if item == "shot" else PLAYER_XP_FLOOR
                            value = measure(item, True)
                            worst[item][band] = min(worst[item][band], value)
                            if value < need:                              # lazily: the bare ground at the same spot sets the bar if it is lower
                                need = min(need, measure(item, False))
                            if value - need < worst["margin"][0]:
                                worst["margin"] = (value - need, (item, radius, round(frac, 2), a_i, phase))
                    finally:
                        screen.set_clip(None)
    return worst


def _check_dense(act: int, kind: HazardType, screen, radii, angles: int, phases) -> None:
    for lowhp in (False, True):
        w = _dense_contrast(act, kind, lowhp, screen, radii, angles, phases)
        where = (act, kind.value, "lowhp" if lowhp else "normal", w)
        assert w["margin"][0] >= -1e-9, where       # inside: shots >= 3.3 (BUG-124/125); outline band: >= 2.7; body and XP >= 3.0; never below bare ground


@pytest.mark.parametrize("kind", TYPES)
@pytest.mark.parametrize("act", range(10))
def test_dense_contrast_every_act_every_hazard_centre_to_rim(act, kind, screen):
    """0.00..1.00 r in 0.05 steps, 2 angles, radii 60/120 (the generation extremes) and 40/90 on one angle, normal and low HP."""
    _check_dense(act, kind, screen, (60, 120), 2, (0.7, 4.9))
    _check_dense(act, kind, screen, (40, 90), 1, (2.4,))


@pytest.mark.slow
@pytest.mark.parametrize("kind", TYPES)
@pytest.mark.parametrize("act", range(10))
def test_dense_contrast_slow_sweep_all_radii_angles_and_phases(act, kind, screen):
    """Radii 40/60/80/100/120, 8 angles, 3 animation phases (about 2400 positions per item), normal and low HP."""
    _check_dense(act, kind, screen, (40, 60, 80, 100, 120), 8, (0.7, 2.4, 4.9))
