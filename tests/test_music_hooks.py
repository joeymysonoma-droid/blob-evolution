"""TASK-026: the music follows the story (ducking under story cards, act music on the opening and on descents).

A real Game is booted; Game.audio music calls are replaced by a recorder, so no theme or file is loaded.
"""
from __future__ import annotations

from typing import List, Tuple

import pytest

from blob_evolution.utils.enums import GameState, NodeType

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
    monkeypatch.setattr(g.audio, "duck_music", lambda f, immediate=False: music.append(("duck", f)))
    g.sounds, g.music = sounds, music
    g._start_new_run()
    g.story = None
    g.state = GameState.OVERWORLD
    sounds.clear()
    music.clear()
    return g


# --- music follows the story ---------------------------------------------------------------------------------

def test_story_cards_duck_the_music_and_restore_it(game) -> None:
    game._start_story([{"title": "a", "body": "x"}, {"title": "b", "body": "y"}], GameState.OVERWORLD)
    assert game.music == [("duck", 0.5)]
    game._advance_story()
    assert game.music == [("duck", 0.5)], "still ducked between cards"
    game._advance_story()
    assert game.music == [("duck", 0.5), ("duck", 1.0)] and game.state == GameState.OVERWORLD


def test_new_run_starts_act_one_music_under_the_opening_cards(game) -> None:
    game.music.clear()
    game._start_new_run()
    assert game.music[0] == ("act", 0) and ("duck", 0.5) in game.music


def test_descending_to_the_next_act_crossfades_into_its_music(game) -> None:
    game.overworld.current_node_id = game.overworld.get_available_nodes()[0].id
    game.overworld.nodes[game.overworld.current_node_id].node_type = NodeType.BOSS
    game._finish_non_combat_node()
    assert ("act", 1) in game.music and game.overworld.act_index == 1


def test_update_ticks_the_music_ducking_every_frame(game, monkeypatch) -> None:
    ticks: List[float] = []
    monkeypatch.setattr(game.audio, "tick", lambda dt: ticks.append(dt))
    game._update(0.05)
    assert ticks == [0.05]
