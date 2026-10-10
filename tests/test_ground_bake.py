"""TASK-036: ground correctness and fast bake (shake direction, void fill outside the world, vignette rewrite).

The ground used to shake the opposite way to the entities, left stale pixels on screen when a world edge was
visible, and spent about 70 ms of its 100 ms bake on a 5 px rect-loop vignette. These tests pin the three fixes.
The strict per-act bake check (90 ms since TASK-037) is slow-marked (wall-clock); a looser guard runs by default.
"""
from __future__ import annotations

import random
import statistics
import time

import pygame
import pytest

from blob_evolution import config
from blob_evolution.entities.projectile import Projectile
from blob_evolution.maps.generator import MapGenerator
from blob_evolution.utils import graphics
from blob_evolution.utils.graphics import generate_map_texture
from blob_evolution.utils.vector2 import Vector2

W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
WORLD = (config.WORLD_WIDTH, config.WORLD_HEIGHT)
MARKER = (255, 0, 255)
SENTINEL = (1, 2, 3)


class _CountingSurface(pygame.Surface):
    """A screen that counts fill() calls."""

    fills = 0

    def fill(self, *args, **kwargs):
        self.fills += 1
        return super().fill(*args, **kwargs)


def _gen_with_flat_world(color=(60, 60, 60)) -> MapGenerator:
    """A MapGenerator whose ground is a plain 2000x2000 surface (no bake needed)."""
    gen = MapGenerator()
    gen.background = pygame.Surface(WORLD)
    gen.background.fill(color)
    return gen


def _bake(act: int, seed: int = 7) -> pygame.Surface:
    th = config.MAP_THEMES[act]
    return generate_map_texture(config.WORLD_WIDTH, config.WORLD_HEIGHT, th["color"], th["accent"], seed, act)


@pytest.fixture(scope="module")
def baked_act0() -> pygame.Surface:
    return _bake(0)


# --- A. shake direction -------------------------------------------------------------------------------------

@pytest.mark.parametrize("shake", [(8, -5), (-6, 7), (0, 0), (3.6, -2.4)])
def test_ground_point_lands_where_an_entity_at_the_same_world_point_lands(shake):
    gen = _gen_with_flat_world()
    gen.background.set_at((1000, 1000), MARKER)
    cam, sh = Vector2(1000, 1000), Vector2(*shake)

    ground = pygame.Surface((W, H))
    gen.draw_background(ground, cam, sh)
    found = [(x, y) for x in range(W) for y in range(H) if ground.get_at((x, y))[:3] == MARKER]
    assert len(found) == 1

    entity = pygame.Surface((W, H))
    shot = Projectile(Vector2(1000, 1000), Vector2(1, 0), 0, 0)
    shot.draw(entity, cam, sh)
    rect = pygame.mask.from_threshold(entity, shot.color, (1, 1, 1, 255)).get_bounding_rects()[0]
    ex, ey = found[0]
    assert abs(rect.centerx - ex) <= 1 and abs(rect.centery - ey) <= 1, (rect, found[0])


