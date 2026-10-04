"""Environmental hazard system."""

from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.utils.enums import HazardType
from blob_evolution.utils.terrain import SS, make_sprite
from blob_evolution.utils.vector2 import Vector2

TAU = math.tau
Color = Tuple[int, int, int]
Point = Tuple[float, float]


def _lerp(a: Color, b: Color, t: float) -> Color:
    return (round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t), round(a[2] + (b[2] - a[2]) * t))


def _ngon(cx: float, cy: float, radii: List[float], phase: float = 0.0) -> List[Point]:
    """Polygon points at equal angles round (cx, cy), one radius per vertex."""
    n = len(radii)
    return [(cx + math.cos(phase + k * TAU / n) * rad, cy + math.sin(phase + k * TAU / n) * rad) for k, rad in enumerate(radii)]


class HazardZone:
    """A single environmental hazard area (art is baked once per zone; behaviour is untouched)."""

    __slots__ = ("pos", "radius", "hazard_type", "phase", "damage_timer", "_sprite", "_core", "_anim")

    def __init__(self, pos: Vector2, radius: float, hazard_type: HazardType) -> None:
        self.pos = pos.copy()
        self.radius = radius
        self.hazard_type = hazard_type
        self.phase = random.uniform(0, math.pi * 2)
        self.damage_timer = 0.0
        self._sprite: Optional[pygame.Surface] = None      # static baked art, (2r + 2 pad)^2 SRCALPHA
        self._core: List[pygame.Surface] = []             # lava: cached core sizes 50% -> 60%
        self._anim: tuple = ()                            # seeded animation parameters (bubbles, sparkle vertices)

    def contains(self, point: Vector2) -> bool:
        """Check if point is inside hazard."""
        return self.pos.distance_to(point) < self.radius

    def update(self, dt: float) -> None:
        """Update animation phase."""
        self.phase += dt * 2

    def get_effects(self, dt: float) -> dict:
        """Return hazard effects when player is inside."""
        intensity = 0.5 + 0.5 * math.sin(self.phase)
        if self.hazard_type == HazardType.LAVA:
            self.damage_timer += dt
            damage = 0.0
            if self.damage_timer >= 0.5:
                self.damage_timer = 0.0
                damage = 8 * intensity
            return {"damage": damage, "speed_mult": 0.6, "regen_mult": 1.0}
        elif self.hazard_type == HazardType.ICE:
            return {"damage": 0.0, "speed_mult": 1.4, "regen_mult": 1.0}
        elif self.hazard_type == HazardType.TOXIC:
            self.damage_timer += dt
            damage = 0.0
            if self.damage_timer >= 1.0:
                self.damage_timer = 0.0
                damage = 5
            return {"damage": damage, "speed_mult": 0.9, "regen_mult": 0.0}
        return {"damage": 0.0, "speed_mult": 1.0, "regen_mult": 1.0}

    # --- baking (once per zone, never in the draw path) -------------------------------------------------------

    def _seed(self) -> int:
        """Stable per-zone seed from position, radius and type (own rng: the global random stream is never touched)."""
        kind = list(HazardType).index(self.hazard_type)
        return (int(self.pos.x) * 73856093) ^ (int(self.pos.y) * 19349663) ^ (int(self.radius) * 83492791) ^ (kind * 2654435761)

    def build(self) -> None:
        """Bake the static sprite, the lava core frames and the animation parameters (idempotent)."""
        if self._sprite is not None:
            return
        rng = random.Random(self._seed())
        pad = config.HAZARD_SPRITE_PAD
        r = int(self.radius)
        size = 2 * r + 2 * pad
        centre = size * SS / 2
        if self.hazard_type == HazardType.LAVA:
            self._sprite, self._core, self._anim = self._bake_lava(rng, size, centre, r)
        elif self.hazard_type == HazardType.TOXIC:
            self._sprite, self._anim = self._bake_toxic(rng, size, centre, r), self._bake_bubbles(rng, r, 3, (3, 7), (1.6, 1.6))
        else:
            self._sprite, self._anim = self._bake_ice(rng, size, centre, r), ()

    def _bake_bubbles(self, rng: random.Random, r: int, count: int, sizes: Tuple[int, int], periods: Tuple[float, float]) -> tuple:
        """(angle, distance fraction, radius, period, offset) per bubble, all inside 60% of the zone."""
        return tuple((rng.uniform(0, TAU), rng.uniform(0.15, 0.55), rng.randint(*sizes), rng.uniform(*periods), rng.uniform(0, 3.0))
                     for _ in range(count))

    def _bake_lava(self, rng: random.Random, size: int, c: float, r: int):
        st = config.HAZARD_STYLE["lava"]
        edge_r = (r - 2.5) * SS                                              # outline outer edge lands on the radius
        radii = [edge_r * (1.0 if k % 2 == 0 else 0.94) * (1 - rng.uniform(0, 0.015)) for k in range(20)]
        outline = _ngon(c, c, radii, rng.uniform(0, TAU))
        crack_ends = [rng.uniform(0, TAU) for _ in range(6)]
        crack_len = [edge_r * rng.uniform(0.78, 0.85) for _ in range(6)]

        def draw(big: pygame.Surface) -> None:
            pygame.draw.polygon(big, st["fill"], outline)
            pygame.draw.polygon(big, (*st["crust"], 255), outline, 5 * SS)
            pygame.draw.polygon(big, (*st["edge"], 255), outline, 2 * SS)
            for a, ln in zip(crack_ends, crack_len):
                pygame.draw.line(big, (*st["crack"], 255), (c + math.cos(a) * edge_r * 0.5, c + math.sin(a) * edge_r * 0.5),
                                 (c + math.cos(a) * ln, c + math.sin(a) * ln), SS)

        sprite = make_sprite(size, size, draw, bg=st["crust"])
        cores = []
        n = config.HAZARD_CORE_FRAMES
        for k in range(n):
            scale = 0.50 + 0.10 * k / max(1, n - 1)
            core_poly = _ngon(0, 0, [edge_r * scale * (1.0 if j % 2 == 0 else 0.9) for j in range(12)], 0.0)
            half = int(r * 0.7) + 2
            cores.append(make_sprite(2 * half, 2 * half, lambda big, poly=core_poly, h=half: pygame.draw.polygon(
                big, st["core"], [(h * SS + x, h * SS + y) for x, y in poly]), bg=st["core"][:3]))
        return sprite, cores, self._bake_bubbles(rng, r, rng.randint(3, 4), (3, 6), (1.4, 2.2))

    def _bake_toxic(self, rng: random.Random, size: int, c: float, r: int) -> pygame.Surface:
        st = config.HAZARD_STYLE["toxic"]
        centres = [(c + math.cos(k * TAU / 10 + 0.3) * 0.78 * r * SS, c + math.sin(k * TAU / 10 + 0.3) * 0.78 * r * SS) for k in range(10)]
        rings = [(rng.uniform(0, TAU), rng.uniform(0.0, 0.55), rng.randint(6, 10)) for _ in range(5)]

        def union(big: pygame.Surface, colour, shrink: float) -> None:
            pygame.draw.circle(big, colour, (c, c), max(1, (0.8 * r - shrink) * SS))
            for x, y in centres:
                pygame.draw.circle(big, colour, (x, y), max(1, (0.2 * r - shrink) * SS))

        def draw(big: pygame.Surface) -> None:
            union(big, (*st["edge"], 255), 0.0)               # 2 px outline
            union(big, (*st["rim"], 255), 2.0)                # 4 px rim
            union(big, st["fill"], 6.0)                       # translucent body (drawing replaces the pixels, no double blend)
            for a, d, rr in rings:
                pygame.draw.circle(big, st["ring"], (c + math.cos(a) * d * r * SS, c + math.sin(a) * d * r * SS), rr * SS, SS)

        return make_sprite(size, size, draw, bg=st["rim"])

    def _bake_ice(self, rng: random.Random, size: int, c: float, r: int) -> pygame.Surface:
        st = config.HAZARD_STYLE["ice"]
        hex_r = (0.97 * r - 1.5) * SS
        pts = _ngon(c, c, [hex_r] * 6)

        def draw(big: pygame.Surface) -> None:
            pygame.draw.polygon(big, st["fill"], pts)
            for k in range(6):
                pygame.draw.polygon(big, (*st["facet"], st["facet_alpha"][k % 2]), [(c, c), pts[k], pts[(k + 1) % 6]])
            pygame.draw.polygon(big, (*st["edge"], 255), pts, 2 * SS)
            for dx in (-0.25, 0.1):                          # two diagonal shine lines
                pygame.draw.line(big, st["shine"], (c + (dx - 0.18) * r * SS, c + 0.35 * r * SS),
                                 (c + (dx + 0.18) * r * SS, c - 0.35 * r * SS), SS)

        return make_sprite(size, size, draw, bg=st["fill"][:3])

    # --- drawing: cached blits plus a handful of 1 px primitives, no allocation ---------------------------------

    def draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw the hazard zone: baked sprite, then a few animated primitives (zones off screen are skipped)."""
        r = int(self.radius)
        reach = r + config.HAZARD_SPRITE_PAD
        sx = int(self.pos.x - camera.x + config.SCREEN_WIDTH // 2 + shake.x)
        sy = int(self.pos.y - camera.y + config.SCREEN_HEIGHT // 2 + shake.y)
        if sx + reach < 0 or sy + reach < 0 or sx - reach > config.SCREEN_WIDTH or sy - reach > config.SCREEN_HEIGHT:
            return
        if self._sprite is None:
            self.build()
        surface.blit(self._sprite, (sx - reach, sy - reach))
        t = self.phase / 2.0                                  # seconds of animation (phase advances at 2 rad/s)
        circle = pygame.draw.circle
        if self.hazard_type == HazardType.LAVA:
            st = config.HAZARD_STYLE["lava"]
            core = self._core[round((0.5 + 0.5 * math.sin(self.phase)) * (len(self._core) - 1))]
            surface.blit(core, (sx - core.get_width() // 2, sy - core.get_height() // 2))
            for angle, dist, big, period, offset in self._anim:       # bubbles grow 0 -> r then pop
                frac = ((t + offset) / period) % 1.0
                if frac < 0.9:
                    circle(surface, st["bubble"], (sx + round(math.cos(angle) * dist * r), sy + round(math.sin(angle) * dist * r)),
                           max(1, round(big * frac / 0.9)), 1)
        elif self.hazard_type == HazardType.TOXIC:
            st = config.HAZARD_STYLE["toxic"]
            for angle, dist, rad, period, offset in self._anim:       # bubbles rise 24 px over 1.6 s, fading into the body
                frac = ((t + offset) / period) % 1.0
                colour = _lerp(st["bubble"], st["bubble_fade"], frac)
                circle(surface, colour, (sx + round(math.cos(angle) * dist * r), sy + round(math.sin(angle) * dist * r) - round(24 * frac)),
                       rad, 1)
        else:
            on, off = config.HAZARD_SPARKLE
            cycle, into = divmod(t, on + off)
            if into < on:                                         # 4-point sparkle at a vertex that changes every cycle
                k = int((self._seed() + int(cycle) * 2654435761) % 6)
                px = sx + round(math.cos(k * TAU / 6) * 0.85 * r)
                py = sy + round(math.sin(k * TAU / 6) * 0.85 * r)
                pygame.draw.line(surface, config.HAZARD_STYLE["ice"]["spark"], (px - 4, py), (px + 4, py), 1)
                pygame.draw.line(surface, config.HAZARD_STYLE["ice"]["spark"], (px, py - 4), (px, py + 4), 1)


class HazardManager:
    """Manages all hazard zones on a map."""

    def __init__(self) -> None:
        self.zones: List[HazardZone] = []

    def generate_for_map(self, hazard_types: List[str], count: int = 5, seed: int = 0) -> None:
        """Generate hazard zones for a map."""
        self.zones.clear()
        rng = random.Random(seed)
        type_map = {
            "lava": HazardType.LAVA,
            "ice": HazardType.ICE,
            "toxic": HazardType.TOXIC,
        }
        for _ in range(count):
            htype_str = rng.choice(hazard_types) if hazard_types else "lava"
            htype = type_map.get(htype_str, HazardType.LAVA)
            pos = Vector2(rng.randint(200, config.WORLD_WIDTH - 200),
                          rng.randint(200, config.WORLD_HEIGHT - 200))
            radius = rng.randint(60, 120)
            zone = HazardZone(pos, radius, htype)
            zone.build()                                   # bake the art at map load, not in the first fight frame
            self.zones.append(zone)

    def get_player_effects(self, player_pos: Vector2, dt: float) -> dict:
        """Combine effects from all overlapping hazards."""
        total = {"damage": 0.0, "speed_mult": 1.0, "regen_mult": 1.0}
        for zone in self.zones:
            if zone.contains(player_pos):
                effects = zone.get_effects(dt)
                total["damage"] += effects["damage"]
                total["speed_mult"] *= effects["speed_mult"]
                total["regen_mult"] *= effects["regen_mult"]
        return total

    def update(self, dt: float) -> None:
        """Update all hazard zones."""
        for zone in self.zones:
            zone.update(dt)

    def draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw all hazard zones."""
        for zone in self.zones:
            zone.draw(surface, camera, shake)

    def draw_minimap(self, surface: pygame.Surface, offset: Tuple[int, int], scale: float) -> None:
        """Draw hazards on minimap: a disc for toxic, a diamond for lava, a hexagon for ice (same colours as before)."""
        ox, oy = offset
        for zone in self.zones:
            mx = int(ox + zone.pos.x * scale)
            my = int(oy + zone.pos.y * scale)
            mr = max(2, int(zone.radius * scale))
            color = config.HAZARD_MINIMAP.get(zone.hazard_type.value, (150, 150, 150))
            if zone.hazard_type == HazardType.LAVA:
                pygame.draw.polygon(surface, color, [(mx, my - mr), (mx + mr, my), (mx, my + mr), (mx - mr, my)])
            elif zone.hazard_type == HazardType.ICE:
                pygame.draw.polygon(surface, color, [(mx + math.cos(k * TAU / 6) * mr, my + math.sin(k * TAU / 6) * mr) for k in range(6)])
            else:
                pygame.draw.circle(surface, color, (mx, my), mr)
