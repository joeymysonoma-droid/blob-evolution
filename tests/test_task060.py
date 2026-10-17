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
