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


@pytest.fixture(autouse=True)
def _shared_caches():
    """Leave the shared drawing caches as found (test_boss_visuals' pattern): these tests draw real bosses, and
    test_readability bounds the shared caches' size."""
    from blob_evolution.utils.graphics import get_graphics_cache
    try:
        from blob_evolution.utils import boss_shapes as bs
    except ImportError:                                    # 055c alone has no boss art
        bs = None
    gc = get_graphics_cache()
    before = (dict(gc._circles), dict(gc._shadows))
    yield
    if bs is not None:
        bs.clear()
    gc._circles.clear(), gc._circles.update(before[0])
    gc._shadows.clear(), gc._shadows.update(before[1])


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


def _run(g, frames: int, at=None):
    """Run `frames` frames; `at` maps a frame to a callable run before it. -> [(frame, text, duration)] shown."""
    shown = []
    real = g.hud.show_notification
    g.hud.show_notification = lambda text, d=2.0, **k: (shown.append((g._frame, text, d)), real(text, d, **k))
    for g._frame in range(frames):
        if at and g._frame in at:
            at[g._frame]()
        g.hud.update(DT)                                   # as Game._update does, before the playing update
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
    assert shown[0][0] == 0 and shown[1][0] - shown[0][0] in (60, 61)        # BUG-166: the second waits at most 1.0 s
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


# ---- 055c: BUG-166 .. 169 ----------------------------------------------------------------------------------------------

def test_bug_166_a_second_crossing_soon_after_waits_at_most_1_s(game):
    """QA t53 finding A: two separate crossings 0.5 s apart; 055b showed FINAL PHASE! 2 s late (f211)."""
    b = Boss(Vector2(1300, 1000), 3, None)
    game.bosses = [b]
    hits = {0: lambda: b.take_damage(b.max_hp * 0.55), 30: lambda: b.take_damage(b.max_hp * 0.25)}
    shown = [s for s in _run(game, 300, hits) if "PHASE" in s[1]]
    assert shown[0][0] == 0 and 30 + 57 <= shown[1][0] <= 30 + 61 and shown[1][1] == "FINAL PHASE!"   # <= 1.0 s


def test_bug_166_a_banner_alone_keeps_its_full_2_5_s(game):
    b = Boss(Vector2(1300, 1000), 3, None)
    game.bosses = [b]
    hits = {0: lambda: b.take_damage(b.max_hp * 0.55)}
    _run(game, 149, hits)
    assert game.hud.notification.endswith("PHASE 2!") and game.hud.notification_timer > 0


def _screen(game, frames, at=None):
    """BUG-167: per frame, (text on screen or None, boss_phase sounds so far), running `at` callables before their frame."""
    seen = []
    for f in range(frames):
        _run(game, 1, {0: at[f]} if at and f in at else None)
        h = game.hud
        seen.append((h.notification if h.notification_timer > 0 else None, game.sounds.count("boss_phase")))
    return seen


def _spans(seen):
    """[(text, first frame, frames)] of each stretch a text is on screen."""
    out = []
    for f, (text, _n) in enumerate(seen):
        if text is None:
            continue
        if out and out[-1][0] == text and out[-1][1] + out[-1][2] == f:
            out[-1][2] += 1
        else:
            out.append([text, f, 1])
    return [tuple(x) for x in out]


def test_bug_167_a_notice_shown_between_two_banners_waits_and_then_gets_its_full_time(game):
    """Ruling: 'Level 5!' shown while PHASE 2 is up waits (gameplay notices queue, 053); FINAL PHASE! replaces PHASE 2 after
    1.0 s (BUG-166, priority), and 'Level 5!' shows after it for its whole 2.0 s."""
    b = Boss(Vector2(1300, 1000), 3, None)
    game.bosses = [b]
    hits = {0: lambda: b.take_damage(b.max_hp * 0.8), 30: lambda: game.hud.show_notification("Level 5!", 2.0)}
    spans = _spans(_screen(game, 400, hits))
    assert [t for t, _f, _n in spans] == ["Warden of Ash — PHASE 2!", "FINAL PHASE!", "Level 5!"]
    assert spans[1][1] in (60, 61) and spans[1][2] in (149, 150, 151)
    assert spans[2][1] == spans[1][1] + spans[1][2] and spans[2][2] in (119, 120, 121)


def test_bug_167_a_banner_lets_the_notice_on_screen_keep_1_s_then_shows_and_the_notice_gets_its_full_time_after(game):
    b = Boss(Vector2(1300, 1000), 3, None)
    game.bosses = [b]
    game.hud.show_notification("Level 5!", 2.0)
    b.take_damage(b.max_hp * 0.55)
    seen = _screen(game, 400)
    spans = _spans(seen)
    assert [t for t, _f, _n in spans] == ["Level 5!", "Warden of Ash — PHASE 2!", "Level 5!"]
    assert spans[0][2] in (59, 60, 61)                                 # at most 1.0 s more
    assert spans[1][2] in (149, 150, 151) and spans[2][2] in (119, 120, 121)   # banner 2.5 s, then 'Level 5!' in full
    first = spans[1][1]
    assert seen[first - 1][1] == 0 and seen[first][1] == 1           # the sound plays when the banner is on screen


def test_bug_167_a_notice_with_under_1_s_left_just_ends_and_is_not_shown_again(game):
    b = Boss(Vector2(1300, 1000), 3, None)
    game.bosses = [b]
    game.hud.show_notification("Level 5!", 0.5)
    b.take_damage(b.max_hp * 0.55)
    spans = _spans(_screen(game, 300))
    assert [t for t, _f, _n in spans] == ["Level 5!", "Warden of Ash — PHASE 2!"]
    assert spans[0][2] in (29, 30, 31)


