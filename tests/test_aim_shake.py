"""BUG-111 (TASK-052): the mouse aim must stay on the drawn target while the screen shakes."""
from __future__ import annotations

import random

import pygame
import pytest

from blob_evolution import config
from blob_evolution.entities.player import Player
from blob_evolution.utils.graphics import world_to_screen
from blob_evolution.utils.vector2 import Vector2


@pytest.fixture
def game(make_game):
    g = make_game()
    g.player = Player(Vector2(1000, 1000))
    return g


@pytest.mark.parametrize("shake", [(0, 0), (24, 0), (0, -24), (13.5, -7.25), (-24, 24)])
def test_screen_to_world_inverts_the_entity_draw_offset(game, shake):
    game.camera.set(873.5, 1204.25)
    game.shake.set(*shake)
    for world in (Vector2(900, 1100), Vector2(1234.5, 877.25), Vector2(873.5, 1204.25)):
        sx, sy = world_to_screen(world, game.camera, config.SCREEN_WIDTH, config.SCREEN_HEIGHT, game.shake)   # what entities use
        back = game._screen_to_world((sx, sy))
        assert abs(back.x - world.x) <= 1.0 and abs(back.y - world.y) <= 1.0, (shake, world, back)


def test_the_player_is_drawn_where_the_aim_says_it_is_under_shake(game):
    """Draw the player on a blank screen with a shake and aim at its drawn centre: the aim lands on the player."""
    game.camera.set(1000, 1000)
    game.shake.set(18, -12)
    game.screen.fill((0, 0, 0))
    game.player.draw(game.screen, game.camera, game.shake)
    xs, ys = zip(*[(x, y) for x in range(0, config.SCREEN_WIDTH, 2) for y in range(0, config.SCREEN_HEIGHT, 2)
                   if game.screen.get_at((x, y))[:3] != (0, 0, 0)])
    centre = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    aim = game._screen_to_world(centre)
    assert game.player.pos.distance_to(aim) < 16                 # inside the body, not ~2 x shake (36 px) away


def test_zero_shake_behaviour_is_unchanged(game):
    game.camera.set(1000, 1000)
    game.shake.set(0, 0)
    centre = game._screen_to_world((config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2))
    corner = game._screen_to_world((0, 0))
    assert (centre.x, centre.y) == (1000, 1000)
    assert (corner.x, corner.y) == (1000 - config.SCREEN_WIDTH // 2, 1000 - config.SCREEN_HEIGHT // 2)


def test_without_a_player_the_origin_is_returned(make_game):
    g = make_game()
    g.player = None
    origin = g._screen_to_world((5, 5))
    assert (origin.x, origin.y) == (0, 0)


def test_the_aim_conversion_never_touches_the_global_random_stream(game):
    random.seed(3)
    state = random.getstate()
    game.shake.set(10, 10)
    game._screen_to_world((10, 10))
    assert random.getstate() == state
