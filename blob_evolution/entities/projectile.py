"""Combat projectile entities."""

from __future__ import annotations

from typing import Tuple

import pygame

from blob_evolution import config
from blob_evolution.utils.vector2 import Vector2


class Projectile:
    """A combat projectile fired by player or enemies."""

    __slots__ = (
        "pos", "vel", "damage", "radius", "color", "active",
        "from_player", "piercing", "lifetime",
    )

    def __init__(
        self,
        pos: Vector2,
        direction: Vector2,
        speed: float,
        damage: float,
        from_player: bool = True,
        piercing: bool = False,
    ) -> None:
        self.pos = pos.copy()
        dir_norm = direction.copy()
        dir_norm.normalize()
        self.vel = dir_norm * speed
        self.damage = damage
        self.radius = 5 if from_player else 6
        self.color: Tuple[int, int, int] = (
            config.COLOR_PROJECTILE_PLAYER if from_player else config.COLOR_PROJECTILE_ENEMY
        )
        self.active = True
        self.from_player = from_player
        self.piercing = piercing
        self.lifetime = 3.0

    def update(self, dt: float) -> None:
        """Move projectile and check bounds."""
        if not self.active:
            return
        self.pos.add(self.vel * dt)
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.active = False
            return
        margin = 50
        if (self.pos.x < -margin or self.pos.x > config.WORLD_WIDTH + margin or
                self.pos.y < -margin or self.pos.y > config.WORLD_HEIGHT + margin):
            self.active = False

    def draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw projectile on screen."""
        if not self.active:
            return
        sx = int(self.pos.x - camera.x + config.SCREEN_WIDTH // 2 + shake.x)
        sy = int(self.pos.y - camera.y + config.SCREEN_HEIGHT // 2 + shake.y)
        glow = pygame.Surface((self.radius * 5, self.radius * 5), pygame.SRCALPHA)
        pygame.draw.circle(
            glow, (*self.color, 70),
            (glow.get_width() // 2, glow.get_height() // 2), self.radius * 2,
        )
        surface.blit(glow, (sx - glow.get_width() // 2, sy - glow.get_height() // 2))
        pygame.draw.circle(surface, self.color, (sx, sy), self.radius)
        pygame.draw.circle(surface, (255, 255, 255), (sx - 1, sy - 1), max(1, self.radius // 3))

    def collides_with(self, other_pos: Vector2, other_radius: float) -> bool:
        """Check circle collision."""
        dist = self.pos.distance_to(other_pos)
        return dist < self.radius + other_radius
