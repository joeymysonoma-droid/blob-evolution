"""BUG-010 / TASK-014: the TAB skills overlay fits every skill row and its text inside the panel.

Geometry comes from ui.hud.skills_overlay_layout, the helper draw_skills_overlay uses;
text rects are captured from the real draw call's blits.
"""

from __future__ import annotations

from typing import List, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.entities.player import Player
from blob_evolution.ui.hud import HUD, skills_overlay_layout
from blob_evolution.utils.vector2 import Vector2

LIST_MARGIN = 48  # last row bottom must be <= panel.bottom - 48 (Evolution label sits below)


class RecordingSurface(pygame.Surface):
    """Screen-sized surface that records the rect of every blit onto it."""

    def __init__(self) -> None:
        super().__init__((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        self.blits: List[pygame.Rect] = []

    def blit(self, source, dest, *args, **kwargs):  # type: ignore[override]
        """Record the destination rect, then blit as normal."""
        self.blits.append(pygame.Rect(dest, source.get_size()))
        return super().blit(source, dest, *args, **kwargs)


def _render(count: int) -> Tuple[pygame.Rect, List[pygame.Rect], List[pygame.Rect]]:
    """Draw the overlay for `count` skills (the real 9, repeated if more); return panel, rows, blits."""
    pygame.init()
    player = Player(Vector2(0, 0))
    player.skill_points = 100
    real = player.skills.get_all_skills()
    player.skills.get_all_skills = lambda: [real[i % len(real)] for i in range(count)]
    surface = RecordingSurface()
    HUD().draw_skills_overlay(surface, player)
    panel, rows = skills_overlay_layout(count)
    return panel, rows, surface.blits


def test_real_skill_list_has_nine_entries():
    """The game ships 9 skills, which is what the overlay must fit."""
    assert len(Player(Vector2(0, 0)).skills.get_all_skills()) == 9


@pytest.mark.parametrize("count", [9, 10, 11, 12])
def test_rows_fit_inside_panel(count):
    """All rows are drawn inside the panel, don't overlap, and end by panel.bottom - 48."""
    panel, rows, blits = _render(count)
    assert len(rows) == count
    for i, row in enumerate(rows):
        assert row in blits, f"row {i + 1} {row} was not drawn where the layout says"
        assert panel.contains(row), f"row {i + 1} {row} leaves panel {panel}"
    for above, below in zip(rows, rows[1:]):
        assert above.bottom <= below.top, f"rows overlap: {above} / {below}"
    assert rows[-1].bottom <= panel.bottom - LIST_MARGIN, (
        f"last row bottom {rows[-1].bottom} > panel.bottom - {LIST_MARGIN} = {panel.bottom - LIST_MARGIN}"
    )


@pytest.mark.parametrize("count", [9, 10])
def test_row_text_fits_inside_row(count):
    """Each row's name, description and cost text sit fully inside the row; name and cost don't touch."""
    _, rows, blits = _render(count)
    for i, row in enumerate(rows):
        at = blits.index(row)  # row panel blit, then name, description, cost
        name, desc, cost = blits[at + 1 : at + 4]
        for label, text in (("name", name), ("description", desc), ("cost", cost)):
            assert row.contains(text), f"row {i + 1} {label} {text} clipped by row {row}"
        assert not name.colliderect(cost), f"row {i + 1} name {name} overlaps cost {cost}"
