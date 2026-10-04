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


def make_sprite(
    width: int, height: int, draw: Callable[[pygame.Surface], None], bg: Color = (0, 0, 0),
) -> pygame.Surface:
    """Build a width x height SRCALPHA sprite: draw(surface) paints it at 2x, then it is smoothscaled down.

    bg is the colour of the transparent background: pass the sprite's main colour so the smoothscale does not
    blend its edge with black (a dark fringe)."""
    big = pygame.Surface((width * 2, height * 2), pygame.SRCALPHA)
    big.fill((*bg, 0))
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



# --- shared decal helpers (TASK-038 / TASK-039) ----------------------------------------------------------------

TAU = math.tau
SS = 2                                    # make_sprite supersampling factor
Segment = Tuple[float, float, float, float]


def _floor(act: int) -> Color:
    """Darkest allowed tone of an act: 0.6 x DARK per channel (rounded up), the 037 readability floor."""
    return tuple(math.ceil(c * 0.6) for c in config.GROUND_RAMPS[act][0])  # type: ignore[return-value]


def _ink(act: int, color: Color) -> Color:
    """A decal colour raised to the act's floor (a couple of plan colours are 1 unit below it in one channel)."""
    floor = _floor(act)
    return (max(floor[0], color[0]), max(floor[1], color[1]), max(floor[2], color[2]))


def _layer(width: int, height: int) -> pygame.Surface:
    return pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)


def _grow(
    rng: random.Random, start: Tuple[float, float], heading: float, length: float, levels: int,
    split_chance: float = 0.6, spread: Tuple[float, float] = (25.0, 40.0), shrink: float = 0.7,
) -> List[Segment]:
    """A branching polyline: each node continues (bending a little) or, with split_chance, forks at +/- spread degrees."""
    segs: List[Segment] = []

    def grow(x: float, y: float, h: float, ln: float, level: int) -> None:
        if level >= levels:
            return
        h += math.radians(rng.uniform(-12, 12))
        x1, y1 = x + math.cos(h) * ln, y + math.sin(h) * ln
        segs.append((x, y, x1, y1))
        if rng.random() < split_chance:
            a = math.radians(rng.uniform(*spread))
            grow(x1, y1, h + a, ln * shrink, level + 1)
            grow(x1, y1, h - a, ln * shrink, level + 1)
        else:
            grow(x1, y1, h, ln * shrink, level + 1)

    grow(start[0], start[1], heading, length, 0)
    return segs


