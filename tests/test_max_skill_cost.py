"""BUG-016 / TASK-018: a max-level skill shows "MAX" (never "999 SP"), isn't highlighted, and can't be bought.

Rendered text is captured from the real HUD / Game draw code by wrapping the HUD's fonts,
so the checks cover what the player actually sees, not just SkillManager.
The label is asserted as the literal "MAX" (not lore.SKILL_MAX_LABEL) so changing the wording fails a test.
"""

from __future__ import annotations

from typing import List

import pygame
import pytest

from blob_evolution import config
from blob_evolution.entities.player import Player
from blob_evolution.systems.hazards import HazardManager
from blob_evolution.systems.skills import SKILL_DEFINITIONS, SKILL_ORDER
from blob_evolution.ui import style
from blob_evolution.ui.hud import HUD, skills_overlay_layout
from blob_evolution.utils.enums import GameState, NodeType
from blob_evolution.utils.vector2 import Vector2

MAX = config.MAX_SKILL_LEVEL
LEVELS = [0, MAX - 1, MAX]


@pytest.fixture(autouse=True)
def _pygame() -> None:
    """HUD fonts need pygame initialised (SDL dummy drivers come from conftest)."""
    pygame.init()


class RecordingFont:
    """Wraps a pygame Font and records the text of every render call."""

    def __init__(self, font: pygame.font.Font, log: List[str]) -> None:
        self._font = font
        self._log = log

    def render(self, text, *args, **kwargs) -> pygame.Surface:
        """Record text, then render with the wrapped font."""
        self._log.append(str(text))
        return self._font.render(text, *args, **kwargs)

    def __getattr__(self, name: str):
        """Delegate everything else (size, get_height, ...) to the wrapped font."""
        return getattr(self._font, name)


def _record_fonts(hud: HUD) -> List[str]:
    """Swap the HUD's fonts for recording wrappers; return the shared text log."""
    log: List[str] = []
    for attr in ("font", "font_small", "font_large"):
        setattr(hud, attr, RecordingFont(getattr(hud, attr), log))
    return log


def _player(level: int, sp: int = 50) -> Player:
    """Player with every skill at `level` and `sp` skill points."""
    player = Player(Vector2(0, 0))
    for key in SKILL_ORDER:
        player.skills.levels[key] = level
    player.skill_points = sp
    return player


def _expected_cost_label(key: str, level: int) -> str:
    """What the overlay's cost slot should say: MAX at max level, else base_cost + level SP."""
    return "MAX" if level >= MAX else f"{SKILL_DEFINITIONS[key]['base_cost'] + level} SP"


def _overlay_cost_labels(texts: List[str]) -> dict:
    """Map skill key -> cost text, using the overlay's per-row render order (name, description, cost)."""
    labels = {}
    for i, key in enumerate(SKILL_ORDER):
        name_at = next(j for j, t in enumerate(texts) if t.startswith(f"[{i + 1}]  {SKILL_DEFINITIONS[key]['name']} "))
        labels[key] = texts[name_at + 2]
    return labels


@pytest.mark.parametrize("level", LEVELS)
def test_overlay_shows_max_or_unchanged_cost(level: int) -> None:
    """TAB overlay: MAX for max-level rows, base_cost + level SP otherwise, never 999."""
    hud = HUD()
    texts = _record_fonts(hud)
    hud.draw_skills_overlay(pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT)), _player(level))
    assert _overlay_cost_labels(texts) == {k: _expected_cost_label(k, level) for k in SKILL_ORDER}
    assert not [t for t in texts if "999" in t]


def test_overlay_mixed_levels_per_row() -> None:
    """Rows are labelled independently: one maxed row doesn't change its neighbours."""
    player = _player(0)
    player.skills.levels.update(speed=MAX, size=MAX - 1)
    hud = HUD()
    texts = _record_fonts(hud)
    hud.draw_skills_overlay(pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT)), player)
    labels = _overlay_cost_labels(texts)
    assert labels["speed"] == "MAX"
    assert labels["size"] == f"{SKILL_DEFINITIONS['size']['base_cost'] + MAX - 1} SP"
    assert labels["damage"] == f"{SKILL_DEFINITIONS['damage']['base_cost']} SP"


@pytest.mark.parametrize("level", LEVELS)
def test_hud_never_shows_a_skill_cost(level: int) -> None:
    """In-game HUD: shows the SP total only; no per-skill cost, no 999, no MAX."""
    hud = HUD()
    texts = _record_fonts(hud)
    player = _player(level, sp=37)
    hud.draw(
        pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT)), player, [], [], [],
        HazardManager(), Vector2(0, 0), 60.0, "Test Map", 0,
    )
    assert "SP" in texts and "37" in texts
    assert not [t for t in texts if "999" in t or t == "MAX" or t.endswith(" SP")]


def test_skill_manager_max_contract() -> None:
    """At max: no cost (None), can't upgrade with any SP, upgrade() refuses and keeps the level."""
    skills = _player(MAX).skills
    for key in SKILL_ORDER:
        assert skills.is_maxed(key)
        assert skills.get_upgrade_cost(key) is None
        assert not skills.can_upgrade(key, 10_000)
        assert skills.upgrade(key) == -1
        assert skills.get_level(key) == MAX
    assert skills.upgrade("not_a_skill") == -1 and not skills.can_upgrade("not_a_skill", 10_000)


