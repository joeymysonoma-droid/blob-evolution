"""TASK-053 / BUG-113: the aim-under-shake rules tested through the real game paths.

The BUG-111 tests (test_aim_shake.py) call _screen_to_world directly with a 1.0 px tolerance; five mutants survived
(int(shake), shake * 2 on the click or the hold-to-shoot path, flipped look target, player drawn without shake).
These go through _handle_event (click), _update_playing (hold) and _draw_game (look target, drawn offset) exactly.
"""
from __future__ import annotations

import math

import pygame
import pytest

from blob_evolution import config
from blob_evolution.utils.enums import GameState, NodeType
from blob_evolution.utils.graphics import world_to_screen
from blob_evolution.utils.vector2 import Vector2

SHAKES = [(11.5, -7.25), (-12, 9.75), (0.4, 0.6)]


@pytest.fixture
def game(make_game, monkeypatch):
    g = make_game()
    for name in ("play", "play_act_music", "play_menu_music"):
        monkeypatch.setattr(g.audio, name, lambda *a, **k: None)
    g._start_new_run()
    g.story = None
    node = next(n for n in g.overworld.nodes.values() if n.node_type == NodeType.FIGHT)
    g._load_encounter(node)
    g.state = GameState.PLAYING
    g.creatures.clear()
    g.bosses.clear()
    g.projectiles.clear()
    g.player.pos = Vector2(1000, 1000)
    g.player.shoot_cooldown = 0.0
    g.camera.set(1003.25, 994.5)
    return g


def _drawn(g, world: Vector2):
    return world_to_screen(world, g.camera, config.SCREEN_WIDTH, config.SCREEN_HEIGHT, g.shake)


def _angle_to(g, target: Vector2) -> float:
    v = g.projectiles[0].vel
    return math.degrees(abs((math.atan2(v.y, v.x) - math.atan2(target.y - g.player.pos.y, target.x - g.player.pos.x)
                             + math.pi) % math.tau - math.pi))


@pytest.mark.parametrize("shake", SHAKES)
def test_screen_to_world_is_the_exact_inverse_with_fractional_shake(game, shake):
    game.shake.set(*shake)
    for sx, sy in ((0, 0), (517, 333), (config.SCREEN_WIDTH - 1, 7)):
        w = game._screen_to_world((sx, sy))
        assert w.x - game.camera.x + config.SCREEN_WIDTH // 2 + game.shake.x == pytest.approx(sx, abs=1e-9)
        assert w.y - game.camera.y + config.SCREEN_HEIGHT // 2 + game.shake.y == pytest.approx(sy, abs=1e-9)


@pytest.mark.parametrize("shake", SHAKES)
def test_click_shot_flies_at_the_drawn_point_under_the_cursor(game, shake):
    game.shake.set(*shake)
    target = Vector2(1060, 1000)                                  # 60 px away: 2 x shake would be 15-25 deg off
    sx, sy = _drawn(game, target)
    game._handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(sx, sy)))
    assert len(game.projectiles) == 1
    assert _angle_to(game, target) < 1.0                          # int() of the screen pos only (<= 1 px at 60 px)


@pytest.mark.parametrize("shake", SHAKES)
def test_hold_to_shoot_uses_the_same_mapping_as_the_click(game, shake, monkeypatch):
    """Hold-to-shoot inside _update_playing, after a drawn frame (the shake it aims with is the drawn frame's)."""
    game.shake.set(*shake)
    game._draw_game()
    target = Vector2(1000, 1060)
    pos = tuple(int(v) for v in _drawn(game, target))
    monkeypatch.setattr(pygame.mouse, "get_pressed", lambda *a, **k: (True, False, False))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: pos)
    game._update_playing(1 / 60)
    assert game.projectiles
    assert _angle_to(game, target) < 1.0


@pytest.mark.parametrize("shake", SHAKES)
def test_player_is_drawn_with_the_shake_and_looks_at_the_cursor(game, shake, monkeypatch):
    game.shake.set(*shake)
    calls = []
    real = game.player.draw

    def spy(surface, camera, shk, look_target=None):
        calls.append(((shk.x, shk.y), look_target))
        real(surface, camera, shk, look_target=look_target)
    monkeypatch.setattr(game.player, "draw", spy)
    mouse = (700, 250)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: mouse)
    game._draw_game()
    assert len(calls) == 1
    (shx, shy), look = calls[0]
    assert (shx, shy) == shake
    p = game.player.pos                                           # unrounded draw offset of the player centre
    px = p.x - game.camera.x + config.SCREEN_WIDTH // 2 + game.shake.x
    py = p.y - game.camera.y + config.SCREEN_HEIGHT // 2 + game.shake.y
    assert look == pytest.approx((mouse[0] - px, mouse[1] - py), abs=1e-9)


@pytest.mark.parametrize("shake", SHAKES)
def test_hold_fire_aims_with_the_last_drawn_shake_through_the_real_update(game, shake, monkeypatch):
    """BUG-114: _update re-rolls the shake before hold-to-shoot; the shot must still go where the drawn frame showed the
    cursor (the click path does that because events are handled before _update)."""
    game.shake.set(*shake)
    game.shake_intensity = 12.0                                   # _update_shake re-rolls up to +-12 px per axis
    game._draw_game()                                             # the frame the player sees
    target = Vector2(1060, 1000)
    pos = tuple(int(v) for v in _drawn(game, target))
    monkeypatch.setattr(pygame.mouse, "get_pressed", lambda *a, **k: (True, False, False))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: pos)
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: pygame.key.ScancodeWrapper([False] * 512))
    rerolled = []
    real = game._update_shake

    def spy(dt):
        real(dt)
        rerolled.append((game.shake.x, game.shake.y))
    monkeypatch.setattr(game, "_update_shake", spy)
    start = game.player.pos.copy()
    game._update(1 / 60)
    assert rerolled and rerolled[0] != shake                      # the shake did change before the shot
    assert game.projectiles
    v = game.projectiles[0].vel
    want = math.atan2(target.y - start.y, target.x - start.x)
    off = math.degrees(abs((math.atan2(v.y, v.x) - want + math.pi) % math.tau - math.pi))
    assert off < 1.0, off


def test_drawn_shake_is_recorded_by_the_draw(game):
    game.shake.set(7.5, -3.25)
    game._draw_game()
    assert (game.drawn_shake.x, game.drawn_shake.y) == (7.5, -3.25)
    game.shake.set(1, 1)
    assert (game.drawn_shake.x, game.drawn_shake.y) == (7.5, -3.25)
