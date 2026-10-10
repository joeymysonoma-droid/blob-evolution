"""BUG-147: a hit crossing two phase thresholds announces both phases, in order, each for its full 2.5 s.

Before: one flag, so only the last banner showed ('FINAL PHASE!'), and layer 9 never showed 'Warden of Echoes — PHASE 2!'.
'FINAL PHASE!' stays the phase 3 text (BUG-148 ruling)."""
from __future__ import annotations

import pytest

from blob_evolution.entities.boss import Boss
from blob_evolution.entities.player import Player
from blob_evolution.utils.enums import GameState
from blob_evolution.utils.vector2 import Vector2

DT = 1 / 60


@pytest.fixture
def game(make_game, monkeypatch):
    g = make_game()
    sounds = []
    monkeypatch.setattr(g.audio, "play", lambda name, *a, **k: sounds.append(name))
    for name in ("play_act_music", "play_menu_music"):
        monkeypatch.setattr(g.audio, name, lambda *a, **k: None)
    g.state = GameState.PLAYING
    g.player = Player(Vector2(1000, 1000))
    g.player.max_hp = g.player.hp = 1e9                     # nothing ends the fight
    g.creatures.clear()
    g.sounds = sounds
    return g


def _run(g, frames: int):
    shown = []
    real = g.hud.show_notification
    g.hud.show_notification = lambda text, d=2.0, **k: (shown.append((g._frame, text, d)), real(text, d, **k))
    for g._frame in range(frames):
        g._update_playing(DT)
    g.hud.show_notification = real
    return shown


@pytest.mark.parametrize("act,first,second", [
    (8, "Warden of Echoes — PHASE 2!", "FINAL PHASE!"),
    (4, "Warden of Frost — PHASE 2!", "FINAL PHASE!"),
    (9, "Prime Anchor — PHASE 2!", "FINAL PHASE!"),
])
def test_one_hit_through_two_thresholds_announces_both_in_order(game, act, first, second):
    b = Boss(Vector2(1300, 1000), act, None)
    game.bosses = [b]
    b.take_damage(b.max_hp * 0.8)
    shown = [s for s in _run(game, 400) if "PHASE" in s[1]]
    assert [t for _f, t, _d in shown] == [first, second]
    assert shown[0][0] == 0 and shown[1][0] - shown[0][0] in (150, 151)      # the second waits the first's 2.5 s
    assert all(d == 2.5 for _f, _t, d in shown)
    assert game.sounds.count("boss_phase") == 2


def test_a_single_crossing_announces_in_the_same_frame_as_before(game):
    b = Boss(Vector2(1300, 1000), 4, None)
    game.bosses = [b]
    b.take_damage(b.max_hp * 0.51)
    shown = [s for s in _run(game, 10) if "PHASE" in s[1]]
    assert shown == [(0, "Warden of Frost — PHASE 2!", 2.5)]


def test_a_dead_boss_drops_its_waiting_banner(game):
    b = Boss(Vector2(1300, 1000), 4, None)
    game.bosses = [b]
    b.take_damage(b.max_hp * 0.8)
    _run(game, 1)
    b.active = False
    assert not [s for s in _run(game, 300) if "PHASE" in s[1]]
