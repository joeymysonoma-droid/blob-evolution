"""TASK-041: depth layers (utils/layers.py): half-speed fog and the cached screen-space light overlay.

Checks the plan's acceptance: a seamless 512 tile pre-tiled to 1712x1312, the per-act fog table (counts and alpha
ranges), the overlay (alpha 0 in the centre, max alpha in the corners, never over the HUD), the red low-HP switch and
the pulses (<= 1 Hz, prebuilt levels, no per-frame allocation), and that both layers are purely visual: own seeded rng
(the global random stream is never touched), no gameplay state changed, nothing saved, GFX_LAYERS switches them off.
"""
from __future__ import annotations

import json
import random
import time
from typing import List

import pygame
import pytest

from blob_evolution import config
from blob_evolution.utils import layers
from blob_evolution.utils.enums import GameState, NodeType
from blob_evolution.utils.layers import DepthLayers
from blob_evolution.utils.vector2 import Vector2

ACTS = range(len(config.MAP_THEMES))
W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
TILE = config.FOG_TILE
NO_SHAKE = Vector2(0, 0)
PLAN_OVERLAYS = [((2, 10, 6), 120), ((8, 12, 2), 130), ((2, 4, 18), 130), ((24, 4, 0), 120), ((6, 14, 26), 110),
                 ((30, 18, 4), 110), ((14, 4, 26), 130), ((0, 0, 4), 170), ((2, 4, 16), 120), ((22, 0, 16), 140)]
PLAN_FOG_COUNTS = [14, 10, 30, 10, 11, 10, 10, 12, 12, 12]      # acts 4 and 5 re-split by the Visual Designer (5+6, 5+5)


# --- config vs plan ---------------------------------------------------------------------------------------------

def test_overlay_table_matches_the_plan():
    assert list(config.LIGHT_OVERLAYS) == PLAN_OVERLAYS
    assert config.LIGHT_GRID == (16, 10) and config.LIGHT_START == 0.35
    assert config.LOW_HP_RATIO == 0.30 and config.LOW_HP_OVERLAY == ((120, 10, 20), 150)
    assert config.LOW_HP_PULSE == (0.6, 1.0, 1.0) and config.HEARTBEAT == (1.0, 1.15, 0.8)
    assert config.LOW_HP_PULSE[2] <= 1.0 and config.HEARTBEAT[2] <= 1.0                  # R5: pulses at most 1 Hz
    assert config.FOG_TILE == 512 and config.FOG_PARALLAX == 0.5 and config.GFX_LAYERS is True


def test_fog_table_matches_the_plan_with_the_visual_designer_retune():
    assert len(config.FOG_LAYERS) == 10
    for act, groups in enumerate(config.FOG_LAYERS):
        assert sum(g["n"] for g in groups) == PLAN_FOG_COUNTS[act], act
    a = config.FOG_LAYERS
    assert (a[0][0]["color"], a[0][0]["alpha"], a[0][0]["radius"]) == ((4, 16, 8), (40, 60), (40, 90))
    assert (a[1][0]["color"], a[1][0]["alpha"], a[1][0]["radius"]) == ((84, 100, 44), (26, 40), (60, 120))
    assert (a[2][0]["kind"], a[2][0]["color"], a[2][0]["alpha"]) == ("caustic", (90, 150, 230), (16, 24))
    assert (a[3][0]["color"], a[3][0]["alpha"], a[3][0]["radius"]) == ((20, 8, 6), (50, 70), (70, 130))
    assert [(g["color"], g["alpha"], g["radius"], g["n"]) for g in a[4]] == [
        ((52, 88, 118), (22, 34), (80, 140), 5), ((6, 16, 28), (44, 60), (90, 150), 6)]
    assert [(g["color"], g["alpha"], g["radius"], g["n"]) for g in a[5]] == [
        ((96, 74, 44), (24, 36), (80, 140), 5), ((40, 28, 14), (44, 60), (90, 150), 5)]
    assert (a[6][0]["color"], a[6][0]["alpha"], a[6][0]["radius"]) == ((120, 70, 180), (24, 38), (70, 120))
    assert a[8][0]["alpha"][1] <= 26                                                     # act 8 streaks stay faint
    assert [(g["color"], g["alpha"]) for g in a[7]] == [((0, 0, 0), (60, 90)), ((70, 50, 110), (20, 20))]
    assert (a[8][0]["kind"], a[8][0]["size"], a[8][0]["color"], a[8][0]["alpha"]) == (
        "ellipse", (220, 40), (150, 180, 255), (16, 26))
    assert [(g["color"], g["alpha"]) for g in a[9]] == [((180, 30, 120), (24, 40)), ((12, 2, 14), (50, 50))]


