"""Per-act ambient mote field (TASK-040): purely visual world-space motes drawn as prebuilt sprites.

The field never touches gameplay state and never uses the global `random` stream: it owns a seeded
random.Random, so creature / hazard / boss spawns and every seeded test are unaffected. Nothing is saved.
Motes live in the camera rect +/- AMBIENT_MARGIN and wrap inside it. A mote is a plain list (no allocation per frame):
[x, y, vx, vy, life, t0, kind, variant, phase, radius_index, orbit_angle, orbit_speed]
where kind is the layer index and t0 the field clock at spawn.
"""

from __future__ import annotations

import math
import random
from typing import List, Sequence, Tuple

import pygame

from blob_evolution import config
from blob_evolution.utils.vector2 import Vector2

Color = Tuple[int, int, int]

HALF_W = config.SCREEN_WIDTH // 2
HALF_H = config.SCREEN_HEIGHT // 2
RECT_W = config.SCREEN_WIDTH + 2 * config.AMBIENT_MARGIN
RECT_H = config.SCREEN_HEIGHT + 2 * config.AMBIENT_MARGIN
LADDER = config.AMBIENT_ALPHA_LADDER
LADDER_STEP = 255.0 / len(LADDER)       # alpha band per ladder rung (42.5)
MIN_ALPHA = 20.0                        # fainter motes are skipped
FRONT_TOP_RUNG = max(i for i, v in enumerate(LADDER) if v <= config.AMBIENT_FRONT_MAX_ALPHA)   # front: alpha 80
MAX_DT = 0.1                            # a long frame never throws motes across the field
TAU = math.tau

# Motion modes
DRIFT, ORBIT, WALK = 0, 1, 2
_MODES = {"drift": DRIFT, "orbit": ORBIT, "walk": WALK}


def _scaled(color: Color, k: float) -> Color:
    """Colour times k (used for additive sprites, where brightness stands in for alpha)."""
    return (int(color[0] * k), int(color[1] * k), int(color[2] * k))


def _lerp(a: Color, b: Color, t: float) -> Color:
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def _optimise(surface: pygame.Surface, alpha: bool) -> pygame.Surface:
    """Match the display format once (when a display exists) so blits stay cheap."""
    if pygame.display.get_surface() is None:
        return surface
    return surface.convert_alpha() if alpha else surface.convert()


