"""TASK-053 / BUG-145: HUD notices queue instead of overwriting each other in the single slot.

QA: the 'Archive: <warden> remembered' notice was replaced by 'Boss Artifact: ...' on the same kill frame (10 of 32 kills),
and 16 of 24 notices that followed another were lost within 2 frames. Now each waits and shows its full duration.
"""
from __future__ import annotations

import random

import pytest

from blob_evolution import config
from blob_evolution.entities.boss import Boss
from blob_evolution.entities.player import Player
from blob_evolution.ui.hud import HUD
from blob_evolution.utils.enums import GameState
from blob_evolution.utils.vector2 import Vector2

DT = 1 / 60


@pytest.fixture
def hud():
    import pygame
    pygame.font.init()
    return HUD()


def _timeline(h: HUD, seconds: float) -> list:
    """(text, frames on screen) in the order shown, stepping the HUD at 60 fps."""
    shown = []
    for _ in range(int(round(seconds / DT))):
        if h.notification_timer > 0:
            if shown and shown[-1][0] == h.notification:
                shown[-1][1] += 1
            else:
                shown.append([h.notification, 1])
        h.update(DT)
    return [tuple(x) for x in shown]


def test_a_second_notice_waits_and_both_show_their_full_time(hud):
    hud.show_notification("Archive: The Mossbound remembered", 3.5)
    hud.show_notification("Boss Artifact: Thorn Shell!", 3.0)
    assert hud.notification == "Archive: The Mossbound remembered"
    assert hud.pending_notifications == ["Boss Artifact: Thorn Shell!"]
    shown = _timeline(hud, 8.0)
    assert [t for t, _n in shown] == ["Archive: The Mossbound remembered", "Boss Artifact: Thorn Shell!"]
    assert abs(shown[0][1] - 3.5 * 60) <= 1 and abs(shown[1][1] - 3.0 * 60) <= 1


def test_notices_show_in_order_and_an_idle_slot_shows_at_once(hud):
    for k in range(4):
        hud.show_notification(f"n{k}", 1.0)
    shown = _timeline(hud, 5.0)
    assert [t for t, _n in shown] == ["n0", "n1", "n2", "n3"]
    assert all(abs(n - 60) <= 1 for _t, n in shown)
    hud.show_notification("later", 2.0)
    assert hud.notification == "later" and hud.pending_notifications == []


def test_repeats_restart_or_merge_instead_of_piling_up(hud):
    hud.show_notification("Sound: OFF", 1.5)
    hud.update(1.0)
    hud.show_notification("Sound: OFF", 1.5)
    assert hud.notification_timer == pytest.approx(1.5) and hud.pending_notifications == []
    hud.show_notification("+1 Skill Point!", 2.0)
    hud.show_notification("+1 Skill Point!", 2.0)
    assert hud.pending_notifications == ["+1 Skill Point!"]


def test_a_burst_of_level_ups_shows_the_latest_level_once(hud):
    hud.show_notification("Level 2!", 2.0)
    for lv in (3, 4, 5):
        hud.show_notification(f"Level {lv}!", 2.0)
    assert hud.notification == "Level 5!" and hud.pending_notifications == []
    hud.show_notification("Archive: X remembered", 3.5)
    hud.show_notification("Level 6!", 2.0)
    hud.show_notification("Level 7!", 2.0)
    assert hud.notification == "Level 7!" and hud.pending_notifications == ["Archive: X remembered"]
    hud2 = HUD()
    hud2.show_notification("Archive: X remembered", 3.5)
    hud2.show_notification("Level 2!", 2.0)
    hud2.show_notification("Level 3!", 2.0)
    assert hud2.pending_notifications == ["Level 3!"]


def test_queue_is_bounded(hud):
    hud.show_notification("now", 2.0)
    for k in range(config.HUD_NOTICE_QUEUE + 3):
        hud.show_notification(f"w{k}", 1.0)
    assert len(hud.pending_notifications) == config.HUD_NOTICE_QUEUE
    assert hud.pending_notifications[-1] == f"w{config.HUD_NOTICE_QUEUE + 2}"


def test_warden_kill_shows_the_archive_notice_and_then_the_artifact(make_game, monkeypatch):
    """The real kill path with the 25 % artifact roll forced: both notices are seen in full, the gameplay result unchanged."""
    g = make_game()
    for name in ("play", "play_act_music", "play_menu_music"):
        monkeypatch.setattr(g.audio, name, lambda *a, **k: None)
    g._start_new_run()
    g.story = None
    g.state = GameState.PLAYING
    g.player = Player(Vector2(1000, 1000))
    boss = Boss(Vector2(1100, 1000), 0)
    assert not boss.is_miniboss
    monkeypatch.setattr(random, "random", lambda: 0.0)           # the artifact drop roll succeeds
    g._on_boss_killed(boss)
    texts = [g.hud.notification] + g.hud.pending_notifications
    archive = [t for t in texts if t.startswith("Archive: ")]
    artifact = [t for t in texts if t.startswith("Boss Artifact: ")]
    assert len(archive) == 1 and len(artifact) == 1
    assert texts.index(archive[0]) < texts.index(artifact[0])
    shown = _timeline(g.hud, 12.0)
    order = [t for t, _n in shown]
    assert archive[0] in order and artifact[0] in order
    assert dict(shown)[archive[0]] >= 3.5 * 60 - 1 and dict(shown)[artifact[0]] >= 3.0 * 60 - 1