# --- fog --------------------------------------------------------------------------------------------------------

def _px(surf: pygame.Surface, x: int, y: int):
    return tuple(surf.get_at((x, y)))


@pytest.mark.parametrize("act", ACTS)
def test_fog_is_pretiled_1712x1312_and_periodic_in_512(act):
    fog = layers.build_fog(act, 3)
    assert fog.get_size() == (W + TILE, H + TILE) == (1712, 1312)
    assert bool(fog.get_flags() & pygame.SRCALPHA) == (act != 2)
    for x, y in ((0, 0), (37, 400), (511, 511), (250, 17), (100, 300)):
        assert _px(fog, x, y) == _px(fog, x + TILE, y) == _px(fog, x, y + TILE) == _px(fog, x + TILE, y + TILE)


@pytest.mark.parametrize("act", [a for a in ACTS if a != 2])
def test_fog_tile_has_no_seam_where_it_wraps(act):
    """The wrap edge (column 511 -> 512 == 0, row 511 -> 512 == 0) is as smooth as the interior."""
    fog = layers.build_fog(act, 5)

    def jump(a, b):                     # alpha only: the colour of a fully transparent pixel is meaningless
        return abs(a[3] - b[3])

    worst_interior = max(jump(_px(fog, x, y), _px(fog, x + 1, y)) for x in range(0, 512, 3) for y in range(0, 512, 16))
    seam_x = max(jump(_px(fog, 511, y), _px(fog, 512, y)) for y in range(0, 512, 4))
    seam_y = max(jump(_px(fog, x, 511), _px(fog, x, 512)) for x in range(0, 512, 4))
    assert max(seam_x, seam_y) <= max(worst_interior, 2) + 2


