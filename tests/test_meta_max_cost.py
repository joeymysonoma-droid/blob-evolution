"""BUG-031 / TASK-019: a maxed permanent upgrade shows "MAX" (never "9999") and can't be bought.

Checks run on the real Game's Upgrades screen (Game._draw_meta_screen) by recording the font
renders and the selected-row panel rect, plus the real key/click handlers for the buy path.
The label is asserted as the literal "MAX" (not lore.SKILL_MAX_LABEL) so changing the wording fails a test.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.systems.permanent import PERMANENT_UPGRADES, PermanentProgress
from blob_evolution.ui import style
from blob_evolution.utils.enums import GameState

IDS = [u["id"] for u in PERMANENT_UPGRADES]
BY_ID = {u["id"]: u for u in PERMANENT_UPGRADES}
LEVEL_CASES = ["zero", "max_minus_1", "max"]
LONGEST_NAME_ID = max(IDS, key=lambda i: len(BY_ID[i]["name"]))
EXPECTED_SAVE_KEYS = [
    "endings_seen", "equipped_skin", "shards", "total_shards_earned",
    "unlocked_artifacts", "unlocked_skins", "unlocked_wardens", "upgrade_levels",
]


def _level(upgrade_id: str, case: str) -> int:
    """Level for a case name: 0, max-1 or max for this upgrade."""
    return {"zero": 0, "max_minus_1": BY_ID[upgrade_id]["max_level"] - 1, "max": BY_ID[upgrade_id]["max_level"]}[case]


def _price(upgrade_id: str, level: int) -> int:
    """Expected shard price of the next level, from the upgrade data (cost_base * cost_scale ** level)."""
    u = BY_ID[upgrade_id]
    return int(u["cost_base"] * (u["cost_scale"] ** level))


class RecordingFont:
    """Wraps a pygame Font; records each render's text and rendered width."""

    def __init__(self, font: pygame.font.Font, log: List[Tuple[str, int]]) -> None:
        self._font = font
        self._log = log

    def render(self, text, *args, **kwargs) -> pygame.Surface:
        """Render with the wrapped font and record (text, width)."""
        surface = self._font.render(text, *args, **kwargs)
        self._log.append((str(text), surface.get_width()))
        return surface

    def __getattr__(self, name: str):
        """Delegate everything else to the wrapped font."""
        return getattr(self._font, name)


@pytest.fixture
def meta_game(make_game, monkeypatch):
    """A real Game on the Upgrades tab; fonts and draw_panel are recorded (log, panels)."""
    pygame.init()
    game = make_game()
    game.state, game.meta_tab, game.meta_selected = GameState.META_SHOP, 0, 0
    log: List[Tuple[str, int]] = []
    panels: List[Tuple[pygame.Rect, tuple]] = []
    real_sysfont = pygame.font.SysFont
    monkeypatch.setattr(pygame.font, "SysFont", lambda *a, **k: RecordingFont(real_sysfont(*a, **k), log))
    real_panel = style.draw_panel

    def draw_panel(surface, rect, *args, **kwargs):
        """Record every panel rect with its edge colour, then draw it."""
        panels.append((pygame.Rect(rect), kwargs.get("edge", style.PANEL_EDGE)))
        return real_panel(surface, rect, *args, **kwargs)

    monkeypatch.setattr(style, "draw_panel", draw_panel)
    game.log, game.panels = log, panels
    return game


def _draw(game) -> None:
    """Redraw the Upgrades screen, clearing the previous records first."""
    game.log.clear()
    game.panels.clear()
    game._draw()


def _row_text(game, upgrade_id: str) -> Tuple[str, int]:
    """(text, width) of the rendered line for this upgrade."""
    prefix = f"{BY_ID[upgrade_id]['name']}  Lv."
    found = [(t, w) for t, w in game.log if t.startswith(prefix)]
    assert len(found) == 1, f"{upgrade_id}: expected one rendered row, got {found}"
    return found[0]


def _selected_row_rect(game) -> pygame.Rect:
    """Rect of the highlighted (selected) upgrade row, as the real draw code passed it to draw_panel."""
    rows = [r for r, edge in game.panels if edge == style.SELECT and r.height == 32]
    assert len(rows) == 1, rows
    return rows[0]


@pytest.mark.parametrize("case", LEVEL_CASES)
@pytest.mark.parametrize("upgrade_id", IDS)
def test_upgrades_screen_text_for_every_upgrade(meta_game, upgrade_id: str, case: str) -> None:
    """Row text is "MAX" at max, else the unchanged shard price; never 9999; fits inside its row rect."""
    game = meta_game
    level = _level(upgrade_id, case)
    game.permanent.upgrade_levels[upgrade_id] = level
    game.meta_selected = IDS.index(upgrade_id)
    _draw(game)
    text, width = _row_text(game, upgrade_id)
    u = BY_ID[upgrade_id]
    tail = "MAX" if case == "max" else f"{_price(upgrade_id, level)} shards"
    assert text == f"{u['name']}  Lv.{level}/{u['max_level']}  —  {tail}"
    assert not [t for t, _ in game.log if "9999" in t]
    row = _selected_row_rect(game)
    assert 14 + width <= row.width, f"{upgrade_id}: text {width}px + 14 inset exceeds row {row.width}px"


