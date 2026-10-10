"""TASK-053 / BUG-135: direct tests for the five hazard-art mutants the 042 r2 tests let through.

P6 lava core pulse 8x, N3 toxic fit limit 0.8 r + 6, N5 minimap lava diamond -> disc, N7 toxic edge back to the r1 bright
colour, N8 ice inner line equal to the edge (QA harness /workspace/qa/t44/h/mut44.py). All small and fast (default suite).
"""
from __future__ import annotations

import math
import random

import pygame
import pytest

from blob_evolution import config
from blob_evolution.systems.hazards import HazardManager, HazardZone
from blob_evolution.utils.enums import HazardType
from blob_evolution.utils.vector2 import Vector2

CAM = Vector2(1000, 1000)
NO_SHAKE = Vector2(0, 0)


@pytest.fixture(scope="module", autouse=True)
def _display():
    pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    yield


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb) -> float:
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def _baked(kind: HazardType, radius: int, seed: int = 0) -> HazardZone:
    random.seed(seed)
    zone = HazardZone(Vector2(1000, 1000), radius, kind)
    zone.build()
    return zone


class _Recorder(pygame.Surface):
    """A screen that remembers what was blitted onto it (to see which cached core frame the lava draws)."""

    def __init__(self, size):
        super().__init__(size)
        self.sources = []

    def blit(self, source, dest, *args, **kwargs):
        self.sources.append(source)
        return super().blit(source, dest, *args, **kwargs)


# --- P6: the lava core breathes once per sin period of the zone phase -------------------------------------------------

