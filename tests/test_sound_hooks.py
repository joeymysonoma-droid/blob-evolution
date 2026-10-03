"""TASK-025/026: the game plays the new sounds at the right moments, and the music follows the story.

A real Game is booted; Game.audio.play is replaced by a recorder (so no mixer timing matters) and the real
event handlers / update code are driven. Music calls are recorded too, without building any theme.
"""
from __future__ import annotations

from typing import List, Tuple

import pygame
import pytest

from blob_evolution.game import BACK_OUT_STATES
from blob_evolution.utils.enums import CreatureType, GameState, NodeType

Played = List[Tuple[str, float]]


@pytest.fixture
def game(make_game, isolated_save, monkeypatch):
    """A real Game in a fresh run, past the opening cards, with sound and music calls recorded."""
    g = make_game()
    sounds: Played = []
    music: List[Tuple[str, object]] = []
    monkeypatch.setattr(g.audio, "play", lambda name, scale=1.0: sounds.append((name, scale)))
    monkeypatch.setattr(g.audio, "play_act_music", lambda act: music.append(("act", act)))
    monkeypatch.setattr(g.audio, "play_menu_music", lambda: music.append(("menu", None)))
    g.sounds, g.music = sounds, music
    g._start_new_run()
    g.story = None
    g.state = GameState.OVERWORLD
    sounds.clear()
    music.clear()
    return g


def _key(game, key: int) -> None:
    game._handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


def _enter(game, node_type: NodeType) -> None:
    """Make the first available node the given type and travel to it."""
    node = game.overworld.get_available_nodes()[0]
    node.node_type = node_type
    game._enter_node(node.id)


def _names(game) -> List[str]:
    return [n for n, _s in game.sounds]


# --- ui_back --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("state", BACK_OUT_STATES, ids=[s.name for s in BACK_OUT_STATES])
def test_escape_plays_ui_back_on_every_screen_that_backs_out(game, state) -> None:
    game.state = state
    _key(game, pygame.K_ESCAPE)
    assert _names(game).count("ui_back") == 1


@pytest.mark.parametrize("state", [GameState.MAIN_MENU, GameState.PLAYING, GameState.STORY, GameState.OVERWORLD,
                                   GameState.GAME_OVER, GameState.VICTORY])
def test_escape_elsewhere_does_not_play_ui_back(game, state) -> None:
    game.state = state
    if state == GameState.STORY:
        game._start_story([{"title": "t", "body": "b"}], GameState.OVERWORLD)
    game.sounds.clear()
    _key(game, pygame.K_ESCAPE)
    assert "ui_back" not in _names(game)


def test_other_keys_do_not_play_ui_back(game) -> None:
    game.state = GameState.HELP
    _key(game, pygame.K_UP)
    _key(game, pygame.K_a)
    assert "ui_back" not in _names(game)


def test_the_save_notice_swallows_escape_before_ui_back(game) -> None:
    game.state = GameState.OPTIONS
    game.save_notice = "partial"
    _key(game, pygame.K_ESCAPE)
    assert "ui_back" not in _names(game)


# --- shield_block ---------------------------------------------------------------------------------------

def _hit_player_during_update(game, monkeypatch) -> None:
    monkeypatch.setattr(game, "_update_playing", lambda dt: game.player.take_damage(5))
    monkeypatch.setattr(game, "_update_ambient", lambda dt: None)
    game.state = GameState.PLAYING
    game._update(0.016)


def test_shield_pop_plays_shield_block_once(game, monkeypatch) -> None:
    game.player.has_shield = True
    _hit_player_during_update(game, monkeypatch)
    assert game.player.has_shield is False and _names(game).count("shield_block") == 1
    _hit_player_during_update(game, monkeypatch)  # no shield now: a real hit, no block sound
    assert _names(game).count("shield_block") == 1


def test_no_shield_block_without_a_shield_or_without_a_hit(game, monkeypatch) -> None:
    _hit_player_during_update(game, monkeypatch)
    game.player.has_shield = True
    monkeypatch.setattr(game, "_update_playing", lambda dt: None)
    game._update(0.016)
    assert "shield_block" not in _names(game) and game.player.has_shield is True