def test_maxed_row_is_not_highlighted_but_affordable_rows_are(monkeypatch) -> None:
    """BUG-033: only an upgradeable row gets the hot edge (draw_panel) and accent name colour; a maxed row doesn't."""
    player = _player(0, sp=50)
    player.skills.levels.update(speed=MAX, size=MAX - 1)  # speed maxed; size (10 SP) and damage (1 SP) affordable
    hud = HUD()
    edges = {}
    real_panel = style.draw_panel

    def draw_panel(surface, rect, *args, **kwargs):
        """Record the edge colour passed for every panel, then draw it."""
        edges[tuple(rect)] = kwargs.get("edge", style.PANEL_EDGE)
        return real_panel(surface, rect, *args, **kwargs)

    monkeypatch.setattr(style, "draw_panel", draw_panel)
    name_colors = {}

    class ColorFont(RecordingFont):
        """Records the colour each row-name text is rendered in."""

        def render(self, text, antialias, color, *args, **kwargs):
            """Record (text -> colour) for the "[n]  Name ..." row titles."""
            name_colors[str(text)] = tuple(color)
            return super().render(text, antialias, color, *args, **kwargs)

    hud.font = ColorFont(hud.font, [])
    hud.draw_skills_overlay(pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT)), player)

    _, rows = skills_overlay_layout(len(SKILL_ORDER))
    row_edge = {key: edges[tuple(rows[i])] for i, key in enumerate(SKILL_ORDER)}
    row_name_color = {
        key: next(c for t, c in name_colors.items() if t.startswith(f"[{i + 1}]  "))
        for i, key in enumerate(SKILL_ORDER)
    }
    for key in ("size", "damage"):  # affordable, not maxed: the check is not vacuous
        assert row_edge[key] == style.PANEL_EDGE_HOT, f"{key} should use the upgradeable edge"
        assert row_name_color[key] == style.ACCENT, f"{key} should use the upgradeable name colour"
    assert row_edge["speed"] == style.PANEL_EDGE, "maxed row must not use the upgradeable edge"
    assert row_name_color["speed"] == style.TEXT, "maxed row must not use the upgradeable name colour"
    assert row_edge["speed"] != row_edge["size"] and row_name_color["speed"] != row_name_color["size"]


@pytest.mark.parametrize("level", [0, MAX - 1])
def test_skill_manager_costs_below_max_unchanged(level: int) -> None:
    """Below max the cost is still base_cost + level."""
    skills = _player(level).skills
    for key in SKILL_ORDER:
        assert not skills.is_maxed(key)
        assert skills.get_upgrade_cost(key) == SKILL_DEFINITIONS[key]["base_cost"] + level


@pytest.fixture
def playing_game(make_game):
    """A real Game inside a fight (state PLAYING) after the opening story."""
    game = make_game()
    game._start_new_run()
    game.story = None
    game.state = GameState.OVERWORLD
    fight = next(n for n in game.overworld.get_available_nodes() if n.node_type == NodeType.FIGHT)
    game._enter_node(fight.id)
    assert game.state == GameState.PLAYING
    return game


def _press(game, key: int) -> None:
    """Deliver one KEYDOWN through the game's real event handler."""
    game._handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


@pytest.mark.parametrize("state", [GameState.PLAYING, GameState.SKILLS])
def test_buying_at_max_changes_nothing(playing_game, state) -> None:
    """Key 1 on a max-level Speed (in play or in the TAB overlay) leaves SP and level unchanged."""
    game = playing_game
    game.player.skills.levels["speed"] = MAX
    game.player.skill_points = 20
    game.state = state
    _press(game, pygame.K_1)
    assert game.player.skills.levels["speed"] == MAX
    assert game.player.skill_points == 20


@pytest.mark.parametrize("state", [GameState.PLAYING, GameState.SKILLS])
def test_buying_at_max_minus_one_still_works(playing_game, state) -> None:
    """Key 1 on Speed at max-1 buys the last level for base_cost + (max-1) SP."""
    game = playing_game
    game.player.skills.levels["speed"] = MAX - 1
    game.player.skill_points = 20
    game.state = state
    _press(game, pygame.K_1)
    assert game.player.skills.levels["speed"] == MAX
    assert game.player.skill_points == 20 - (SKILL_DEFINITIONS["speed"]["base_cost"] + MAX - 1)


def test_real_game_tab_overlay_shows_max(playing_game) -> None:
    """Game._draw in the SKILLS state renders MAX for the maxed row and a cost for the others."""
    game = playing_game
    game.player.skills.levels.update(speed=MAX, size=MAX - 1)
    texts = _record_fonts(game.hud)
    _press(game, pygame.K_TAB)
    assert game.state == GameState.SKILLS
    game._draw()
    labels = _overlay_cost_labels(texts)
    assert labels["speed"] == "MAX"
    assert labels["size"] == f"{SKILL_DEFINITIONS['size']['base_cost'] + MAX - 1} SP"
    assert labels["health"] == f"{SKILL_DEFINITIONS['health']['base_cost']} SP"
    assert not [t for t in texts if "999" in t]
