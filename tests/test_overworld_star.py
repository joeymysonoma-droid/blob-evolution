"""BUG-009 / BUG-025 / TASK-016: the elite/miniboss star, checked against the real overworld render.

Every position here is recorded from a real OverworldRenderer.draw on a headless display:
star centers and sizes from the draw_star calls, label plates from the style.draw_panel calls,
ring reach from the pygame.draw.circle calls around a selected node with the pulse held at max.
No node radius, star size, ring reach or label offset is copied from _draw_node.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.systems.overworld import MAX_ROUNDS, MIN_ROUNDS, OverworldMap, OverworldNode
from blob_evolution.ui import overworld_map, style
from blob_evolution.utils.enums import NodeType

HEADER_BOTTOM = config.OVERWORLD_HEADER_RECT[1] + config.OVERWORLD_HEADER_RECT[3]
SEEDS_PER_HEIGHT = 8
ACTS = (0, 7)
STAR_CENTER_MARK = (-3, 2)  # offset the star_center spy adds, so a star placed without it is caught


def _seeds_for(rows: int, count: int = SEEDS_PER_HEIGHT) -> List[int]:
    """The first `count` seeds whose map has `rows` encounter rows."""
    seeds = [s for s in range(2000) if OverworldMap(0, s).encounter_rows == rows]
    return seeds[:count]


HEIGHTS = list(range(MIN_ROUNDS, MAX_ROUNDS + 1))
SEEDS_BY_HEIGHT = {rows: _seeds_for(rows) for rows in HEIGHTS}
MAPS = [(act, rows, seed) for act in ACTS for rows in HEIGHTS for seed in SEEDS_BY_HEIGHT[rows]]


@dataclass
class Star:
    """One draw_star call: center, outer and inner radius, color."""

    center: Tuple[float, float]
    outer: float
    inner: float
    color: tuple

    def box(self) -> pygame.Rect:
        """Axis-aligned box around the star's outer points."""
        cx, cy = self.center
        left, top = math.floor(cx - self.outer), math.floor(cy - self.outer)
        right, bottom = math.ceil(cx + self.outer), math.ceil(cy + self.outer)
        return pygame.Rect(left, top, right - left, bottom - top)


@dataclass
class NodeDraw:
    """Everything one _draw_node call put on the main surface."""

    stars: List[Star] = field(default_factory=list)
    plates: List[pygame.Rect] = field(default_factory=list)
    circles: List[Tuple[Tuple[int, int], int]] = field(default_factory=list)
    texts: List[str] = field(default_factory=list)
    star_center_calls: List[Tuple[tuple, Tuple[int, int]]] = field(default_factory=list)


class _FontSpy:
    """Wraps a pygame font and records every string it renders."""

    def __init__(self, font: pygame.font.Font, log: Callable[[str], None]) -> None:
        self._font = font
        self._log = log

    def render(self, text, *args, **kwargs) -> pygame.Surface:
        """Record the text, then render it with the real font."""
        self._log(str(text))
        return self._font.render(text, *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._font, name)


@pytest.fixture(scope="module")
def renderer() -> overworld_map.OverworldRenderer:
    """A real renderer (real fonts) on a headless display."""
    pygame.init()
    pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    return overworld_map.OverworldRenderer()