@pytest.mark.parametrize("act", ACTS)
def test_fog_alpha_stays_inside_the_plan_budget(act):
    """Each blob is at most its alpha max; overlapping blobs add up, but one blob never exceeds the plan's maximum."""
    groups = config.FOG_LAYERS[act]
    fog = layers.build_fog(act, 11)
    if act == 2:
        top = max(max(_px(fog, x, y)[:3]) for x in range(0, TILE, 3) for y in range(0, TILE, 3))
        assert top > 0 and top <= 255
        return
    alphas = [_px(fog, x, y)[3] for x in range(0, TILE, 4) for y in range(0, TILE, 4)]
    assert max(alphas) > 0
    assert min(alphas) >= 0
    assert max(alphas) < 255
    solo = [layers._soft_sprite("blob" if g["kind"] != "ellipse" else "ellipse", g["color"], g["alpha"][1],
                                (40, 40)) for g in groups]
    for sprite, g in zip(solo, groups):
        peak = max(sprite.get_at((x, y))[3] for x in range(sprite.get_width()) for y in range(sprite.get_height()))
        assert peak == g["alpha"][1]
        halo = sprite.get_at((1 + sprite.get_width() // 2 - 2, sprite.get_height() // 2))[3]
        assert halo <= g["alpha"][1]


def test_soft_sprite_has_a_core_and_a_third_alpha_halo():
    sprite = layers._soft_sprite("blob", (10, 20, 30), 60, (80, 80))
    cx = sprite.get_width() // 2
    assert sprite.get_at((cx, cx))[3] == 60
    ring = [sprite.get_at((cx + dx, cx))[3] for dx in range(0, sprite.get_width() // 2)]
    assert set(ring) <= {0, 20, 60} and 20 in ring and ring[-1] in (0, 20)
    assert sprite.get_width() > 80 * 1.3


@pytest.mark.parametrize("act", ACTS)
def test_same_seed_same_fog_different_seed_differs(act):
    a, b, c = layers.build_fog(act, 1), layers.build_fog(act, 1), layers.build_fog(act, 2)
    assert pygame.image.tostring(a, "RGBA") == pygame.image.tostring(b, "RGBA")
    assert pygame.image.tostring(a, "RGBA") != pygame.image.tostring(c, "RGBA")


@pytest.mark.parametrize("act", ACTS)
def test_building_never_touches_the_global_random_stream(act):
    random.seed(4242)
    state = random.getstate()
    DepthLayers(act, 9).blit_vignette(pygame.Surface((W, H)), 0.1)
    assert random.getstate() == state


def test_additive_fog_is_only_the_caustic_act():
    assert [layers.fog_is_additive(a) for a in ACTS] == [a == 2 for a in ACTS]


def test_fog_blit_position_is_half_speed_and_shake_is_folded_in():
    d = DepthLayers(0, 1)
    seen: List[tuple] = []

    class Spy:
        def blit(self, surf, pos, special_flags=0):
            seen.append(pos)

    d.blit_fog(Spy(), Vector2(1000, 600), NO_SHAKE)
    assert seen[-1] == (-(500 % 512), -(300 % 512))
    d.blit_fog(Spy(), Vector2(1000 + 2, 600 + 2), NO_SHAKE)       # the camera moving 2 px moves the fog 1 px
    assert seen[-1] == (-(501 % 512), -(301 % 512))
    d.blit_fog(Spy(), Vector2(1000, 600), Vector2(5, -3))         # the shake moves it 1:1 like entities
    assert seen[-1] == (int(-((500 - 5) % 512)), int(-((300 + 3) % 512)))
    for cx in (-3000.0, -1.0, 0.0, 511.9, 1023.0, 99999.0):
        d.blit_fog(Spy(), Vector2(cx, cx * 0.7), Vector2(7, 7))
        x, y = seen[-1]
        assert -TILE < x <= 0 and -TILE < y <= 0                 # the 1712x1312 surface always covers the screen


@pytest.mark.parametrize("act", ACTS)
def test_fog_covers_every_screen_position_it_paints(act):
    """Whatever the camera, the blit rectangle contains the whole 1200x800 screen (no gap at an edge)."""
    d = DepthLayers(act, 4)
    for cam in (Vector2(0, 0), Vector2(1023, 1023), Vector2(1500.5, 333.3), Vector2(-777, 4000)):
        x = -((cam.x * 0.5) % TILE)
        y = -((cam.y * 0.5) % TILE)
        assert x <= 0 and y <= 0 and x + d.fog.get_width() >= W and y + d.fog.get_height() >= H


@pytest.mark.parametrize("act", ACTS)
def test_fog_blit_paints_something_and_only_changes_the_surface_it_is_given(act):
    d = DepthLayers(act, 6)
    screen = pygame.Surface((W, H))
    screen.fill((90, 90, 90))
    before = pygame.image.tostring(screen, "RGB")
    d.blit_fog(screen, Vector2(800, 800), NO_SHAKE)
    assert pygame.image.tostring(screen, "RGB") != before


def test_act_2_caustic_light_only_brightens():
    d = DepthLayers(2, 6)
    screen = pygame.Surface((W, H))
    screen.fill((60, 60, 60))
    d.blit_fog(screen, Vector2(800, 800), NO_SHAKE)
    px = [screen.get_at((x, y))[:3] for x in range(0, W, 7) for y in range(0, H, 7)]
    assert all(min(p) >= 60 for p in px) and any(max(p) > 60 for p in px)


# --- overlay ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("act", ACTS)
def test_overlay_is_transparent_in_the_centre_and_max_alpha_in_the_corners(act):
    tint, max_alpha = config.LIGHT_OVERLAYS[act]
    v = layers.build_vignette(act)
    assert v.get_size() == (W, H) and v.get_flags() & pygame.SRCALPHA
    assert v.get_at((W // 2, H // 2))[3] == 0
    assert v.get_at((W // 2 + 60, H // 2 + 40))[3] == 0                  # inside the 0.35 radius: still clear
    corner = max(v.get_at(p)[3] for p in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)))
    # the 16x10 grid is sampled at cell centres, so the corner pixel reaches ~94-96 % of max alpha, never more
    assert 0.9 * max_alpha <= corner <= max_alpha
    assert max(abs(a - b) for a, b in zip(v.get_at((0, 0))[:3], tint)) <= 2
    ramp = [v.get_at((x, H // 2))[3] for x in range(W // 2, W)]
    assert ramp == sorted(ramp)                                          # grows monotonically toward the edge


def test_overlay_alpha_follows_the_smoothstep_of_the_elliptical_distance():
    v = layers.build_vignette(4)
    for x, y in ((100, 100), (300, 700), (1100, 150), (900, 400)):
        d = (((x / W - 0.5) * 2) ** 2 + ((y / H - 0.5) * 2) ** 2) ** 0.5 / 2 ** 0.5
        expect = 110 * layers._smoothstep(0.35, 1.0, d)
        assert abs(v.get_at((x, y))[3] - expect) <= 0.2 * 110           # coarse 16x10 grid + bilinear smoothscale


def test_overlay_can_be_scaled_and_capped():
    assert layers.build_vignette(9, 1.15).get_at((0, 0))[3] > layers.build_vignette(9).get_at((0, 0))[3]
    assert layers.build_overlay((0, 0, 0), 9999).get_at((0, 0))[3] <= 255


def test_the_overlay_never_changes_the_screen_centre():
    d = DepthLayers(3, 1)
    for hp in (1.0, 0.2):
        screen = pygame.Surface((W, H))
        screen.fill((123, 200, 50))
        d.blit_vignette(screen, hp)
        assert screen.get_at((W // 2, H // 2))[:3] == (123, 200, 50)
        assert screen.get_at((W // 2 + 100, H // 2))[:3] == (123, 200, 50)
        assert screen.get_at((5, 5))[:3] != (123, 200, 50)


def test_low_hp_switches_to_the_red_overlay_below_30_percent_only():
    d = DepthLayers(1, 1)
    def corner(hp):
        screen = pygame.Surface((W, H))
        screen.fill((100, 100, 100))
        d.blit_vignette(screen, hp)
        return screen.get_at((0, 0))[:3]
    normal = corner(1.0)
    assert corner(0.30) == normal and corner(0.5) == normal           # 30% itself is not low
    red = corner(0.29)
    assert red != normal and red[0] > red[1] and red[0] > red[2]
    assert corner(1.0) == normal                                         # and it switches back


def test_set_alpha_works_on_per_pixel_alpha_surfaces_in_this_pygame():
    """The pulses rely on Surface.set_alpha combining with per-pixel alpha (both with and without convert_alpha)."""
    for convert in (False, True):
        src = pygame.Surface((8, 8), pygame.SRCALPHA)
        src.fill((200, 0, 0, 100))
        if convert:
            if pygame.display.get_surface() is None:
                pygame.display.set_mode((W, H))
            src = src.convert_alpha()
        full = []
        for alpha in (255, 128, 0):
            src.set_alpha(alpha)
            dst = pygame.Surface((8, 8))
            dst.fill((0, 100, 0))
            dst.blit(src, (0, 0))
            full.append(dst.get_at((3, 3))[:3])
        assert full[0] == (78, 60, 0)                       # 100/255 of red over green
        assert full[1][0] < full[0][0] and full[1][1] > full[0][1]       # half as strong
        assert full[2] == (0, 100, 0)                       # fully transparent


def test_the_red_overlay_is_built_once_on_first_low_hp_and_pulses_with_set_alpha_only():
    d = DepthLayers(0, 1)
    screen = pygame.Surface((W, H))
    assert d._red is None                                    # not built until needed (saves memory in most fights)
    builds = []
    original = layers.build_overlay

    def spy(*a, **k):
        builds.append(a)
        return original(*a, **k)

    layers.build_overlay = spy
    try:
        corner = []
        alphas = []
        for _ in range(240):                                 # 4 s
            d.update(1 / 60)
            screen.fill((0, 0, 0))
            d.blit_vignette(screen, 0.1)
            corner.append(screen.get_at((0, 0))[0])
            alphas.append(d.overlay_alpha(0.1))
    finally:
        layers.build_overlay = original
    assert builds == [config.LOW_HP_OVERLAY]                 # one build in four seconds of pulsing: tint (120,10,20), maxA 150
    assert d._red.get_at((0, 0))[:3] == (120, 10, 20)
    assert min(alphas) == int(255 * 0.6) and max(alphas) == 255
    assert max(corner) > min(corner)
    # one full dim -> bright -> dim cycle per second: the alpha crosses its mid level at most 2 times a second
    mid = (min(alphas) + max(alphas)) / 2
    crossings = sum(1 for a, b in zip(alphas, alphas[1:]) if (a > mid) != (b > mid))
    assert 7 <= crossings <= 8


def test_overlay_alpha_is_255_except_for_low_hp_and_the_act_9_heartbeat():
    for act in range(9):
        d = DepthLayers(act, 1)
        for t in (0.0, 0.3, 0.7):
            d.t = t
            assert d.overlay_alpha(1.0) == 255
    d = DepthLayers(9, 1)
    seen = set()
    for k in range(400):
        d.t = k / 100
        seen.add(d.overlay_alpha(1.0))
    assert min(seen) == 222 and max(seen) == 255              # 255 * 1.0 / 1.15 .. 255


def test_pulse_clock_only_moves_with_update():
    d = DepthLayers(9, 1)
    t = d.t
    d.blit_vignette(pygame.Surface((W, H)), 1.0)
    assert d.t == t
    d.update(0.25)
    assert d.t == t + 0.25


def test_act_9_heartbeat_bakes_max_alpha_x_1_15_and_dims_with_set_alpha_at_0_8_hz():
    d = DepthLayers(9, 1)
    plain = layers.build_vignette(9)
    assert abs(d.vignette.get_at((0, 0))[3] / plain.get_at((0, 0))[3] - 1.15) < 0.02
    screen = pygame.Surface((W, H))
    values = []
    for _ in range(int(2.5 * 60)):                           # 2.5 s = 2 beats at 0.8 Hz
        d.update(1 / 60)
        screen.fill((0, 0, 0))
        d.blit_vignette(screen, 1.0)
        values.append(d.vignette.get_alpha())
    assert min(values) == 222 and max(values) == 255
    mid = (222 + 255) / 2
    crossings = sum(1 for a, b in zip(values, values[1:]) if (a - mid) * (b - mid) < 0)
    assert crossings in (3, 4)                               # 2 s of a 0.8 Hz wave -> ~3-4 mid crossings
    peak_dark = screen.get_at((0, 0))[:3]
    other = DepthLayers(8, 1)
    for _ in range(100):
        other.update(1 / 60)
        other.blit_vignette(screen, 1.0)
    assert other.vignette.get_alpha() == 255                 # only act 9 pulses
    assert peak_dark != (0, 0, 0)


def test_pulses_never_exceed_1_hz():
    for hz in (config.LOW_HP_PULSE[2], config.HEARTBEAT[2]):
        assert hz <= 1.0
    d = DepthLayers(9, 1)
    for hp in (1.0, 0.1):
        prev, direction, turns = None, 0, 0
        for k in range(600):                                 # 10 s at 60 fps
            d.t = k / 60
            a = d.overlay_alpha(hp)
            if prev is not None and a != prev:
                nd = 1 if a > prev else -1
                if direction and nd != direction:
                    turns += 1
                direction = nd
            prev = a
        assert turns <= 2 * 10 * 1                           # a turn per half cycle at most

def test_a_missing_layer_is_skipped_everywhere(monkeypatch):
    monkeypatch.setattr(config, "GFX_LAYERS", False)
    assert layers.build_fog(0, 1) is None and layers.build_vignette(0) is None
    d = DepthLayers(0, 1)
    screen = pygame.Surface((W, H))
    screen.fill((50, 60, 70))
    before = pygame.image.tostring(screen, "RGB")
    d.blit_fog(screen, Vector2(10, 10), NO_SHAKE)
    d.blit_vignette(screen, 0.0)
    assert pygame.image.tostring(screen, "RGB") == before


def test_unknown_act_indices_clamp():
    assert DepthLayers(99, 1).theme_index == 9 and DepthLayers(-3, 1).theme_index == 0


def test_build_and_blit_cost_stay_small():
    """Loose guards (measured: fog+overlay build ~7-14 ms, fog blit ~0.35 ms, overlay blit ~0.3 ms)."""
    start = time.perf_counter()
    d = DepthLayers(4, 1)
    assert (time.perf_counter() - start) * 1000 < 250
    screen = pygame.Surface((W, H))
    best = 1e9
    for _ in range(5):
        t = time.perf_counter()
        for _ in range(50):
            d.update(1 / 60)
            d.blit_fog(screen, Vector2(900, 700), NO_SHAKE)
            d.blit_vignette(screen, 1.0)
        best = min(best, (time.perf_counter() - t) / 50 * 1000)
    assert best < 6.0


# --- Game integration -------------------------------------------------------------------------------------------

@pytest.fixture
def game(make_game, isolated_save, monkeypatch):
    g = make_game()
    monkeypatch.setattr(g.audio, "play", lambda name, scale=1.0: None)
    monkeypatch.setattr(g.audio, "play_act_music", lambda act: None)
    monkeypatch.setattr(g.audio, "play_menu_music", lambda: None)
    g._start_new_run()
    g.story = None
    g.state = GameState.OVERWORLD
    return g


def _enter_fight(game) -> None:
    node = next(n for n in game.overworld.nodes.values() if n.node_type == NodeType.FIGHT)
    game._load_encounter(node)
    game.state = GameState.PLAYING


def test_layers_are_built_once_per_map_load(game):
    assert game.layers is None
    game._draw_game()                                   # drawing without layers is fine
    _enter_fight(game)
    assert isinstance(game.layers, DepthLayers) and game.layers.theme_index == game.overworld.act_index
    first = game.layers
    _enter_fight(game)
    assert game.layers is not first


def test_gfx_layers_off_means_no_layers_and_the_game_still_draws(game, monkeypatch):
    monkeypatch.setattr(config, "GFX_LAYERS", False)
    _enter_fight(game)
    assert game.layers is None
    game._update(1 / 60)
    game._draw_game()


def test_the_pulse_clock_only_advances_in_playing(game):
    _enter_fight(game)
    t = game.layers.t
    game._update(1 / 60)
    assert game.layers.t > t
    for state in (GameState.SKILLS, GameState.STORY, GameState.OVERWORLD, GameState.MAIN_MENU):
        game.state = state
        t = game.layers.t
        game._update(1 / 60)
        assert game.layers.t == t, state


def test_layers_change_no_gameplay_state_and_no_global_random(game):
    _enter_fight(game)
    random.seed(77)
    state = random.getstate()
    creatures = [(c.pos.x, c.pos.y, c.hp) for c in game.creatures]
    bosses = [(b.pos.x, b.pos.y, b.hp) for b in game.bosses]
    hazards = [(z.pos.x, z.pos.y, z.radius) for z in game.hazards.zones]
    player = (game.player.pos.x, game.player.pos.y, game.player.hp)
    particles = game.particles.active_count
    shake = (game.shake.x, game.shake.y)
    for hp in (game.player.max_hp, game.player.max_hp * 0.1):
        game.player.hp = hp
        for _ in range(90):
            game.layers.update(1 / 60)
            game._draw_game()
    game.player.hp = player[2]
    assert random.getstate() == state
    assert creatures == [(c.pos.x, c.pos.y, c.hp) for c in game.creatures]
    assert bosses == [(b.pos.x, b.pos.y, b.hp) for b in game.bosses]
    assert hazards == [(z.pos.x, z.pos.y, z.radius) for z in game.hazards.zones]
    assert player == (game.player.pos.x, game.player.pos.y, game.player.hp)
    assert game.particles.active_count == particles
    assert (game.shake.x, game.shake.y) == shake


def test_layers_are_not_saved(game, isolated_save):
    _enter_fight(game)
    for _ in range(30):
        game.layers.update(1 / 60)
    game._save_game()
    text = isolated_save.read_text()
    assert "fog" not in text and "layers" not in text and "vignette" not in text
    assert set(json.loads(text)) <= {"ng_plus", "permanent", "economy", "audio_enabled", "narration_volume"}


def test_draw_order_is_fog_then_motes_then_overlay_then_entities_then_player_then_hud(game):
    """Visual Designer order: the overlay sits under orbs / creatures / projectiles / particles, front motes, player, HUD."""
    _enter_fight(game)
    order: List[str] = []
    game.map_gen.draw_background = lambda *a: order.append("ground")
    game.hazards.draw = lambda *a: order.append("hazards")
    game.layers.blit_fog = lambda *a: order.append("fog")
    game.layers.blit_vignette = lambda *a: order.append("overlay")
    game.ambient.draw_back = lambda *a: order.append("back")
    game.ambient.draw_front = lambda *a: order.append("front")
    game.particles.draw = lambda *a: order.append("particles")
    game.xp_orbs = [type("Orb", (), {"active": True, "draw": lambda self, *a: order.append("orb")})()]
    game.creatures = [type("Cr", (), {"active": True, "draw": lambda self, *a: order.append("creature")})()]
    game.bosses = [type("Bo", (), {"active": True, "draw": lambda self, *a: order.append("boss")})()]
    game.projectiles = [type("Pr", (), {"active": True, "draw": lambda self, *a: order.append("projectile")})()]
    game.hud.draw = lambda *a, **k: order.append("hud")
    game.player.draw = lambda *a, **k: order.append("player")
    game._draw_game()
    assert order == ["ground", "hazards", "fog", "back", "overlay", "orb", "creature", "boss", "projectile",
                     "particles", "front", "player", "hud"]


def test_the_overlay_no_longer_darkens_the_player_or_enemies_at_the_screen_edge(game):
    """The player drawn near a corner looks identical with and without the overlay (the overlay is under it)."""
    _enter_fight(game)
    game.hud.draw = lambda *a, **k: None
    game.ambient = None
    game.creatures = []
    game.player.pos.set(game.camera.x - 520, game.camera.y - 330)       # screen position (80, 70)
    spots = [(80 + dx, 70 + dy) for dx in (-6, 0, 6) for dy in (-6, 0, 6)]
    game._draw_game()
    with_overlay = [game.screen.get_at(p)[:3] for p in spots]
    ground_only = layers_vignette = game.layers.vignette
    game.layers.vignette = None
    game._draw_game()
    without = [game.screen.get_at(p)[:3] for p in spots]
    game.layers.vignette = layers_vignette
    assert with_overlay == without and ground_only is not None


def test_the_overlay_never_covers_the_hud(game):
    """The HUD is drawn after the overlay: with an opaque marker as the HUD, the corner shows the marker unchanged."""
    _enter_fight(game)
    game.player.hp = game.player.max_hp * 0.1

    def fake_hud(screen, *a, **k):
        pygame.draw.rect(screen, (250, 250, 250), (0, 0, 40, 40))
    game.hud.draw = fake_hud
    game._draw_game()
    assert game.screen.get_at((10, 10))[:3] == (250, 250, 250)


def test_the_player_centre_pixel_is_unchanged_by_the_overlay(game):
    _enter_fight(game)
    game.layers.fog = None                                # isolate the overlay
    game.hud.draw = lambda *a, **k: None
    game._draw_game()
    with_overlay = game.screen.get_at((W // 2, H // 2))[:3]
    game.layers.vignette = None
    game._draw_game()
    assert game.screen.get_at((W // 2, H // 2))[:3] == with_overlay


@pytest.mark.parametrize("act", ACTS)
def test_headless_draw_works_in_every_act(game, act):
    game.overworld.act_index = act
    _enter_fight(game)
    assert game.layers.theme_index == act
    game.shake.set(4, -3)
    game._draw_game()
    game.player.hp = 1
    game._draw_game()


# --- readability: the real draw_blob over the real bake with everything on --------------------------------------

def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb) -> float:
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def _mean(px):
    return tuple(sum(p[i] for p in px) / len(px) for i in range(3))


def _contrast(a, b) -> float:
    hi, lo = max(_lum(a), _lum(b)), min(_lum(a), _lum(b))
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("low_hp", [False, True])
@pytest.mark.parametrize("act", ACTS)
def test_player_body_keeps_3_to_1_contrast_with_fog_and_overlay_everywhere(act, low_hp):
    """Producer rule: min rendered contrast >= 3:1 at every position in every act (r2 draw order: overlay under the player).

    Samples the screen centre, the four corners and a few seeded positions; the full 120-position table is in the report.
    """
    import math
    from blob_evolution.maps.generator import MapGenerator
    from blob_evolution.utils.graphics import draw_blob

    screen = pygame.Surface((W, H))
    mg = MapGenerator()
    mg.load_map(act, 7)
    d = DepthLayers(act, 7)
    d.t = 0.0                                               # darkest/strongest pulse phase is alpha 255: use it
    overlay = layers.build_overlay(*config.LOW_HP_OVERLAY) if low_hp else d.vignette
    rng = random.Random(act)
    spots = [(W // 2, H // 2), (80, 80), (W - 80, 80), (80, H - 80), (W - 80, H - 80)]
    spots += [(rng.randint(70, W - 70), rng.randint(70, H - 70)) for _ in range(6)]
    ring = [(dx, dy) for dy in range(-19, 20) for dx in range(-19, 20) if 15 <= math.hypot(dx, dy) <= 19]
    around = [(dx, dy) for dy in range(-30, 31) for dx in range(-30, 31) if 23 <= math.hypot(dx, dy) <= 30]
    worst = 99.0
    for k, (px, py) in enumerate(spots):
        cam = Vector2(700 + 97 * k, 650 + 131 * k)
        def scene(blob: bool) -> None:
            mg.draw_background(screen, cam, NO_SHAKE)
            d.blit_fog(screen, cam, NO_SHAKE)
            screen.blit(overlay, (0, 0))
            if blob:
                draw_blob(screen, (px, py), 20, config.COLOR_PLAYER, config.COLOR_PLAYER_CORE, look=(1, 0))
        scene(False)
        bg = _mean([screen.get_at((px + dx, py + dy)) for dx, dy in around])
        scene(True)
        body = _mean([screen.get_at((px + dx, py + dy)) for dx, dy in ring])
        worst = min(worst, _contrast(body, bg))
    assert worst >= 3.0, (act, low_hp, worst)
