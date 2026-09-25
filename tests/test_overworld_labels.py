"""TASK-012: overworld label plates stay clear of every node ring, on screen and below the header."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from typing import Dict, List, Tuple  # noqa: E402

import pygame  # noqa: E402
import pytest  # noqa: E402

from blob_evolution import config  # noqa: E402
from blob_evolution.systems.overworld import MAX_ROUNDS, OverworldMap, OverworldNode  # noqa: E402
from blob_evolution.ui import overworld_map, style  # noqa: E402
from blob_evolution.utils.enums import NodeType  # noqa: E402

HEADER_BOTTOM = config.OVERWORLD_HEADER_RECT[1] + config.OVERWORLD_HEADER_RECT[3]
RING_REACH = 11  # selected ring max beyond the node radius (5 + 3 pulse + 3)
TIGHT_SEEDS = [s for s in range(400) if OverworldMap(0, s).encounter_rows == MAX_ROUNDS][:60]


@pytest.fixture(scope="module")
def renderer() -> overworld_map.OverworldRenderer:
    """A real renderer (real font_small) on a headless display."""
    pygame.init()
    pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    return overworld_map.OverworldRenderer()


def _node_radius(node: OverworldNode) -> int:
    """Node radius as drawn by OverworldRenderer._draw_node."""
    return 22 if node.node_type in (NodeType.BOSS, NodeType.MINIBOSS) else 16


def _plates(renderer: overworld_map.OverworldRenderer, ow: OverworldMap, monkeypatch) -> Dict[str, pygame.Rect]:
    """Draw every node with its label forced on and capture each label plate rect."""
    for node in ow.nodes.values():
        node.completed = False
        node.available = True
    plates: Dict[str, pygame.Rect] = {}
    current: List[str] = []
    real_draw_node = renderer._draw_node

    def capture_panel(surface, rect, *args, **kwargs) -> None:
        if current:
            assert current[-1] not in plates, "more than one panel drawn for a node"
            plates[current[-1]] = pygame.Rect(rect)

    def tracked_draw_node(surface, node, *args, **kwargs) -> None:
        current.append(node.id)
        try:
            real_draw_node(surface, node, *args, **kwargs)
        finally:
            current.pop()

    monkeypatch.setattr(style, "draw_panel", capture_panel)
    monkeypatch.setattr(renderer, "_draw_node", tracked_draw_node)
    surface = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    renderer.draw(surface, ow, 0, 0, selected_node_id=None)
    monkeypatch.undo()
    return plates


def _gap(rect: pygame.Rect, center: Tuple[int, int], r: int) -> float:
    """Distance from the circle edge to the nearest pixel of rect (negative = overlap)."""
    cx, cy = center
    nx = min(max(cx, rect.left), rect.right - 1)
    ny = min(max(cy, rect.top), rect.bottom - 1)
    return ((nx - cx) ** 2 + (ny - cy) ** 2) ** 0.5 - r


def test_tight_seeds_exist() -> None:
    """There are enough 11-encounter seeds for the layout tests to be meaningful."""
    assert len(TIGHT_SEEDS) >= 30


@pytest.mark.parametrize("act_index", [0, 7])
def test_label_plates_clear_rings_screen_and_header(renderer, monkeypatch, act_index: int) -> None:
    """Every plate sits right of its node, clear of all radius+11 rings, on screen, below y=96."""
    for seed in TIGHT_SEEDS:
        ow = OverworldMap(act_index=act_index, seed=seed)
        plates = _plates(renderer, ow, monkeypatch)
        assert set(plates) == set(ow.nodes), (seed, "every node should get exactly one plate")
        for nid, plate in plates.items():
            owner = ow.nodes[nid]
            ox = int(owner.screen_x)
            assert plate.left > ox + _node_radius(owner) + RING_REACH, (seed, nid, plate)
            assert plate.left >= 0 and plate.right <= config.SCREEN_WIDTH, (seed, nid, plate)
            assert plate.bottom <= config.SCREEN_HEIGHT, (seed, nid, plate)
            assert plate.top >= HEADER_BOTTOM, (seed, nid, plate)
            for other in ow.nodes.values():
                center = (int(other.screen_x), int(other.screen_y))
                gap = _gap(plate, center, _node_radius(other) + RING_REACH)
                assert gap > 0, (seed, nid, other.id, plate, gap)