def test_ground_moves_with_the_shake_not_against_it():
    gen = _gen_with_flat_world()
    gen.background.set_at((1000, 1000), MARKER)
    screen = pygame.Surface((W, H))
    gen.draw_background(screen, Vector2(1000, 1000), Vector2(8, -5))
    assert screen.get_at((W // 2 + 8, H // 2 - 5))[:3] == MARKER


# --- B. void fill outside the world ----------------------------------------------------------------------

@pytest.mark.parametrize("cam", [(40, 40), (1960, 40), (40, 1960), (1960, 1960), (20, 1000), (1000, 15), (1990, 1000)])
def test_every_pixel_outside_the_world_is_the_void_colour(cam):
    gen = _gen_with_flat_world((70, 80, 90))
    gen.void_color = (11, 22, 33)
    screen = pygame.Surface((W, H))
    screen.fill(SENTINEL)   # stale previous frame
    gen.draw_background(screen, Vector2(*cam), Vector2(0, 0))
    ox, oy = cam[0] - W // 2, cam[1] - H // 2   # world coordinate of the screen's top-left
    outside = inside = 0
    for sy in range(0, H, 5):
        for sx in range(0, W, 5):
            wx, wy = ox + sx, oy + sy
            px = screen.get_at((sx, sy))[:3]
            if 0 <= wx < WORLD[0] and 0 <= wy < WORLD[1]:
                inside += 1
                assert px == (70, 80, 90)
            else:
                outside += 1
                assert px == (11, 22, 33), (sx, sy, px)
    assert outside > 0 and inside > 0


def test_corner_with_shake_and_a_real_bake_still_has_no_stale_pixels(baked_act0):
    gen = MapGenerator()
    gen.background = baked_act0
    screen = pygame.Surface((W, H))
    screen.fill(SENTINEL)
    gen.draw_background(screen, Vector2(40, 40), Vector2(-6, 4))
    stale = sum(1 for y in range(0, H, 4) for x in range(0, W, 4) if screen.get_at((x, y))[:3] == SENTINEL)
    assert stale == 0
    assert screen.get_at((5, 5))[:3] == gen.void_color


def test_fill_only_runs_when_a_world_edge_is_on_screen():
    gen = _gen_with_flat_world()
    screen = _CountingSurface((W, H))
    gen.draw_background(screen, Vector2(1000, 1000), Vector2(0, 0))
    gen.draw_background(screen, Vector2(W // 2, H // 2), Vector2(0, 0))                 # edges exactly on screen edges
    gen.draw_background(screen, Vector2(config.WORLD_WIDTH - W // 2, config.WORLD_HEIGHT - H // 2), Vector2(0, 0))
    assert screen.fills == 0
    gen.draw_background(screen, Vector2(W // 2 - 1, 1000), Vector2(0, 0))               # one pixel of void on the left
    assert screen.fills == 1
    gen.draw_background(screen, Vector2(1000, 1000), Vector2(0, 0))
    assert screen.fills == 1


def test_no_background_still_clears_to_the_default_colour():
    gen = MapGenerator()
    screen = pygame.Surface((W, H))
    screen.fill(SENTINEL)
    gen.draw_background(screen, Vector2(1000, 1000), Vector2(0, 0))
    assert screen.get_at((3, 3))[:3] == config.COLOR_BG


@pytest.mark.parametrize("act", range(len(config.MAP_THEMES)))
def test_load_map_sets_void_colour_from_the_act_dark_tone(act):
    """TASK-037: void colour = the act's DARK ground tone x 0.5 (TASK-036 used theme colour x 0.4 as a stand-in)."""
    dark = config.GROUND_RAMPS[act][0]
    expected = tuple(int(c * 0.5) for c in dark)
    assert MapGenerator._void_color_for(act) == expected
    assert all(isinstance(c, int) and 0 <= c <= 255 for c in expected)
    assert all(e < c for e, c in zip(expected, dark))


def test_load_map_updates_void_colour_with_the_act():
    gen = MapGenerator()
    gen.load_map(3, seed=1)
    assert gen.void_color == (17, 8, 7)
    gen.load_map(7, seed=1)
    assert gen.void_color == (5, 4, 9)


# --- C. vignette rewrite ---------------------------------------------------------------------------------

def test_vignette_is_transparent_in_the_middle_and_darkest_in_the_corners():
    vg = graphics._make_vignette(*WORLD)
    assert vg.get_size() == WORLD
    for x, y in [(1000, 1000), (600, 750), (1399, 1249), (600, 1249), (1399, 750)]:   # the central 800x500
        assert vg.get_at((x, y))[3] == 0
    corner = vg.get_at((0, 0))[3]
    assert 90 <= corner <= graphics.VIGNETTE_MAX_ALPHA
    assert all(vg.get_at((x, y))[:3] == (0, 0, 0) for x, y in [(0, 0), (1999, 1999), (0, 1999), (1999, 0)])
    # darker towards the edge along a ray from the centre
    ray = [vg.get_at((1000 + d, 1000))[3] for d in range(0, 1000, 50)]
    assert ray == sorted(ray) and ray[-1] > 0


def test_vignette_is_symmetric():
    vg = graphics._make_vignette(*WORLD)
    for x, y in [(30, 100), (400, 50), (1000, 30)]:
        a = vg.get_at((x, y))[3]
        assert abs(a - vg.get_at((WORLD[0] - 1 - x, y))[3]) <= 2
        assert abs(a - vg.get_at((x, WORLD[1] - 1 - y))[3]) <= 2


def test_central_800x500_is_identical_to_a_bake_without_any_vignette(baked_act0, monkeypatch):
    monkeypatch.setattr(graphics, "_make_vignette", lambda w, h: pygame.Surface((w, h), pygame.SRCALPHA))
    no_vignette = _bake(0)
    box = pygame.Rect(600, 750, 800, 500)
    assert pygame.image.tobytes(baked_act0.subsurface(box), "RGB") == pygame.image.tobytes(no_vignette.subsurface(box), "RGB")
    assert pygame.image.tobytes(baked_act0, "RGB") != pygame.image.tobytes(no_vignette, "RGB")   # the edges do change


def test_edges_are_darker_than_without_the_vignette(baked_act0, monkeypatch):
    monkeypatch.setattr(graphics, "_make_vignette", lambda w, h: pygame.Surface((w, h), pygame.SRCALPHA))
    flat = _bake(0)
    lum = lambda c: c[0] + c[1] + c[2]
    for p in [(2, 2), (1997, 5), (3, 1996), (1996, 1996)]:
        assert lum(baked_act0.get_at(p)) < lum(flat.get_at(p))


def test_bake_is_deterministic_and_does_not_touch_the_global_random_stream():
    random.seed(99)
    state = random.getstate()
    a = _bake(4, seed=145)
    assert random.getstate() == state
    b = _bake(4, seed=145)
    assert pygame.image.tobytes(a, "RGB") == pygame.image.tobytes(b, "RGB")
    assert pygame.image.tobytes(a, "RGB") != pygame.image.tobytes(_bake(4, seed=146), "RGB")


def test_texture_is_the_world_size_and_opaque(baked_act0):
    assert baked_act0.get_size() == WORLD
    assert baked_act0.get_at((1000, 1000))[3] == 255
    assert baked_act0.get_at((0, 0))[3] == 255


# --- timing ------------------------------------------------------------------------------------------------

def _best_bake_ms(act: int, runs: int) -> float:
    best = 1e9
    for _ in range(runs):
        t = time.process_time()
        _bake(act)
        best = min(best, (time.process_time() - t) * 1000)
    return best


@pytest.mark.parametrize("act", [0, 4])
def test_bake_is_well_under_the_old_100_ms(act):
    """Loose guard (the old rect-loop vignette alone cost ~72 ms): best of 3 under 80 ms."""
    assert _best_bake_ms(act, 3) < 80


@pytest.mark.slow
@pytest.mark.parametrize("act", range(len(config.MAP_THEMES)))
def test_bake_time_per_act_is_at_most_90_ms(act):
    """TASK-037 acceptance 2: each of the 10 acts bakes in <= 90 ms (seed 7); best of 5 to ignore scheduler noise.

    TASK-036 asserted 45 ms for the old terrain; the 037 terrain (macro noise) has a 90 ms budget and ~45 ms measured."""
    assert _best_bake_ms(act, 5) <= 90


@pytest.mark.slow
def test_centred_ground_draw_is_cheap(baked_act0):
    """TASK-036 acceptance 5 (proxy): the conditional fill adds nothing when no edge is on screen."""
    gen = MapGenerator()
    gen.background = baked_act0
    screen = pygame.Surface((W, H))
    cam, sh = Vector2(1000, 1000), Vector2(0, 0)
    gen.draw_background(screen, cam, sh)
    times = []
    for _ in range(5):
        t = time.process_time()
        for _ in range(200):
            gen.draw_background(screen, cam, sh)
        times.append((time.process_time() - t) / 200 * 1000)
    assert statistics.median(times) < 0.6
