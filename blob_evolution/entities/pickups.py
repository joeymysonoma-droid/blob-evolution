"""XP orbs and collectible pickups."""

from __future__ import annotations

import math
from typing import Tuple

import pygame

from blob_evolution import config
from blob_evolution.utils.vector2 import Vector2


class XPOrb:
    """Experience orb dropped by defeated creatures."""

    __slots__ = ("pos", "vel", "value", "radius", "active", "lifetime", "bob_phase")

    def __init__(self, pos: Vector2, value: int = 10) -> None:
        self.pos = pos.copy()
        self.vel = Vector2()
        self.value = value
        self.radius = 6 + min(value // 20, 8)
        self.active = True
        self.lifetime = 30.0
        self.bob_phase = 0.0

    def update(self, dt: float, player_pos: Vector2, magnet_radius: float) -> None:
        """Update orb with magnet attraction."""
        if not self.active:
            return
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.active = False
            return
        self.bob_phase += dt * 4
        dist = self.pos.distance_to(player_pos)
        if dist < magnet_radius and dist > 1:
            direction = (player_pos - self.pos).copy()
            direction.normalize()
            speed = min(400, (magnet_radius - dist) * 3)
            self.vel = direction * speed
        self.pos.add(self.vel * dt)
        self.vel.scale(0.9)

    def draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw XP orb with bobbing animation."""
        if not self.active:
            return
        bob = math.sin(self.bob_phase) * 3
        sx = int(self.pos.x - camera.x + config.SCREEN_WIDTH // 2 + shake.x)
        sy = int(self.pos.y - camera.y + config.SCREEN_HEIGHT // 2 + shake.y + bob)
        color = config.COLOR_XP
        glow = pygame.Surface((self.radius * 4, self.radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(
            glow, (*color, 55),
            (glow.get_width() // 2, glow.get_height() // 2), self.radius * 2,
        )
        surface.blit(glow, (sx - glow.get_width() // 2, sy - glow.get_height() // 2))
        pygame.draw.circle(surface, color, (sx, sy), self.radius)
        pygame.draw.circle(surface, (255, 245, 180), (sx - 2, sy - 2), max(1, self.radius // 3))

    def collides_with(self, other_pos: Vector2, other_radius: float) -> bool:
        """Check collection collision."""
        return self.pos.distance_to(other_pos) < self.radius + other_radius
