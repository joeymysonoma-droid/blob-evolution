"""Combat projectile entities."""

from __future__ import annotations

from typing import Dict, Tuple

import pygame

from blob_evolution import config
from blob_evolution.utils.graphics import _shade
from blob_evolution.utils.vector2 import Vector2

Color = Tuple[int, int, int]

# Pre-rendered shot sprites keyed by (kind, draw radius, colour); bounded by the boss colours (about 12)
_SPRITES: Dict[Tuple[str, int, Color], pygame.Surface] = {}
SPRITE_CACHE_MAX = 40


def get_shot_sprite(kind: str, color: Color) -> pygame.Surface:
    """Return the cached halo + dark ring + body + type-mark sprite for a shot kind and colour."""
    radius = config.SHOT_DRAW_RADIUS.get(kind, 6)
    key = (kind, radius, color)
    sprite = _SPRITES.get(key)
    if sprite is None:
        sprite = _build_shot_sprite(kind, radius, color)
        if len(_SPRITES) < SPRITE_CACHE_MAX:    # a runaway colour set never grows the cache past the cap
            _SPRITES[key] = sprite
    return sprite


def _luminance(color: Color) -> float:
    """WCAG relative luminance of an sRGB colour."""
    lin = [(v / 255) / 12.92 if v / 255 <= 0.03928 else (((v / 255) + 0.055) / 1.055) ** 2.4 for v in color[:3]]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def shot_sprite_count() -> int:
    """Number of cached shot sprites."""
    return len(_SPRITES)


def _build_shot_sprite(kind: str, r: int, color: Color) -> pygame.Surface:
    """Draw one shot sprite: type mark is a white core (player) or a dark eye in a bright rim (enemy, boss)."""
    size = 4 * r + 4
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = (size // 2, size // 2)
    pygame.draw.circle(surf, (*color, config.SHOT_HALO_ALPHA), c, 2 * r)
    if _luminance(color) < config.DARK_SHOT_LUMINANCE:      # a dark shot would vanish into the dark outline: ring it in light instead
        pygame.draw.circle(surf, (*config.SHOT_LIGHT_OUTLINE, 120), c, r + 3)
        pygame.draw.circle(surf, (*config.SHOT_LIGHT_OUTLINE, 230), c, r + 2)
    else:
        pygame.draw.circle(surf, (*config.XP_OUTLINE, 215), c, r + 2)
    pygame.draw.circle(surf, color, c, r)
    if kind == "player":
        mark, mark_r = (255, 255, 255), max(2, r // 2)
        pygame.draw.circle(surf, mark, c, mark_r)
    else:
        mark, mark_r = (60, 20, 8), max(2, round(r * 0.45))
        pygame.draw.circle(surf, mark, c, mark_r)
        pygame.draw.circle(surf, _shade(color, 30), c, r - 1, 1)
    pygame.draw.rect(surf, mark, (c[0] - 1, c[1] - 1, 3, 3))      # a radius-2 circle leaves the 3x3 corners out: keep the centre solid
    if pygame.display.get_surface() is not None:
        surf = surf.convert_alpha()
    return surf


class Projectile:
    """A combat projectile fired by player or enemies."""

    __slots__ = (
        "pos", "vel", "damage", "radius", "color", "active",
        "from_player", "piercing", "lifetime", "kind",
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
        if config.GFX_READABILITY:
            self.color: Tuple[int, int, int] = (
                config.COLOR_PROJECTILE_PLAYER if from_player else config.COLOR_PROJECTILE_ENEMY
            )
        else:
            self.color = (
                config.COLOR_PROJECTILE_PLAYER_LEGACY if from_player else config.COLOR_PROJECTILE_ENEMY_LEGACY
            )
        self.kind = "player" if from_player else "enemy"
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
        if config.GFX_READABILITY:
            sprite = get_shot_sprite(self.kind, self.color)
            surface.blit(sprite, (sx - sprite.get_width() // 2, sy - sprite.get_height() // 2))
            return
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
