"""BUG-137 (Visual Designer approved): phantom wisps get an opaque 1 px rim (201,193,217), kept opaque while phased;
the PHANTOM body becomes (150,130,200) so it no longer matches BASIC in grayscale. Toggle off keeps the pre-046 look."""
from __future__ import annotations

import pytest

import pygame

from blob_evolution import config
from blob_evolution.entities.creature import Creature
from blob_evolution.utils import clock as anim_clock
from blob_evolution.utils import creature_shapes as shapes
from blob_evolution.utils.enums import CreatureType
from enemy_scene import BG, CX, CY, make, render

CT = CreatureType
RIM = (201, 193, 217)


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(config, "GFX_ENEMY_SHAPES", True)
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    monkeypatch.setattr(anim_clock, "game_ms", lambda: 0)
    pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb) -> float:
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def _cr(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _grey(c) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def test_wisp_rim_colour_reads_4_19_on_every_ground_tone():
    assert config.ENEMY_WISP_RIM == RIM
    worst = min(_cr(RIM, ramp[i]) for ramp in config.GROUND_RAMPS for i in range(3))
    assert worst >= 4.19, worst


def _wisps(c: Creature, monkeypatch):
    got = []
    real = shapes._blit_c

    def spy(dst, spr, x, y):
        got.append((spr, x, y))
        real(dst, spr, x, y)
    monkeypatch.setattr(shapes, "_blit_c", spy)
    s = render(c)
    return s, got[:6]


@pytest.mark.parametrize("phased", [False, True])
def test_every_wisp_has_an_opaque_rim_also_while_phased(phased, monkeypatch):
    c = make(CT.PHANTOM, 22, phased=phased)
    s, blits = _wisps(c, monkeypatch)
    fills, rims = blits[:3], blits[3:6]
    assert len(rims) == 3
    for ((fs, fox, foy), fx, fy), ((rs, rox, roy), rx, ry) in zip(fills, rims):
        assert (int(fx) + fox, int(fy) + foy, fs.get_size()) == (int(rx) + rox, int(ry) + roy, rs.get_size())   # same disc
        assert any(fs.get_at((x, y)).a < 255 for x in range(fs.get_width()) for y in range(fs.get_height()))  # fill translucent
        lit = [(x, y) for x in range(rs.get_width()) for y in range(rs.get_height()) if rs.get_at((x, y)).a]
        assert lit and all(tuple(rs.get_at(xy)) == (*RIM, 255) for xy in lit)
        # every fill pixel on the disc edge is covered by the rim
        w, h = fs.get_size()
        for x in range(w):
            for y in range(h):
                if fs.get_at((x, y)).a and any(not (0 <= x + dx < w and 0 <= y + dy < h) or not fs.get_at((x + dx, y + dy)).a
                                               for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    assert rs.get_at((x, y)).a == 255, (x, y)
    # on screen, rim pixels clear of the body are exactly the rim colour (opaque, not blended), phased or not. Clear of the
    # body means outside the phased glow (1.55 r, alpha 40), which tints whatever lies under it by design.
    clear = 0
    for (rs, ox, oy), x, y in rims:
        for yy in range(rs.get_height()):
            for xx in range(rs.get_width()):
                if rs.get_at((xx, yy)).a:
                    sx, sy = int(x) + ox + xx, int(y) + oy + yy
                    if (sx - CX) ** 2 + (sy - CY) ** 2 > (1.55 * 22 + 1) ** 2:
                        got = tuple(s.get_at((sx, sy)))[:3]
                        tol = 3 if phased else 0                     # phased: the body's faint glow edge may add 1-2 levels
                        assert all(abs(g - w) <= tol for g, w in zip(got, RIM)), (phased, sx, sy, got)
                        clear += 1
    assert clear >= 20, clear


def test_phantom_body_is_distinct_from_basic_in_grayscale():
    phantom, basic = Creature.COLORS[CT.PHANTOM][0], Creature.COLORS[CT.BASIC][0]
    assert phantom == (150, 130, 200)
    assert abs(_grey(phantom) - _grey(basic)) >= 30


def test_drawn_phantom_and_basic_bodies_differ_in_grayscale():
    def centre_grey(kind):
        s = render(make(kind, 22))
        px = s.get_at((CX + 6, CY + 8))
        return _grey(px)
    assert abs(centre_grey(CT.PHANTOM) - centre_grey(CT.BASIC)) >= 20


def test_toggle_off_keeps_the_pre_046_phantom_colour(monkeypatch):
    monkeypatch.setattr(config, "GFX_ENEMY_SHAPES", False)
    assert Creature.LEGACY_PHANTOM_COLORS == ((120, 100, 160), (180, 160, 220))
