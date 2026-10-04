"""Depth layers (TASK-041): a half-speed fog / parallax layer and a cached screen-space light overlay.

Both layers are built once per map load from config (FOG_LAYERS, LIGHT_OVERLAYS) and only blitted each frame. They
are purely visual: the fog uses its own seeded random.Random (never the global stream), nothing is saved, and every
Surface is allocated at build time, never per frame. config.GFX_LAYERS turns both off.
"""

from __future__ import annotations

import math
import random
from typing import Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.utils.vector2 import Vector2

Color = Tuple[int, int, int]


def _optimise(surface: pygame.Surface, alpha: bool) -> pygame.Surface:
    """Match the display format once (when a display exists) so per-frame blits stay cheap."""
    if pygame.display.get_surface() is None:
        return surface
    return surface.convert_alpha() if alpha else surface.convert()


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3 - 2 * t)


def _groups(theme_index: int) -> list:
    return config.FOG_LAYERS[max(0, min(theme_index, len(config.FOG_LAYERS) - 1))]


def fog_is_additive(theme_index: int) -> bool:
    """True for the act 2 caustic light, which is drawn with BLEND_RGB_ADD."""
    return _groups(theme_index)[0]["kind"] == "caustic"


# --- fog ----------------------------------------------------------------------------------------------------

