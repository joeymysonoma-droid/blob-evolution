"""TASK-013d: game-over progress line selection, fallback, and end-screen footers."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from blob_evolution import config  # noqa: E402
from blob_evolution.data import lore  # noqa: E402
from blob_evolution.ui.menus import MenuRenderer, game_over_progress  # noqa: E402


def test_copy_matches_narrative_exactly() -> None:
    """Template constants are Narrative's strings, character for character."""
    assert lore.GAME_OVER_PROGRESS_LINE == "Reached Layer {reached}  \u00b7  Best: Layer {best}"
    assert lore.GAME_OVER_DEEPEST_LINE == "Reached Layer {reached}, your deepest yet"
    assert lore.VICTORY_NG_PLUS_LINE == "New Game Plus {n} unlocked. The Lattice remembers."


@pytest.mark.parametrize(
    ("maps_cleared", "best_before", "expected", "new_best"),
    [
        (0, 1, "Reached Layer 1, your deepest yet", True),  # tie on Layer 1
        (4, 3, "Reached Layer 5, your deepest yet", True),  # new best
        (4, 5, "Reached Layer 5, your deepest yet", True),  # tie
        (4, 8, "Reached Layer 5  \u00b7  Best: Layer 8", False),  # higher saved best
        (9, 10, "Reached Layer 10, your deepest yet", True),  # tie on the last layer
        (0, 10, "Reached Layer 1  \u00b7  Best: Layer 10", False),
    ],
)
def test_progress_line_selection(maps_cleared: int, best_before: int, expected: str, new_best: bool) -> None:
    """New or tied best uses the deepest-yet form; otherwise Reached/Best."""
    stats = {"maps_cleared": maps_cleared, "best_layer_before": best_before}
    assert game_over_progress(stats) == (expected, new_best)


def test_reached_is_capped_at_layer_10() -> None:
    """Reached never shows Layer 11."""
    text, _ = game_over_progress({"maps_cleared": 10, "best_layer_before": 10})
    assert text == "Reached Layer 10, your deepest yet"


@pytest.mark.parametrize("stats", [{}, {"maps_cleared": 3}])
def test_missing_best_layer_before_falls_back(stats: dict) -> None:
    """Older run_stats without best_layer_before fall back to the deepest-yet form."""
    reached = stats.get("maps_cleared", 0) + 1
    assert game_over_progress(stats) == (f"Reached Layer {reached}, your deepest yet", True)


@pytest.fixture(scope="module")
def menu() -> MenuRenderer:
    """A real MenuRenderer on a headless display."""
    pygame.init()
    pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    return MenuRenderer()


@pytest.mark.parametrize(
    ("panel", "inset", "divider_up", "text_up"),
    [
        (pygame.Rect(340, 200, 520, 320), 48, 64, 48),  # game over
        (pygame.Rect(340, 175, 520, 232), 40, 52, 38),  # victory
    ],
)
def test_footer_keeps_a_50_char_line_inside_the_panel(menu, panel, inset, divider_up, text_up) -> None:
    """A 50-character line stays inside the panel (tiny_font fallback if needed)."""
    surface = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
    line = lore.VICTORY_NG_PLUS_LINE.format(n=100)
    assert len(line) == 50
    menu._draw_panel_footer(surface, panel, line, (255, 255, 255), inset, divider_up, text_up)
    text_band = pygame.Rect(0, panel.bottom - text_up, config.SCREEN_WIDTH, text_up)
    bounds = surface.subsurface(text_band).get_bounding_rect()
    assert bounds.width > 0
    assert bounds.left >= panel.x + 24 - 1 and bounds.right <= panel.right - 24 + 1
    assert text_band.y + bounds.bottom <= panel.bottom


@pytest.mark.parametrize("ending", ["reopen", "merge", "broker"])
def test_end_screens_draw(menu, ending: str) -> None:
    """Both screens draw with and without best_layer_before, for every ending."""
    surface = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    menu.draw_game_over(surface, {"maps_cleared": 4}, 0)
    menu.draw_game_over(surface, {"maps_cleared": 4, "best_layer_before": 8}, 1)
    menu.draw_victory(surface, {"level": 30, "kills": 900, "essence": 5000, "artifacts": 7, "ending": ending}, 0, 10, ending)
