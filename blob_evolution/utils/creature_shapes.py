"""TASK-046 reference implementation: per-type enemy silhouettes (visual only).

Drop-in as blob_evolution/utils/creature_shapes.py.  Everything is baked to
cached SRCALPHA sprites (lazy, bounded); per frame a creature costs one or two
blits plus one circle.  No hitbox / stat / AI is touched.
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.utils.vector2 import Vector2

Color = Tuple[int, int, int]

# 60% toward white from each body colour (>= 3.8:1 vs every act LIGHT ground tone).
RIM: Dict[str, Color] = {
    "BASIC": (241, 177, 177), "SHOOTER": (233, 193, 173), "SPLITTER": (225, 173, 225),
    "CHARGER": (233, 173, 173), "SHIELDER": (189, 205, 233), "ORBITER": (241, 225, 177),
    "BOMBER": (245, 189, 169), "PHANTOM": (201, 193, 217), "LEECH": (235, 231, 223),
}
DARK_FILL: Dict[str, Color] = {
    "SHOOTER": (92, 48, 24), "CHARGER": (104, 18, 28), "ORBITER": (255, 230, 120),
}
SHIELD_FILL: Color = (170, 205, 255)
SHIELD_EDGE: Color = (20, 32, 64)
FUSE: Color = (150, 100, 50)
SPARK: Color = (255, 230, 120)
BLAST: Color = (220, 50, 40)
WHITE: Color = (255, 255, 255)

N_AIM = config.ENEMY_AIM_STEPS                  # shooter / charger aim steps (11.25 deg)
N_SHIELD = config.ENEMY_SHIELD_STEPS
N_ORBIT = config.ENEMY_ORBIT_STEPS              # 3 satellites repeat every 120 deg -> 10 deg steps
N_TENDRIL = config.ENEMY_TENDRIL_PHASES
MAX_SPRITES = config.ENEMY_SPRITE_CACHE_MAX

UNDER_KINDS = frozenset({"BOMBER", "SPLITTER", "PHANTOM"})                       # kinds with something behind the body
OVER_KINDS = frozenset({"SHOOTER", "CHARGER", "SHIELDER", "ORBITER", "SPLITTER", "BOMBER", "LEECH"})   # kinds with something in front

Sprite = Tuple[pygame.Surface, int, int]                      # (cropped surface, x offset, y offset from the centre it is drawn at)
_cache: Dict[tuple, Sprite] = {}


def cache_size() -> int:
    """Number of cached sprites (bounded by MAX_SPRITES)."""
    return len(_cache)


def _put(key: tuple, surf: pygame.Surface) -> Sprite:
    """Store surf cropped to its visible pixels (less to blit, less memory); the offset keeps it centred on the draw point."""
    if len(_cache) >= MAX_SPRITES:
        _cache.clear()
    rect = surf.get_bounding_rect(1)
    spr = (surf.subsurface(rect).copy(), rect.x - surf.get_width() // 2, rect.y - surf.get_height() // 2)
    _cache[key] = spr
    return spr


def _canvas(r: int) -> Tuple[pygame.Surface, int]:
    half = int(r * 1.8) + 4
    return pygame.Surface((half * 2, half * 2), pygame.SRCALPHA), half


def _pt(cx: float, cy: float, ang: float, d: float) -> Tuple[int, int]:
    return int(cx + math.cos(ang) * d), int(cy + math.sin(ang) * d)


def _poly(s: pygame.Surface, fill: Color, edge: Color, pts) -> None:
    pygame.draw.polygon(s, fill, pts)
    pygame.draw.polygon(s, edge, pts, 1)


# ---------------------------------------------------------------- bakers
def _bake_barrel(r: int, a: float, flash: bool) -> pygame.Surface:
    """Dark barrel pointing along angle a (SHOOTER)."""
    s, c = _canvas(r)
    f, p = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
    w = max(2.5, 0.28 * r)
    d0, d1 = 0.85 * r, 1.6 * r
    pts = [(c + f[0] * d + p[0] * sw * w, c + f[1] * d + p[1] * sw * w)
           for d, sw in ((d0, -1), (d0, 1), (d1, 1), (d1, -1))]
    fill = WHITE if flash else DARK_FILL["SHOOTER"]
    _poly(s, fill, WHITE if flash else RIM["SHOOTER"], pts)
    tip = (int(c + f[0] * (d1 - 1)), int(c + f[1] * (d1 - 1)))
    pygame.draw.circle(s, (255, 200, 120), tip, max(1, int(0.12 * r)))
    return s


def _bake_horns(r: int, a: float, flash: bool) -> pygame.Surface:
    """Three dark horns, one forward on angle a (CHARGER)."""
    s, c = _canvas(r)
    fill = WHITE if flash else DARK_FILL["CHARGER"]
    edge = WHITE if flash else RIM["CHARGER"]
    for off, length in ((0.0, 1.75), (2.35, 1.45), (-2.35, 1.45)):
        ang = a + off
        pts = [_pt(c, c, ang - 0.5, 0.85 * r), _pt(c, c, ang, length * r),
               _pt(c, c, ang + 0.5, 0.85 * r)]
        _poly(s, fill, edge, pts)
    return s


def _bake_crescent(r: int, a: float, thick: float, flash: bool) -> pygame.Surface:
    """Bright plate in front on angle a (SHIELDER)."""
    s, c = _canvas(r)
    r_in, r_out = 1.12 * r, (1.12 + thick) * r
    steps = 7
    arc = [(-0.95 + 1.9 * i / (steps - 1)) for i in range(steps)]
    pts = [_pt(c, c, a + t, r_out) for t in arc] + [_pt(c, c, a + t, r_in) for t in reversed(arc)]
    _poly(s, WHITE if flash else SHIELD_FILL, WHITE if flash else SHIELD_EDGE, pts)
    return s


def _bake_satellites(r: int, a: float, flash: bool) -> pygame.Surface:
    """Three satellites circling the body (ORBITER)."""
    s, c = _canvas(r)
    sr = max(3, int(0.26 * r))
    for k in range(3):
        x, y = _pt(c, c, a + k * math.tau / 3, 1.5 * r)
        pygame.draw.circle(s, (60, 45, 10), (x, y), sr + 1)
        pygame.draw.circle(s, WHITE if flash else DARK_FILL["ORBITER"], (x, y), sr)
    return s


def _bake_bulbs(r: int, flash: bool) -> pygame.Surface:
    """Two side bulbs behind the body (SPLITTER)."""
    s, c = _canvas(r)
    body = WHITE if flash else (180, 50, 180)
    rim = WHITE if flash else RIM["SPLITTER"]
    br = int(0.6 * r)
    for sx in (-1, 1):
        pos = (c + int(sx * 0.9 * r), c)
        pygame.draw.circle(s, body, pos, br)
        pygame.draw.circle(s, rim, pos, br, 2)
    return s


def _bake_groove(r: int, flash: bool) -> pygame.Surface:
    """Dark groove down the middle (SPLITTER)."""
    s, c = _canvas(r)
    pygame.draw.line(s, (255, 255, 255) if flash else (60, 10, 60),
                     (c, c - int(0.75 * r)), (c, c + int(0.75 * r)), 2)
    return s


def _bake_fuse(r: int, spark_big: bool, flash: bool) -> pygame.Surface:
    """Capped fuse with a spark on top (BOMBER)."""
    s, c = _canvas(r)
    a = (c + 0.15 * r, c - 0.95 * r)
    b = (c + 0.5 * r, c - 1.65 * r)
    cap = (int(c + 0.1 * r), int(c - 0.95 * r))
    pygame.draw.line(s, (40, 25, 10), a, b, 5)
    pygame.draw.line(s, WHITE if flash else FUSE, a, b, 3)
    pygame.draw.circle(s, RIM["BOMBER"], cap, max(3, int(0.26 * r)) + 1)
    pygame.draw.circle(s, WHITE if flash else (70, 45, 28), cap, max(3, int(0.26 * r)))
    pygame.draw.circle(s, SPARK, (int(b[0]), int(b[1])), 4 if spark_big else 3)
    return s


def _bake_leech(r: int, phase: int, flash: bool) -> pygame.Surface:
    """Four wriggling tendrils and two fangs (LEECH)."""
    s, c = _canvas(r)
    col = WHITE if flash else RIM["LEECH"]
    for k in range(4):
        base = math.pi / 4 + k * math.pi / 2
        pts = []
        for i in range(4):
            d = (0.9 + 0.22 * i) * r
            wob = math.sin(phase / N_TENDRIL * math.tau + k * 1.7 + i * 0.9) * 0.2 * r * (i / 3)
            ang = base + wob / max(d, 1.0)
            pts.append(_pt(c, c, ang, d))
        pygame.draw.lines(s, (40, 36, 30), False, pts, 5)
        pygame.draw.lines(s, col, False, pts, 3)
    for sx in (-1, 1):                       # two fangs pointing down
        ang = math.pi / 2 + sx * 0.38
        pts = [_pt(c, c, ang - 0.14, 0.9 * r), _pt(c, c, ang, 1.32 * r), _pt(c, c, ang + 0.14, 0.9 * r)]
        _poly(s, WHITE if flash else (250, 248, 240), (40, 36, 30), pts)
    return s


def _bake_blast(q: int) -> pygame.Surface:
    s = pygame.Surface((q * 2 + 4, q * 2 + 4), pygame.SRCALPHA)
    pygame.draw.circle(s, (*BLAST, config.ENEMY_BLAST_ALPHA[0]), (q + 2, q + 2), q)
    pygame.draw.circle(s, (*BLAST, config.ENEMY_BLAST_ALPHA[1]), (q + 2, q + 2), q, 2)
    return s


def _bake_disc(radius: int, color: Color, alpha: int) -> pygame.Surface:
    s = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
    pygame.draw.circle(s, (*color, alpha), (radius + 1, radius + 1), radius)
    return s


def _bake_ring(radius: int) -> pygame.Surface:
    s = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
    pygame.draw.circle(s, (255, 80, 80, 90), (radius + 4, radius + 4), radius, 3)
    return s


def _get(key: tuple, fn, *args) -> Sprite:
    """Cached sprite for key, baked lazily."""
    s = _cache.get(key)
    return s if s is not None else _put(key, fn(*args))


def _blit_c(dst: pygame.Surface, spr: Sprite, x: float, y: float) -> None:
    """Blit a cached sprite centred on (x, y)."""
    dst.blit(spr[0], (int(x) + spr[1], int(y) + spr[2]))


def draw_telegraph(dst: pygame.Surface, sx: float, sy: float, size: float) -> None:
    """Blit the cached charger telegraph ring (replaces the per-frame Surface of the old draw)."""
    radius = int(size * 1.6)
    _blit_c(dst, _get(("ring", radius), _bake_ring, radius), sx, sy)


# ---------------------------------------------------------------- public API
def draw_under(dst: pygame.Surface, kind: str, sx: float, sy: float, size: float, face: Vector2, vel: Vector2,
               fuse_timer: float, explosion_radius: float, flash: bool, ticks_ms: int) -> None:
    """Draw what sits behind the body (blast disc, bulbs, wisps); call before the contact shadow and draw_blob."""
    r = max(6, int(size))
    if kind == "BOMBER" and fuse_timer < 1.0:
        q = max(8, (int(explosion_radius) + 2) // 4 * 4)       # blast radius in steps of 4 px
        _blit_c(dst, _get(("blast", q), _bake_blast, q), sx, sy)
    elif kind == "SPLITTER":
        _blit_c(dst, _get(("bulbs", r, flash), _bake_bulbs, r, flash), sx, sy)
    elif kind == "PHANTOM":
        vx, vy = (vel.x, vel.y) if (vel.x * vel.x + vel.y * vel.y) > 25 else (face.x, face.y)
        n = math.hypot(vx, vy) or 1.0
        bx, by = -vx / n, -vy / n
        px, py = -by, bx
        t = ticks_ms * 0.0044            # 0.7 Hz sway
        for k, (d, rr, al) in enumerate(((0.9, 0.55, 150), (1.3, 0.4, 100), (1.65, 0.25, 60))):
            sway = math.sin(t + k * 1.3) * 0.18 * r
            rad = max(2, int(rr * r))
            _blit_c(dst, _get(("disc", rad, al), _bake_disc, rad, (120, 100, 160), al),
                    sx + bx * d * r + px * sway, sy + by * d * r + py * sway)


def draw_over(dst: pygame.Surface, kind: str, sx: float, sy: float, size: float, face: Vector2,
              orbit_angle: float, shield_frac: float, fuse_timer: float, flash: bool, ticks_ms: int) -> None:
    """Draw the extras in front of the body (barrel, horns, plate, satellites, fuse, tendrils); call after draw_blob and the rim."""
    r = max(6, int(size))
    a = math.atan2(face.y, face.x)
    if kind == "SHOOTER":
        i = round(a / math.tau * N_AIM) % N_AIM
        spr = _get(("barrel", r, i, flash), _bake_barrel, r, i * math.tau / N_AIM, flash)
    elif kind == "CHARGER":
        i = round(a / math.tau * N_AIM) % N_AIM
        spr = _get(("horns", r, i, flash), _bake_horns, r, i * math.tau / N_AIM, flash)
    elif kind == "SHIELDER":
        if shield_frac <= 0:
            return
        i = round(a / math.tau * N_SHIELD) % N_SHIELD
        thin = shield_frac < 0.5
        spr = _get(("crescent", r, i, thin, flash), _bake_crescent, r,
                   i * math.tau / N_SHIELD, 0.22 if thin else 0.4, flash)
    elif kind == "ORBITER":
        step = math.tau / 3 / N_ORBIT
        i = int(round((orbit_angle % (math.tau / 3)) / step)) % N_ORBIT
        spr = _get(("sats", r, i, flash), _bake_satellites, r, i * step, flash)
    elif kind == "SPLITTER":
        spr = _get(("groove", r, flash), _bake_groove, r, flash)
    elif kind == "BOMBER":
        spr = _get(("fuse", r, int(max(fuse_timer, 0) * 2) % 2 == 0, flash),
                   _bake_fuse, r, int(max(fuse_timer, 0) * 2) % 2 == 0, flash)
    elif kind == "LEECH":
        ph = int(ticks_ms / 1000.0 * 0.7 * N_TENDRIL) % N_TENDRIL      # 0.7 Hz loop
        spr = _get(("leech", r, ph, flash), _bake_leech, r, ph, flash)
    else:
        return
    _blit_c(dst, spr, sx, sy)


# ---------------------------------------------------------------- phased phantom buffer
SCRATCH = 160
_scratch: Optional[pygame.Surface] = None


def _phase_rect(size: float) -> pygame.Rect:
    """The part of the scratch buffer a creature of this size can touch (glow 1.55 r, rim, blob layers), centred in it."""
    half = min(SCRATCH // 2, int(size * 1.7) + 4)
    return pygame.Rect(SCRATCH // 2 - half, SCRATCH // 2 - half, half * 2, half * 2)


def phase_scratch(size: float = 30.0) -> pygame.Surface:
    """The one shared, cleared buffer a phased phantom's body is drawn into (a whole-surface fill is a memset: far cheaper than a rect fill)."""
    global _scratch
    if _scratch is None:
        _scratch = pygame.Surface((SCRATCH, SCRATCH), pygame.SRCALPHA)
    _scratch.fill((0, 0, 0, 0))
    return _scratch


def blit_phased(dst: pygame.Surface, sx: float, sy: float, size: float = 30.0) -> None:
    """Blit the phased phantom buffer see-through (alpha 110) centred on (sx, sy)."""
    scratch = _scratch if _scratch is not None else phase_scratch(size)
    scratch.set_alpha(config.ENEMY_PHASED_ALPHA)
    rect = _phase_rect(size)
    dst.blit(scratch, (int(sx) - SCRATCH // 2 + rect.x, int(sy) - SCRATCH // 2 + rect.y), rect)
