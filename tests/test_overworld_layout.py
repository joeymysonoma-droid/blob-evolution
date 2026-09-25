"""BUG-008: overworld nodes (boss ring included) stay clear of the header panel.

The render tests run the real OverworldRenderer.draw headlessly and record its calls
(_draw_node, pygame.draw.circle, style.draw_panel) with the pulse held at a given phase.
"""

from __future__ import annotations

import sys
from typing import Callable, List, Optional, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.systems.overworld import OverworldMap
from blob_evolution.ui import style
from blob_evolution.ui.overworld_map import OverworldRenderer
from blob_evolution.utils.enums import NodeType

HEADER_BOTTOM = config.OVERWORLD_HEADER_RECT[1] + config.OVERWORLD_HEADER_RECT[3]
Event = Tuple[str, Optional[str], pygame.Rect, tuple]  # kind, node id (or caller), rect, color


def test_header_bottom_is_96() -> None:
    """The header rect in config still ends at y=96, the value BUG-008 was filed against."""
    assert HEADER_BOTTOM == 96


def test_restored_map_keeps_layout() -> None:
    """from_dict re-runs the layout, so a loaded map is also clear of the header."""
    for seed in range(50):
        ow = OverworldMap.from_dict(OverworldMap(act_index=7, seed=seed).to_dict())
        top = min(node.screen_y for node in ow.nodes.values())
        assert top - config.OVERWORLD_NODE_TOP_REACH >= HEADER_BOTTOM, (seed, top)


@pytest.fixture
def record(monkeypatch) -> Callable[[OverworldMap, str, float], List[Event]]:
    """Return render(ow, selected_id, phase) -> ordered draw events from the real draw call."""
    pygame.init()
    events: List[Event] = []
    current: List[Optional[str]] = [None]
    phase = [1.0]
    orig_node = OverworldRenderer._draw_node
    orig_circle = pygame.draw.circle
    orig_panel = style.draw_panel

    def draw_node(self, surface, node, *args, **kwargs):
        """Tag every draw call made while drawing this node."""
        current[0] = node.id
        events.append(("node", node.id, pygame.Rect(0, 0, 0, 0), ()))
        try:
            return orig_node(self, surface, node, *args, **kwargs)
        finally:
            current[0] = None

    def circle(surface, color, center, radius, *args, **kwargs):
        """Record circles drawn on the screen surface."""
        rect = orig_circle(surface, color, center, radius, *args, **kwargs)
        if surface.get_size() == (config.SCREEN_WIDTH, config.SCREEN_HEIGHT):
            events.append(("circle", current[0], pygame.Rect(rect), tuple(color)))
        return rect

    def draw_panel(surface, rect, *args, **kwargs):
        """Record panels with the name of the function that asked for them."""
        events.append(("panel", sys._getframe(1).f_code.co_name, pygame.Rect(rect), ()))
        return orig_panel(surface, rect, *args, **kwargs)

    monkeypatch.setattr(OverworldRenderer, "_draw_node", draw_node)
    monkeypatch.setattr(pygame.draw, "circle", circle)
    monkeypatch.setattr(style, "draw_panel", draw_panel)
    monkeypatch.setattr(style, "pulse", lambda speed=2.0, lo=0.0, hi=1.0: lo + (hi - lo) * phase[0])

    def render(ow: OverworldMap, selected_id: str, at_phase: float = 1.0) -> List[Event]:
        """Draw ow with selected_id selected, pulse at at_phase (1.0 = largest ring)."""
        events.clear()
        phase[0] = at_phase
        surface = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        OverworldRenderer().draw(surface, ow, 0, 0, selected_node_id=selected_id)
        return list(events)

    return render


def _boss_selectable(ow: OverworldMap) -> str:
    """Make the boss the only available node (as after clearing the last row); return its id."""
    boss = next(n for n in ow.nodes.values() if n.node_type == NodeType.BOSS)
    last = next(n for n in ow.nodes.values() if boss.id in n.connections)
    for n in ow.nodes.values():
        n.available = False
    last.completed = True
    ow.current_node_id = last.id
    ow._update_availability()
    assert boss.available
    return boss.id


def _first_seed_with_rows(rows: int) -> int:
    """Smallest seed whose map has `rows` encounter rows."""
    return next(s for s in range(1000) if OverworldMap(seed=s).encounter_rows == rows)


def _header(events: List[Event]) -> Tuple[int, pygame.Rect]:
    """Index and rect of the header panel (the only panel draw() itself asks for)."""
    found = [(i, e[2]) for i, e in enumerate(events) if e[0] == "panel" and e[1] == "draw"]
    assert len(found) == 1, found
    return found[0]


@pytest.mark.parametrize("rows", [8, 11])
def test_selected_boss_ring_clears_drawn_header(record, rows: int) -> None:
    """At max pulse the boss's drawn selected rings stay within the layout's reach and below the drawn header."""
    ow = OverworldMap(act_index=0, seed=_first_seed_with_rows(rows))
    boss_id = _boss_selectable(ow)
    events = record(ow, boss_id, 1.0)
    boss = ow.nodes[boss_id]
    rings = [e[2] for e in events if e[0] == "circle" and e[1] == boss_id and e[3] == tuple(style.SELECT)]
    assert len(rings) == 2, "selected boss should draw a double ring"
    ring_top = min(r.top for r in rings)
    reach = int(boss.screen_y) - ring_top
    assert reach <= config.OVERWORLD_NODE_TOP_REACH, (
        f"drawn ring reaches {reach}px above the boss, layout reserves {config.OVERWORLD_NODE_TOP_REACH}"
    )
    _, header = _header(events)
    assert ring_top >= header.bottom, f"ring top {ring_top} is inside the drawn header (bottom {header.bottom})"


@pytest.mark.parametrize("phase", [0.0, 0.34, 0.67, 1.0])
@pytest.mark.parametrize(
    ("seed", "act", "current", "selected"),
    [
        (145, 0, None, "boss"),  # Visual Designer's case: Boss over a Mini Boss, Layer 1
        (25, 7, "n_9_1", "n_10_1"),  # selected Mini Boss with another Mini Boss drawn above it
    ],
)
def test_selected_node_drawn_last_then_header(record, phase, seed, act, current, selected) -> None:
    """At every pulse phase the selected node draws after all other nodes, and the header after it."""
    ow = OverworldMap(act_index=act, seed=seed)
    if selected == "boss":
        selected = _boss_selectable(ow)
    else:
        ow.nodes[current].completed = True
        ow.current_node_id = current
        ow._update_availability()
        assert ow.nodes[selected].available
    events = record(ow, selected, phase)
    node_calls = [i for i, e in enumerate(events) if e[0] == "node"]
    assert len(node_calls) == len(ow.nodes)
    assert events[node_calls[-1]][1] == selected, "another node draws after (over) the selected ring"
    rings = [i for i, e in enumerate(events) if e[0] == "circle" and e[1] == selected and e[3] == tuple(style.SELECT)]
    assert len(rings) == 2, "selected node should draw a double ring"
    others_after = [e for e in events[rings[0]:] if e[0] in ("node", "circle") and e[1] not in (selected, None)]
    assert not others_after, f"drawn over the selected ring: {others_after[:3]}"
    header_i, _ = _header(events)
    assert header_i > node_calls[-1], "header must draw after every node"