def _soft_sprite(kind: str, color: Color, alpha: int, size: Tuple[int, int]) -> pygame.Surface:
    """A filled circle / ellipse plus a larger one at a third of the alpha for a soft edge, on its own SRCALPHA."""
    w, h = size
    halo_w, halo_h = int(w * config.FOG_HALO), int(h * config.FOG_HALO)
    sprite = pygame.Surface((halo_w + 2, halo_h + 2), pygame.SRCALPHA)
    cx, cy = halo_w // 2 + 1, halo_h // 2 + 1
    if kind == "ellipse":
        pygame.draw.ellipse(sprite, (*color, alpha // 3), (cx - halo_w // 2, cy - halo_h // 2, halo_w, halo_h))
        pygame.draw.ellipse(sprite, (*color, alpha), (cx - w // 2, cy - h // 2, w, h))
    else:
        pygame.draw.circle(sprite, (*color, alpha // 3), (cx, cy), halo_w // 2)
        pygame.draw.circle(sprite, (*color, alpha), (cx, cy), w // 2)
    return sprite


def _stamp_wrapped(tile: pygame.Surface, sprite: pygame.Surface, cx: int, cy: int) -> None:
    """Blit sprite centred on (cx, cy) at every +/- tile offset it touches, so the tile wraps seamlessly."""
    size = tile.get_width()
    x0, y0 = cx - sprite.get_width() // 2, cy - sprite.get_height() // 2
    for dx in (-size, 0, size):
        for dy in (-size, 0, size):
            x, y = x0 + dx, y0 + dy
            if x < size and y < size and x + sprite.get_width() > 0 and y + sprite.get_height() > 0:
                tile.blit(sprite, (x, y))


def _caustic_lines(tile: pygame.Surface, group: dict, rng: random.Random) -> None:
    """Wavy 1 px lines whose brightness stands in for alpha (the tile is added to the screen)."""
    size = tile.get_width()
    lo, hi = group["alpha"]
    for _ in range(group["n"]):
        tone = tuple(int(c * rng.uniform(lo, hi) / 255) for c in group["color"])
        base = rng.uniform(0, size)
        amp = rng.uniform(6, 16)
        cycles = rng.randint(1, 3)           # whole cycles per tile keep the line seamless in x
        phase = rng.uniform(0, math.tau)
        pts = [(x, base + amp * math.sin(math.tau * cycles * x / size + phase)) for x in range(-8, size + 16, 8)]
        for dy in (-size, 0, size):
            pygame.draw.lines(tile, tone, False, [(x, y + dy) for x, y in pts], 1)


def build_fog(theme_index: int, seed: int) -> Optional[pygame.Surface]:
    """Build the act's fog: a seamless 512x512 tile pre-tiled to (screen + 512) so one blit covers the screen."""
    if not config.GFX_LAYERS:
        return None
    rng = random.Random(seed)
    size = config.FOG_TILE
    additive = fog_is_additive(theme_index)
    tile = pygame.Surface((size, size)) if additive else pygame.Surface((size, size), pygame.SRCALPHA)
    for group in _groups(theme_index):
        if group["kind"] == "caustic":
            _caustic_lines(tile, group, rng)
            continue
        for _ in range(group["n"]):
            alpha = rng.randint(*group["alpha"])
            if group["kind"] == "ellipse":
                sprite = _soft_sprite("ellipse", group["color"], alpha, group["size"])
            else:
                r = rng.randint(*group["radius"])
                sprite = _soft_sprite("blob", group["color"], alpha, (r * 2, r * 2))
            _stamp_wrapped(tile, sprite, rng.randrange(size), rng.randrange(size))
    full = (config.SCREEN_WIDTH + size, config.SCREEN_HEIGHT + size)
    fog = pygame.Surface(full) if additive else pygame.Surface(full, pygame.SRCALPHA)
    for x in range(0, full[0], size):
        for y in range(0, full[1], size):
            fog.blit(tile, (x, y))
    return _optimise(fog, not additive)


# --- screen-space light overlay ---------------------------------------------------------------------------------

def build_overlay(tint: Color, max_alpha: float) -> pygame.Surface:
    """Screen-sized SRCALPHA overlay: alpha 0 in the middle, up to max_alpha at the edges (16x10 grid, smoothscaled)."""
    gw, gh = config.LIGHT_GRID
    small = pygame.Surface((gw, gh), pygame.SRCALPHA)
    cap = min(255.0, max_alpha)
    for j in range(gh):
        for i in range(gw):
            nx, ny = ((i + 0.5) / gw - 0.5) * 2, ((j + 0.5) / gh - 0.5) * 2
            d = math.hypot(nx, ny) / math.sqrt(2)       # 0 centre .. 1 corner of the screen ellipse
            small.set_at((i, j), (*tint, round(cap * _smoothstep(config.LIGHT_START, 1.0, d))))
    return _optimise(pygame.transform.smoothscale(small, (config.SCREEN_WIDTH, config.SCREEN_HEIGHT)), True)


def build_vignette(theme_index: int, scale: float = 1.0) -> Optional[pygame.Surface]:
    """The act's light overlay (tint and max alpha per act), optionally with max alpha times scale."""
    if not config.GFX_LAYERS:
        return None
    tint, max_alpha = config.LIGHT_OVERLAYS[max(0, min(theme_index, len(config.LIGHT_OVERLAYS) - 1))]
    return build_overlay(tint, max_alpha * scale)


def _wave(t: float, hz: float) -> float:
    """Smooth 0..1..0 pulse at hz (0 at t = 0), a raised cosine so it never flashes harder than its rate."""
    return 0.5 - 0.5 * math.cos(math.tau * hz * t)


class DepthLayers:
    """The fog and light overlay of one map. Construct per map load; update() while PLAYING; blit each frame."""

    def __init__(self, theme_index: int, seed: int = 0) -> None:
        self.theme_index = max(0, min(theme_index, len(config.LIGHT_OVERLAYS) - 1))
        self.fog = build_fog(self.theme_index, seed)
        self.fog_additive = fog_is_additive(self.theme_index)
        # act 9 is baked at the top of its heartbeat; set_alpha dims it to HEARTBEAT low/high at the bottom
        self.vignette = build_vignette(self.theme_index, config.HEARTBEAT[1] if self.theme_index == 9 else 1.0)
        self.t = 0.0
        self._red: Optional[pygame.Surface] = None    # low-HP overlay, built once on first use

    def update(self, dt: float) -> None:
        """Advance the pulse clock (only called while PLAYING, so pulses freeze with the game)."""
        self.t += dt

    def blit_fog(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Blit the fog at half the camera speed (plus the shake, like the ground); skipped when there is none."""
        if self.fog is None:
            return
        size = config.FOG_TILE
        x = -((camera.x * config.FOG_PARALLAX - shake.x) % size)
        y = -((camera.y * config.FOG_PARALLAX - shake.y) % size)
        if self.fog_additive:
            surface.blit(self.fog, (int(x), int(y)), special_flags=pygame.BLEND_RGB_ADD)
        else:
            surface.blit(self.fog, (int(x), int(y)))

    def overlay_alpha(self, hp_ratio: float) -> int:
        """Surface alpha (0..255) the overlay is blitted with: 255 normally, pulsing for low HP and the act 9 heartbeat."""
        if hp_ratio < config.LOW_HP_RATIO:
            lo, hi, hz = config.LOW_HP_PULSE
            return round(255 * (lo + (hi - lo) * _wave(self.t, hz)))
        if self.theme_index == 9:
            lo, hi, hz = config.HEARTBEAT
            return round(255 * (lo / hi + (1 - lo / hi) * _wave(self.t, hz)))
        return 255

    def blit_vignette(self, surface: pygame.Surface, hp_ratio: float = 1.0) -> None:
        """Blit the light overlay (red and pulsing when HP is low, heartbeat in act 9); skipped when there is none."""
        if self.vignette is None:
            return
        surf = self.vignette
        if hp_ratio < config.LOW_HP_RATIO:
            if self._red is None:
                self._red = build_overlay(*config.LOW_HP_OVERLAY)
            surf = self._red
        alpha = self.overlay_alpha(hp_ratio)
        if alpha != 255 or surf.get_alpha() != 255:
            surf.set_alpha(alpha)
        surface.blit(surf, (0, 0))
