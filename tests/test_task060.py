"""TASK-060 polish: one block per QA item (BUG-179..195). Each test fails on main e222d44 (or on the named mutant)."""
from __future__ import annotations

import pygame
import pytest

from blob_evolution import config
from blob_evolution.ui.hud import HUD

DT = 1 / 60
B = "Warden of Ash — PHASE 2!"


@pytest.fixture
def hud():
    pygame.font.init()
    return HUD()


def _spans(h: HUD, events: dict, frames: int = 900) -> list:
    """Run the HUD at 60 fps with `events` {frame: [(text, s, kwargs) or callable]} -> [(text, first frame, frames)]."""
    out = []
    for f in range(frames):
        for ev in events.get(f, []):
            ev(h) if callable(ev) else h.show_notification(ev[0], ev[1], **ev[2])
        shown = h.notification if h.notification_timer > 0 else None
        if shown is not None:
            if out and out[-1][0] == shown and out[-1][1] + out[-1][2] == f:
                out[-1][2] += 1
            else:
                out.append([shown, f, 1])
        h.update(DT)
    return [tuple(x) for x in out]


# ---- BUG-179: overflow drops the oldest notice, never a banner or a cut-short notice waiting to be re-shown -----------

def test_bug_179_a_banner_into_a_full_queue_drops_the_oldest_waiting_notices(hud):
    """QA t57 S12: 'Archive: X' on screen + 6 waiting artifacts, then a banner. Main dropped the two NEWEST (A4, A5) to
    make room for the banner and the re-queued Archive; now the two oldest (A0, A1) drop."""
    hud.show_notification("Archive: X", 3.5)
    for i in range(config.HUD_NOTICE_QUEUE):
        hud.show_notification(f"Boss Artifact: A{i}", 1.0)
    hud.update(0.5)
    hud.show_notification(B, 2.5, priority=True)
    assert hud.pending_notifications == [B, "Archive: X"] + [f"Boss Artifact: A{i}" for i in range(2, 6)]


def test_bug_179_feedback_floods_never_drop_the_banner_or_the_cut_short_notice(hud):
    """t58: five feedbacks during the yield dropped the re-queued Archive. Now the oldest feedback goes instead."""
    hud.show_notification("Archive: X", 3.5)
    hud.update(0.5)
    hud.show_notification(B, 2.5, priority=True)
    for i in range(config.HUD_NOTICE_QUEUE + 2):
        hud.show_notification(f"Bought {i}", 1.0, now=True)
    assert hud.pending_notifications == [B, "Bought 4", "Bought 5", "Bought 6", "Bought 7", "Archive: X"]


def test_bug_179_plain_gameplay_overflow_still_drops_the_oldest(hud):
    """Guard (passes on main too): the BUG-145 behaviour for appended gameplay notices is unchanged."""
    hud.show_notification("now", 2.0)
    for k in range(config.HUD_NOTICE_QUEUE + 3):
        hud.show_notification(f"w{k}", 1.0)
    assert hud.pending_notifications == [f"w{k}" for k in range(3, config.HUD_NOTICE_QUEUE + 3)]


# ---- BUG-180: a withdrawn banner does not leave the notice it cut short re-queued -------------------------------------

def test_bug_180_a_withdrawn_banner_leaves_the_cut_notice_shown_once_with_its_own_time(hud):
    """QA t57 S7/G03: the boss died while its banner waited; 'Archive' was then shown 1.5 s + 3.5 s again (5.0 s, no banner
    in between). Now it is shown once, for its own 3.5 s, and nothing it cut short is re-queued."""
    ev = {0: [("Archive: X", 3.5, {})], 30: [(B, 2.5, {"priority": True})], 45: [lambda h: h.withdraw(B)]}
    sp = _spans(hud, ev)
    assert len(sp) == 1 and sp[0][:2] == ("Archive: X", 0) and sp[0][2] in (209, 210, 211)


def test_bug_180_two_banners_one_withdrawn_the_other_still_shows_then_the_notice_in_full(hud):
    ev = {0: [("Archive: X", 3.5, {})], 30: [(B, 2.5, {"priority": True})], 40: [("FINAL PHASE!", 2.5, {"priority": True})],
          45: [lambda h: h.withdraw(B)]}
    sp = _spans(hud, ev)
    assert [t for t, _f, _n in sp] == ["Archive: X", "FINAL PHASE!", "Archive: X"] and sp[2][2] in (209, 210, 211)


# ---- BUG-181: a notice cut short a second time comes back in full ----------------------------------------------------

def test_bug_181_a_notice_resumed_after_feedback_then_cut_by_a_banner_is_re_shown_in_full(hud):
    """QA t57 S12b: Archive (3.5 s) interrupted by feedback resumes with its 3.0 s left; a banner then cuts it again.
    Main re-showed it for 3.0 s (the remainder); the ruling is its FULL 3.5 s."""
    ev = {0: [("Archive: Warden of Ash", 3.5, {})], 30: [("Healed 25 HP!", 1.0, {"now": True})],
          120: [(B, 2.5, {"priority": True})]}
    sp = _spans(hud, ev)
    assert [t for t, _f, _n in sp] == ["Archive: Warden of Ash", "Healed 25 HP!", "Archive: Warden of Ash", B,
                                       "Archive: Warden of Ash"]
    assert sp[4][2] in (209, 210, 211)


