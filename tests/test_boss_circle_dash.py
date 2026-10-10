"""BUG-143 (QA t47): direct seeded test of boss_attacks.move_circle_dash (Ash).

The 054 boss_trace digests never reached a frame where a 0.35 -> 0.36 change of the dash chance per second altered the
outcome (mutant m04 survived). This drives the movement function itself: the exact threshold, what a dash sets, and a
seeded run whose dash count and end state are pinned.
"""
from __future__ import annotations

import hashlib
import math
import random

import pytest

from blob_evolution.entities import boss_attacks
from blob_evolution.entities.boss import Boss
from blob_evolution.utils.vector2 import Vector2

DT = 1 / 60
PLAYER = Vector2(1000, 1000)


def _ash() -> Boss:
    random.seed(11)
    b = Boss(Vector2(700, 900), 3, None)
    assert b.name == "Warden of Ash"
    return b


def _step(b: Boss, roll: float, monkeypatch) -> None:
    monkeypatch.setattr(random, "random", lambda: roll)
    boss_attacks.move_circle_dash(b, DT, PLAYER, b.speed)


def test_ash_moves_with_circle_dash():
    assert boss_attacks.MOVERS["circle_dash"] is boss_attacks.move_circle_dash


@pytest.mark.parametrize("dt", [DT, 1 / 30, 0.1])
def test_dash_chance_is_exactly_0_35_per_second(dt, monkeypatch):
    p = dt * 0.35
    for roll, dashes in ((p * (1 - 1e-6), True), (p, False), (p * 1.02, False), (dt * 0.355, False), (0.0, True)):
        b = _ash()
        monkeypatch.setattr(random, "random", lambda r=roll: r)
        boss_attacks.move_circle_dash(b, dt, PLAYER, b.speed)
        assert (b.dash_timer > 0) == dashes, (dt, roll)


def test_a_dash_aims_at_the_player_and_telegraphs(monkeypatch):
    b = _ash()
    angle0 = b.angle
    _step(b, 0.0, monkeypatch)
    to_p = PLAYER - b.pos
    want = math.atan2(to_p.y, to_p.x)
    assert math.atan2(b.dash_dir.y, b.dash_dir.x) == pytest.approx(want, abs=1e-9)
    assert b.dash_dir.length() == pytest.approx(1.0)
    assert (b.dash_timer, b.telegraph, b.telegraph_type) == (0.35, 0.35, "dash")
    assert b.angle == pytest.approx(angle0 + DT * 1.3)


def test_no_dash_without_a_direction(monkeypatch):
    b = _ash()
    b.pos = PLAYER.copy()
    _step(b, 0.0, monkeypatch)
    assert b.dash_timer == 0.0 and b.telegraph_type != "dash"


def test_seeded_run_dash_count_and_end_state():
    """6000 frames (100 s) of only move_circle_dash under random.seed(143): about 35 dashes expected (0.35 / s)."""
    b = _ash()
    random.seed(143)
    dashes = 0
    for _ in range(6000):
        before = b.dash_timer
        boss_attacks.move_circle_dash(b, DT, PLAYER, b.speed)
        if b.dash_timer == 0.35 and before != 0.35:
            dashes += 1
        b.dash_timer = max(0.0, b.dash_timer - DT)           # what Boss._update_movement does between frames
    state = (round(b.angle, 9), round(b.vel.x, 6), round(b.vel.y, 6), round(b.dash_dir.x, 9), round(b.dash_dir.y, 9),
             hashlib.sha1(repr(random.getstate()).encode()).hexdigest()[:12])
    assert dashes == DASHES_143, (dashes, state)
    assert repr(state) == STATE_143, repr(state)


DASHES_143 = 37                                 # recorded on 202188c (TASK-054), unchanged on 055-058
STATE_143 = "(132.842384564, 49.83311, 33.41648, 0.948683298, 0.316227766, 'dc9829da30e4')"