def test_bug_167_a_waiting_banner_switches_the_plate_only_when_it_shows(game):
    b = Boss(Vector2(1300, 1000), 3, None)
    game.bosses = [b]
    game.hud.show_notification("Level 5!", 2.0)
    b.take_damage(b.max_hp * 0.55)
    plates = []
    for f in range(80):
        _run(game, 1)
        plates.append((game.hud.notification, b.shown_phase()))
    first = next(f for f, (t, _p) in enumerate(plates) if t.endswith("PHASE 2!"))
    assert first > 50 and all(p == 1 for _t, p in plates[:first]) and plates[first][1] == 2


def test_bug_167_a_dead_boss_takes_its_handed_banner_back_out_of_the_queue(game):
    b = Boss(Vector2(1300, 1000), 3, None)
    game.bosses = [b]
    game.hud.show_notification("Level 5!", 2.0)
    b.take_damage(b.max_hp * 0.55)
    _run(game, 1)
    assert any("PHASE" in t for t in game.hud.pending_notifications)
    b.active = False
    spans = _spans(_screen(game, 300))
    assert all("PHASE" not in t for t, _f, _n in spans) and not game.hud.pending_notifications[1:]


def test_bug_168_loading_a_fight_clears_the_waiting_banners(game):
    from blob_evolution.systems.overworld import OverworldMap
    from blob_evolution.utils.enums import NodeType
    b = Boss(Vector2(1300, 1000), 4, None)
    game.bosses = [b]
    b.take_damage(b.max_hp * 0.8)
    _run(game, 1)
    assert game._phase_banners and any(e[0] for e in game._phase_banners.values())
    game.overworld = OverworldMap(act_index=4, seed=7)
    node = next(n for n in game.overworld.nodes.values() if n.node_type == NodeType.FIGHT)
    game._load_encounter(node)
    assert game._phase_banners == {}


def _plate_texts(b, monkeypatch):
    """The strings Boss.draw renders (name and phase label)."""
    import pygame
    from blob_evolution.entities import boss as boss_module
    texts = []

    class _Font:
        def __init__(self, *a, **k):
            self.f = real(*a, **k)

        def render(self, text, *a, **k):
            texts.append(text)
            return self.f.render(text, *a, **k)
    real = pygame.font.SysFont
    monkeypatch.setattr(boss_module.pygame.font, "SysFont", _Font)
    b.draw(pygame.Surface((1200, 800)), Vector2(1300, 1000), Vector2(0, 0))
    monkeypatch.setattr(boss_module.pygame.font, "SysFont", real)
    return texts


def test_bug_169_layer_9_plate_switches_only_when_each_banner_shows(game, monkeypatch):
    from blob_evolution import config
    monkeypatch.setattr(config, "GFX_BOSS_ART", False, raising=False)   # the text plate (058's art plate has its own test)
    b = Boss(Vector2(1300, 1000), 8, None)
    game.bosses = [b]
    start = b.name
    b.take_damage(b.max_hp * 0.8)                                     # one hit: phase 2 and phase 3 start
    assert b.phase == 3 and b.name == "Warden of Stillness"
    plates = {}
    for f in range(70):
        _run(game, 1)
        plates[f] = (b.shown_phase(), b.shown_name(), tuple(_plate_texts(b, monkeypatch)))
    assert start != "Warden of Echoes"
    assert plates[0][:2] == (2, "Warden of Echoes") and plates[59][:2] == (2, "Warden of Echoes")
    assert "Warden of Echoes" in plates[30][2] and "FINAL PHASE" not in plates[30][2]
    first_final = min(f for f, p in plates.items() if p[0] == 3)
    assert first_final in (60, 61) and plates[first_final][1] == "Warden of Stillness"
    assert "FINAL PHASE" in plates[first_final][2] and "Warden of Stillness" in plates[first_final][2]
    assert b.plate_hold is None                                       # nothing waiting: the plate is the real phase again


def test_bug_169_a_single_crossing_switches_the_plate_in_the_same_frame(game):
    b = Boss(Vector2(1300, 1000), 8, None)
    game.bosses = [b]
    b.take_damage(b.max_hp * 0.55)
    _run(game, 1)
    assert (b.shown_phase(), b.shown_name()) == (b.phase, b.name) == (2, "Warden of Echoes") and b.plate_hold is None


def test_bug_169_a_boss_outside_a_game_shows_its_real_phase():
    b = Boss(Vector2(1300, 1000), 8, None)
    b.take_damage(b.max_hp * 0.8)
    assert (b.shown_phase(), b.shown_name()) == (3, "Warden of Stillness")


def test_bug_169_a_crossing_waiting_behind_a_banner_keeps_the_announced_plate(game):
    """Layer 9, phase 2 at f0 and phase 3 at f30: while FINAL PHASE! waits (<= 1.0 s), the plate still reads Echoes."""
    b = Boss(Vector2(1300, 1000), 8, None)
    game.bosses = [b]
    hits = {0: lambda: b.take_damage(b.max_hp * 0.55), 30: lambda: b.take_damage(b.max_hp * 0.25)}
    plates = {}
    for f in range(100):
        _run(game, 1, {0: hits[f]} if f in hits else None)
        plates[f] = (b.phase, b.shown_phase(), b.shown_name())
    assert plates[31][0] == 3 and plates[31][1:] == (2, "Warden of Echoes")
    assert plates[99][1:] == (3, "Warden of Stillness")
