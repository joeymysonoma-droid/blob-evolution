"""Drawing utilities and procedural texture generation."""

from __future__ import annotations

import math
import random
from typing import Dict, Optional, Tuple

import pygame

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


def generate_map_texture(
    width: int,
    height: int,
    base_color: Color,
    accent_color: Color,
    seed: int,
    theme_index: int = 0,
) -> pygame.Surface:
    """Procedurally generate a themed map background texture."""
    rng = random.Random(seed)
    surface = pygame.Surface((width, height))
    surface.fill(base_color)

    # Soft gradient wash
    wash = pygame.Surface((width, height), pygame.SRCALPHA)
    for y in range(0, height, 6):
        t = y / max(1, height)
        shade = tuple(int(base_color[i] * (1 - t * 0.15) + accent_color[i] * t * 0.12) for i in range(3))
        pygame.draw.line(wash, (*shade, 90), (0, y), (width, y), 6)
    surface.blit(wash, (0, 0))

    # Soft membrane blobs
    for _ in range(rng.randint(70, 160)):
        bx = rng.randint(0, width)
        by = rng.randint(0, height)
        br = rng.randint(28, 110)
        shade = tuple(min(255, c + rng.randint(-25, 25)) for c in accent_color)
        alpha_surf = pygame.Surface((br * 2, br * 2), pygame.SRCALPHA)
        pygame.draw.circle(alpha_surf, (*shade, rng.randint(28, 70)), (br, br), br)
        pygame.draw.circle(alpha_surf, (*_shade(shade, 30), 25), (int(br * 0.7), int(br * 0.65)), int(br * 0.45))
        surface.blit(alpha_surf, (bx - br, by - br))

    # Speckles / grit
    for _ in range(rng.randint(800, 1800)):
        sx = rng.randint(0, width - 1)
        sy = rng.randint(0, height - 1)
        brightness = rng.randint(-35, 35)
        speckle = tuple(max(0, min(255, c + brightness)) for c in base_color)
        surface.set_at((sx, sy), speckle)

    # Theme-specific overlays
    _draw_theme_details(surface, width, height, base_color, accent_color, seed, theme_index, rng)

    # Soft vignette (sampled)
    vignette = pygame.Surface((width, height), pygame.SRCALPHA)
    cx, cy = width // 2, height // 2
    max_dist = math.hypot(cx, cy)
    step = 5
    for vy in range(0, height, step):
        for vx in range(0, width, step):
            dist = math.hypot(vx - cx, vy - cy) / max_dist
            if dist > 0.45:
                alpha = int((dist - 0.45) / 0.55 * 110)
                pygame.draw.rect(vignette, (0, 0, 0, min(110, alpha)), (vx, vy, step, step))
    surface.blit(vignette, (0, 0))

    return surface


