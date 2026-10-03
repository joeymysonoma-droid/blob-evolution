"""TASK-023 (BUG-045): every save notice variant really draws its title, each body line and its button.

QA's TASK-021 found nothing checked that the title was drawn. These tests record every string the notice renders
and every surface it blits, so skipping the title, a body line or the button makes them fail, for all three variants.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.data.lore import SAVE_NOTICES
from blob_evolution.ui.menus import MenuRenderer

VARIANTS = ("recovered", "partial", "saving_paused")
PANEL_X, PANEL_Y, PANEL_W = config.SCREEN_WIDTH // 2 - 280, 288, 560


class _FontSpy:
    """Wraps a pygame font; remembers the text of every surface it renders."""

    def __init__(self, font, seen: Dict[int, str], keep: list) -> None:
        self._font, self._seen, self._keep = font, seen, keep

    def render(self, text, *args, **kwargs) -> pygame.Surface:
        surf = self._font.render(text, *args, **kwargs)
        self._keep.append(surf)  # keeps id() unique
        self._seen[id(surf)] = text
        return surf

    def __getattr__(self, name):
        return getattr(self._font, name)


class _RecSurface(pygame.Surface):
    """A surface that logs every blit (source, destination rect)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.log: List[Tuple[pygame.Surface, pygame.Rect]] = []

    def blit(self, source, dest, *args, **kwargs):
        self.log.append((source, pygame.Rect(tuple(dest)[:2], source.get_size())))
        return super().blit(source, dest, *args, **kwargs)


def _spy_fonts(menu: MenuRenderer, small=None, tiny=None) -> Dict[int, str]:
    """Replace the menu's fonts (optionally small/tiny with other fonts) by recording wrappers."""
    seen: Dict[int, str] = {}
    keep: list = []
    for tag, font in (("menu_font", None), ("small_font", small), ("tiny_font", tiny)):
        setattr(menu, tag, _FontSpy(font or getattr(menu, tag), seen, keep))
    menu._seen = seen  # type: ignore[attr-defined]
    return seen


def _drawn_texts(surface: _RecSurface, seen: Dict[int, str]) -> List[Tuple[str, pygame.Rect]]:
    """(text, rect) of every rendered string that was actually blitted to the surface, in draw order."""
    return [(seen[id(src)], rect) for src, rect in surface.log if id(src) in seen]


@pytest.fixture
def menu() -> MenuRenderer:
    pygame.init()
    pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    return MenuRenderer()


def _draw(menu: MenuRenderer, variant: str) -> Tuple[List[Tuple[str, pygame.Rect]], pygame.Rect]:
    surface = _RecSurface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    menu.draw_save_notice(surface, variant, **SAVE_NOTICES[variant])
    return _drawn_texts(surface, menu._seen), pygame.Rect(PANEL_X, PANEL_Y, PANEL_W, 224 + menu.save_notice_extra)


@pytest.mark.parametrize("variant", VARIANTS)
def test_title_body_lines_and_button_are_drawn(menu, variant: str) -> None:
    """The exact title, every body line (one per \\n) and the button text are blitted, in that order."""
    _spy_fonts(menu)
    texts, _panel = _draw(menu, variant)
    notice = SAVE_NOTICES[variant]
    drawn = [t for t, _ in texts]
    lines = notice["body"].split("\n")
    assert notice["title"] in drawn, "title not drawn"
    assert notice["button"] in drawn, "button label not drawn"
    for line in lines:
        assert line in drawn, f"body line not drawn: {line!r}"
    assert drawn[0] == notice["title"] and drawn[1:1 + len(lines)] == lines
    assert drawn[1 + len(lines)] == notice["button"]


@pytest.mark.parametrize("variant", VARIANTS)
def test_every_string_sits_inside_the_panel(menu, variant: str) -> None:
    """Title, body lines and button all land within the panel (and the body inside its right margin)."""
    _spy_fonts(menu)
    texts, panel = _draw(menu, variant)
    notice = SAVE_NOTICES[variant]
    for text, rect in texts:
        if text == "SPACE / ENTER / ESC":
            continue
        assert panel.contains(rect), (text, rect, panel)
        if text in notice["body"].split("\n"):
            assert rect.right <= panel.right - 36
    assert menu.save_notice_extra == 0


@pytest.mark.parametrize("variant", VARIANTS)
def test_game_draws_the_variants_copy_over_the_main_menu(make_game, isolated_save, variant: str) -> None:
    """Through the real Game._draw: with save_notice set, that variant's own strings reach the screen."""
    game = make_game()
    seen = _spy_fonts(game.menu)
    game.screen = _RecSurface(game.screen.get_size())
    game.save_notice = variant
    game._draw()
    drawn = [t for t, _ in _drawn_texts(game.screen, seen)]
    notice = SAVE_NOTICES[variant]
    for text in (notice["title"], notice["button"], *notice["body"].split("\n")):
        assert text in drawn, text
    other = {v: SAVE_NOTICES[v]["title"] for v in VARIANTS if v != variant}
    assert not set(other.values()) & set(drawn)


# --- overflow fallback with wider fonts -------------------------------------------------------------------

WIDE = [(34, 26), (44, 30), (60, 40), (90, 70)]  # (small, tiny) sizes: wide enough that the small font cannot hold the copy


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("small_size,tiny_size", WIDE)
def test_overflow_fallback_still_draws_everything_inside_the_panel(menu, variant: str, small_size: int, tiny_size: int) -> None:
    """With wider small/tiny fonts the body wraps, the panel grows, and title, every word and button still draw inside it."""
    wide_small = pygame.font.SysFont("segoeui", small_size)
    wide_tiny = pygame.font.SysFont("segoeui", tiny_size)
    _spy_fonts(menu, small=wide_small, tiny=wide_tiny)
    texts, panel = _draw(menu, variant)
    notice = SAVE_NOTICES[variant]
    drawn = [t for t, _ in texts]
    body_drawn = [t for t in drawn if t not in (notice["title"], notice["button"], "SPACE / ENTER / ESC")]
    assert notice["title"] in drawn and notice["button"] in drawn
    assert " ".join(body_drawn).split() == notice["body"].split(), "a body word was lost or reordered"
    assert len(body_drawn) > len(notice["body"].split("\n")), "the wide font should have forced extra wrapping"
    assert menu.save_notice_extra == max(0, len(body_drawn) - 4) * 17 and panel.height == 224 + menu.save_notice_extra
    for text, rect in texts:
        if text == "SPACE / ENTER / ESC":
            continue
        assert panel.contains(rect), (text, rect, panel)
        if text in body_drawn:
            assert rect.right <= panel.right - 36, (text, rect)
    button = MenuRenderer.save_notice_button_rect(menu.save_notice_extra)
    assert panel.contains(button) and button.centerx == panel.centerx
    label = next(r for t, r in texts if t == notice["button"])
    assert button.contains(label) or label.width > button.width, "button text is centred on the button"
    assert abs(label.centerx - button.centerx) <= 1 and abs(label.centery - button.centery) <= 1
