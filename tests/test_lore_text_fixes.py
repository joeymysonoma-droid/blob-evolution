"""TASK-029: Narrative's lore text fixes (intro_scripts.md 1-5, 7; layer_scripts.md 1-4) are in place.

Strings are asserted literally on purpose, so a wording change fails a test. The two Director-pending
items (Warden card repeating the intro; Layer 10 Warden title) are deliberately not pinned here.
"""

from __future__ import annotations

from typing import List

import pygame
import pytest

from blob_evolution.config import MAP_THEMES
from blob_evolution.data.lore import (
    ACT_LORE,
    OPENING_BLURB,
    PILGRIMAGE_OPENING,
    build_act_descent_pages,
    build_boss_intro_pages,
    get_act_lore,
)
from blob_evolution.ui.menus import MenuRenderer

ACTS = range(len(ACT_LORE))


def _all_lore_strings() -> List[str]:
    """Every string reachable from the story-card builders and the act table."""
    out = [OPENING_BLURB]
    for page in PILGRIMAGE_OPENING:
        out += [page["eyebrow"], page["title"], page["body"]]
    for act in ACTS:
        out += [get_act_lore(act)["intro"], get_act_lore(act)["warden_quote"]]
        for page in build_act_descent_pages(act) + build_boss_intro_pages(act) + build_boss_intro_pages(act, miniboss=True):
            out += [page["eyebrow"], page["title"], page["body"]]
    return out


def test_there_are_ten_acts_matching_the_map_themes() -> None:
    """The per-act checks below cover every layer."""
    assert len(ACT_LORE) == 10 == len(MAP_THEMES)


def test_opening_blurb_fix() -> None:
    """Fix 5: the layers lead to the Core (the First Divide is layer 10, not a place between)."""
    assert OPENING_BLURB.endswith("Ten layers lead to the Core where evolution began.")
    assert "stand between" not in OPENING_BLURB


def test_pilgrimage_card_one_text() -> None:
    """Fixes 4, 5, 1: 'Your membrane', 'in ten layers. The last is...', 'the Stillness'."""
    body = PILGRIMAGE_OPENING[0]["body"]
    assert body == (
        "Your membrane cools around a new Seedling. No name. No caste. Only appetite.\n"
        "Above you, the Lattice stretches in ten layers. The last is a wound called the First Divide.\n"
        "Wardens keep the peace of the Stillness. You are the opposite of peace."
    )


def test_layer_five_intro_and_warden_quote_have_the() -> None:
    """Layer-5 intro and Warden quote say 'the Stillness'."""
    act = get_act_lore(4)
    assert act["intro"] == "The Stillness touched this layer first. Motion itself feels like rebellion."
    assert act["warden_quote"] == "Stop moving. The Stillness is the only shape that lasts."


def test_layer_nine_wardens_capitalised() -> None:
    """Fix 2: 'The Wardens convene.'"""
    assert get_act_lore(8)["intro"].startswith("The Wardens convene. ")


@pytest.mark.parametrize("act", ACTS)
def test_descent_card_warden_line(act: int) -> None:
    """Fix 3: every descent card ends 'Its Warden is the <Warden>.'; the old clumsy line is gone."""
    (page,) = build_act_descent_pages(act)
    warden = get_act_lore(act)["warden"]
    assert page["body"] == f"{get_act_lore(act)['intro']}\n\nIts Warden is the {warden}."
    assert "The Warden of this layer" not in page["body"]


def test_descent_card_examples() -> None:
    """Layer 1 and Layer 10 read naturally ('the Warden of Sprouting', 'the Prime Anchor')."""
    assert build_act_descent_pages(0)[0]["body"].endswith("Its Warden is the Warden of Sprouting.")
    assert build_act_descent_pages(9)[0]["body"].endswith("Its Warden is the Prime Anchor.")


@pytest.mark.parametrize("act", ACTS)
def test_miniboss_card_lowercases_the(act: int) -> None:
    """Layer-4 fix: 'A compressed memory of the Verdant Rim bars the path.' (lower-case 'the' mid-sentence)."""
    name = get_act_lore(act)["lore_name"]
    assert name.startswith("The ")
    (page,) = build_boss_intro_pages(act, miniboss=True)
    assert page["body"] == (
        f"A compressed memory of the {name[4:]} bars the path.\n"
        "It does not speak. It only tests whether you still remember how to change."
    )
    assert "of The " not in page["body"]


def test_miniboss_card_layer_one_literal() -> None:
    """The exact text Narrative voices for Layer 1."""
    body = build_boss_intro_pages(0, miniboss=True)[0]["body"]
    assert body.startswith("A compressed memory of the Verdant Rim bars the path.")


def test_layer_names_in_data_are_unchanged() -> None:
    """The fix is applied at display time: lore_name keeps its capital 'The' (used as a title elsewhere)."""
    assert get_act_lore(0)["lore_name"] == "The Verdant Rim"
    assert build_act_descent_pages(0)[0]["title"] == "The Verdant Rim"


def test_no_old_wording_left_in_any_card() -> None:
    """None of the replaced phrases survives anywhere in the story-card text."""
    old = ["peace of Stillness", "Membrane cools", "stand between you and the Core", "toward a wound",
           "The wardens", "Warden of this layer", "of The "]
    text = "\n".join(_all_lore_strings())
    assert [o for o in old if o in text] == []
    assert "Stillness touched this layer first" not in text.replace("The Stillness touched", "")
    assert "Stop moving. Stillness" not in text


def test_help_screen_broker_line(monkeypatch) -> None:
    """Fix 7: the Help screen says '(once unlocked) become the Broker' and the line fits the panel."""
    pygame.init()
    renderer = MenuRenderer()
    seen = []
    for attr in ("small_font", "tiny_font", "menu_font"):
        font = getattr(renderer, attr)
        real = font.render

        class Rec:
            """Records each rendered string and its width."""

            def __init__(self, f, real_render):
                self._f, self._r = f, real_render

            def render(self, text, *a, **k):
                s = self._r(text, *a, **k)
                seen.append((text, s.get_width()))
                return s

            def __getattr__(self, n):
                return getattr(self._f, n)

        setattr(renderer, attr, Rec(font, real))
    surface = pygame.Surface((1200, 800))
    renderer.draw_help(surface)
    lines = [(t, w) for t, w in seen if "Broker" in t]
    assert lines == [("Reopen evolution, merge, or (once unlocked) become the Broker.", lines[0][1])]
    assert 80 + 200 + lines[0][1] <= 80 + (1200 - 160), "help line overflows the panel"
    assert "(later)" not in "".join(t for t, _ in seen)
