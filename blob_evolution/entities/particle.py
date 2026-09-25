"""Particle effects system with pooling."""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.utils.enums import ParticleType
from blob_evolution.utils.vector2 import Vector2


class Particle:
    """Single physics-based particle."""

    __slots__ = (
        "pos", "vel", "color", "size", "lifetime", "max_lifetime",
        "ptype", "active", "gravity", "bounce",
    )

    def __init__(self) -> None:
        self.pos = Vector2()
        self.vel = Vector2()
        self.color: Tuple[int, int, int] = (255, 255, 255)
        self.size: float = 3.0
        self.lifetime: float = 0.0
        self.max_lifetime: float = 0.5
        self.ptype: ParticleType = ParticleType.EXPLOSION
        self.active: bool = False
        self.gravity: bool = True
        self.bounce: bool = False

    def spawn(
        self,
        pos: Vector2,
        vel: Vector2,
        color: Tuple[int, int, int],
        size: float,
        lifetime: float,
        ptype: ParticleType = ParticleType.EXPLOSION,
        gravity: bool = True,
        bounce: bool = False,
    ) -> None:
        """Activate particle with given parameters."""
        self.pos.set(pos.x, pos.y)
        self.vel.set(vel.x, vel.y)
        self.color = color
        self.size = size
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.ptype = ptype
        self.active = True
        self.gravity = gravity
        self.bounce = bounce

    def update(self, dt: float) -> None:
        """Update particle physics."""
        if not self.active:
            return
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.active = False
            return
        if self.gravity:
            self.vel.y += config.GRAVITY * dt
        self.pos.add(self.vel * dt)
        self.vel.scale(0.98)
        if self.bounce and self.pos.y > config.WORLD_HEIGHT - 10:
            self.pos.y = config.WORLD_HEIGHT - 10
            self.vel.y *= -0.5

    def draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw particle on screen."""
        if not self.active:
            return
        alpha = int(255 * (self.lifetime / self.max_lifetime))
        sx = int(self.pos.x - camera.x + config.SCREEN_WIDTH // 2 + shake.x)
        sy = int(self.pos.y - camera.y + config.SCREEN_HEIGHT // 2 + shake.y)
        if -10 < sx < config.SCREEN_WIDTH + 10 and -10 < sy < config.SCREEN_HEIGHT + 10:
            s = max(1, int(self.size * (self.lifetime / self.max_lifetime)))
            color = (*self.color, alpha)
            particle_surf = pygame.Surface((s * 2, s * 2), pygame.SRCALPHA)
            pygame.draw.circle(particle_surf, color, (s, s), s)
            surface.blit(particle_surf, (sx - s, sy - s))


class ParticleSystem:
    """Manages a pool of particles."""

    def __init__(self, pool_size: int = config.MAX_PARTICLES) -> None:
        self.particles: List[Particle] = [Particle() for _ in range(pool_size)]
        self._index = 0

    def _get_particle(self) -> Particle:
        """Get next available particle from pool."""
        for _ in range(len(self.particles)):
            p = self.particles[self._index]
            self._index = (self._index + 1) % len(self.particles)
            if not p.active:
                return p
        return self.particles[self._index]

    def emit(
        self,
        pos: Vector2,
        count: int,
        color: Tuple[int, int, int],
        speed_range: Tuple[float, float] = (50, 200),
        size_range: Tuple[float, float] = (2, 4),
        lifetime: float = 0.5,
        ptype: ParticleType = ParticleType.EXPLOSION,
        direction: Optional[Vector2] = None,
        spread: float = 6.28,
        gravity: bool = True,
    ) -> None:
        """Emit burst of particles."""
        for _ in range(count):
            p = self._get_particle()
            import math
            angle = random.uniform(0, spread)
            if direction:
                angle = direction.angle() + random.uniform(-spread / 2, spread / 2)
            speed = random.uniform(*speed_range)
            vel = Vector2(math.cos(angle) * speed, math.sin(angle) * speed)
            size = random.uniform(*size_range)
            p.spawn(pos, vel, color, size, lifetime + random.uniform(-0.1, 0.1), ptype, gravity)

    def emit_trail(self, pos: Vector2, vel: Vector2, color: Tuple[int, int, int]) -> None:
        """Emit trail particle behind moving entity."""
        p = self._get_particle()
        import math
        angle = vel.angle() + math.pi + random.uniform(-0.3, 0.3)
        speed = random.uniform(10, 40)
        pvel = Vector2(math.cos(angle) * speed, math.sin(angle) * speed)
        p.spawn(pos, pvel, color, random.uniform(2, 4), 0.4, ParticleType.TRAIL, gravity=True)

    def emit_explosion(self, pos: Vector2, color: Tuple[int, int, int], count: int = 20) -> None:
        """Emit explosion particles."""
        self.emit(pos, count, color, (80, 300), (3, 6), 0.6, ParticleType.EXPLOSION)

    def emit_sparkle(self, pos: Vector2, color: Tuple[int, int, int]) -> None:
        """Emit sparkle particles."""
        self.emit(pos, 5, color, (20, 80), (1, 3), 0.8, ParticleType.SPARKLE, gravity=False)

    def update(self, dt: float) -> None:
        """Update all active particles."""
        for p in self.particles:
            if p.active:
                p.update(dt)

    def draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw all active particles."""
        for p in self.particles:
            if p.active:
                p.draw(surface, camera, shake)

    @property
    def active_count(self) -> int:
        """Count active particles."""
        return sum(1 for p in self.particles if p.active)
