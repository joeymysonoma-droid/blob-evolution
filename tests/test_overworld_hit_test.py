"""BUG-013: overworld clicks go to the node the player sees and can enter.

hit_test rule: when click rects overlap, available nodes win, then the node drawn on top.
Rects come from the real OverworldRenderer.draw.
"""

from __future__ import annotations

from typing import Optional

import pygame
import pytest

from blob_evolution import config
from blob_evolution.systems.overworld import OverworldMap
from blob_evolution.ui.overworld_map import OverworldRenderer
from blob_evolution.utils.enums import GameState, NodeType

SEED25_CLICK = (800, 207)  # bottom of Mini Boss n_11_1's disc, inside Mini Boss n_10_1's rect too


def _at(ow: OverworldMap, current_id: str) -> OverworldMap:
    """Put the player on current_id (completed) with its connections available."""
    ow.nodes[current_id].completed = True
    ow.current_node_id = current_id
    ow._update_availability()
    return ow


def _drawn(ow: OverworldMap, selected_id: Optional[str] = None) -> OverworldRenderer:
    """Draw ow headlessly and return the renderer holding the fresh click rects."""
    pygame.init()
    renderer = OverworldRenderer()
    surface = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    renderer.draw(surface, ow, 0, 0, selected_node_id=selected_id)
    return renderer


def _radius(node) -> int:
    """Visual node radius, mirrored from OverworldRenderer._draw_node."""
    return 22 if node.node_type in (NodeType.BOSS, NodeType.MINIBOSS) else 16


def test_seed25_click_enters_available_upper_node(make_game) -> None:
    """QA repro: after Mini Boss n_10_1, clicking (800,207) enters n_11_1, not the completed node below."""
    game = make_game()
    game._start_new_run()
    game.story = None
    ow = _at(OverworldMap(act_index=7, seed=25), "n_10_1")
    assert ow.encounter_rows == 11 and ow.nodes["n_11_1"].available
    game.overworld, game.state, game.overworld_selected = ow, GameState.OVERWORLD, 0
    game._draw()
    rects = dict(game.overworld_renderer.node_rects)
    assert rects["n_10_1"].collidepoint(SEED25_CLICK) and rects["n_11_1"].collidepoint(SEED25_CLICK)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=SEED25_CLICK, button=1))
    for event in pygame.event.get():
        game._handle_event(event)
    assert ow.current_node_id == "n_11_1"


def test_available_node_wins_even_when_drawn_underneath() -> None:
    """An available node beats an unavailable node drawn on top of it."""
    ow = _at(OverworldMap(act_index=7, seed=25), "n_9_1")
    assert ow.nodes["n_10_1"].available and not ow.nodes["n_11_1"].available
    renderer = _drawn(ow, selected_id=None)
    order = [nid for nid, _ in renderer.node_rects]
    assert order.index("n_11_1") > order.index("n_10_1")  # the unavailable one is on top
    assert renderer.hit_test(SEED25_CLICK) == "n_10_1"


@pytest.mark.parametrize("available", [False, True])
def test_topmost_wins_between_equals(available: bool) -> None:
    """With equal availability the node drawn last wins, and the selected node is drawn last."""
    ow = OverworldMap(act_index=7, seed=25)
    for n in ow.nodes.values():
        n.available = False
    ow.nodes["n_10_1"].available = ow.nodes["n_11_1"].available = available
    assert _drawn(ow).hit_test(SEED25_CLICK) == "n_11_1"  # upper row is drawn later
    if available:
        assert _drawn(ow, selected_id="n_10_1").hit_test(SEED25_CLICK) == "n_10_1"  # selected is drawn last


def test_hit_test_outside_all_rects_is_none() -> None:
    """A click on empty map space hits nothing."""
    assert _drawn(OverworldMap(seed=25)).hit_test((5, 400)) is None


def test_every_available_disc_pixel_hits_its_node() -> None:
    """Over 300 seeds, from every node: each available node's centre, and every pixel of its disc under another rect, hit it."""
    failures = []
    states = 0
    for seed in range(300):
        base = OverworldMap(seed=seed)
        base_renderer = _drawn(base)  # rect geometry doesn't depend on state; order/availability do
        rects = dict(base_renderer.node_rects)
        for current_id, current in base.nodes.items():
            for target_id in current.connections:
                t = base.nodes[target_id]
                x, y, r = int(t.screen_x), int(t.screen_y), _radius(t)
                shadow = [
                    (px, py)
                    for nid, other in rects.items() if nid != t.id and other.colliderect(rects[t.id])
                    for px in range(max(other.left, x - r), min(other.right, x + r + 1))
                    for py in range(max(other.top, y - r), min(other.bottom, y + r + 1))
                    if (px - x) ** 2 + (py - y) ** 2 <= r * r
                ]
                if shadow:  # overlap: redraw in the real state, with the game's default selection
                    states += 1
                    ow = _at(OverworldMap(seed=seed), current_id)
                    first = min(ow.get_available_nodes(), key=lambda n: (n.layer, n.col))
                    renderer = _drawn(ow, selected_id=first.id)
                else:
                    renderer = base_renderer
                bad = [p for p in [(x, y)] + shadow if renderer.hit_test(p) != t.id]
                if bad:
                    failures.append((seed, current_id, t.id, len(bad), bad[0]))
    assert states, "sweep never hit an overlapping case"
    assert not failures, f"{len(failures)} shadowed available nodes (seed, from, node, px, first): {failures[:10]}"