def _stroke(target: pygame.Surface, segs: List[Segment], width: int, rgba, ox: float = 0.0, oy: float = 0.0) -> None:
    """Draw segments with round joints (pygame's wide lines leave gaps at corners)."""
    for x0, y0, x1, y1 in segs:
        a = (round(x0 - ox), round(y0 - oy))
        b = (round(x1 - ox), round(y1 - oy))
        pygame.draw.line(target, rgba, a, b, width)
        if width > 2:
            pygame.draw.circle(target, rgba, a, width // 2)
            pygame.draw.circle(target, rgba, b, width // 2)


def _bounds(segs: List[Segment], pad: int, size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """Pixel bounding box of the segments (+ pad), clipped to the surface: x, y, w, h."""
    x0 = max(0, int(min(min(s[0], s[2]) for s in segs)) - pad)
    y0 = max(0, int(min(min(s[1], s[3]) for s in segs)) - pad)
    x1 = min(size[0], int(max(max(s[0], s[2]) for s in segs)) + pad + 1)
    y1 = min(size[1], int(max(max(s[1], s[3]) for s in segs)) + pad + 1)
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def _stroke_layer(surface: pygame.Surface, segs: List[Segment], passes) -> None:
    """Draw several (width, rgba) passes of the same segments onto one transparent layer, then blit it once."""
    if not segs:
        return
    x, y, w, h = _bounds(segs, max(width for width, _ in passes) + 1, surface.get_size())
    layer = _layer(w, h)
    for width, rgba in passes:
        _stroke(layer, segs, width, rgba, x, y)
    surface.blit(layer, (x, y))


def _convex_quad(rng: random.Random, cx: float, cy: float, size: float) -> List[Tuple[float, float]]:
    """A random convex quadrilateral about (cx, cy), roughly `size` across."""
    for _ in range(12):
        base = rng.uniform(0, TAU)
        pts = []
        for k in range(4):
            a = base + k * TAU / 4 + rng.uniform(-0.45, 0.45)
            r = size / 2 * rng.uniform(0.6, 1.0)
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
        signs = []
        for k in range(4):
            ax, ay = pts[k]
            bx, by = pts[(k + 1) % 4]
            qx, qy = pts[(k + 2) % 4]
            signs.append((bx - ax) * (qy - by) - (by - ay) * (qx - bx) > 0)
        if all(signs) or not any(signs):
            return pts
    base = rng.uniform(0, TAU)
    return [(cx + math.cos(base + k * TAU / 4) * size / 2, cy + math.sin(base + k * TAU / 4) * size / 2) for k in range(4)]


def _plates(
    surface: pygame.Surface, rng: random.Random, count: int, size_range: Tuple[float, float],
    tones: Tuple[Color, Color], alpha: int, edge: Color,
) -> None:
    """Random convex plates, alternately tinted with two tones at `alpha`, with a 1 px edge."""
    width, height = surface.get_size()
    for i in range(count):
        pts = _convex_quad(rng, rng.uniform(0, width), rng.uniform(0, height), rng.uniform(*size_range))
        x0, y0 = int(min(p[0] for p in pts)) - 1, int(min(p[1] for p in pts)) - 1
        x1, y1 = int(max(p[0] for p in pts)) + 2, int(max(p[1] for p in pts)) + 2
        if x1 <= 0 or y1 <= 0 or x0 >= width or y0 >= height:
            continue
        layer = _layer(x1 - x0, y1 - y0)
        rel = [(p[0] - x0, p[1] - y0) for p in pts]
        pygame.draw.polygon(layer, (*tones[i % 2], alpha), rel)
        pygame.draw.polygon(layer, (*edge, 255), rel, 1)
        surface.blit(layer, (x0, y0))


def _in_ellipse(rng: random.Random, cx: float, cy: float, w: float, h: float, inner: float = 0.8) -> Tuple[int, int]:
    """A uniform random point inside the ellipse (cx, cy, w x h), shrunk to `inner` of its size."""
    r, a = math.sqrt(rng.random()) * inner, rng.uniform(0, TAU)
    return int(cx + math.cos(a) * r * w / 2), int(cy + math.sin(a) * r * h / 2)


# --- Act 0, The Verdant Rim: meadow edge, pollen light ----------------------------------------------------------

def _tuft_sprite(rng: random.Random, act: int) -> pygame.Surface:
    """Fan of 5 thin blades from the sprite centre (base 2 px, length 10-18, angles -50..50 +/- 8)."""
    body, tip = _ink(act, (46, 120, 62)), _ink(act, (92, 170, 90))
    size = 48
    blades = [(math.radians(a + rng.uniform(-8, 8)), rng.uniform(10, 18)) for a in (-50, -25, 0, 25, 50)]

    def draw(big: pygame.Surface) -> None:
        c = size * SS // 2
        for ang, length in blades:
            dx, dy = math.sin(ang), -math.cos(ang)                  # 0 degrees = straight up
            px, py = -dy, dx
            half = 1.0 * SS                                         # base 2 px wide
            base_l = (c + px * half, c + py * half)
            base_r = (c - px * half, c - py * half)
            end = (c + dx * length * SS, c + dy * length * SS)
            pygame.draw.polygon(big, (*body, 255), [base_l, base_r, end])
            pygame.draw.rect(big, (*tip, 255), (int(end[0]) - 1, int(end[1]) - 1, 2, 2))

    return make_sprite(size, size, draw, bg=body)


def _clover_sprite(act: int) -> pygame.Surface:
    """Three r4 circles in a triangle of side 6 with a bright centre dot."""
    leaf, dot = _ink(act, (36, 100, 56)), _ink(act, (110, 190, 120))
    size = 18

    def draw(big: pygame.Surface) -> None:
        c = size * SS / 2
        for k in range(3):
            a = math.radians(90 + 120 * k)
            pygame.draw.circle(big, (*leaf, 255), (c + math.cos(a) * 3.46 * SS, c - math.sin(a) * 3.46 * SS), 4 * SS)
        pygame.draw.circle(big, (*dot, 255), (c, c), 1 * SS)

    return make_sprite(size, size, draw, bg=leaf)


def _dot_sprite(radius: float, color: Color, alpha: int) -> pygame.Surface:
    size = int(radius * 2) + 2

    def draw(big: pygame.Surface) -> None:
        pygame.draw.circle(big, (*color, alpha), (size * SS // 2, size * SS // 2), radius * SS)

    return make_sprite(size, size, draw, bg=color)


def _ellipse_patch(w: int, h: int, color: Color, alpha: int) -> pygame.Surface:
    def draw(big: pygame.Surface) -> None:
        pygame.draw.ellipse(big, (*color, alpha), (2 * SS, 2 * SS, w * SS, h * SS))

    return make_sprite(w + 4, h + 4, draw, bg=color)


def decals_act_0(surface: pygame.Surface, rng: random.Random, scatter: Scatter) -> None:
    """The Verdant Rim: moss patches, grass tufts, clover, wildflowers and the flat 'rim ring' landmark."""
    act = 0
    for x, y in scatter(14, 170):
        w, h = rng.randint(60, 140), rng.randint(40, 90)
        stamp(surface, _ellipse_patch(w, h, _ink(act, (52, 60, 34)), 90), (x, y), angle=rng.uniform(0, 180))
    tufts = [_tuft_sprite(rng, act) for _ in range(4)]
    for x, y in scatter(220):
        stamp(surface, rng.choice(tufts), (x, y), angle=rng.uniform(0, 360), scale=rng.uniform(0.8, 1.3), alpha=200)
    clover = _clover_sprite(act)
    for x, y in scatter(60):
        stamp(surface, clover, (x, y), angle=rng.uniform(0, 360))
    # radius 1-2 per the plan, capped at 1.5 so a bright dot is never wider than 3 px (38 acceptance 3)
    flowers = [_dot_sprite(r, _ink(act, c), 190) for r in (1, 1.5) for c in ((200, 225, 120), (236, 236, 170))]
    for x, y in scatter(80):
        stamp(surface, rng.choice(flowers), (x, y))
    # landmark: the rim ring, 8 flat discs on a circle of r 150 round the world centre (R2: no shadow)
    cx, cy = surface.get_width() // 2, surface.get_height() // 2
    line = _layer(2 * 152 + 2, 2 * 152 + 2)
    pygame.draw.circle(line, (*_ink(act, (56, 100, 66)), 70), (152 + 1, 152 + 1), 150, 1)
    surface.blit(line, (cx - 153, cy - 153))

    def disc(big: pygame.Surface) -> None:
        c = 11 * SS
        pygame.draw.circle(big, (*_ink(act, (92, 118, 98)), 255), (c, c), 10 * SS)
        pygame.draw.circle(big, (*_ink(act, (62, 84, 68)), 255), (c, c), 9 * SS)

    disc_sprite = make_sprite(22, 22, disc, bg=_ink(act, (62, 84, 68)))
    for k in range(8):
        a = k * TAU / 8
        stamp(surface, disc_sprite, (round(cx + math.cos(a) * 150 + rng.uniform(-1, 1)),
                                     round(cy + math.sin(a) * 150 + rng.uniform(-1, 1))))


# --- Act 1, The Sinking Garden: bog pools, lily pads, reeds, a dry stepping-stone causeway -------------------------

def _pool_sprite(w: int, h: int, act: int) -> pygame.Surface:
    fill, rim, ripple = _ink(act, (22, 34, 24)), _ink(act, (74, 96, 40)), _ink(act, (96, 122, 58))

    def draw(big: pygame.Surface) -> None:
        ox, oy = 3 * SS, 3 * SS
        pygame.draw.ellipse(big, (*fill, 200), (ox, oy, w * SS, h * SS))
        pygame.draw.ellipse(big, (*rim, 140), (ox, oy, w * SS, h * SS), 3 * SS)
        for k in (0.55, 0.8):
            rw, rh = w * k, h * k
            pygame.draw.ellipse(big, (*ripple, 90), (ox + (w - rw) / 2 * SS, oy + (h - rh) / 2 * SS, rw * SS, rh * SS), SS)

    return make_sprite(w + 6, h + 6, draw, bg=fill)


def _pad_sprite(radius: int, act: int) -> pygame.Surface:
    """Lily pad: disc with a 40 degree wedge cut out (left transparent, so the pool shows through) and a centre dot."""
    pad, dot = _ink(act, (58, 104, 50)), _ink(act, (96, 150, 70))
    size = radius * 2 + 4

    def draw(big: pygame.Surface) -> None:
        c = size * SS / 2
        pygame.draw.circle(big, (*pad, 255), (c, c), radius * SS)
        wedge = [(c, c)] + [(c + math.cos(math.radians(a)) * (radius + 2) * SS, c + math.sin(math.radians(a)) * (radius + 2) * SS)
                            for a in (-20, -7, 7, 20)]
        pygame.draw.polygon(big, (*pad, 0), wedge)
        pygame.draw.circle(big, (*dot, 255), (c, c), SS)

    return make_sprite(size, size, draw, bg=pad)


def _reed_sprite(rng: random.Random, act: int) -> pygame.Surface:
    """3-5 reed lines (length 12-20, width 1-2) from the sprite centre with a tuft dot at each end."""
    reed, tuft = _ink(act, (92, 100, 44)), _ink(act, (140, 120, 60))
    size = 46
    stems = [(math.radians(rng.uniform(-28, 28)), rng.uniform(12, 20), rng.choice((1, 2))) for _ in range(rng.randint(3, 5))]

    def draw(big: pygame.Surface) -> None:
        c = size * SS // 2
        for ang, length, width in stems:
            end = (c + math.sin(ang) * length * SS, c - math.cos(ang) * length * SS)
            pygame.draw.line(big, (*reed, 255), (c, c), end, width * SS)
            pygame.draw.circle(big, (*tuft, 255), end, SS)

    return make_sprite(size, size, draw, bg=reed)


def _ring_sprite(radius: int, color: Color, alpha: int) -> pygame.Surface:
    size = radius * 2 + 4

    def draw(big: pygame.Surface) -> None:
        pygame.draw.circle(big, (*color, alpha), (size * SS // 2, size * SS // 2), radius * SS, SS)

    return make_sprite(size, size, draw, bg=color)


def decals_act_1(surface: pygame.Surface, rng: random.Random, scatter: Scatter) -> None:
    """The Sinking Garden: bog pools with ripples, lily pads, reeds, bubbles and the 'sunken causeway' of dry stones."""
    act = 1
    pools = []
    for x, y in scatter(14, 160):
        w, h = rng.randint(70, 160), rng.randint(40, 90)
        pools.append((x, y, w, h))
        stamp(surface, _pool_sprite(w, h, act), (x, y), angle=0)
    pads = {r: _pad_sprite(r, act) for r in range(8, 13)}
    for _ in range(40):
        px, py, pw, ph = rng.choice(pools)
        stamp(surface, pads[rng.randint(8, 12)], _in_ellipse(rng, px, py, pw, ph, 0.7), angle=rng.uniform(0, 360), alpha=225)
    reeds = [_reed_sprite(rng, act) for _ in range(5)]
    for _ in range(60):
        px, py, pw, ph = rng.choice(pools)
        a = rng.uniform(0, TAU)
        stamp(surface, rng.choice(reeds), (round(px + math.cos(a) * pw / 2), round(py + math.sin(a) * ph / 2)),
              angle=rng.uniform(-30, 30))
    bubbles = {r: _ring_sprite(r, _ink(act, (120, 150, 70)), 120) for r in (2, 3, 4)}
    for _ in range(80):
        px, py, pw, ph = rng.choice(pools)
        stamp(surface, bubbles[rng.randint(2, 4)], _in_ellipse(rng, px, py, pw, ph, 0.85))
    # landmark: the sunken causeway, dry stones along a sine route (a path, blocks nothing)
    stone_fill, stone_rim = _ink(act, (70, 76, 52)), _ink(act, (96, 104, 66))

    def stone(big: pygame.Surface) -> None:
        pygame.draw.ellipse(big, (*stone_rim, 255), (2 * SS, 2 * SS, 26 * SS, 18 * SS))
        pygame.draw.ellipse(big, (*stone_fill, 255), (3 * SS, 3 * SS, 24 * SS, 16 * SS))

    stone_sprite = make_sprite(30, 22, stone, bg=stone_fill)
    phase = rng.uniform(0, TAU)
    count = rng.randint(10, 12)

    def route(x: float) -> float:
        return 1000 + 260 * math.sin(x / 1850 * math.pi * 2 + phase)

    for i in range(count):
        x = 150 + i * 1700 / (count - 1)
        slope = (route(x + 1) - route(x - 1)) / 2
        stamp(surface, stone_sprite, (round(x), round(route(x))), angle=-math.degrees(math.atan2(slope, 1)))


# --- Act 2, The Memory Vaults: indigo flagstone, inlaid runes, crystals, the memory dais ----------------------------

FACET_ALPHA = 128           # crystal facets are translucent so their rendered luma stays <= 0.104 (see tests)


def _rune_tile_sprite(act: int) -> pygame.Surface:
    line, dot = _ink(act, (50, 84, 140)), _ink(act, (80, 130, 200))
    size = 50

    def draw(big: pygame.Surface) -> None:
        c = size * SS // 2
        pygame.draw.circle(big, (*line, 255), (c, c), 22 * SS, SS)
        pygame.draw.line(big, (*line, 255), (c - 5 * SS, c), (c + 5 * SS, c), SS)
        pygame.draw.line(big, (*line, 255), (c, c - 5 * SS), (c, c + 5 * SS), SS)
        pygame.draw.circle(big, (*dot, 255), (c, c), 2 * SS)

    return make_sprite(size, size, draw, bg=line)


def _crystal_sprite(radius: int, act: int) -> pygame.Surface:
    """Flat top-down crystal: hexagon of 6 shaded triangles, a bright outline, and a soft glow disc beneath."""
    tones = [_ink(act, c) for c in ((46, 86, 160), (60, 110, 190), (84, 140, 220))]
    outline, glow = _ink(act, (150, 200, 255)), _ink(act, (90, 160, 230))
    size = int(radius * 2.2 * 2) + 4

    def draw(big: pygame.Surface) -> None:
        c = size * SS / 2
        pygame.draw.circle(big, (*glow, 36), (c, c), radius * 2.2 * SS)
        verts = [(c + math.cos(k * TAU / 6) * radius * SS, c + math.sin(k * TAU / 6) * radius * SS) for k in range(6)]
        for k in range(6):
            pygame.draw.polygon(big, (*tones[k % 3], FACET_ALPHA), [(c, c), verts[k], verts[(k + 1) % 6]])
        pygame.draw.polygon(big, (*outline, 255), verts, SS)

    return make_sprite(size, size, draw, bg=glow)


def _dais_sprite(act: int) -> pygame.Surface:
    ring, spoke, rune = _ink(act, (50, 84, 140)), _ink(act, (40, 66, 116)), _ink(act, (110, 170, 240))
    size = 348

    def draw(big: pygame.Surface) -> None:
        c = size * SS / 2
        for r in (90, 130, 170):
            pygame.draw.circle(big, (*ring, 255), (c, c), r * SS, 2 * SS)
        for k in range(8):
            a = k * TAU / 8
            pygame.draw.line(big, (*spoke, 255), (c + math.cos(a) * 90 * SS, c + math.sin(a) * 90 * SS),
                             (c + math.cos(a) * 170 * SS, c + math.sin(a) * 170 * SS), SS)
        for k in range(4):
            a = k * TAU / 4
            at = (c + math.cos(a) * 130 * SS, c + math.sin(a) * 130 * SS)
            pygame.draw.circle(big, (*rune, 100), at, 3 * SS)              # translucent core keeps the wide part <= 0.104 luma
            pygame.draw.circle(big, (*rune, 255), at, 3 * SS, SS)          # 1 px bright ring

    return make_sprite(size, size, draw, bg=ring)


GRID_JITTER = 18  # px; each flagstone grid line wanders +/- this far from its 160 px slot


def decals_act_2(surface: pygame.Surface, rng: random.Random, scatter: Scatter) -> None:
    """The Memory Vaults: flagstone grid, rune and cracked tiles, crystal clusters and the 'memory dais'."""
    act = 2
    dark, _, light = config.GROUND_RAMPS[act]
    width, height = surface.get_size()
    step = 160
    tints = []
    for tone in (dark, light):
        tile = pygame.Surface((step + 2 * GRID_JITTER, step + 2 * GRID_JITTER))
        tile.fill(tone)
        tile.set_alpha(40)
        tints.append(tile)
    rune = _rune_tile_sprite(act)
    edge = _ink(act, (14, 20, 52))
    crack_dark, crack_lit = _ink(act, (12, 16, 40)), _ink(act, (40, 62, 110))
    # Grid lines sit near every 160 px but each is jittered independently (the plan's perfectly regular grid is a
    # rigid periodic stripe pattern and fails the 038 autocorrelation acceptance).
    cols, rows = math.ceil(width / step), math.ceil(height / step)
    xs = [i * step + (rng.randint(-GRID_JITTER, GRID_JITTER) if 0 < i <= cols else 0) for i in range(cols + 2)]
    ys = [j * step + (rng.randint(-GRID_JITTER, GRID_JITTER) if 0 < j <= rows else 0) for j in range(rows + 2)]
    for j in range(rows):
        for i in range(cols):
            x0, y0 = xs[i], ys[j]
            tw, th = xs[i + 1] - x0, ys[j + 1] - y0
            surface.blit(tints[rng.randint(0, 1)], (x0, y0), (0, 0, tw, th))
            if rng.random() < 1 / 3:
                stamp(surface, rune, (x0 + tw // 2, y0 + th // 2))
            if rng.random() < 1 / 8:
                a = (x0 + rng.randint(10, step - 10), y0 + rng.randint(0, 30))
                b = (a[0] + rng.randint(-30, 30), y0 + step // 3 + rng.randint(-12, 12))
                c = (b[0] + rng.randint(-30, 30), y0 + 2 * step // 3 + rng.randint(-12, 12))
                d = (c[0] + rng.randint(-30, 30), y0 + step - rng.randint(0, 30))
                pts = [a, b, c, d]
                lit = _layer(step + 80, step)
                shifted = [(p[0] - x0 + 40 + 1, p[1] - y0) for p in pts]
                pygame.draw.lines(lit, (*crack_lit, 120), False, shifted, 1)
                surface.blit(lit, (x0 - 40, y0))
                pygame.draw.lines(surface, crack_dark, False, pts, 1)
    for x in xs[:cols + 1]:
        pygame.draw.rect(surface, edge, (x - 1, 0, 2, height))
    for y in ys[:rows + 1]:
        pygame.draw.rect(surface, edge, (0, y - 1, width, 2))
    crystals = {r: _crystal_sprite(r, act) for r in range(8, 17)}
    for cx, cy in scatter(14, 90):
        for _ in range(rng.randint(3, 5)):
            stamp(surface, crystals[rng.randint(8, 16)], (round(cx + rng.gauss(0, 24)), round(cy + rng.gauss(0, 24))),
                  angle=rng.uniform(0, 60))
    stamp(surface, _dais_sprite(act), (width // 2, height // 2))


# --- Act 3, The Forge Veins: basalt plates, cooled seams, ash, cinder pits, the great seam -----------------------

def _pit_sprite(radius: int, act: int) -> pygame.Surface:
    fill, ring = _ink(act, (24, 10, 8)), _ink(act, (140, 52, 20))
    size = radius * 2 + 4

    def draw(big: pygame.Surface) -> None:
        c = size * SS // 2
        pygame.draw.circle(big, (*fill, 255), (c, c), radius * SS)
        pygame.draw.circle(big, (*ring, 160), (c, c), radius * SS, SS)

    return make_sprite(size, size, draw, bg=fill)


def decals_act_3(surface: pygame.Surface, rng: random.Random, scatter: Scatter) -> None:
    """The Forge Veins: basalt plates, cooled lava veins (dimmer than the hazard), ash, cinder pits, the great seam."""
    act = 3
    dark, mid, _ = config.GROUND_RAMPS[act]
    width, height = surface.get_size()
    _plates(surface, rng, 120, (60, 140), (dark, mid), 120, _ink(act, (22, 10, 8)))
    # cooled veins: 3 passes, width 7 (alpha 110) / 3 / 1
    for x, y in scatter(8, 140):
        segs = _grow(rng, (x, y), rng.uniform(0, TAU), 130, 4)
        _stroke_layer(surface, segs, [(7, (*_ink(act, (60, 18, 10)), 110))])
        _stroke(surface, segs, 3, _ink(act, (150, 44, 18)))
        _stroke(surface, segs, 1, _ink(act, (210, 80, 28)))
    flecks = [_dot_sprite(r, _ink(act, (70, 52, 46)), 170) for r in (1, 1, 2)]
    for x, y in scatter(300):
        stamp(surface, rng.choice(flecks), (x, y))
    pits = {r: _pit_sprite(r, act) for r in range(10, 23)}
    for x, y in scatter(24):
        stamp(surface, pits[rng.randint(10, 22)], (x, y))
    # landmark: the great seam, a wide vein across the map that keeps >= 250 px from the centre
    side = rng.choice((-1, 1))
    x_end, y_end = width, height - 500                 # the route runs (0, 500) -> (2000, 1500) on the 2000 x 2000 world
    length = math.hypot(x_end, y_end - 500)
    nx, ny = -(y_end - 500) / length * side, x_end / length * side      # unit normal of the route
    pts = []
    for k in range(0, 101):
        s = k / 100
        off = 340 * math.sin(math.pi * s) + 30 * math.sin(4 * math.pi * s) * math.sin(math.pi * s)   # bows away from the centre
        pts.append((s * x_end + nx * off, 500 + s * (y_end - 500) + ny * off))
    segs = [(pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1]) for k in range(len(pts) - 1)]
    _stroke(surface, segs, 14, _ink(act, (50, 14, 8)))
    _stroke(surface, segs, 6, _ink(act, (120, 36, 14)))
    _stroke(surface, segs, 2, _ink(act, (190, 70, 26)))


# --- Act 4, The Still Expanse: night ice, cracks, drifts, frost ferns, the frozen lake -----------------------------

def _drift_sprite(w: int, h: int, act: int) -> pygame.Surface:
    fill, crest = _ink(act, (112, 140, 168)), _ink(act, (160, 190, 220))

    def draw(big: pygame.Surface) -> None:
        pygame.draw.ellipse(big, (*fill, 70), (2 * SS, 2 * SS, w * SS, h * SS))
        pygame.draw.arc(big, (*crest, 80), (2 * SS, 2 * SS, w * SS, h * SS), math.radians(15), math.radians(165), SS)

    return make_sprite(w + 4, h + 4, draw, bg=fill)


def _fern_sprite(stem: int, act: int) -> pygame.Surface:
    """Frost fern: a stem from the sprite centre with 4-6 branch pairs at +/-55 degrees, each pair 15% shorter."""
    color = _ink(act, (150, 196, 230))
    size = 72
    pairs = 4 + stem % 3

    def draw(big: pygame.Surface) -> None:
        c = size * SS / 2
        pygame.draw.line(big, (*color, 255), (c, c), (c, c - stem * SS), SS)
        branch = stem * 0.4
        for k in range(pairs):
            y = c - stem * SS * (k + 1) / (pairs + 1)
            for sign in (-1, 1):
                a = math.radians(55) * sign
                pygame.draw.line(big, (*color, 255), (c, y), (c + math.sin(a) * branch * SS, y - math.cos(a) * branch * SS), SS)
            branch *= 0.85

    return make_sprite(size, size, draw, bg=color)


def _lake_sprite(act: int, rng: random.Random) -> pygame.Surface:
    w, h = 560, 380
    fill, frost, crack = _ink(act, (18, 34, 48)), _ink(act, (120, 170, 205)), _ink(act, (150, 190, 225))
    ox = rng.uniform(-0.45, 0.45)
    oy = rng.uniform(-0.45, 0.45)
    rays = [math.radians(k * 45 + rng.uniform(-12, 12)) for k in range(8)]

    def draw(big: pygame.Surface) -> None:
        pad = 4 * SS
        pygame.draw.ellipse(big, (*fill, 200), (pad, pad, w * SS, h * SS))
        pygame.draw.ellipse(big, (*frost, 120), (pad, pad, w * SS, h * SS), 3 * SS)
        cx, cy = pad + w * SS / 2, pad + h * SS / 2
        sx, sy = cx + ox * w * SS / 2, cy + oy * h * SS / 2
        for a in rays:
            ux, uy = math.cos(a), math.sin(a)
            # distance along the ray to the ellipse border: solve ((sx+t*ux-cx)/A)^2 + ((sy+t*uy-cy)/B)^2 = 1
            A, B = w * SS / 2 - SS, h * SS / 2 - SS
            qa = (ux / A) ** 2 + (uy / B) ** 2
            qb = 2 * ((sx - cx) * ux / A ** 2 + (sy - cy) * uy / B ** 2)
            qc = ((sx - cx) / A) ** 2 + ((sy - cy) / B) ** 2 - 1
            t = (-qb + math.sqrt(qb * qb - 4 * qa * qc)) / (2 * qa)
            pygame.draw.line(big, (*crack, 150), (sx, sy), (sx + ux * t, sy + uy * t), SS)

    return make_sprite(w + 8, h + 8, draw, bg=fill)


def decals_act_4(surface: pygame.Surface, rng: random.Random, scatter: Scatter) -> None:
    """The Still Expanse: ice plates, crack network, snow drifts, frost ferns near cracks, the frozen lake."""
    act = 4
    dark, mid, _ = config.GROUND_RAMPS[act]
    width, height = surface.get_size()
    _plates(surface, rng, 40, (150, 320), (dark, mid), 90, _ink(act, (18, 32, 46)))
    cracks: List[Segment] = []
    for x, y in scatter(10, 150):
        segs = _grow(rng, (x, y), rng.uniform(0, TAU), 160, 4)
        cracks.extend(segs)
        _stroke_layer(surface, segs, [(3, (*_ink(act, (20, 36, 52)), 120)), (1, (*_ink(act, (150, 190, 225)), 170))])
    for x, y in scatter(24):
        stamp(surface, _drift_sprite(rng.randint(60, 180), rng.randint(20, 60), act), (x, y), angle=rng.uniform(-20, 20))
    ferns = {s: _fern_sprite(s, act) for s in range(14, 31, 4)}
    near = round(120 * 0.7)
    loose = scatter(120 - near)
    for k in range(120):
        if k < near and cracks:
            x0, y0, x1, y1 = rng.choice(cracks)
            t = rng.random()
            a, r = rng.uniform(0, TAU), rng.uniform(0, 40)
            pos = (round(x0 + (x1 - x0) * t + math.cos(a) * r), round(y0 + (y1 - y0) * t + math.sin(a) * r))
        else:
            pos = loose[k - near]
        stamp(surface, ferns[rng.choice(sorted(ferns))], pos, angle=rng.uniform(0, 360))
    stamp(surface, _lake_sprite(act, rng), (rng.randint(650, 1350), rng.randint(650, 1350)))


# Acts 5-9 arrive in TASK-039; until then they draw no decals.
def _no_decals(surface: pygame.Surface, rng: random.Random, scatter: Scatter) -> None:
    """Placeholder decal pass."""


decals_act_5 = decals_act_6 = decals_act_7 = decals_act_8 = decals_act_9 = _no_decals

ACT_DECALS: Tuple[Decals, ...] = (
    decals_act_0, decals_act_1, decals_act_2, decals_act_3, decals_act_4,
    decals_act_5, decals_act_6, decals_act_7, decals_act_8, decals_act_9,
)