def test_lava_core_frame_follows_one_sine_of_the_phase():
    zone = _baked(HazardType.LAVA, 90)
    cores = zone._core
    n = len(cores)
    assert n == config.HAZARD_CORE_FRAMES >= 3
    screen = _Recorder((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    picked = []
    for k in range(240):                                     # one full period, 1.5 degree steps
        zone.phase = k * math.tau / 240
        screen.sources.clear()
        zone.draw(screen, CAM, NO_SHAKE)
        frames = [cores.index(s) for s in screen.sources if any(s is c for c in cores)]
        assert len(frames) == 1
        picked.append(frames[0])
        assert frames[0] == round((0.5 + 0.5 * math.sin(zone.phase)) * (n - 1))
    changes = sum(a != b for a, b in zip(picked, picked[1:]))
    assert changes == 2 * (n - 1)                            # up once and down once per period: no faster pulse


# --- N3: toxic bubbles keep their whole rise inside the green body (0.8 r - 6 px) -----------------------------------------

@pytest.mark.parametrize("radius", [60, 75, 90, 105, 120])
def test_every_toxic_bubble_rise_stays_inside_0_8_r_minus_6(radius):
    for seed in range(6):
        zone = _baked(HazardType.TOXIC, radius, seed)
        assert zone._anim
        for angle, dist, rad, _period, _offset, rise in zone._anim:
            bx, by = math.cos(angle) * dist * radius, math.sin(angle) * dist * radius
            reach = max(math.hypot(bx, by), math.hypot(bx, by - rise)) + rad
            assert reach <= 0.8 * radius - 6 + 1e-6, (radius, seed, reach)


def test_the_fit_uses_the_inner_limit_where_a_wider_limit_would_not_have_moved_the_bubble():
    """A bubble that fits 0.8 r + 6 but not 0.8 r - 6 must be moved (pins the sign of the 6 px margin)."""
    r, rad = 100, 4
    dist = (0.8 * r + 6 - rad - 0.5) / r                    # sits between the two limits, no rise needed horizontally
    fitted = HazardZone._fit_rise(((0.0, dist, rad, 1.6, 0.0),), r)[0]
    _a, d2, _r2, _p, _o, rise = fitted
    bx = d2 * r
    assert max(abs(bx), math.hypot(bx, rise)) + rad <= 0.8 * r - 6 + 1e-6


# --- N5: minimap shapes (lava diamond, ice hexagon, toxic disc) -------------------------------------------------------------

def _minimap_pixel(kind: str, fx: float, fy: float):
    hm = HazardManager()
    hm.zones = [HazardZone(Vector2(500, 500), 100, HazardType(kind))]
    surf = pygame.Surface((100, 100))
    surf.fill((0, 0, 0))
    hm.draw_minimap(surf, (0, 0), 0.1)                       # centre (50, 50), mr = 10 px
    return tuple(surf.get_at((50 + round(fx * 10), 50 + round(fy * 10))))[:3]


def test_minimap_lava_is_a_diamond_and_toxic_a_disc():
    lava, toxic = config.HAZARD_MINIMAP["lava"], config.HAZARD_MINIMAP["toxic"]
    assert _minimap_pixel("lava", 0.0, 0.0) == lava
    assert _minimap_pixel("lava", 0.6, 0.6) == (0, 0, 0)     # |x| + |y| = 1.2 r: outside a diamond, inside a disc
    assert _minimap_pixel("lava", -0.6, 0.6) == (0, 0, 0)
    assert _minimap_pixel("lava", 0.9, 0.0) == lava
    assert _minimap_pixel("toxic", 0.6, 0.6) == toxic        # the disc covers that corner
    assert _minimap_pixel("ice", 0.0, 0.0) == config.HAZARD_MINIMAP["ice"]


# --- N7 / N8: outline colours as drawn on the baked sprite -------------------------------------------------------------------

def _ray_pixels(zone: HazardZone, angle: float):
    """Opaque sprite pixels from the sprite edge inward along `angle` (outermost first)."""
    spr = zone._sprite
    c = spr.get_width() / 2
    out = []
    for step in range(int(c * 4), -1, -1):
        d = step / 4
        x, y = int(c + math.cos(angle) * d), int(c + math.sin(angle) * d)
        px = spr.get_at((x, y))
        if px.a >= 250 and (not out or out[-1][0] != (x, y)):
            out.append(((x, y), tuple(px)[:3]))
    return out


def test_toxic_outline_stays_at_the_r2_dimmed_brightness():
    """r2 (BUG-124) dimmed the toxic edge so a shot on the rim reads; r1's (190,255,90) is too bright. If the Visual Designer
    accepts a new edge colour (TASK-053-hazard-contrast.md), move this bound with it."""
    zone = _baked(HazardType.TOXIC, 90)
    brightest = max(_lum(rgb) for k in range(36) for _xy, rgb in _ray_pixels(zone, k * math.tau / 36 + 0.05)[:6])
    assert _lum(config.HAZARD_STYLE["toxic"]["edge"]) <= 0.50
    assert 0.25 <= brightest <= 0.50 + 1e-6


def _lit(sprite: pygame.Surface) -> float:
    """Sum of luminance x alpha over the sprite (how much light the baked art adds)."""
    total = 0.0
    for y in range(sprite.get_height()):
        for x in range(sprite.get_width()):
            px = sprite.get_at((x, y))
            if px.a:
                total += _lum(px) * px.a / 255
    return total


def test_ice_outline_is_a_bright_outer_line_over_a_dim_inner_line(monkeypatch):
    edge, inner = config.HAZARD_STYLE["ice"]["edge"], config.HAZARD_STYLE["ice"]["edge_inner"]
    assert _lum(inner) < 0.5 * _lum(edge)
    zone = _baked(HazardType.ICE, 60)
    c = zone._sprite.get_width() // 2
    column = [tuple(zone._sprite.get_at((c, y))) for y in range(c, 2 * c)]
    lit = [i for i, px in enumerate(column) if px[3] == 255 and _lum(px) >= 0.9 * _lum(edge)]
    assert lit, "the bright outer line is drawn at the bottom side midpoint"
    assert _lum(column[lit[-1] - 1]) < 0.5 * _lum(edge)          # just inside it: dimmer (inner line / fill), not a 2 px bright band
    dim = _lit(zone._sprite)
    monkeypatch.setitem(config.HAZARD_STYLE, "ice", {**config.HAZARD_STYLE["ice"], "edge_inner": edge})
    bright = _lit(_baked(HazardType.ICE, 60)._sprite)
    assert dim < 0.97 * bright                                   # the dim inner line takes visible light off the rim
