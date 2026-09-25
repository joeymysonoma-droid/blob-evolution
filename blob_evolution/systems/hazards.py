"""Environmental hazard system."""

from __future__ import annotations

import math
import random
from typing import List, Tuple

import pygame

from blob_evolution import config
from blob_evolution.utils.enums import HazardType
from blob_evolution.utils.vector2 import Vector2


class HazardZone:
    """A single environmental hazard area."""

    __slots__ = ("pos", "radius", "hazard_type", "phase", "damage_timer")

    def __init__(self, pos: Vector2, radius: float, hazard_type: HazardType) -> None:
        self.pos = pos.copy()
        self.radius = radius
        self.hazard_type = hazard_type
        self.phase = random.uniform(0, math.pi * 2)
        self.damage_timer = 0.0

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

    def draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw animated hazard zone."""
        sx = int(self.pos.x - camera.x + config.SCREEN_WIDTH // 2 + shake.x)
        sy = int(self.pos.y - camera.y + config.SCREEN_HEIGHT // 2 + shake.y)
        intensity = 0.5 + 0.5 * math.sin(self.phase)
        r = int(self.radius)

        colors = {
            HazardType.LAVA: (200, int(50 + 50 * intensity), 20, int(80 + 40 * intensity)),
            HazardType.ICE: (100, int(180 + 40 * intensity), 255, int(60 + 30 * intensity)),
            HazardType.TOXIC: (50, int(180 + 50 * intensity), 50, int(70 + 30 * intensity)),
        }
        color = colors.get(self.hazard_type, (100, 100, 100, 80))
        hazard_surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(hazard_surf, color, (r, r), r)
        inner_r = int(r * 0.7 * intensity)
        inner_color = (*color[:3], int(color[3] * 0.5))
        pygame.draw.circle(hazard_surf, inner_color, (r, r), inner_r)
        surface.blit(hazard_surf, (sx - r, sy - r))


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
            self.zones.append(HazardZone(pos, radius, htype))

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
        """Draw hazards on minimap."""
        colors = {
            HazardType.LAVA: (255, 80, 30),
            HazardType.ICE: (100, 200, 255),
            HazardType.TOXIC: (80, 255, 80),
        }
        ox, oy = offset
        for zone in self.zones:
            mx = int(ox + zone.pos.x * scale)
            my = int(oy + zone.pos.y * scale)
            mr = max(2, int(zone.radius * scale))
            color = colors.get(zone.hazard_type, (150, 150, 150))
            pygame.draw.circle(surface, color, (mx, my), mr)