@pytest.fixture
def render(renderer, monkeypatch) -> Callable[..., Dict[str, NodeDraw]]:
    """Return render(ow, selected_id=None, mark_star_center=False) -> {node id: NodeDraw}."""

    def _render(ow: OverworldMap, selected_id: Optional[str] = None, mark_star_center: bool = False) -> Dict[str, NodeDraw]:
        surface = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        draws: Dict[str, NodeDraw] = {nid: NodeDraw() for nid in ow.nodes}
        current: List[str] = []
        loose_texts: List[str] = []

        def node() -> Optional[NodeDraw]:
            return draws[current[-1]] if current else None

        real_draw_node = renderer._draw_node
        real_star = overworld_map.draw_star
        real_center = overworld_map.star_center
        real_panel = style.draw_panel
        real_circle = pygame.draw.circle

        def draw_node(surf, n, *args, **kwargs) -> None:
            current.append(n.id)
            try:
                real_draw_node(surf, n, *args, **kwargs)
            finally:
                current.pop()

        def draw_star(surf, center, outer, inner, color, *args, **kwargs):
            if surf is surface and node() is not None:
                node().stars.append(Star((float(center[0]), float(center[1])), float(outer), float(inner), tuple(color)))
            return real_star(surf, center, outer, inner, color, *args, **kwargs)

        def star_center(*args, **kwargs):
            sx, sy = real_center(*args, **kwargs)
            if mark_star_center:
                sx, sy = sx + STAR_CENTER_MARK[0], sy + STAR_CENTER_MARK[1]
            if node() is not None:
                node().star_center_calls.append((args, (sx, sy)))
            return sx, sy

        def draw_panel(surf, rect, *args, **kwargs):
            if surf is surface and node() is not None:
                node().plates.append(pygame.Rect(rect))
            return real_panel(surf, rect, *args, **kwargs)

        def circle(surf, color, center, radius, *args, **kwargs):
            if surf is surface and node() is not None:
                node().circles.append(((int(center[0]), int(center[1])), int(radius)))
            return real_circle(surf, color, center, radius, *args, **kwargs)

        def log_text(text: str) -> None:
            (node().texts if node() is not None else loose_texts).append(text)

        with monkeypatch.context() as m:
            m.setattr(renderer, "_draw_node", draw_node)
            m.setattr(overworld_map, "draw_star", draw_star)
            m.setattr(overworld_map, "star_center", star_center)
            m.setattr(style, "draw_panel", draw_panel)
            m.setattr(pygame.draw, "circle", circle)
            m.setattr(style, "pulse", lambda speed, lo=0.0, hi=1.0: hi)  # rings at their widest
            for attr in ("font", "font_small", "font_large"):
                m.setattr(renderer, attr, _FontSpy(getattr(renderer, attr), log_text))
            renderer.draw(surface, ow, 0, 0, selected_node_id=selected_id)
        assert not any("\u2605" in t for t in loose_texts), loose_texts
        return draws

    return _render


def _all_available(ow: OverworldMap) -> OverworldMap:
    """Force every node available and not completed: every star and every label is drawn."""
    for n in ow.nodes.values():
        n.available = True
        n.completed = False
    return ow


def _elite_ids(ow: OverworldMap) -> List[str]:
    """Ids of nodes that carry the star marker."""
    return [nid for nid, n in ow.nodes.items() if n.is_elite_marked]


def _xy(n: OverworldNode) -> Tuple[int, int]:
    """The node's draw position (layout coordinates, as _draw_node truncates them)."""
    return int(n.screen_x), int(n.screen_y)


def _gap(rect: pygame.Rect, center: Tuple[int, int], r: float) -> float:
    """Distance from the circle edge to the nearest pixel of rect (negative = overlap)."""
    cx, cy = center
    nx = min(max(cx, rect.left), rect.right - 1)
    ny = min(max(cy, rect.top), rect.bottom - 1)
    return math.hypot(nx - cx, ny - cy) - r


@pytest.fixture
def ring_reach(render) -> Callable[[OverworldMap, str], int]:
    """Return reach(ow, node_id): outermost circle radius drawn around that node when selected, pulse at max."""
    cache: Dict[Tuple[int, int, str], int] = {}

    def _reach(ow: OverworldMap, nid: str) -> int:
        key = (ow.act_index, ow.seed, nid)
        if key not in cache:
            draws = render(ow, selected_id=nid)
            center = _xy(ow.nodes[nid])
            radii = [r for c, r in draws[nid].circles if c == center]
            assert radii, (key, "no circle drawn at the node center")
            cache[key] = max(radii)
        return cache[key]

    return _reach


def test_every_height_has_seeds() -> None:
    """Each encounter-row count (map height) contributes a full set of seeds."""
    assert HEIGHTS == [8, 9, 10, 11]
    for rows, seeds in SEEDS_BY_HEIGHT.items():
        assert len(seeds) == SEEDS_PER_HEIGHT, (rows, seeds)


def test_elite_nodes_exist_in_the_sample() -> None:
    """The sampled maps actually contain starred nodes at every height."""
    for rows in HEIGHTS:
        stars = sum(len(_elite_ids(OverworldMap(0, s))) for s in SEEDS_BY_HEIGHT[rows])
        assert stars >= SEEDS_PER_HEIGHT, (rows, stars)


