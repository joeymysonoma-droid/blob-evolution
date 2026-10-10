"""BUG-169 on the 058 art plate: name, colour and pips read Boss.shown_name() / shown_phase() (055c) when they exist,
else the real name / phase (058 alone). Instance attributes stand in for 055c's methods so this runs on both trees."""

from __future__ import annotations

import pygame

from blob_evolution import config
from blob_evolution.entities.boss import Boss
from blob_evolution.utils import boss_shapes as bs
from blob_evolution.utils.vector2 import Vector2

from test_boss_visuals import _art_on  # noqa: F401  (autouse: art on, boss caches cleared, shared draw caches restored)


def _drawn(b, monkeypatch):
    seen = []
    real_plate, real_pips = bs.name_plate, bs.phase_pips
    monkeypatch.setattr(bs, "name_plate", lambda text, colour=(230, 210, 180): (seen.append(("plate", text, colour)),
                                                                                   real_plate(text, colour))[1])
    monkeypatch.setattr(bs, "phase_pips", lambda total, lit, colour: (seen.append(("pips", lit)),
                                                                       real_pips(total, lit, colour))[1])
    b.draw(pygame.Surface((1200, 800)), Vector2(1300, 1000), Vector2(0, 0))
    monkeypatch.setattr(bs, "name_plate", real_plate)
    monkeypatch.setattr(bs, "phase_pips", real_pips)
    return seen


def test_the_art_plate_follows_shown_name_and_shown_phase(monkeypatch):
    pygame.font.init()
    monkeypatch.setattr(config, "GFX_BOSS_ART", True)
    b = Boss(Vector2(1300, 1000), 8, None)
    b.warm_art()
    b.take_damage(b.max_hp * 0.8)                       # really phase 3, Stillness
    assert b.phase == 3 and b.name == "Warden of Stillness"
    real = _drawn(b, monkeypatch)
    assert ("pips", 3) in real and any(e[0] == "plate" and "Stillness" in e[1] for e in real)
    b.shown_phase = lambda: 2                           # what 055c reports while FINAL PHASE! waits
    b.shown_name = lambda: "Warden of Echoes"
    held = _drawn(b, monkeypatch)
    assert ("pips", 2) in held and any(e[0] == "plate" and "Echoes" in e[1] for e in held)
    assert [e[2] for e in held if e[0] == "plate"][0] == bs.pal(b.art_key, 2)[2]