def test_buying_a_shield_does_not_play_shield_block(game) -> None:
    game.economy.essence = 10_000
    game._purchase_shop_item("shield")
    assert game.player.has_shield and "shield_block" not in _names(game)


# --- heal -----------------------------------------------------------------------------------------------

def test_shop_heal_and_rest_site_heal_play_heal(game) -> None:
    game.economy.essence = 10_000
    game.player.hp = 1
    game._purchase_shop_item("health_potion")
    assert _names(game) == ["heal"]
    game.sounds.clear()
    _enter(game, NodeType.REST)
    assert game.state == GameState.REST and _names(game) == ["heal"]


def test_other_shop_items_do_not_play_heal(game) -> None:
    game.economy.essence = 10_000
    game._purchase_shop_item("shield")
    assert "heal" not in _names(game)


# --- artifact -------------------------------------------------------------------------------------------

def test_artifact_chime_plays_for_shop_purchase(game, monkeypatch) -> None:
    game.economy.essence = 10_000
    item = next(i for i in game.economy.get_shop_items() if i["type"] == "artifact")
    game._purchase_shop_item(item["id"])
    assert _names(game).count("artifact") == 1


def test_artifact_chime_plays_for_kill_and_boss_drops(game, monkeypatch) -> None:
    import blob_evolution.game as game_module
    from blob_evolution.entities.boss import Boss
    from blob_evolution.entities.creature import Creature
    from blob_evolution.utils.vector2 import Vector2

    monkeypatch.setattr(game_module.random, "random", lambda: 0.0)  # every drop roll succeeds
    ids = iter(["thick_skin", "xp_chain"])  # two different artifacts, so neither add() is a duplicate
    monkeypatch.setattr(game_module.ArtifactManager, "random_drop", staticmethod(lambda: next(ids)))
    diff = dict(game._diff_mult())
    creature = Creature(Vector2(500, 500), CreatureType.BASIC, 15.0, 1.0, diff)
    game._on_creature_killed(creature)
    assert _names(game).count("artifact") == 1
    game.sounds.clear()
    game._on_boss_killed(Boss(Vector2(900, 900), 0, diff, slot=0))
    assert _names(game).count("artifact") == 1


def test_artifact_chime_is_tied_to_the_archive_hook(game) -> None:
    game._unlock_artifact_archive("thick_skin")
    assert _names(game) == ["artifact"]


# --- merge / victory ------------------------------------------------------------------------------------

@pytest.mark.parametrize("ending,expected", [("merge", "merge"), ("reopen", "victory"), ("broker", "victory")])
def test_ending_stinger(game, ending: str, expected: str) -> None:
    game._trigger_victory(ending)
    stingers = [n for n in _names(game) if n in ("merge", "victory")]
    assert stingers == [expected]
    assert game.state == GameState.VICTORY and ("menu", None) in game.music


# --- boss warning / spawn ordering ------------------------------------------------------------------------

@pytest.mark.parametrize("node_type,scale", [(NodeType.BOSS, 1.0), (NodeType.MINIBOSS, 0.8)])
def test_boss_warning_on_entry_and_spawn_when_the_intro_ends(game, node_type, scale) -> None:
    _enter(game, node_type)
    assert game.state == GameState.STORY
    assert game.sounds == [("boss_warning", scale)], "only the warning while the intro cards are up"
    game.sounds.clear()
    guard = 0
    while game.state == GameState.STORY and guard < 50:
        game._advance_story()
        guard += 1
    assert game.state == GameState.PLAYING
    spawns = [(n, s) for n, s in game.sounds if n == "boss_spawn"]
    assert spawns == [("boss_spawn", scale)]
    assert game.sounds.index(("story", 1.0)) < game.sounds.index(("boss_spawn", scale))
    game.sounds.clear()
    game._advance_story()
    assert "boss_spawn" not in _names(game), "fires once, not on later story cards"


def test_ordinary_fights_and_opening_cards_play_no_boss_sounds(game) -> None:
    _enter(game, NodeType.FIGHT)
    assert game.state == GameState.PLAYING
    assert not {"boss_warning", "boss_spawn"} & set(_names(game))
    game._start_story([{"title": "t", "body": "b"}], GameState.OVERWORLD)
    game._advance_story()
    assert "boss_spawn" not in _names(game)
