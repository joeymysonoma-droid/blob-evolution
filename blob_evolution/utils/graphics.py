"""Drawing utilities and procedural texture generation."""

from __future__ import annotations

import math
import random
from typing import Dict, Optional, Tuple

import pygame

from blob_evolution.utils import terrain
from blob_evolution.utils.vector2 import Vector2

Color = Tuple[int, int, int]


class GraphicsCache:
    """Cache for pre-rendered circle surfaces."""

    def __init__(self) -> None:
        self._circles: Dict[Tuple[int, Color, int], pygame.Surface] = {}

    def get_circle(self, radius: int, color: Color, alpha: int = 255) -> pygame.Surface:
        """Get or create a cached circle surface."""
        key = (radius, color, alpha)
        if key not in self._circles:
            size = radius * 2 + 2
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            c = (*color, alpha)
            pygame.draw.circle(surf, c, (radius + 1, radius + 1), radius)
            self._circles[key] = surf
        return self._circles[key]

    def clear(self) -> None:
        """Clear the cache."""
        self._circles.clear()


_graphics_cache = GraphicsCache()


def get_graphics_cache() -> GraphicsCache:
    """Return global graphics cache."""
    return _graphics_cache


def _shade(color: Color, amount: int) -> Color:
    return tuple(max(0, min(255, c + amount)) for c in color)  # type: ignore[return-value]


