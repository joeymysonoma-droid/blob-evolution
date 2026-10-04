"""Ground terrain helpers: tone-ramp macro noise, grit, clustered scatter and supersampled stamping (TASK-037)."""

from __future__ import annotations

import math
import random
from typing import Callable, List, Optional, Tuple

import pygame

from blob_evolution import config

Color = Tuple[int, int, int]
Ramp = Tuple[Color, Color, Color]          # (DARK, MID, LIGHT)
Point = Tuple[int, int]
Scatter = Callable[..., List[Point]]
Decals = Callable[[pygame.Surface, random.Random, Scatter], None]


def ramp_for_act(theme_index: int) -> Ramp:
    """Ground ramp (DARK, MID, LIGHT) of an act; out-of-range indices use the nearest act."""
    return config.GROUND_RAMPS[max(0, min(theme_index, len(config.GROUND_RAMPS) - 1))]


def lerp_color(a: Color, b: Color, t: float) -> Color:
    """Linear blend from a (t=0) to b (t=1)."""
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def noise_layer(
    width: int, height: int, cells: int, lo: float, hi: float, ramp: Ramp, rng: random.Random,
) -> pygame.Surface:
    """A cells x cells grid of DARK..LIGHT tones (ramp position uniform in [lo, hi]) smoothscaled to width x height."""
    small = pygame.Surface((cells, cells))
    for j in range(cells):
        for i in range(cells):
            small.set_at((i, j), lerp_color(ramp[0], ramp[2], rng.uniform(lo, hi)))
    return pygame.transform.smoothscale(small, (width, height))


def macro_noise_ground(width: int, height: int, ramp: Ramp, rng: random.Random) -> pygame.Surface:
    """Three octaves of value noise stacked into one opaque ground; every tone stays inside DARK..LIGHT."""
    ground: Optional[pygame.Surface] = None
    for cells, lo, hi, alpha in config.GROUND_NOISE_OCTAVES:
        layer = noise_layer(width, height, cells, lo, hi, ramp, rng)
        if ground is None:
            ground = layer
        else:
            layer.set_alpha(alpha)     # bake-time only, never per frame
            ground.blit(layer, (0, 0))
    assert ground is not None
    return ground


def add_grit(surface: pygame.Surface, ramp: Ramp, rng: random.Random) -> None:
    """Scatter single-pixel specks of MID +/- a small brightness step (never darker than 0.6 x DARK)."""
    dark, mid, _ = ramp
    floor = tuple(math.ceil(c * 0.6) for c in dark)
    width, height = surface.get_size()
    for _ in range(rng.randint(*config.GROUND_GRIT_COUNT)):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        step = rng.randint(-config.GROUND_GRIT_SPREAD, config.GROUND_GRIT_SPREAD)
        surface.set_at((x, y), tuple(max(floor[i], min(255, mid[i] + step)) for i in range(3)))


def make_scatter(width: int, height: int, rng: random.Random) -> Scatter:
    """Build scatter(n, sigma=None): n decal positions, mostly gaussian around random cluster centres.

    Centres are K uniform points inside the world margin plus one at the world centre (player start).
    scatter.total counts the positions handed out, so a bake can be checked against MAX_STAMPS_PER_ACT.
    """
    margin = config.GROUND_CLUSTER_MARGIN
    centres = [
        (rng.uniform(margin, width - margin), rng.uniform(margin, height - margin))
        for _ in range(rng.randint(*config.GROUND_CLUSTER_COUNT))
    ]
    centres.append((width / 2, height / 2))

    def scatter(n: int, sigma: Optional[float] = None) -> List[Point]:
        spread = sigma if sigma is not None else rng.uniform(*config.GROUND_CLUSTER_SIGMA)
        points: List[Point] = []
        for _ in range(n):
            if rng.random() < config.GROUND_CLUSTER_SHARE:
                cx, cy = rng.choice(centres)
                x, y = rng.gauss(cx, spread), rng.gauss(cy, spread)
            else:
                x, y = rng.uniform(0, width), rng.uniform(0, height)
            points.append((int(max(0, min(width - 1, x))), int(max(0, min(height - 1, y)))))
        scatter.total += n  # type: ignore[attr-defined]
        return points

    scatter.total = 0  # type: ignore[attr-defined]
    return scatter


def make_sprite(width: int, height: int, draw: Callable[[pygame.Surface], None]) -> pygame.Surface:
    """Build a width x height SRCALPHA sprite: draw(surface) paints it at 2x, then it is smoothscaled down."""
    big = pygame.Surface((width * 2, height * 2), pygame.SRCALPHA)
    draw(big)
    return pygame.transform.smoothscale(big, (width, height))


def stamp(
    surface: pygame.Surface,
    sprite: pygame.Surface,
    pos: Point,
    angle: float = 0.0,
    scale: float = 1.0,
    alpha: int = 255,
) -> None:
    """Blit sprite centred on pos, rotated by angle degrees and scaled; alpha < 255 fades it."""
    image = pygame.transform.rotozoom(sprite, angle, scale) if (angle or scale != 1.0) else sprite
    if alpha < 255:
        if image is sprite:
            image = sprite.copy()
        image.set_alpha(alpha)
    surface.blit(image, (pos[0] - image.get_width() // 2, pos[1] - image.get_height() // 2))


# Per-act decals and landmarks arrive in TASK-038 (acts 0-4) and TASK-039 (acts 5-9); until then no decals.
def _no_decals(surface: pygame.Surface, rng: random.Random, scatter: Scatter) -> None:
    """Placeholder decal pass."""


decals_act_0 = decals_act_1 = decals_act_2 = decals_act_3 = decals_act_4 = _no_decals
decals_act_5 = decals_act_6 = decals_act_7 = decals_act_8 = decals_act_9 = _no_decals

ACT_DECALS: Tuple[Decals, ...] = (
    decals_act_0, decals_act_1, decals_act_2, decals_act_3, decals_act_4,
    decals_act_5, decals_act_6, decals_act_7, decals_act_8, decals_act_9,
)