def _draw_theme_details(
    surface: pygame.Surface,
    width: int,
    height: int,
    base_color: Color,
    accent_color: Color,
    seed: int,
    theme_index: int,
    rng: random.Random,
) -> None:
    """Draw per-act environmental flourishes."""
    if theme_index == 0:  # Verdant Rim — soft grass arcs
        for _ in range(90):
            gx = rng.randint(0, width)
            gy = rng.randint(0, height)
            gl = rng.randint(8, 22)
            green = (40 + rng.randint(0, 40), 120 + rng.randint(0, 60), 50)
            pygame.draw.arc(
                surface, green,
                (gx, gy, gl, gl * 2),
                0.2, 2.2, 1,
            )
    elif theme_index == 1:  # Sinking Garden — toxic pools + ripples
        for _ in range(18):
            px = rng.randint(40, width - 40)
            py = rng.randint(40, height - 40)
            pr = rng.randint(30, 80)
            pool = pygame.Surface((pr * 2, pr * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(pool, (60, 140, 40, 70), (0, 0, pr * 2, pr))
            pygame.draw.ellipse(pool, (90, 180, 50, 40), (pr // 3, pr // 4, pr, pr // 2), 2)
            surface.blit(pool, (px - pr, py - pr // 2))
        for y in range(0, height, 10):
            offset = int(math.sin(y * 0.04 + seed) * 18)
            pygame.draw.line(surface, (*_shade(accent_color, 20),), (offset, y), (width + offset, y), 1)
    elif theme_index == 2:  # Memory Vaults — crystal shards
        for _ in range(70):
            cx = rng.randint(0, width)
            cy = rng.randint(0, height)
            pts = [
                (cx, cy - rng.randint(12, 28)),
                (cx + rng.randint(4, 12), cy + rng.randint(6, 16)),
                (cx - rng.randint(4, 12), cy + rng.randint(6, 16)),
            ]
            crystal = (100 + rng.randint(0, 80), 170 + rng.randint(0, 50), 230)
            pygame.draw.polygon(surface, crystal, pts)
            pygame.draw.polygon(surface, (220, 240, 255), pts, 1)
    elif theme_index == 3:  # Forge Veins — embers + cracks
        for _ in range(40):
            x1 = rng.randint(0, width)
            y1 = rng.randint(0, height)
            x2 = x1 + rng.randint(-60, 60)
            y2 = y1 + rng.randint(20, 90)
            pygame.draw.line(surface, (180, 60, 20), (x1, y1), (x2, y2), 2)
            pygame.draw.line(surface, (255, 140, 40), (x1, y1), (x2, y2), 1)
        for _ in range(120):
            surface.set_at(
                (rng.randint(0, width - 1), rng.randint(0, height - 1)),
                (255, 120 + rng.randint(0, 80), 40),
            )
    elif theme_index == 4:  # Still Expanse — frost veins
        for _ in range(140):
            fx = rng.randint(0, width)
            fy = rng.randint(0, height)
            fl = rng.randint(12, 48)
            frost = (210, 230, 255)
            pygame.draw.line(surface, frost, (fx, fy), (fx + fl, fy - fl // 2), 1)
            pygame.draw.line(surface, frost, (fx + fl // 2, fy), (fx + fl // 2 + fl // 3, fy - fl // 3), 1)
    elif theme_index == 5:  # Mirage Basin — dunes + heat shimmer
        for y in range(0, height, 14):
            offset = int(math.sin(y * 0.03 + seed * 0.1) * 30)
            dune = tuple(min(255, c + 18) for c in accent_color)
            pygame.draw.line(surface, dune, (offset, y), (width + offset, y), 2)
        for _ in range(12):
            ox = rng.randint(50, width - 50)
            oy = rng.randint(50, height - 50)
            oasis = pygame.Surface((80, 40), pygame.SRCALPHA)
            pygame.draw.ellipse(oasis, (40, 140, 120, 55), (0, 0, 80, 40))
            surface.blit(oasis, (ox - 40, oy - 20))
    elif theme_index == 6:  # Dreaming Thicket — mystic swirls
        for _ in range(35):
            sx = rng.randint(0, width)
            sy = rng.randint(0, height)
            sr = rng.randint(20, 70)
            swirl = pygame.Surface((sr * 2, sr * 2), pygame.SRCALPHA)
            for a in range(0, 360, 40):
                rad = math.radians(a)
                pygame.draw.circle(
                    swirl, (160, 90, 220, 50),
                    (int(sr + math.cos(rad) * sr * 0.55), int(sr + math.sin(rad) * sr * 0.55)),
                    max(2, sr // 8),
                )
            surface.blit(swirl, (sx - sr, sy - sr))
        for y in range(0, height, 9):
            offset = int(math.sin(y * 0.06 + seed) * 22)
            pygame.draw.line(surface, (*_shade(accent_color, 25),), (offset, y), (width + offset, y), 1)
    elif theme_index == 7:  # Hollow — void wells
        for _ in range(25):
            vx = rng.randint(0, width)
            vy = rng.randint(0, height)
            vr = rng.randint(20, 70)
            well = pygame.Surface((vr * 2, vr * 2), pygame.SRCALPHA)
            pygame.draw.circle(well, (0, 0, 0, 90), (vr, vr), vr)
            pygame.draw.circle(well, (80, 60, 120, 70), (vr, vr), int(vr * 0.55), 2)
            surface.blit(well, (vx - vr, vy - vr))
    elif theme_index == 8:  # Ascending Strata — stars + light bands
        for _ in range(280):
            sx = rng.randint(0, width - 1)
            sy = rng.randint(0, height - 1)
            brightness = rng.randint(170, 255)
            surface.set_at((sx, sy), (brightness, brightness, 255))
            if rng.random() < 0.08:
                pygame.draw.circle(surface, (220, 230, 255), (sx, sy), 2)
        for i in range(6):
            y = int(height * (0.15 + i * 0.12))
            band = pygame.Surface((width, 8), pygame.SRCALPHA)
            band.fill((180, 200, 255, 28))
            surface.blit(band, (0, y))
    else:  # First Divide / Core — pulsing wound motif
        for _ in range(20):
            cx = rng.randint(width // 4, 3 * width // 4)
            cy = rng.randint(height // 4, 3 * height // 4)
            rr = rng.randint(40, 120)
            wound = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
            pygame.draw.circle(wound, (180, 40, 140, 55), (rr, rr), rr)
            pygame.draw.circle(wound, (255, 80, 180, 70), (rr, rr), int(rr * 0.4))
            surface.blit(wound, (cx - rr, cy - rr))
        for _ in range(60):
            x1 = rng.randint(0, width)
            y1 = rng.randint(0, height)
            pygame.draw.line(
                surface, (220, 60, 160),
                (x1, y1), (x1 + rng.randint(-40, 40), y1 + rng.randint(-40, 40)), 1,
            )


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