def draw_blob(
    surface: pygame.Surface,
    pos: Tuple[float, float],
    radius: float,
    color: Color,
    core_color: Color,
    velocity: Optional[Vector2] = None,
    pulse: float = 0.0,
    glow: bool = False,
    rotation: float = 0.0,
    eyes: bool = True,
    look: Optional[Tuple[float, float]] = None,
    variant: str = "default",
    outline: Optional[Color] = None,
) -> None:
    """Draw a multi-layered jelly blob with optional eyes and type accents."""
    cache = get_graphics_cache()
    x, y = int(pos[0]), int(pos[1])
    r = max(4, int(radius * (1.0 + pulse)))

    squish_x, squish_y = 1.0, 1.0
    look_dx, look_dy = 0.0, 0.0
    if velocity and velocity.length() > 10:
        speed_factor = min(velocity.length() / 300.0, 0.35)
        angle = velocity.angle()
        along = 1.0 + speed_factor * 0.6
        across = 1.0 - speed_factor * 0.35
        if abs(math.cos(angle)) > abs(math.sin(angle)):
            squish_x, squish_y = along, across
        else:
            squish_x, squish_y = across, along
        look_dx = math.cos(angle)
        look_dy = math.sin(angle)
    if look is not None:
        lx, ly = look
        length = math.hypot(lx, ly)
        if length > 0.01:
            look_dx, look_dy = lx / length, ly / length

    if glow:
        glow_surf = cache.get_circle(int(r * 1.55), color, 40)
        surface.blit(glow_surf, glow_surf.get_rect(center=(x, y)))
        outer = cache.get_circle(int(r * 1.85), color, 18)
        surface.blit(outer, outer.get_rect(center=(x, y)))

    rim_color = outline or _shade(color, -40)
    rim = cache.get_circle(r + 2, rim_color, 70)
    surface.blit(rim, rim.get_rect(center=(x, y)))

    layers = [
        (r, color, 190),
        (int(r * 0.78), _shade(color, 18), 230),
        (int(r * 0.48), core_color, 255),
        (int(r * 0.22), _shade(core_color, 40), 220),
    ]

    for layer_r, layer_color, alpha in layers:
        if layer_r < 1:
            continue
        circle = cache.get_circle(layer_r, layer_color, alpha)
        scaled = pygame.transform.scale(
            circle,
            (max(2, int((layer_r * 2 + 2) * squish_x)), max(2, int((layer_r * 2 + 2) * squish_y))),
        )
        surface.blit(scaled, scaled.get_rect(center=(x, y)))

    # Membrane ripple ring
    if r >= 10:
        ring = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
        pygame.draw.circle(ring, (*_shade(color, 50), 55), (r + 3, r + 3), r - 1, 2)
        surface.blit(ring, ring.get_rect(center=(x, y)))

    # Specular highlights
    highlight_r = max(2, int(r * 0.24))
    highlight = cache.get_circle(highlight_r, (255, 255, 255), 145)
    surface.blit(
        highlight,
        (x + int(-r * 0.30) - highlight_r, y + int(-r * 0.32) - highlight_r),
    )
    hi2 = cache.get_circle(max(1, highlight_r // 2), (255, 255, 255), 80)
    surface.blit(
        hi2,
        (x + int(r * 0.18) - hi2.get_width() // 2, y + int(r * 0.12) - hi2.get_height() // 2),
    )

    if variant == "spikes" and r >= 8:
        for i in range(6):
            ang = rotation + i * (math.tau / 6) + 0.2
            tip = (
                x + int(math.cos(ang) * (r + 4)),
                y + int(math.sin(ang) * (r + 4)),
            )
            base1 = (
                x + int(math.cos(ang - 0.25) * (r * 0.7)),
                y + int(math.sin(ang - 0.25) * (r * 0.7)),
            )
            base2 = (
                x + int(math.cos(ang + 0.25) * (r * 0.7)),
                y + int(math.sin(ang + 0.25) * (r * 0.7)),
            )
            pygame.draw.polygon(surface, _shade(color, -20), [tip, base1, base2])
    elif variant == "orbs" and r >= 8:
        for i in range(3):
            ang = rotation + i * (math.tau / 3)
            ox = x + int(math.cos(ang) * r * 0.95)
            oy = y + int(math.sin(ang) * r * 0.95)
            orb = cache.get_circle(max(2, r // 5), core_color, 200)
            surface.blit(orb, orb.get_rect(center=(ox, oy)))
    elif variant == "split" and r >= 8:
        offset = max(3, int(r * 0.28))
        left = cache.get_circle(max(2, int(r * 0.28)), core_color, 210)
        right = cache.get_circle(max(2, int(r * 0.28)), _shade(core_color, 30), 210)
        surface.blit(left, left.get_rect(center=(x - offset, y)))
        surface.blit(right, right.get_rect(center=(x + offset, y)))
    elif variant == "crown" and r >= 12:
        for i in range(5):
            ang = -math.pi / 2 + (i - 2) * 0.35
            px = x + int(math.cos(ang) * r * 1.05)
            py = y + int(math.sin(ang) * r * 1.05)
            gem = cache.get_circle(max(2, r // 7), (255, 220, 140), 220)
            surface.blit(gem, gem.get_rect(center=(px, py)))
    elif variant == "shield" and r >= 8:
        arc = pygame.Surface((r * 3, r * 3), pygame.SRCALPHA)
        cx = arc.get_width() // 2
        cy = arc.get_height() // 2
        pygame.draw.arc(arc, (180, 210, 255, 200), (2, 2, r * 3 - 4, r * 3 - 4), -0.9, 0.9, 3)
        surface.blit(arc, (x - cx, y - cy))
    elif variant == "ghost" and r >= 8:
        ghost = cache.get_circle(int(r * 1.15), color, 40)
        surface.blit(ghost, ghost.get_rect(center=(x, y)))
    elif variant == "bomb" and r >= 8:
        fuse_ang = rotation
        fx = x + int(math.cos(fuse_ang) * r * 0.9)
        fy = y + int(math.sin(fuse_ang) * r * 0.9)
        pygame.draw.circle(surface, (255, 200, 80), (fx, fy), max(2, r // 6))

    if eyes and r >= 7:
        _draw_eyes(surface, x, y, r, look_dx, look_dy, angry=(variant in ("spikes", "crown")))


def _draw_eyes(
    surface: pygame.Surface,
    x: int,
    y: int,
    r: int,
    look_dx: float,
    look_dy: float,
    angry: bool = False,
) -> None:
    """Draw a pair of expressive eyes."""
    eye_sep = max(3, int(r * 0.32))
    eye_r = max(2, int(r * 0.18))
    pupil_r = max(1, int(eye_r * 0.45))
    eye_y = y - int(r * 0.12)
    pupil_off = min(eye_r - pupil_r, int(eye_r * 0.45))
    px = int(look_dx * pupil_off)
    py = int(look_dy * pupil_off)

    for side in (-1, 1):
        ex = x + side * eye_sep
        ey = eye_y
        pygame.draw.circle(surface, (250, 250, 255), (ex, ey), eye_r)
        pygame.draw.circle(surface, (20, 24, 36), (ex + px, ey + py), pupil_r)
        pygame.draw.circle(
            surface, (255, 255, 255),
            (ex + px - max(1, pupil_r // 2), ey + py - max(1, pupil_r // 2)),
            max(1, pupil_r // 3),
        )
        if angry:
            pygame.draw.line(
                surface, (40, 30, 40),
                (ex - eye_r, ey - eye_r + 1),
                (ex + eye_r, ey - eye_r // 2),
                2,
            )


def draw_health_bar(
    surface: pygame.Surface,
    x: int,
    y: int,
    width: int,
    height: int,
    current: float,
    maximum: float,
    color: Color = (239, 68, 68),
) -> None:
    """Draw a gradient health bar."""
    ratio = max(0.0, min(1.0, current / maximum)) if maximum > 0 else 0
    pygame.draw.rect(surface, (36, 48, 64), (x, y, width, height), border_radius=4)
    fill_width = int(width * ratio)
    if fill_width > 0:
        if ratio < 0.3:
            color = (255, min(120, color[1] + 40), 60)
        for i in range(fill_width):
            t = i / max(1, fill_width)
            r = int(color[0] * (1 - t * 0.25) + 20 * t)
            g = int(color[1] * (1 - t * 0.25))
            b = int(color[2] * (1 - t * 0.2))
            pygame.draw.line(surface, (r, g, b), (x + i, y + 1), (x + i, y + height - 2))
        sheen = pygame.Surface((fill_width, max(1, height // 3)), pygame.SRCALPHA)
        sheen.fill((255, 255, 255, 35))
        surface.blit(sheen, (x, y + 1))
    pygame.draw.rect(surface, (90, 110, 130), (x, y, width, height), 1, border_radius=4)


# World-edge vignette: a VIGNETTE_GRID x VIGNETTE_GRID alpha map scaled to the world size
VIGNETTE_GRID = 20
VIGNETTE_START = 0.45      # fraction of the centre-to-corner distance where darkening begins
VIGNETTE_MAX_ALPHA = 110


def _make_vignette(width: int, height: int) -> pygame.Surface:
    """Build the black edge-darkening overlay (alpha 0 in the middle, up to 110 at the corners)."""
    n = VIGNETTE_GRID
    small = pygame.Surface((n, n), pygame.SRCALPHA)
    for j in range(n):
        for i in range(n):
            d = math.hypot((i + 0.5) / n - 0.5, (j + 0.5) / n - 0.5) / 0.7071   # 0 centre .. 1 corner
            a = 0 if d < VIGNETTE_START else int(min(
                VIGNETTE_MAX_ALPHA, (d - VIGNETTE_START) / (1 - VIGNETTE_START) * VIGNETTE_MAX_ALPHA))
            small.set_at((i, j), (0, 0, 0, a))
    return pygame.transform.smoothscale(small, (width, height))


def generate_map_texture(
    width: int,
    height: int,
    base_color: Color,
    accent_color: Color,
    seed: int,
    theme_index: int = 0,
) -> pygame.Surface:
    """Procedurally generate a themed map background texture (tone-ramp macro noise, grit, decals, vignette)."""
    rng = random.Random(seed)
    ramp = terrain.ramp_for_act(theme_index)

    # Macro noise ground and grit (base stream: Random(seed))
    surface = terrain.macro_noise_ground(width, height, ramp, rng)
    terrain.add_grit(surface, ramp, rng)

    # Clustered decals and landmark (stamp stream: Random(seed ^ 0x5EED), so the ground above never shifts)
    stamp_rng = random.Random(seed ^ 0x5EED)
    scatter = terrain.make_scatter(width, height, stamp_rng)
    terrain.ACT_DECALS[max(0, min(theme_index, len(terrain.ACT_DECALS) - 1))](surface, stamp_rng, scatter)

    # Soft vignette (small alpha map scaled up)
    surface.blit(_make_vignette(width, height), (0, 0))

    return surface


def draw_star(
    surface: pygame.Surface,
    center: Tuple[float, float],
    outer: float,
    inner: float,
    color: Color,
    points: int = 5,
) -> None:
    """Draw a filled star polygon (font-independent marker)."""
    cx, cy = center
    pts = []
    for k in range(points * 2):
        r = outer if k % 2 == 0 else inner
        a = -math.pi / 2 + k * math.pi / points
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pygame.draw.polygon(surface, color, pts)


def world_to_screen(
    world_pos: Vector2,
    camera: Vector2,
    screen_width: int,
    screen_height: int,
    shake: Vector2,
) -> Tuple[int, int]:
    """Convert world coordinates to screen coordinates."""
    return (
        int(world_pos.x - camera.x + screen_width // 2 + shake.x),
        int(world_pos.y - camera.y + screen_height // 2 + shake.y),
    )


# Per-act boss color palettes (body, core)
BOSS_PALETTES: Tuple[Tuple[Color, Color], ...] = (
    ((60, 140, 70), (140, 230, 120)),      # Sprouting
    ((80, 110, 40), (160, 200, 60)),       # Rot
    ((70, 110, 180), (160, 210, 255)),     # Echoes
    ((180, 70, 30), (255, 140, 60)),       # Ash
    ((140, 180, 210), (230, 245, 255)),    # Frost
    ((190, 150, 70), (255, 220, 120)),     # Thirst
    ((120, 60, 160), (200, 130, 255)),     # Masks
    ((50, 40, 70), (120, 90, 160)),        # Silence
    ((100, 120, 200), (200, 220, 255)),    # Ascent
    ((160, 40, 120), (255, 100, 200)),     # Prime Anchor
)


def get_boss_palette(act_index: int, enraged: bool = False) -> Tuple[Color, Color]:
    """Return body/core colors for a warden of the given act."""
    idx = min(max(act_index, 0), len(BOSS_PALETTES) - 1)
    body, core = BOSS_PALETTES[idx]
    if enraged:
        return _shade(body, 40), (255, 90, 90)
    return body, core