# ---- BUG-182: the HUD clock stops while the game is paused ------------------------------------------------------------

def test_bug_182_notices_and_a_waiting_banner_do_not_run_down_while_paused(make_game, monkeypatch):
    """QA t57 G07: the banner reached the screen while PAUSED, its sound and plate only at unpause (+1.17 s)."""
    from blob_evolution.utils.enums import GameState
    g = make_game()
    for name in ("play", "play_act_music", "play_menu_music"):
        monkeypatch.setattr(g.audio, name, lambda *a, **k: None)
    g.state = GameState.PAUSED
    g.hud.show_notification("Archive: X", 3.5)
    g.hud.show_notification(B, 2.5, priority=True)
    t0 = g.hud.notification_timer
    for _ in range(120):
        g._update(DT)
    assert g.hud.notification == "Archive: X" and g.hud.notification_timer == t0
    assert g.hud.pending_notifications[0] == B


# ---- BUG-191: the shake cap is on the offset's length (12 px), not per axis -------------------------------------------

def _shake_fuzz(seed, frames=1200):
    import math
    import random
    from blob_evolution.systems import hitfx as hx
    rng = random.Random(seed)
    sh = hx.Shake(seed=seed)
    worst = worst_int = 0.0
    for _f in range(frames):
        if rng.random() < 0.3:
            sh.add(rng.choice((5, 6, 8, 12, 20, 40)), rng.choice(("", "charger", "boss_hit", "kill", "boss_kill")))
        sh.update(DT)
        worst = max(worst, math.hypot(sh.offset_x, sh.offset_y))
        x, y = sh.int_offset()
        worst_int = max(worst_int, math.hypot(x, y))
    return worst, worst_int


@pytest.mark.parametrize("seed", range(8))
def test_bug_191_the_shake_offset_never_exceeds_12_px_in_length(seed):
    """QA t59 fuzz: per axis <= 11 but the length reached 15.56 px."""
    from blob_evolution.systems import hitfx as hx
    worst, worst_int = _shake_fuzz(seed)
    assert worst <= hx.SHAKE_CAP + 1e-9 and worst_int <= hx.SHAKE_CAP, (worst, worst_int)


def test_bug_191_a_single_big_shake_still_reaches_close_to_the_cap():
    """Guard (passes on main too): the cap limits, it does not shrink; a lone 12 shake peaks at 6.10 px as on main."""
    import math
    from blob_evolution.systems import hitfx as hx
    sh = hx.Shake(seed=3)
    sh.add(12, "boss_kill")
    peak = 0.0
    for _f in range(60):
        sh.update(DT)
        peak = max(peak, math.hypot(sh.offset_x, sh.offset_y))
    assert peak == pytest.approx(6.1011784571858945, abs=1e-6)


# ---- BUG-194: the shake state is reset when an encounter loads ---------------------------------------------------------

def _loaded_game(make_game, monkeypatch):
    import random
    from blob_evolution.systems.overworld import OverworldMap
    from blob_evolution.utils.enums import GameState
    g = make_game()
    for name in ("play", "play_act_music", "play_menu_music"):
        monkeypatch.setattr(g.audio, name, lambda *a, **k: None)
    random.seed(1234)
    g._start_new_run()
    g.story = None
    g.state = GameState.PLAYING
    g.overworld = OverworldMap(act_index=2)
    return g, [n for n in g.overworld.get_available_nodes() if n.node_type.name == "FIGHT"][0]


def test_bug_194_a_shake_running_at_the_end_of_a_fight_does_not_carry_into_the_next(make_game, monkeypatch):
    import random
    monkeypatch.setattr(config, "GFX_HITFX", True)
    g, node = _loaded_game(make_game, monkeypatch)
    g._add_screen_shake(12, "boss_kill")
    for _ in range(3):
        g._update_shake(DT)
    assert g.shake_fx.active and g.shake_fx.last
    random.seed(5)
    g._load_encounter(node)
    assert not g.shake_fx.active and not g.shake_fx.last and g.shake_fx.clk == 0.0
    assert (g.shake.x, g.shake.y) == (0, 0)
    g._update_shake(DT)
    assert g.shake_fx.int_offset() == (0, 0)


def test_bug_194_the_shake_after_a_load_depends_only_on_the_encounter_seed(make_game, monkeypatch):
    """Same encounter seed -> same shake phases, whatever shook before the load."""
    import random
    monkeypatch.setattr(config, "GFX_HITFX", True)
    out = []
    for pre in (0, 7):
        g, node = _loaded_game(make_game, monkeypatch)
        for _ in range(pre):
            g._add_screen_shake(8)
            g._update_shake(0.4)
        random.seed(5)
        g._load_encounter(node)
        g._add_screen_shake(8)
        xs = []
        for _ in range(20):
            g._update_shake(DT)
            xs.append((round(g.shake_fx.offset_x, 6), round(g.shake_fx.offset_y, 6)))
        out.append(xs)
    assert out[0] == out[1]


