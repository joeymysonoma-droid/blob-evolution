"""BUG-009 / TASK-011b: the elite/miniboss star stays clear of node rings, labels and the screen edge.

The star center comes from ui.overworld_map.star_center, the same helper _draw_node uses.
The node radius (22 for Boss/Mini Boss, else 16) and the label position (centered,
y + radius + 5) are mirrored from _draw_node here.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.systems.overworld import OverworldMap, OverworldNode
from blob_evolution.ui.overworld_map import star_center
from blob_evolution.utils.enums import NodeType

STAR_HALF = 8  # backing star outer radius; box is center +- 8
RING_CLEARANCE = 11  # selected ring outer edge: radius + 5 + 3 pulse + 3
SEEDS = range(4000)
ACTS = (0, 1, 4)  # act_index doesn't change layout today; cheap guard if it ever does


def _radius(node: OverworldNode) -> int:
    """Node radius, mirrored from OverworldRenderer._draw_node."""
    return 22 if node.node_type in (NodeType.BOSS, NodeType.MINIBOSS) else 16


def _star_box(node: OverworldNode) -> pygame.Rect:
    """Star bounding box (center +- STAR_HALF) computed like _draw_node does."""
    sx, sy = star_center(int(node.screen_x), int(node.screen_y), _radius(node))
    return pygame.Rect(sx - STAR_HALF, sy - STAR_HALF, 2 * STAR_HALF, 2 * STAR_HALF)


def _rect_circle_gap(rect: pygame.Rect, cx: float, cy: float, r: float) -> float:
    """Distance from the circle's edge to the nearest rect point (negative = overlap)."""
    nx = min(max(cx, rect.left), rect.right)
    ny = min(max(cy, rect.top), rect.bottom)
    return math.hypot(cx - nx, cy - ny) - r


def _eleven_row_maps() -> List[OverworldMap]:
    """Every seed in SEEDS that generates an 11-encounter-row map, for each act in ACTS."""
    maps = []
    for act in ACTS:
        for seed in SEEDS:
            ow = OverworldMap(act_index=act, seed=seed)
            if ow.encounter_rows == 11:
                maps.append(ow)
    return maps


@pytest.fixture(scope="module")
def eleven_row_maps() -> List[OverworldMap]:
    """Module-cached list of 11-row maps (generation is the slow part)."""
    maps = _eleven_row_maps()
    assert maps, "no 11-row maps in the seed range"
    return maps


def test_star_clear_of_all_node_rings_and_on_screen(eleven_row_maps):
    """Each star box is outside every node's radius+11 circle and fully on screen."""
    screen = pygame.Rect(0, 0, config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    failures: List[Tuple[int, int, str, str, float]] = []
    stars = 0
    for ow in eleven_row_maps:
        for node in ow.nodes.values():
            if not node.is_elite_marked:
                continue
            stars += 1
            box = _star_box(node)
            if not screen.contains(box):
                failures.append((ow.act_index, ow.seed, node.id, "off-screen", 0.0))
            for other in ow.nodes.values():
                gap = _rect_circle_gap(
                    box, int(other.screen_x), int(other.screen_y), _radius(other) + RING_CLEARANCE,
                )
                if gap <= 0:
                    failures.append((ow.act_index, ow.seed, node.id, other.id, round(gap, 2)))
    assert stars, "no Elite/Mini Boss nodes generated"
    assert not failures, f"{len(failures)} star clearance failures (act, seed, star node, hit, gap px): {failures[:20]}"


def test_star_clear_of_node_labels(eleven_row_maps):
    """Each star box misses every node's name label (drawn centered at y + radius + 5)."""
    pygame.font.init()
    font = pygame.font.SysFont("segoeui", 12)  # same font as OverworldRenderer.font_small
    sizes = {t: font.size(OverworldNode("x", t, 0, 0).label) for t in NodeType}
    failures: List[Tuple[int, int, str, str]] = []
    for ow in eleven_row_maps:
        for node in ow.nodes.values():
            if not node.is_elite_marked:
                continue
            box = _star_box(node)
            for other in ow.nodes.values():
                w, h = sizes[other.node_type]
                x, y = int(other.screen_x), int(other.screen_y)
                label = pygame.Rect(x - w // 2, y + _radius(other) + 5, w, h)
                if box.colliderect(label):
                    failures.append((ow.act_index, ow.seed, node.id, other.id))
    assert not failures, f"{len(failures)} star/label overlaps (act, seed, star node, label node): {failures[:20]}"
