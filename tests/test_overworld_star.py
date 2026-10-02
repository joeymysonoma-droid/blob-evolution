"""BUG-009 / BUG-025 / TASK-016: the elite/miniboss star, checked against the real overworld render.

Every position here is recorded from a real OverworldRenderer.draw on a headless display:
star centers and sizes from the draw_star calls, label plates from the style.draw_panel calls,
ring reach from the pygame.draw.circle calls around a node drawn selected, current and plain-available
(the widest of the three), with the pulse held at max.
No node radius, star size, ring reach or label offset is copied from _draw_node.
Each map's all-available render and each node's ring reach are recorded once per module and shared.

Three sets of maps run the same geometry checks (star vs label plates, star vs rings, on screen and
below the header; plus each label plate vs its own ring):
  tight  16 hand-picked tight maps (2 per height, Layers 1 and 8): the fast guard.
  broad  seeds 0-99 on Layer 1, every one with >= 3 starred nodes: catches a layout change that makes
         the hand-picked maps stop being the tight ones (BUG-037). Part of the default run.
  sweep  seeds 0-399 on Layer 1, marked `slow`: skipped by default (pytest.ini addopts `-m "not slow"`),
         run with `pytest -m slow`.
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
ACTS = (0, 7)  # Layers 1 and 8; layout is identical across layers today, this guards it staying so
MIN_STARS = 3  # a map needs this many starred nodes to be a useful star check
BROAD_SEEDS = range(100)  # Layer 1, default run
SWEEP_SEEDS = range(400)  # Layer 1, `slow` run
CURRENT_FROM_MAP = object()  # render(): keep the map's own current node
STAR_CENTER_MARK = (-3, 2)  # offset the star_center spy adds, so a star placed without it is caught

# Two seeds per map height, picked from seeds 0-399 (>= 3 starred nodes each) as the tightest cases:
# the closest star-to-plate gap per height, and the closest star-to-other-ring gap per height.
SEEDS_BY_HEIGHT: Dict[int, Tuple[int, ...]] = {
    8: (2, 37),  # 2: star-plate 50 px, star 2 px below header; 37: star-ring 25.5 px
    9: (3, 33),  # 3: star-plate 43 px; 33: star-ring 18.6 px
    10: (7, 5),  # 7: star-plate 38 px and star-ring 13.7 px; 5: star-plate 38 px
    11: (0, 271),  # 0: star-plate 33 px (closest overall); 271: star-ring 8.8 px (closest overall)
}
SEEDS_PER_HEIGHT = 2
HEIGHTS = list(range(MIN_ROUNDS, MAX_ROUNDS + 1))


def _map(act: int, seed: int) -> OverworldMap:
    """Build a map, failing with a clear message if its row count is outside MIN_ROUNDS..MAX_ROUNDS."""
    ow = OverworldMap(act_index=act, seed=seed)
    assert MIN_ROUNDS <= ow.encounter_rows <= MAX_ROUNDS, (
        f"seed {seed} on layer {act + 1} has {ow.encounter_rows} encounter rows, "
        f"outside the supported {MIN_ROUNDS}-{MAX_ROUNDS}"
    )
    return ow


def _starred_seeds(seeds: range) -> Tuple[List[int], List[int]]:
    """Split Layer 1 seeds into (usable, skipped), skipping maps with fewer than MIN_STARS starred nodes.

    Counts nodes only (no row-count check), so a bad row count fails inside a test, not at collection.
    """
    usable, skipped = [], []
    for seed in seeds:
        stars = sum(n.is_elite_marked for n in OverworldMap(act_index=0, seed=seed).nodes.values())
        (usable if stars >= MIN_STARS else skipped).append(seed)
    return usable, skipped


BROAD_USABLE, BROAD_SKIPPED = _starred_seeds(BROAD_SEEDS)
SWEEP_USABLE, SWEEP_SKIPPED = _starred_seeds(SWEEP_SEEDS)
# (layer index, seed) per set; the same four geometry tests run over all of them
TIGHT_MAPS = [(act, seed) for act in ACTS for seeds in SEEDS_BY_HEIGHT.values() for seed in seeds]
GEOMETRY_MAPS = (
    [pytest.param(a, s, id=f"tight-L{a + 1}-s{s}") for a, s in TIGHT_MAPS]
    + [pytest.param(0, s, id=f"broad-s{s}") for s in BROAD_USABLE]
    + [pytest.param(0, s, id=f"sweep-s{s}", marks=pytest.mark.slow) for s in SWEEP_USABLE]
)


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


@pytest.fixture(scope="module")
def render(renderer) -> Callable[..., Dict[str, NodeDraw]]:
    """Return render(ow, selected_id=None, mark_star_center=False, only_node=None, current_id=...) -> {node id: NodeDraw}.

    only_node draws just that node through the real _draw_node (as draw() would), skipping the rest.
    current_id overrides which node counts as current (default: the map's own) for an only_node draw.
    """
    surface = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))  # reused: only draw calls are recorded

    def _render(
        ow: OverworldMap,
        selected_id: Optional[str] = None,
        mark_star_center: bool = False,
        only_node: Optional[str] = None,
        current_id=CURRENT_FROM_MAP,
    ) -> Dict[str, NodeDraw]:
        draws: Dict[str, NodeDraw] = {nid: NodeDraw() for nid in ow.nodes}
        current_nodes: List[str] = []
        loose_texts: List[str] = []

        def node() -> Optional[NodeDraw]:
            return draws[current_nodes[-1]] if current_nodes else None

        real_draw_node = renderer._draw_node
        real_star = overworld_map.draw_star
        real_center = overworld_map.star_center
        real_panel = style.draw_panel
        real_circle = pygame.draw.circle

        def draw_node(surf, n, *args, **kwargs) -> None:
            current_nodes.append(n.id)
            try:
                real_draw_node(surf, n, *args, **kwargs)
            finally:
                current_nodes.pop()

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

        with pytest.MonkeyPatch.context() as m:
            m.setattr(renderer, "_draw_node", draw_node)
            m.setattr(overworld_map, "draw_star", draw_star)
            m.setattr(overworld_map, "star_center", star_center)
            m.setattr(style, "draw_panel", draw_panel)
            m.setattr(pygame.draw, "circle", circle)
            m.setattr(style, "pulse", lambda speed, lo=0.0, hi=1.0: hi)  # rings at their widest
            for attr in ("font", "font_small", "font_large"):
                m.setattr(renderer, attr, _FontSpy(getattr(renderer, attr), log_text))
            if only_node is None:
                renderer.draw(surface, ow, 0, 0, selected_node_id=selected_id)
            else:
                current = ow.current_node_id if current_id is CURRENT_FROM_MAP else current_id
                renderer._draw_node(surface, ow.nodes[only_node], current, selected_id)
        assert not any("\u2605" in t for t in loose_texts), loose_texts
        return draws

    return _render


def _all_available(ow: OverworldMap) -> OverworldMap:
    """Force every node available and not completed: every star and every label is drawn."""
    for n in ow.nodes.values():
        n.available = True
        n.completed = False
    return ow


@pytest.fixture(scope="module")
def available_render(render) -> Callable[[int, int], Tuple[OverworldMap, Dict[str, NodeDraw]]]:
    """Return shared(act, seed) -> (all-available map, its recorded draws), rendered once per module."""
    cache: Dict[Tuple[int, int], Tuple[OverworldMap, Dict[str, NodeDraw]]] = {}

    def _shared(act: int, seed: int) -> Tuple[OverworldMap, Dict[str, NodeDraw]]:
        if (act, seed) not in cache:
            ow = _all_available(_map(act, seed))
            cache[(act, seed)] = (ow, render(ow))
        return cache[(act, seed)]

    return _shared


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


@pytest.fixture(scope="module")
def ring_states(render) -> Callable[[OverworldMap, str], Dict[str, int]]:
    """Return states(ow, node_id) -> outermost ring radius drawn around that node in each ring state.

    "selected", "current" and "plain" (available, neither selected nor current), each measured from the
    pygame.draw.circle calls the real _draw_node makes at the node's center, with the pulse at max.
    """
    cache: Dict[Tuple[int, int, str], Dict[str, int]] = {}

    def _states(ow: OverworldMap, nid: str) -> Dict[str, int]:
        key = (ow.act_index, ow.seed, nid)
        if key not in cache:
            assert ow.nodes[nid].available, (key, "ring states are measured on available nodes")
            center = _xy(ow.nodes[nid])
            draws = {
                "selected": render(ow, selected_id=nid, only_node=nid, current_id=None),
                "current": render(ow, selected_id=None, only_node=nid, current_id=nid),
                "plain": render(ow, selected_id=None, only_node=nid, current_id=None),
            }
            radii = {}
            for state, drawn in draws.items():
                found = [r for c, r in drawn[nid].circles if c == center]
                assert found, (key, state, "no ring drawn at the node center")
                radii[state] = max(found)
            cache[key] = radii
        return cache[key]

    return _states


@pytest.fixture(scope="module")
def ring_reach(ring_states) -> Callable[[OverworldMap, str], int]:
    """Return reach(ow, node_id): the widest ring drawn around that node in any of its ring states."""
    return lambda ow, nid: max(ring_states(ow, nid).values())


def test_every_height_has_seeds() -> None:
    """Each encounter-row count (map height) has its seeds, and each seed really makes that height on both layers."""
    assert sorted(SEEDS_BY_HEIGHT) == HEIGHTS, (
        f"map heights are {HEIGHTS} but the tight-seed table covers {sorted(SEEDS_BY_HEIGHT)}: add or drop seeds"
    )
    for rows, seeds in SEEDS_BY_HEIGHT.items():
        assert len(seeds) == SEEDS_PER_HEIGHT, (rows, seeds)
        for seed in seeds:
            for act in ACTS:
                made = _map(act, seed).encounter_rows
                assert made == rows, f"seed {seed} on layer {act + 1} has {made} encounter rows, the table says {rows}"


def test_elite_nodes_exist_in_the_sample() -> None:
    """Every tight map has at least MIN_STARS starred nodes, so all three node states get a star to check."""
    for act, seed in TIGHT_MAPS:
        assert len(_elite_ids(_map(act, seed))) >= MIN_STARS, (act, seed)


def test_broad_run_covers_most_seeds() -> None:
    """Seeds 0-99 skip only maps with too few stars, and still cover every map height."""
    assert len(BROAD_SKIPPED) <= len(BROAD_SEEDS) // 10, f"too many skipped seeds: {BROAD_SKIPPED}"
    heights = {_map(0, seed).encounter_rows for seed in BROAD_USABLE}
    assert heights == set(HEIGHTS), (sorted(heights), HEIGHTS)


@pytest.mark.slow
def test_sweep_covers_most_seeds() -> None:
    """Seeds 0-399 skip only maps with too few stars, and still cover every map height."""
    assert len(SWEEP_SKIPPED) <= len(SWEEP_SEEDS) // 10, f"too many skipped seeds: {SWEEP_SKIPPED}"
    assert {_map(0, seed).encounter_rows for seed in SWEEP_USABLE} == set(HEIGHTS)


@pytest.mark.parametrize("act,seed", TIGHT_MAPS)
def test_star_is_drawn_as_a_shape_only_on_uncompleted_elite_nodes(render, act: int, seed: int) -> None:
    """Available and dimmed elite nodes get a backing + front draw_star; completed and plain nodes get none; no ★ glyph."""
    ow = _map(act, seed)
    elite = set(_elite_ids(ow))
    states = {}
    for group in (sorted(elite), sorted(set(ow.nodes) - elite)):  # cycle states within each group
        for i, nid in enumerate(group):
            state = ("available", "completed", "dimmed")[i % 3]
            ow.nodes[nid].available, ow.nodes[nid].completed = state == "available", state == "completed"
            states[nid] = state
    draws = render(ow)
    assert {states[nid] for nid in elite} == {"available", "completed", "dimmed"}, (seed, "every state needs a starred node")
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


@pytest.mark.parametrize("act,seed", TIGHT_MAPS)
def test_star_is_placed_by_star_center(render, act: int, seed: int) -> None:
    """_draw_node asks star_center (with the node's draw x, y) and draws exactly where it answers."""
    ow = _all_available(_map(act, seed))
    draws = render(ow, mark_star_center=True)
    for nid in _elite_ids(ow):
        d = draws[nid]
        assert len(d.star_center_calls) == 1, (seed, nid, d.star_center_calls)
        args, answer = d.star_center_calls[0]
        assert tuple(args[:2]) == _xy(ow.nodes[nid]), (seed, nid, args)
        assert d.stars and all(s.center == answer for s in d.stars), (seed, nid, answer, d.stars)


def test_ring_reach_is_the_widest_of_the_selected_current_and_plain_rings(ring_states, ring_reach) -> None:
    """All three ring states are measured from real draw calls, and reach is the widest (BUG-038)."""
    for act, seed in TIGHT_MAPS[:: len(TIGHT_MAPS) // 4]:
        ow = _all_available(_map(act, seed))
        for nid in list(ow.nodes)[:8]:
            radii = ring_states(ow, nid)
            assert set(radii) == {"selected", "current", "plain"}, (seed, nid, radii)
            assert ring_reach(ow, nid) == max(radii.values()), (seed, nid, radii)


# --- the four geometry checks: tight maps (fast guard), seeds 0-99 (default), seeds 0-399 (slow) ---------


@pytest.mark.parametrize("act,seed", GEOMETRY_MAPS)
def test_label_plate_is_where_012_draws_it(available_render, ring_reach, act: int, seed: int) -> None:
    """Every labelled node draws one plate, vertically centered on the node and right of its widest ring."""
    ow, draws = available_render(act, seed)
    for nid, d in draws.items():
        n = ow.nodes[nid]
        x, y = _xy(n)
        assert len(d.plates) == 1, (seed, nid, d.plates)
        assert n.label in d.texts, (seed, nid, d.texts)
        plate = d.plates[0]
        assert abs(plate.centery - y) <= 1, (seed, nid, plate, y)
        assert plate.left > x + ring_reach(ow, nid), (seed, nid, plate, ring_reach(ow, nid))


@pytest.mark.parametrize("act,seed", GEOMETRY_MAPS)
def test_star_never_overlaps_a_label_plate(available_render, act: int, seed: int) -> None:
    """No drawn star (backing included) touches any drawn label plate on the map."""
    ow, draws = available_render(act, seed)
    plates = [(nid, p) for nid, d in draws.items() for p in d.plates]
    assert len(plates) == len(ow.nodes)
    hits = []
    for nid, d in draws.items():
        for star in d.stars:
            for pid, plate in plates:
                if star.box().colliderect(plate):
                    hits.append((nid, pid, star.box(), plate))
    assert not hits, (act, seed, hits)


@pytest.mark.parametrize("act,seed", GEOMETRY_MAPS)
def test_star_left_of_its_node_and_clear_of_every_ring(available_render, ring_reach, act: int, seed: int) -> None:
    """Each star sits left of its node's ring, level with it, and outside every node's widest ring."""
    ow, draws = available_render(act, seed)
    for nid in _elite_ids(ow):
        x, y = _xy(ow.nodes[nid])
        for star in draws[nid].stars:
            box = star.box()
            assert box.right <= x - ring_reach(ow, nid), (seed, nid, box, "star not left of its own ring")
            assert abs(star.center[1] - y) <= 1, (seed, nid, star.center, y)
            for oid, other in ow.nodes.items():
                gap = _gap(box, _xy(other), ring_reach(ow, oid))
                assert gap > 0, (seed, nid, oid, box, round(gap, 2))


@pytest.mark.parametrize("act,seed", GEOMETRY_MAPS)
def test_star_on_screen_and_below_the_header(available_render, act: int, seed: int) -> None:
    """Each star box is fully on screen and below the header."""
    ow, draws = available_render(act, seed)
    screen = pygame.Rect(0, 0, config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    for nid in _elite_ids(ow):
        for star in draws[nid].stars:
            box = star.box()
            assert screen.contains(box) and box.top >= HEADER_BOTTOM, (seed, nid, box)