@pytest.mark.parametrize("act,rows,seed", MAPS)
def test_star_is_drawn_as_a_shape_only_on_uncompleted_elite_nodes(render, act: int, rows: int, seed: int) -> None:
    """Available and dimmed elite nodes get a backing + front draw_star; completed and plain nodes get none; no ★ glyph."""
    ow = OverworldMap(act_index=act, seed=seed)
    elite = set(_elite_ids(ow))
    states = {}
    for group in (sorted(elite), sorted(set(ow.nodes) - elite)):  # cycle states within each group
        for i, nid in enumerate(group):
            state = ("available", "completed", "dimmed")[i % 3]
            ow.nodes[nid].available, ow.nodes[nid].completed = state == "available", state == "completed"
            states[nid] = state
    draws = render(ow)
    assert len(elite) < 3 or {states[nid] for nid in elite} == {"available", "completed", "dimmed"}
    for nid, d in draws.items():
        assert not any("\u2605" in t for t in d.texts), (seed, nid, d.texts)
        if nid in elite and states[nid] != "completed":
            assert len(d.stars) == 2, (seed, nid, states[nid], d.stars)
            back, front = d.stars
            assert back.center == front.center, (seed, nid)
            assert back.outer > front.outer and back.inner > front.inner, (seed, nid, "backing must frame the star")
            assert back.color == tuple(style.BG_DEEP) and front.color == tuple(style.SELECT), (seed, nid)
        else:
            assert d.stars == [], (seed, nid, states[nid], "star drawn on a completed or unmarked node")


@pytest.mark.parametrize("act,rows,seed", MAPS)
def test_star_is_placed_by_star_center(render, act: int, rows: int, seed: int) -> None:
    """_draw_node asks star_center (with the node's draw x, y) and draws exactly where it answers."""
    ow = _all_available(OverworldMap(act_index=act, seed=seed))
    draws = render(ow, mark_star_center=True)
    for nid in _elite_ids(ow):
        d = draws[nid]
        assert len(d.star_center_calls) == 1, (seed, nid, d.star_center_calls)
        args, answer = d.star_center_calls[0]
        assert tuple(args[:2]) == _xy(ow.nodes[nid]), (seed, nid, args)
        assert d.stars and all(s.center == answer for s in d.stars), (seed, nid, answer, d.stars)


@pytest.mark.parametrize("act,rows,seed", MAPS)
def test_label_plate_is_where_012_draws_it(render, ring_reach, act: int, rows: int, seed: int) -> None:
    """Every labelled node draws one plate, vertically centered on the node and right of its widest ring."""
    ow = _all_available(OverworldMap(act_index=act, seed=seed))
    draws = render(ow)
    for nid, d in draws.items():
        n = ow.nodes[nid]
        x, y = _xy(n)
        assert len(d.plates) == 1, (seed, nid, d.plates)
        assert n.label in d.texts, (seed, nid, d.texts)
        plate = d.plates[0]
        assert abs(plate.centery - y) <= 1, (seed, nid, plate, y)
        assert plate.left > x + ring_reach(ow, nid), (seed, nid, plate, ring_reach(ow, nid))


@pytest.mark.parametrize("act,rows,seed", MAPS)
def test_star_never_overlaps_a_label_plate(render, act: int, rows: int, seed: int) -> None:
    """No drawn star (backing included) touches any drawn label plate on the map."""
    ow = _all_available(OverworldMap(act_index=act, seed=seed))
    draws = render(ow)
    plates = [(nid, p) for nid, d in draws.items() for p in d.plates]
    assert len(plates) == len(ow.nodes)
    hits = []
    for nid, d in draws.items():
        for star in d.stars:
            for pid, plate in plates:
                if star.box().colliderect(plate):
                    hits.append((nid, pid, star.box(), plate))
    assert not hits, (act, rows, seed, hits)


@pytest.mark.parametrize("act,rows,seed", MAPS)
def test_star_left_of_its_node_clear_of_rings_on_screen(render, ring_reach, act: int, rows: int, seed: int) -> None:
    """Each star sits left of its node, outside every node's widest ring, fully on screen and below the header."""
    ow = _all_available(OverworldMap(act_index=act, seed=seed))
    draws = render(ow)
    screen = pygame.Rect(0, 0, config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    for nid in _elite_ids(ow):
        x, y = _xy(ow.nodes[nid])
        for star in draws[nid].stars:
            box = star.box()
            assert box.right <= x - ring_reach(ow, nid), (seed, nid, box, "star not left of its own ring")
            assert abs(star.center[1] - y) <= 1, (seed, nid, star.center, y)
            assert screen.contains(box) and box.top >= HEADER_BOTTOM, (seed, nid, box)
            for oid, other in ow.nodes.items():
                gap = _gap(box, _xy(other), ring_reach(ow, oid))
                assert gap > 0, (seed, nid, oid, box, round(gap, 2))
