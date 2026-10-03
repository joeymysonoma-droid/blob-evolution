"""TASK-029: Narrative's lore text fixes (intro_scripts.md 1-5, 7; layer_scripts.md 1-4) are in place.

Strings are asserted literally on purpose, so a wording change fails a test. The two Director-pending
items (Warden card repeating the intro; Layer 10 Warden title) are deliberately not pinned here.
"""

from __future__ import annotations

from typing import List

import pygame
import pytest

from blob_evolution.config import MAP_THEMES
from blob_evolution.data import lore
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


# --- Director decisions: the Warden card (layer_scripts.md items 5 and 6; TASK-029-narrative-decisions.md) -----

CARD_LINES = [
    "Once a Seedling who refused to leave the Rim. The Lattice made them a gatekeeper so that no pilgrim would rush growth again.",
    "They watched a whole lineage dissolve into toxin and called it kindness. Their memory tastes of green water and unfinished names.",
    "A librarian of extinct shapes. They catalogued every pilgrim who died here — including versions of you that never reached the Core.",
    "Forged themselves into a trial. They believe only what survives heat deserves a future.",
    "Closest ally of the Stillness. They were the first pilgrim to accept freezing as paradise.",
    "Built the mirages so no one else would starve like they did. Peace was their weapon.",
    "Wore every face they absorbed until none remained theirs. They envy your unfinished self — and fear it.",
    "Speaks only in what is missing. Their gift is erasure.",
    "Three verdicts in one membrane: climb, remember, freeze. They argued for ages. Your arrival was the only motion they could not vote down.",
    "The first blob that refused the Divide. Everything else is their unfinished children. Defeating them does not kill them — it asks the question again.",
]


@pytest.mark.parametrize("act", ACTS)
def test_card_line_text_is_the_decided_text_and_a_prefix_of_the_fragment(act: int) -> None:
    """Each card_line is the exact string from the decisions file and the opening of the Archive fragment."""
    lore_act = get_act_lore(act)
    assert lore_act["card_line"] == CARD_LINES[act]
    assert lore_act["fragment"].startswith(lore_act["card_line"])


@pytest.mark.parametrize("act", [8, 9])
def test_finale_layers_show_the_whole_fragment(act: int) -> None:
    """Layers 9 and 10 give the card the full fragment (the decisions file: the finale shows all of it)."""
    assert get_act_lore(act)["card_line"] == get_act_lore(act)["fragment"]


@pytest.mark.parametrize("ng_level", [0, 2, 5, 10])
@pytest.mark.parametrize("act", ACTS)
def test_warden_card_body_is_quote_then_card_line_without_the_intro(act: int, ng_level: int) -> None:
    (page,) = build_boss_intro_pages(act, ng_level)
    lore_act = get_act_lore(act)
    quote = lore.get_warden_quote(act, ng_level)
    assert page["body"] == f'"{quote}"\n\n{lore_act["card_line"]}'
    assert lore_act["intro"] not in page["body"]


@pytest.mark.parametrize("act", range(9))
def test_layers_one_to_nine_keep_the_warden_encounter_eyebrow_and_name_title(act: int) -> None:
    (page,) = build_boss_intro_pages(act)
    assert page["eyebrow"] == "Warden Encounter"
    assert page["title"] == get_act_lore(act)["warden"] and "warden_title" not in get_act_lore(act)


def test_layer_ten_card_title_and_eyebrow() -> None:
    """The Prime Anchor card: eyebrow 'Prime Anchor', title 'Warden of the Divide' (keeps 'Warden' for the crown blob)."""
    (page,) = build_boss_intro_pages(9)
    assert page["eyebrow"] == "Prime Anchor" and page["title"] == "Warden of the Divide"
    assert "Warden" in page["title"]


def test_prime_anchor_name_is_unchanged_everywhere_else() -> None:
    """HUD/boss name, descent card line and Archive tab keep 'Prime Anchor'; only the encounter card title changed."""
    assert get_act_lore(9)["warden"] == "Prime Anchor"
    assert lore.get_boss_name(9) == "Prime Anchor"
    assert build_act_descent_pages(9)[0]["body"].endswith("Its Warden is the Prime Anchor.")


def test_warden_card_layout_fits_the_longest_cards() -> None:
    """Layer 9 at NG+ 5 and Layer 10 at NG+ 10 (the two longest) wrap to <= 2 quote lines + 3 card lines at 660 px."""
    pygame.font.init()
    font = pygame.font.SysFont("segoeui", 18)
    for act, level in ((8, 5), (9, 10)):
        (page,) = build_boss_intro_pages(act, level)
        quote, card = page["body"].split("\n\n")
        assert len(lore.wrap_text(quote, font, 660)) <= 2
        assert len(lore.wrap_text(card, font, 660)) <= 3