def test_longest_name_maxed_row_fits_and_is_not_wider_than_priced_row(meta_game) -> None:
    """At the longest upgrade name, the MAX row fits its rect and is narrower than the same row with a price."""
    game = meta_game
    game.meta_selected = IDS.index(LONGEST_NAME_ID)
    game.permanent.upgrade_levels[LONGEST_NAME_ID] = BY_ID[LONGEST_NAME_ID]["max_level"]
    _draw(game)
    max_text, max_width = _row_text(game, LONGEST_NAME_ID)
    assert max_text.endswith("—  MAX")
    assert 14 + max_width <= _selected_row_rect(game).width
    game.permanent.upgrade_levels[LONGEST_NAME_ID] = 0
    _draw(game)
    assert max_width < _row_text(game, LONGEST_NAME_ID)[1]


def test_all_maxed_screen_never_shows_9999_or_a_price(meta_game) -> None:
    """With every upgrade maxed, each visible row ends in MAX and nothing mentions 9999 or a shard price."""
    game = meta_game
    for uid in IDS:
        game.permanent.upgrade_levels[uid] = BY_ID[uid]["max_level"]
    for i in (0, len(IDS) // 2, len(IDS) - 1):  # scroll top, middle, bottom
        game.meta_selected = i
        _draw(game)
        rows = [t for t, _ in game.log if "  Lv." in t]
        assert rows and all(t.endswith("—  MAX") for t in rows), rows
        assert not [t for t, _ in game.log if "9999" in t or (t.endswith(" shards") and "—" in t)]


def test_permanent_progress_contract() -> None:
    """get_upgrade_cost is None at max / unknown, the price below max; nothing can be bought at max."""
    perm = PermanentProgress()
    perm.shards = 10**6
    for uid in IDS:
        top = BY_ID[uid]["max_level"]
        perm.upgrade_levels[uid] = top - 1
        assert perm.get_upgrade_cost(uid) == _price(uid, top - 1)
        assert perm.can_upgrade(uid) and perm.purchase_upgrade(uid)
        assert perm.upgrade_levels[uid] == top
        assert perm.get_upgrade_cost(uid) is None
        before = perm.shards
        assert not perm.can_upgrade(uid) and not perm.purchase_upgrade(uid)
        assert perm.shards == before and perm.upgrade_levels[uid] == top
        assert perm.get_purchase_failure_reason(uid) == "Already at max level!"
    assert perm.get_upgrade_cost("nope") is None
    assert not perm.can_upgrade("nope") and not perm.purchase_upgrade("nope")


def test_known_price_unchanged() -> None:
    """Eternal Fury at Lv.4 still costs 151 shards (the figure on the old Upgrades screen)."""
    perm = PermanentProgress()
    perm.upgrade_levels["perm_damage"] = 4
    assert perm.get_upgrade_cost("perm_damage") == 151


def test_save_format_unchanged() -> None:
    """to_dict keeps exactly the same keys, and upgrade_levels holds plain level ints."""
    data = PermanentProgress().to_dict()
    assert sorted(data) == EXPECTED_SAVE_KEYS
    assert data["upgrade_levels"] == {uid: 0 for uid in IDS}


def _press(game, key: int) -> None:
    """Deliver one KEYDOWN through the game's real event handler."""
    game._handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


@pytest.mark.parametrize("key", [pygame.K_SPACE, pygame.K_RETURN])
@pytest.mark.parametrize("upgrade_id", IDS)
def test_buying_at_max_changes_nothing(meta_game, upgrade_id: str, key: int) -> None:
    """SPACE / RETURN on a maxed upgrade with plenty of shards leaves shards and level unchanged."""
    game = meta_game
    top = BY_ID[upgrade_id]["max_level"]
    game.permanent.upgrade_levels[upgrade_id] = top
    game.permanent.shards = 1_000_000
    game.meta_selected = IDS.index(upgrade_id)
    _press(game, key)
    assert game.permanent.shards == 1_000_000
    assert game.permanent.upgrade_levels[upgrade_id] == top
    assert game.hud.notification == "Already at max level!"


@pytest.mark.parametrize("upgrade_id", IDS)
def test_buying_at_max_minus_one_still_works(meta_game, upgrade_id: str) -> None:
    """SPACE on an upgrade at max-1 buys the last level for the unchanged price."""
    game = meta_game
    top = BY_ID[upgrade_id]["max_level"]
    price = _price(upgrade_id, top - 1)
    game.permanent.upgrade_levels[upgrade_id] = top - 1
    game.permanent.shards = price + 7
    game.meta_selected = IDS.index(upgrade_id)
    _press(game, pygame.K_SPACE)
    assert game.permanent.upgrade_levels[upgrade_id] == top
    assert game.permanent.shards == 7


def test_clicking_a_maxed_row_changes_nothing(meta_game) -> None:
    """The Upgrades screen has no click-to-buy: a click on a maxed row leaves shards and level alone."""
    game = meta_game
    game.permanent.upgrade_levels["perm_damage"] = BY_ID["perm_damage"]["max_level"]
    game.permanent.shards = 1_000_000
    _draw(game)
    row = _selected_row_rect(game)
    game._handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=row.center, button=1))
    assert game.state == GameState.META_SHOP
    assert game.permanent.shards == 1_000_000
    assert game.permanent.upgrade_levels["perm_damage"] == BY_ID["perm_damage"]["max_level"]
