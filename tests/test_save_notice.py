"""TASK-009c: save-recovery notice over the main menu (recovered / saving_paused)."""

from __future__ import annotations

import pygame
import pytest

from blob_evolution import config
from blob_evolution.data.lore import SAVE_NOTICES
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


def test_invalid_field_is_recovered_too(make_game, isolated_save, fixture_data) -> None:
    """A readable save with a wrong-typed field is backed up and also shows recovered."""
    import json

    fixture_data["permanent"]["shards"] = "72"
    isolated_save.write_text(json.dumps(fixture_data), encoding="utf-8")
    assert make_game().save_notice == "recovered"


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