def _disc_sprite(color: Color, radius: int, alpha: int, additive: bool) -> pygame.Surface:
    """Soft disc: a full-strength core and a wider halo (radius x1.8) at a third of the strength."""
    halo = max(radius + 1, int(round(radius * 1.8)))
    size = halo * 2 + 2
    centre = (halo + 1, halo + 1)
    if additive:
        surf = pygame.Surface((size, size))
        pygame.draw.circle(surf, _scaled(color, alpha / 255 / 3), centre, halo)
        pygame.draw.circle(surf, _scaled(color, alpha / 255), centre, radius)
        return _optimise(surf, False)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(surf, (*color, alpha // 3), centre, halo)
    pygame.draw.circle(surf, (*color, alpha), centre, radius)
    return _optimise(surf, True)


def _streak_sprite(color: Color, w: int, h: int, alpha: int, additive: bool) -> pygame.Surface:
    """Soft streak w x h: full-strength body, half-strength ends."""
    horizontal = w >= h
    length = w if horizontal else h
    end = max(1, length // 5)
    if additive:
        surf = pygame.Surface((w, h))
        full, half = _scaled(color, alpha / 255), _scaled(color, alpha / 510)
    else:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        full, half = (*color, alpha), (*color, alpha // 2)
    surf.fill(half)
    body = (end, 0, length - 2 * end, h) if horizontal else (0, end, w, length - 2 * end)
    surf.fill(full, body)
    return _optimise(surf, not additive)


class _Layer:
    """One kind of mote in an act: its parameters and its prebuilt sprite ladder."""

    def __init__(self, spec: dict) -> None:
        self.name: str = spec["name"]
        self.cap: int = spec["cap"]
        self.additive: bool = spec["blend"] == "add"
        self.peak: float = float(spec["peak"])
        self.shape: str = spec["shape"]
        self.size: Tuple[int, int] = tuple(spec["size"])  # type: ignore[assignment]
        self.vx: Tuple[float, float] = spec["vx"]
        self.vy: Tuple[float, float] = spec["vy"]
        self.life: Tuple[float, float] = spec["life"]
        self.mode: int = _MODES[spec["motion"]]
        self.sway_amp, self.sway_hz = spec.get("sway", (0.0, 0.0))
        self.gust_amp, self.gust_w = spec.get("gust", (0.0, 0.0))
        self.orbit_lo, self.orbit_hi, self.orbit_w = spec.get("orbit", (0.0, 0.0, 0.0))
        self.walk_max, self.walk_jitter = spec.get("walk", (0.0, 0.0))
        self.mod_lo, self.mod_hz = spec.get("mod", (1.0, 0.0))
        self.colors: Sequence[Color] = spec["colors"]
        end = spec.get("end_color")
        self.steps = config.AMBIENT_COLOR_STEPS if end else 1
        # sprites[variant][radius_index][alpha_index]; variant = colour * steps + lerp step
        self.sprites: List[List[List[pygame.Surface]]] = []
        radii = range(self.size[0], self.size[1] + 1) if self.shape == "disc" else (0,)
        self.radius_lo = self.size[0] if self.shape == "disc" else 0
        for colour in self.colors:
            for step in range(self.steps):
                tone = _lerp(colour, end, step / max(1, self.steps - 1) * 0.85) if end else colour
                rows = []
                for r in radii:
                    if self.shape == "disc":
                        rows.append([_disc_sprite(tone, r, a, self.additive) for a in LADDER])
                    else:
                        rows.append([_streak_sprite(tone, self.size[0], self.size[1], a, self.additive) for a in LADDER])
                self.sprites.append(rows)
        self.radius_count = len(radii)


class AmbientField:
    """The mote field of one act. Construct per map load; update() in PLAYING; draw_back / draw_front each frame."""

    def __init__(self, theme_index: int, seed: int = 0) -> None:
        self.theme_index = max(0, min(theme_index, len(config.AMBIENT_LAYERS) - 1))
        self.rng = random.Random(seed)
        self.layers = [_Layer(spec) for spec in config.AMBIENT_LAYERS[self.theme_index]]
        self.t = 0.0
        self._placed = False
        self.motes: List[list] = []
        for kind, layer in enumerate(self.layers):
            for _ in range(layer.cap):
                self.motes.append([0.0, 0.0, 0.0, 0.0, 1.0, 0.0, kind, 0, 0.0, 0, 0.0, 0.0])
        every = config.AMBIENT_FRONT_EVERY
        self._back = [m for i, m in enumerate(self.motes) if i % every != every - 1]
        self._front = [m for i, m in enumerate(self.motes) if i % every == every - 1]
        # act 7 rings: [x, y, t0], ring sprites by progress step
        self._ring_cfg = config.AMBIENT_RINGS.get(self.theme_index)
        self.rings: List[list] = []
        self._ring_sprites: List[pygame.Surface] = []
        self._next_ring = 0.0
        if self._ring_cfg:
            self._build_rings()
            self._next_ring = self.rng.uniform(*self._ring_cfg["every"])

    # --- setup ---------------------------------------------------------------------------------------------

    def _build_rings(self) -> None:
        cfg = self._ring_cfg
        n = config.AMBIENT_RING_STEPS
        for k in range(n):
            radius = max(1, int(cfg["radius"] * (k + 1) / n))
            alpha = int(cfg["alpha"] * (1 - (k + 0.5) / n))
            surf = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*cfg["color"], alpha), (radius + 1, radius + 1), radius, 1)
            self._ring_sprites.append(_optimise(surf, True))

    def _spawn(self, mote: list, ox: float, oy: float, fresh: bool) -> None:
        """(Re)initialise a mote at a random place in the rect; fresh motes start part-way through their life."""
        rng, layer = self.rng, self.layers[mote[6]]
        life = rng.uniform(*layer.life)
        mote[0] = ox + rng.random() * RECT_W
        mote[1] = oy + rng.random() * RECT_H
        mote[2] = rng.uniform(*layer.vx)
        mote[3] = rng.uniform(*layer.vy)
        mote[4] = life
        mote[5] = self.t - (rng.random() * life if fresh else 0.0)
        mote[7] = rng.randrange(len(layer.colors)) * layer.steps
        mote[8] = rng.random() * TAU
        mote[9] = rng.randrange(layer.radius_count)
        mote[10] = rng.random() * TAU
        mote[11] = rng.uniform(layer.orbit_lo, layer.orbit_hi)
        if layer.mode == WALK:
            mote[2] = mote[3] = 0.0

    # --- update --------------------------------------------------------------------------------------------

    def update(self, dt: float, camera: Vector2) -> None:
        """Advance every mote; motes that leave the camera rect wrap to the opposite edge, expired ones respawn."""
        dt = min(dt, MAX_DT)
        ox = camera.x - HALF_W - config.AMBIENT_MARGIN
        oy = camera.y - HALF_H - config.AMBIENT_MARGIN
        if not self._placed:
            self._placed = True
            for mote in self.motes:
                self._spawn(mote, ox, oy, True)
        self.t += dt
        t = self.t
        layers = self.layers
        rng_random = self.rng.random
        for m in self.motes:
            layer = layers[m[6]]
            if t - m[5] >= m[4]:
                self._spawn(m, ox, oy, False)
                continue
            mode = layer.mode
            if mode == DRIFT:
                k = 1.0 + layer.gust_amp * math.sin(layer.gust_w * t) if layer.gust_amp else 1.0
                m[0] += m[2] * k * dt
                m[1] += m[3] * dt
            elif mode == ORBIT:
                a = m[10] + layer.orbit_w * dt
                m[10] = a
                m[0] += (m[2] + m[11] * math.cos(a)) * dt
                m[1] += (m[3] + m[11] * math.sin(a)) * dt
            else:   # random walk with a speed cap
                top = layer.walk_max
                vx = m[2] + (rng_random() - 0.5) * layer.walk_jitter * dt * 4
                vy = m[3] + (rng_random() - 0.5) * layer.walk_jitter * dt * 4
                m[2] = top if vx > top else -top if vx < -top else vx
                m[3] = top if vy > top else -top if vy < -top else vy
                m[0] += m[2] * dt
                m[1] += m[3] * dt
            dx = m[0] - ox
            if dx < 0 or dx >= RECT_W:
                m[0] = ox + dx % RECT_W
            dy = m[1] - oy
            if dy < 0 or dy >= RECT_H:
                m[1] = oy + dy % RECT_H
        if self._ring_cfg:
            self._update_rings(ox, oy)

    def _update_rings(self, ox: float, oy: float) -> None:
        cfg = self._ring_cfg
        t = self.t
        self.rings = [r for r in self.rings if t - r[2] < cfg["life"]]
        if t >= self._next_ring and len(self.rings) < cfg["max"]:
            rng = self.rng
            self.rings.append([ox + config.AMBIENT_MARGIN + rng.random() * config.SCREEN_WIDTH,
                               oy + config.AMBIENT_MARGIN + rng.random() * config.SCREEN_HEIGHT, t])
            self._next_ring = t + rng.uniform(*cfg["every"])

    # --- draw ----------------------------------------------------------------------------------------------

    def draw_back(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw the back 75% of the motes (and the act 7 rings), behind the entities."""
        self._draw(surface, camera, shake, self._back, len(LADDER) - 1)
        if self.rings:
            self._draw_rings(surface, camera, shake)

    def draw_front(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw the front 25% of the motes, in front of the entities but never brighter than 90 alpha (ladder rung 80)."""
        self._draw(surface, camera, shake, self._front, FRONT_TOP_RUNG)

    def _draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2, motes: List[list], top: int) -> None:
        bx = HALF_W - camera.x + shake.x
        by = HALF_H - camera.y + shake.y
        t = self.t
        layers = self.layers
        fade = config.AMBIENT_FADE
        add = pygame.BLEND_RGB_ADD
        sw, sh = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
        blit = surface.blit
        for m in motes:
            layer = layers[m[6]]
            age = t - m[5]
            life = m[4]
            e = (age if age < life - age else life - age) / fade
            if e <= 0:
                continue
            a = layer.peak if e >= 1 else layer.peak * e
            if layer.mod_hz:
                a *= layer.mod_lo + (1 - layer.mod_lo) * (0.5 + 0.5 * math.sin(TAU * layer.mod_hz * t + m[8]))
            if a < MIN_ALPHA:
                continue
            rung = int(a / LADDER_STEP)
            if rung > top:
                rung = top
            variant = m[7]
            if layer.steps > 1:
                variant += min(layer.steps - 1, int(age / life * layer.steps))
            sprite = layer.sprites[variant][m[9]][rung]
            x = m[0]
            if layer.sway_amp:
                x += layer.sway_amp * math.sin(TAU * layer.sway_hz * t + m[8])
            sx = int(x + bx) - sprite.get_width() // 2
            sy = int(m[1] + by) - sprite.get_height() // 2
            if -20 < sx < sw and -20 < sy < sh:
                if layer.additive:
                    blit(sprite, (sx, sy), special_flags=add)
                else:
                    blit(sprite, (sx, sy))

    def _draw_rings(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        cfg = self._ring_cfg
        bx = HALF_W - camera.x + shake.x
        by = HALF_H - camera.y + shake.y
        n = len(self._ring_sprites)
        for r in self.rings:
            k = min(n - 1, int((self.t - r[2]) / cfg["life"] * n))
            sprite = self._ring_sprites[k]
            surface.blit(sprite, (int(r[0] + bx) - sprite.get_width() // 2, int(r[1] + by) - sprite.get_height() // 2))

    # --- inspection ----------------------------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Number of motes in the field (constant: the sum of the layer caps)."""
        return len(self.motes)