# ---- BUG-186: notice / banner mutants that survived t57/t58 (M09, M10, M11) ------------------------------------------

def test_bug_186_m09_a_fight_load_takes_the_waiting_banner_back_out_of_the_hud(make_game, monkeypatch):
    """M09 (load clears the banner book-keeping without withdrawing): the handed banner would still show in the new fight."""
    from blob_evolution.entities.boss import Boss
    from blob_evolution.utils.vector2 import Vector2
    import random
    g, node = _loaded_game(make_game, monkeypatch)
    random.seed(9)
    g._load_encounter(node)
    g.creatures, g.projectiles, g.xp_orbs = [], [], []
    g.player.max_hp = g.player.hp = 1e9
    b = Boss(Vector2(g.player.pos.x + 500, g.player.pos.y), 3, None)
    b.speed, b.special_cooldown = 0.0, 1e9
    g.bosses = [b]
    g.hud.show_notification("Archive: X", 3.5)
    for f in range(45):
        if f == 30:
            b.take_damage(b.max_hp * 0.55, ignore_defense=1.0)
        g._update(DT)
    assert any("PHASE" in t for t in g.hud.pending_notifications)
    g._load_encounter(node)
    seen = set()
    for _ in range(400):
        g.player.hp = g.player.max_hp
        g._update(DT)
        if g.hud.notification_timer > 0:
            seen.add(g.hud.notification)
    assert not any("PHASE" in t for t in seen | set(g.hud.pending_notifications))


def test_bug_186_m10_a_second_banner_during_the_yield_does_not_re_queue_the_notice_twice(hud):
    hud.show_notification("Archive: X", 3.5)
    hud.update(0.5)
    hud.show_notification(B, 2.5, priority=True)
    hud.update(0.2)
    hud.show_notification("FINAL PHASE!", 2.5, priority=True)
    assert hud.pending_notifications.count("Archive: X") == 1


def test_bug_186_m10_both_banners_withdrawn_during_one_yield_give_the_notice_its_whole_time_back(hud):
    """Without the yield guard the second banner overwrote what the notice had left before it began to yield."""
    ev = {0: [("Archive: X", 3.5, {})], 30: [(B, 2.5, {"priority": True})], 42: [("FINAL PHASE!", 2.5, {"priority": True})],
          50: [lambda h: h.withdraw(B), lambda h: h.withdraw("FINAL PHASE!")]}
    sp = _spans(hud, ev)
    assert len(sp) == 1 and sp[0][0] == "Archive: X" and sp[0][2] in (209, 210, 211)


def test_bug_186_m11_a_notice_with_0_8_s_left_just_ends_and_is_not_shown_again(hud):
    """The ruling's threshold: only a notice with MORE than 1.0 s left is re-shown afterwards."""
    sp = _spans(hud, {0: [("Level 5!", 0.8, {})], 1: [(B, 2.5, {"priority": True})]})
    assert [t for t, _f, _n in sp] == ["Level 5!", B]


# ---- BUG-192: the two hitfx mutants that survived t59/t60 ------------------------------------------------------------

def test_bug_192_m1_a_shake_above_the_cap_is_treated_as_the_cap():
    """m1 (shake cap removed): add(40) took A = 40 and a 0.4 s longer decay; the cap clamps the intensity itself."""
    from blob_evolution.systems import hitfx as hx
    big, cap = hx.Shake(seed=1), hx.Shake(seed=1)
    big.add(40)
    cap.add(hx.SHAKE_CAP)
    assert big.A == hx.SHAKE_CAP and big.T == cap.T


def test_bug_192_m9_no_hurt_sound_from_boss_contact_while_invulnerable(make_game, monkeypatch):
    """m9 (boss-contact hurt sound unconditional): touching a boss while invulnerable played 'hurt' every 0.6 s."""
    import random
    from blob_evolution.entities.boss import Boss
    g, node = _loaded_game(make_game, monkeypatch)
    sounds = []
    monkeypatch.setattr(g.audio, "play", lambda name, *a, **k: sounds.append(name))
    random.seed(9)
    g._load_encounter(node)
    g.creatures, g.projectiles, g.xp_orbs = [], [], []
    g.player.max_hp = g.player.hp = 100.0
    g.bosses = [Boss(g.player.pos.copy(), 3, None)]
    g.player.invulnerable = 5.0
    g._boss_touch_cooldown = 0.0
    for _ in range(40):
        g.bosses[0].pos.set(g.player.pos.x, g.player.pos.y)
        g._update_collisions()
        g._boss_touch_cooldown = 0.0
    assert sounds.count("hurt") == 0 and g.player.hp == 100.0

