"""TASK-009c: save-recovery notice over the main menu (recovered / saving_paused)."""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.data.lore import SAVE_NOTICES, wrap_text
from blob_evolution.systems import savefile
from blob_evolution.ui import style
from blob_evolution.ui.menus import MenuRenderer
from blob_evolution.utils.enums import GameState

BUTTON = MenuRenderer.save_notice_button_rect()
PANEL_TOP_EDGE = (config.SCREEN_WIDTH // 2, 288)


def _key(game, key: int) -> None:
    """Send one KEYDOWN through the real event router."""
    game._handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


def _click(game, pos, button: int = 1) -> None:
    """Send one mouse click through the real event router."""
    game._handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))


def _recording(game, monkeypatch) -> list:
    """Wrap the real draw_save_notice and record the variants it draws."""
    calls: list = []
    real = game.menu.draw_save_notice

    def record(surface, variant, title, body, button):
        calls.append((variant, title, body, button))
        return real(surface, variant, title, body, button)

    monkeypatch.setattr(game.menu, "draw_save_notice", record)
    return calls


def _damaged(isolated_save, fixture_bytes) -> None:
    """Write a truncated (unreadable) copy of the fixture save."""
    isolated_save.write_bytes(fixture_bytes[: len(fixture_bytes) // 2])


@pytest.fixture
def recovered_game(make_game, isolated_save, fixture_bytes):
    """A booted game whose damaged save 007 backed up."""
    _damaged(isolated_save, fixture_bytes)
    game = make_game()
    assert (isolated_save.parent / (isolated_save.name + config.SAVE_BACKUP_SUFFIX)).exists()
    return game


def _fill_backup_slots(isolated_save) -> None:
    """Occupy every backup slot with different bytes, so 007 can't back up."""
    for path in savefile.backup_paths(str(isolated_save)):
        with open(path, "wb") as f:
            f.write(f"prefilled {path}\n".encode())


def test_recovered_variant_after_backup(recovered_game, monkeypatch) -> None:
    """A damaged save that 007 backs up shows the recovered notice with Narrative's copy."""
    assert recovered_game.save_notice == "recovered"
    assert recovered_game._save_blocked is False
    calls = _recording(recovered_game, monkeypatch)
    recovered_game._draw()
    assert calls == [("recovered", *SAVE_NOTICES["recovered"].values())]
    assert recovered_game.screen.get_at(PANEL_TOP_EDGE)[:3] == style.PANEL_EDGE_HOT


def test_invalid_field_shows_partial_notice(make_game, isolated_save, fixture_data) -> None:
    """A readable save with one wrong-typed field is backed up and shows the partial notice (TASK-023)."""
    import json

    fixture_data["permanent"]["shards"] = "72"
    isolated_save.write_text(json.dumps(fixture_data), encoding="utf-8")
    assert make_game().save_notice == "partial"


def test_saving_paused_when_backup_slots_full(make_game, isolated_save, fixture_bytes, monkeypatch) -> None:
    """When 007 can't back up (all slots full) and pauses saving, the paused notice shows."""
    _damaged(isolated_save, fixture_bytes)
    _fill_backup_slots(isolated_save)
    game = make_game()
    assert game._save_blocked is True
    assert game.save_notice == "saving_paused"
    calls = _recording(game, monkeypatch)
    game._draw()
    assert calls == [("saving_paused", *SAVE_NOTICES["saving_paused"].values())]
    assert game.screen.get_at(PANEL_TOP_EDGE)[:3] == style.DANGER


def test_saving_paused_when_backup_write_raises(make_game, isolated_save, fixture_bytes, monkeypatch) -> None:
    """An OSError while writing the backup (inside 007's backup_save) also gives saving_paused."""
    _damaged(isolated_save, fixture_bytes)

    def failing_fsync(fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(savefile.os, "fsync", failing_fsync)
    game = make_game()
    assert game._save_blocked is True
    assert game.save_notice == "saving_paused"


def test_no_notice_for_valid_fixture(make_game, isolated_save, fixture_bytes, monkeypatch) -> None:
    """A valid save shows no notice."""
    isolated_save.write_bytes(fixture_bytes)
    game = make_game()
    assert game.save_notice is None
    calls = _recording(game, monkeypatch)
    game._draw()
    assert calls == []


def test_no_notice_without_a_save(make_game, isolated_save, monkeypatch) -> None:
    """A first boot with no save shows no notice."""
    assert not isolated_save.exists()
    game = make_game()
    assert game.save_notice is None
    calls = _recording(game, monkeypatch)
    game._draw()
    assert calls == []


def test_menu_input_blocked_while_open(recovered_game) -> None:
    """Menu keys, hover and clicks on menu items do nothing while the notice is up."""
    game = recovered_game
    game._draw()  # populates the main menu's item rects under the notice
    selected, difficulty = game.menu_selected, game.difficulty
    for key in (pygame.K_DOWN, pygame.K_s, pygame.K_UP, pygame.K_a, pygame.K_d, pygame.K_TAB, pygame.K_q):
        _key(game, key)
    play_rect = game.menu.item_rects[0]
    game._handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=game.menu.item_rects[2].center, rel=(0, 0), buttons=(0, 0, 0)))
    _click(game, play_rect.center)
    assert game.state == GameState.MAIN_MENU
    assert game.menu_selected == selected
    assert game.difficulty == difficulty
    assert game.save_notice == "recovered"


@pytest.mark.parametrize("key", [pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE], ids=["space", "enter", "esc"])
def test_dismiss_keys(recovered_game, key: int) -> None:
    """SPACE, ENTER and ESC dismiss the notice without also acting on the menu."""
    game = recovered_game
    _key(game, key)
    assert game.save_notice is None
    assert game.state == GameState.MAIN_MENU
    assert game.menu_selected == 0


def test_dismiss_by_button_click(recovered_game) -> None:
    """A left click on the button dismisses the notice and doesn't click through."""
    game = recovered_game
    game._draw()
    _click(game, BUTTON.center)
    assert game.save_notice is None
    assert game.state == GameState.MAIN_MENU


@pytest.mark.parametrize(
    ("pos", "button"),
    [
        ((BUTTON.left - 5, BUTTON.centery), 1),  # just left of the button, inside the panel
        ((config.SCREEN_WIDTH // 2, 300), 1),  # panel title area
        ((40, 40), 1),  # outside the panel
        (BUTTON.center, 3),  # right click on the button
    ],
    ids=["beside-button", "panel", "outside", "right-click"],
)
def test_other_clicks_do_not_dismiss(recovered_game, pos, button: int) -> None:
    """Clicks that aren't a left click on the button leave the notice up."""
    game = recovered_game
    game._draw()
    _click(game, pos, button)
    assert game.save_notice == "recovered"
    assert game.state == GameState.MAIN_MENU


def test_shows_once_per_boot(recovered_game, monkeypatch) -> None:
    """After dismissal the notice doesn't come back, and the menu takes input again."""
    game = recovered_game
    _key(game, pygame.K_ESCAPE)
    calls = _recording(game, monkeypatch)
    for _ in range(3):
        game._draw()
    assert calls == []
    _key(game, pygame.K_DOWN)
    assert game.menu_selected == 1
    assert game.save_notice is None


# ---------------------------------------------------------------------------------------------
# TASK-009c rework (BUG-028 overflow layout, BUG-029 mutation coverage, BUG-030 pulse contrast)
# ---------------------------------------------------------------------------------------------

PANEL_X, PANEL_Y = config.SCREEN_WIDTH // 2 - 280, 288  # 320, 288
ICON = (PANEL_X + 44, PANEL_Y + 44)  # icon center
TEXT_X = PANEL_X + 76
HINT_TEXT = "SPACE / ENTER / ESC"
VARIANTS = ("recovered", "saving_paused")


class _FontSpy:
    """Wraps a pygame font; remembers every surface it renders, with its tag, text and color."""

    def __init__(self, font: pygame.font.Font, tag: str, registry: Dict[int, tuple]) -> None:
        self._font, self.tag, self._registry = font, tag, registry
        self._keep: List[pygame.Surface] = []  # keep surfaces alive so id() stays unique

    def render(self, text, antialias, color, *args, **kwargs) -> pygame.Surface:
        """Render with the real font and record (tag, text, color) for the returned surface."""
        surf = self._font.render(text, antialias, color, *args, **kwargs)
        self._keep.append(surf)
        self._registry[id(surf)] = (self.tag, text, tuple(color))
        return surf

    def __getattr__(self, name: str):
        return getattr(self._font, name)


class _RecSurface(pygame.Surface):
    """A surface that logs every blit as (source, destination rect)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.log: List[Tuple[pygame.Surface, pygame.Rect]] = []

    def blit(self, source, dest, *args, **kwargs):
        """Log the blit, then do it."""
        top_left = tuple(dest)[:2]
        self.log.append((source, pygame.Rect(top_left, source.get_size())))
        return super().blit(source, dest, *args, **kwargs)


class _Drawn:
    """One draw_save_notice call on a recording surface, with its blits decoded."""

    def __init__(self, menu: MenuRenderer, surface: _RecSurface, button: pygame.Rect) -> None:
        self.surface, self.button = surface, button
        reg = menu.fonts_registry
        self.texts = [(*reg[id(src)], rect) for src, rect in surface.log if id(src) in reg]
        self.body = [t for t in self.texts if t[2] == tuple(style.TEXT)]
        self.hint = next(t for t in self.texts if t[1] == HINT_TEXT)
        self.panel_blit = next(r for src, r in surface.log if src.get_size()[0] == 560)
        self.glow = [r for src, r in surface.log if src.get_size() == (200, 42)]

    @property
    def body_lines(self) -> List[str]:
        """Body line texts in draw order."""
        return [t[1] for t in self.body]

    @property
    def body_tops(self) -> List[int]:
        """Body line top y values."""
        return [t[3].top for t in self.body]


@pytest.fixture
def menu() -> MenuRenderer:
    """A real MenuRenderer whose fonts record what they render."""
    pygame.init()
    pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    m = MenuRenderer()
    m.fonts_registry = {}
    for tag in ("menu_font", "small_font", "tiny_font"):
        setattr(m, tag, _FontSpy(getattr(m, tag), tag, m.fonts_registry))
    return m


@pytest.fixture
def draw_notice(menu) -> Callable[..., _Drawn]:
    """Return draw(variant, body, title='Title', button='Button') -> _Drawn, via the real draw_save_notice."""

    def _draw(variant: str, body: str, title: str = "Title", button: str = "Button") -> _Drawn:
        surface = _RecSurface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        rect = menu.draw_save_notice(surface, variant, title, body, button)
        return _Drawn(menu, surface, rect)

    return _draw


def _lines(n: int) -> str:
    """A body of n short paragraphs: n lines in any font."""
    return "\n".join(f"line {i + 1}" for i in range(n))


def _luminance(c: Tuple[int, int, int]) -> float:
    """WCAG relative luminance of an sRGB color."""
    def lin(v: int) -> float:
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> float:
    """WCAG contrast ratio between two colors."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.fixture
def paused_game(make_game, isolated_save, fixture_bytes):
    """A booted game whose damaged save could not be backed up (every backup slot is taken)."""
    _damaged(isolated_save, fixture_bytes)
    _fill_backup_slots(isolated_save)
    game = make_game()
    assert game._save_blocked is True
    return game


@pytest.fixture(params=VARIANTS)
def notice_game(request, recovered_game, paused_game):
    """Each variant's booted game, with the notice up."""
    game = recovered_game if request.param == "recovered" else paused_game
    assert game.save_notice == request.param
    return game


# --- copy ---------------------------------------------------------------------------------

def test_copy_is_the_final_ascii_text() -> None:
    """Bodies match Narrative's 009d/009e copy character for character; titles and buttons are unchanged."""
    rec, paused = SAVE_NOTICES["recovered"], SAVE_NOTICES["saving_paused"]
    assert rec["body"] == "Your save was damaged.\nShards, upgrades, and NG+ begin again.\nYour old save rests in a .bak file."
    assert paused["body"] == "Your damaged save could not be backed up.\nTo guard it, saving waits for a backup."
    assert (rec["title"], rec["button"]) == ("The Lattice Forgot You", "Begin Again")
    assert (paused["title"], paused["button"]) == ("The Lattice Stops Remembering", "Walk On")
    for notice in SAVE_NOTICES.values():
        assert notice["body"].isascii() and "\r" not in notice["body"]


# --- BUG-028: overflow layout ---------------------------------------------------------------

@pytest.mark.parametrize("variant,count", [("recovered", 3), ("saving_paused", 2)])
def test_real_copy_fits_small_font_without_growing(menu, draw_notice, variant: str, count: int) -> None:
    """The real copy draws every \\n line on its own line in the small font; the panel does not grow."""
    body = SAVE_NOTICES[variant]["body"]
    drawn = draw_notice(variant, body)
    assert menu.save_notice_extra == 0
    assert drawn.body_lines == body.split("\n") and len(drawn.body_lines) == count
    assert {t[0] for t in drawn.body} == {"small_font"}
    assert drawn.body_tops == [PANEL_Y + 72 + i * 22 for i in range(count)]  # 360 / 382 / 404
    assert drawn.panel_blit.height == 224
    assert drawn.button == MenuRenderer.save_notice_button_rect(0)
    assert drawn.glow == [drawn.button]
    b = drawn.button
    assert menu.save_notice_hit_test(b.topleft) and menu.save_notice_hit_test((b.right - 1, b.bottom - 1))
    assert not menu.save_notice_hit_test((b.left, b.top - 1)) and not menu.save_notice_hit_test((b.left, b.bottom))


@pytest.mark.parametrize("variant", VARIANTS)
def test_real_copy_stays_within_four_tiny_lines(menu, variant: str) -> None:
    """Even in the tiny font the real copy needs at most 4 lines, so the fallback never needs to grow the panel."""
    wrap_w = PANEL_X + 560 - 36 - TEXT_X
    paras = SAVE_NOTICES[variant]["body"].split("\n")
    assert len([ln for p in paras for ln in wrap_text(p, menu.tiny_font, wrap_w)]) <= 4


def test_four_line_body_switches_to_tiny_font_without_growing(menu, draw_notice) -> None:
    """4 lines don't fit the small font's 3: switch to tiny at pitch 17, panel stays 224, nothing is dropped."""
    drawn = draw_notice("recovered", _lines(4))
    assert menu.save_notice_extra == 0
    assert drawn.body_lines == [f"line {i}" for i in range(1, 5)]
    assert {t[0] for t in drawn.body} == {"tiny_font"}
    assert drawn.body_tops == [360, 377, 394, 411]
    assert drawn.panel_blit.height == 224
    assert drawn.button == MenuRenderer.save_notice_button_rect(0)
    last_bottom = drawn.body[-1][3].bottom
    assert drawn.button.top - last_bottom >= 17, (last_bottom, drawn.button)


def test_three_lines_stay_in_small_font(draw_notice) -> None:
    """Exactly 3 lines is still the small font (the tiny fallback starts at 4)."""
    drawn = draw_notice("recovered", _lines(3))
    assert {t[0] for t in drawn.body} == {"small_font"}


@pytest.mark.parametrize("n", [5, 6, 9, 18])
def test_long_body_grows_panel_and_moves_button_and_hit_area_together(menu, draw_notice, n: int) -> None:
    """n tiny lines grow the panel 17 px per line beyond 4; the button, its drawn glow, hit area and hint move with it."""
    drawn = draw_notice("saving_paused", _lines(n))
    extra = (n - 4) * 17
    assert menu.save_notice_extra == extra
    assert drawn.body_lines == [f"line {i}" for i in range(1, n + 1)], "every line must be drawn"
    assert drawn.body_tops == [360 + i * 17 for i in range(n)]
    assert drawn.panel_blit == pygame.Rect(PANEL_X, PANEL_Y, 560, 224 + extra)
    base = MenuRenderer.save_notice_button_rect(0)
    assert drawn.button == base.move(0, extra)
    assert drawn.glow == [drawn.button], "the button is drawn where draw_save_notice says it is"
    assert drawn.hint[3].top == drawn.panel_blit.bottom + 12
    assert drawn.hint[3].bottom <= 788
    assert drawn.body[-1][3].bottom <= drawn.button.top
    # the hit area is exactly the drawn button, corner to corner
    b = drawn.button
    inside = [b.topleft, (b.right - 1, b.bottom - 1), b.center, (b.right - 1, b.top), (b.left, b.bottom - 1)]
    outside = [(b.left - 1, b.centery), (b.right, b.centery), (b.centerx, b.top - 1), (b.centerx, b.bottom)]
    assert all(menu.save_notice_hit_test(pos) for pos in inside)
    assert not any(menu.save_notice_hit_test(pos) for pos in outside)
    assert menu.save_notice_hit_test(base.topleft) is (extra == 0), "the old (extra=0) button spot is stale"


def test_long_paragraph_wraps_in_tiny_font_and_loses_no_words(menu, draw_notice) -> None:
    """One long paragraph wraps in the tiny font, grows the panel, and every word is still drawn."""
    words = [f"w{i:02d}" for i in range(90)]
    drawn = draw_notice("recovered", " ".join(words))
    lines = drawn.body_lines
    assert len(lines) > 4 and {t[0] for t in drawn.body} == {"tiny_font"}
    assert " ".join(lines).split() == words
    assert menu.save_notice_extra == (len(lines) - 4) * 17
    assert drawn.button == MenuRenderer.save_notice_button_rect(menu.save_notice_extra)


def test_layout_extra_resets_when_a_short_body_follows_a_long_one(menu, draw_notice) -> None:
    """save_notice_extra is recomputed each draw, so the hit area never keeps a stale offset."""
    draw_notice("recovered", _lines(8))
    assert menu.save_notice_extra == 68
    drawn = draw_notice("recovered", _lines(2))
    assert menu.save_notice_extra == 0
    assert menu.save_notice_hit_test(drawn.button.center)


def test_game_click_follows_the_grown_button(make_game, isolated_save, fixture_bytes, monkeypatch) -> None:
    """Through the real Game: with a 6-line body only a click on the moved button dismisses; the old spot does not."""
    _damaged(isolated_save, fixture_bytes)
    monkeypatch.setitem(SAVE_NOTICES["recovered"], "body", _lines(6))
    game = make_game()
    game._draw()
    assert game.menu.save_notice_extra == 34
    old = MenuRenderer.save_notice_button_rect(0)
    new = MenuRenderer.save_notice_button_rect(34)
    assert not new.collidepoint(old.center)
    _click(game, old.center)
    assert game.save_notice == "recovered"
    _click(game, new.center)
    assert game.save_notice is None


# --- BUG-029: variants, pixels --------------------------------------------------------------

def _pin_pulse(monkeypatch, value: str = "lo") -> List[tuple]:
    """Pin style.pulse to its lo (or hi) argument and return the recorded argument tuples."""
    calls: List[tuple] = []

    def fake(speed: float = 2.0, lo: float = 0.0, hi: float = 1.0) -> float:
        calls.append((speed, lo, hi))
        return lo if value == "lo" else hi

    monkeypatch.setattr(style, "pulse", fake)
    return calls


def _px(game, pos: Tuple[int, int]) -> Tuple[int, int, int]:
    """RGB of a pixel on the game's screen."""
    return tuple(game.screen.get_at(pos))[:3]


def test_recovered_look_info_icon_and_one_pixel_edge(recovered_game, monkeypatch) -> None:
    """Recovered: circle-i icon (no warn triangle), 1 px hot-green edge, and no pulse."""
    calls = _pin_pulse(monkeypatch)
    game = recovered_game
    game._draw()
    cx, cy = ICON
    top = config.SCREEN_WIDTH // 2
    assert _px(game, (cx - 14, cy)) == style.ACCENT, "info circle"
    assert _px(game, (cx, cy - 6)) == style.ACCENT, "info dot"
    assert _px(game, (cx, cy - 15)) != style.ACCENT, "no triangle apex"
    assert _px(game, (cx, cy + 8)) != style.ACCENT, "no warn dot"
    assert _px(game, (top, PANEL_Y)) == style.PANEL_EDGE_HOT
    assert _px(game, (top, PANEL_Y + 1)) != style.PANEL_EDGE_HOT, "edge must be 1 px"
    assert _px(game, (top, PANEL_Y + 223)) == style.PANEL_EDGE_HOT
    assert _px(game, (top, PANEL_Y + 222)) != style.PANEL_EDGE_HOT
    assert calls == [], "the recovered icon must not animate"


def test_paused_look_warn_icon_and_two_pixel_edge(paused_game, monkeypatch) -> None:
    """Saving paused: warn triangle (no info circle), 2 px DANGER edge, and a pulse."""
    calls = _pin_pulse(monkeypatch, "hi")
    game = paused_game
    game._draw()
    cx, cy = ICON
    top = config.SCREEN_WIDTH // 2
    assert _px(game, (cx, cy - 15)) == style.DANGER, "triangle apex"
    assert _px(game, (cx, cy + 8)) == style.DANGER, "warn dot"
    assert _px(game, (cx - 14, cy)) != style.DANGER, "no info circle"
    assert _px(game, (top, PANEL_Y)) == style.DANGER and _px(game, (top, PANEL_Y + 1)) == style.DANGER
    assert _px(game, (top, PANEL_Y + 2)) != style.DANGER
    assert calls and set(calls) == {(3.0, 0.75, 1.0)}


def test_notice_drawn_only_over_the_main_menu(notice_game, monkeypatch) -> None:
    """With the notice pending, other states never draw it."""
    calls = _recording(notice_game, monkeypatch)
    notice_game.state = GameState.OPTIONS
    notice_game._draw()
    notice_game.state = GameState.HELP
    notice_game._draw()
    assert calls == []


def test_notice_does_not_return_after_options_or_help(notice_game, monkeypatch) -> None:
    """Dismiss, visit Options and Help and come back (ESC, SPACE, or Options' Back row): the notice stays gone."""
    game = notice_game
    _key(game, pygame.K_ESCAPE)
    assert game.save_notice is None
    calls = _recording(game, monkeypatch)
    # (menu row, screen reached, keys that leave it)
    trips = [
        (3, GameState.OPTIONS, [pygame.K_ESCAPE]),
        (3, GameState.OPTIONS, [pygame.K_UP, pygame.K_SPACE]),  # UP wraps to the "Back" row, SPACE confirms it
        (4, GameState.HELP, [pygame.K_SPACE]),
        (4, GameState.HELP, [pygame.K_ESCAPE]),
    ]
    for row, screen, leave in trips:
        game.menu_selected = row
        _key(game, pygame.K_SPACE)
        assert game.state == screen
        game._draw()
        for key in leave:
            _key(game, key)
        assert game.state == GameState.MAIN_MENU, (screen, leave)
        for _ in range(3):
            game._draw()
        assert game.save_notice is None, (screen, leave)
    assert calls == []
    game.menu_selected = 0
    _key(game, pygame.K_DOWN)
    assert game.menu_selected == 1


# --- BUG-030: pulse contrast ----------------------------------------------------------------

def test_pulse_low_point_is_184_74_86_and_readable(paused_game, monkeypatch) -> None:
    """At the pulse's dimmest the icon is (184,74,86), at least 3.0:1 against the panel; brightest is DANGER."""
    calls = _pin_pulse(monkeypatch, "lo")
    game = paused_game
    game._draw()
    dot = (ICON[0], ICON[1] + 8)
    low = _px(game, dot)
    assert calls and set(calls) == {(3.0, 0.75, 1.0)}
    assert low == (184, 74, 86)
    assert low == style.lerp_color(style.PANEL, style.DANGER, 0.75)
    assert _contrast(low, style.PANEL) >= 3.0
    _pin_pulse(monkeypatch, "hi")
    game._draw()
    high = _px(game, dot)
    assert high == style.DANGER
    assert _contrast(high, style.PANEL) >= _contrast(low, style.PANEL)


def test_contrast_helper_matches_known_values() -> None:
    """The WCAG helper itself: black on white is 21:1, same color is 1:1."""
    assert _contrast((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert _contrast(style.PANEL, style.PANEL) == pytest.approx(1.0)


# --- BUG-029: saving paused protects the damaged save ----------------------------------------

def _quit_through_run(game, monkeypatch) -> None:
    """Run the real main loop for one frame with a QUIT event queued (so it saves on the way out)."""
    monkeypatch.setattr(pygame, "quit", lambda: None)  # keep pygame alive for later tests
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    game.run()


def test_paused_save_game_leaves_damaged_save_untouched(paused_game, isolated_save) -> None:
    """While no backup exists, _save_game must not overwrite the damaged file."""
    before = isolated_save.read_bytes()
    paused_game._save_game()
    assert isolated_save.read_bytes() == before
    assert paused_game._save_blocked is True


def test_quit_while_still_paused_leaves_damaged_save_untouched(paused_game, isolated_save, monkeypatch) -> None:
    """Quitting through the real loop with backups still impossible keeps the damaged file as it was."""
    before = isolated_save.read_bytes()
    _quit_through_run(paused_game, monkeypatch)
    assert isolated_save.read_bytes() == before
    assert paused_game._save_blocked is True


def test_quit_retries_the_backup_then_saves(paused_game, isolated_save, monkeypatch) -> None:
    """If a backup slot frees up, quitting backs up the damaged save first, then writes the new one."""
    damaged = isolated_save.read_bytes()
    for path in savefile.backup_paths(str(isolated_save)):
        os.remove(path)
    _quit_through_run(paused_game, monkeypatch)
    backups = [open(p, "rb").read() for p in savefile.backup_paths(str(isolated_save)) if os.path.exists(p)]
    assert damaged in backups, "the damaged bytes must be preserved in a backup"
    assert paused_game._save_blocked is False
    assert savefile.read_save(str(isolated_save)) is not None, "the new save must be valid"
    assert isolated_save.read_bytes() != damaged
