"""XP orbs and collectible pickups."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.utils.vector2 import Vector2

# Pre-rendered orb sprites keyed by (tier, radius); at most 4 tiers x 9 radii
_SPRITES: Dict[Tuple[int, int], pygame.Surface] = {}
_ACT = [0]      # act whose median sets the tier cut-offs of orbs created from now on (set when an encounter loads)


def set_xp_act(act: int) -> None:
    """Choose the act whose XP_TIER_MEDIAN scales the orb tiers."""
    _ACT[0] = max(0, min(int(act), len(config.XP_TIER_MEDIAN) - 1))


def xp_thresholds(act: Optional[int] = None) -> Tuple[float, float, float]:
    """Tier cut-offs (factors x m) of an act's median orb value m (default 0.75, 1.4, 2.5; act 7 has its own); None: the current act."""
    i = _ACT[0] if act is None else max(0, min(act, len(config.XP_TIER_MEDIAN) - 1))
    m, f = config.XP_TIER_MEDIAN[i], config.XP_TIER_FACTORS[i]
    return (f[0] * m, f[1] * m, f[2] * m)


def xp_tier(value: int, act: Optional[int] = None) -> int:
    """Return the orb tier 1..4 for an XP value in an act (None: the current act) from its three cut-offs."""
    return 1 + sum(1 for t in xp_thresholds(act) if value >= t)


def xp_sprite_count() -> int:
    """Number of cached XP orb sprites."""
    return len(_SPRITES)


def _tier_points(tier: int, r: int, scale: float = 1.0) -> List[Tuple[float, float]]:
    """Polygon points (relative to the centre) of the tier 3 diamond or the tier 4 four-point star."""
    if tier == 3:
        k = config.XP_DIAMOND_REACH * r * scale
        return [(0, -k), (k, 0), (0, k), (-k, 0)]
    pts = []
    for i in range(8):
        rad = config.XP_STAR_REACH[i % 2] * r * scale
        ang = -math.pi / 2 + i * math.pi / 4
        pts.append((rad * math.cos(ang), rad * math.sin(ang)))
    return pts


def get_xp_sprite(tier: int, r: int) -> pygame.Surface:
    """Return the cached orb sprite: halo, dark outline, body in the tier shape, then the core."""
    key = (tier, r)
    sprite = _SPRITES.get(key)
    if sprite is None:
        sprite = _build_xp_sprite(tier, r)
        _SPRITES[key] = sprite
    return sprite


def _build_xp_sprite(tier: int, r: int) -> pygame.Surface:
    """Draw one orb sprite (tier 1 disc, 2 disc + ring, 3 diamond, 4 star)."""
    style = config.XP_TIER_STYLE[tier - 1]
    body, core = style["body"], style["core"]
    size = int(2 * (1.9 * r)) + 4
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    pygame.draw.circle(surf, (*body, 55), (c, c), int(1.9 * r))
    if tier <= 2:
        pygame.draw.circle(surf, (*config.XP_OUTLINE, 200), (c, c), r + 2)
        if tier == 2:
            pygame.draw.circle(surf, (255, 255, 255, 200), (c, c), r + 3, 1)
        pygame.draw.circle(surf, body, (c, c), r)
    else:
        outer = (config.XP_DIAMOND_REACH if tier == 3 else config.XP_STAR_REACH[0]) * r
        grow = (outer + 2) / outer
        pygame.draw.polygon(surf, (*config.XP_OUTLINE, 200), [(c + x, c + y) for x, y in _tier_points(tier, r, grow)])
        pygame.draw.polygon(surf, body, [(c + x, c + y) for x, y in _tier_points(tier, r)])
    pygame.draw.circle(surf, core, (c + (-r // 4), c + (-r // 4)), max(1, r // 3))
    if pygame.display.get_surface() is not None:
        surf = surf.convert_alpha()
    return surf


class XPOrb:
    """Experience orb dropped by defeated creatures."""

    __slots__ = ("pos", "vel", "value", "radius", "active", "lifetime", "bob_phase", "tier")

    def __init__(self, pos: Vector2, value: int = 10) -> None:
        self.pos = pos.copy()
        self.vel = Vector2()
        self.value = value
        self.radius = 6 + min(value // 20, 8)
        self.active = True
        self.lifetime = 30.0
        self.bob_phase = 0.0
        self.tier = xp_tier(value)      # fixed at creation, so the draw path computes nothing

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
        if config.GFX_READABILITY:
            sprite = get_xp_sprite(self.tier, self.radius)
            if self.lifetime < config.XP_BLINK_SECONDS:
                wave = 0.5 + 0.5 * math.sin(self.lifetime * 2 * math.pi * config.XP_BLINK_HZ)
                sprite.set_alpha(int(150 + 105 * wave))
            else:
                sprite.set_alpha(255)
            surface.blit(sprite, (sx - sprite.get_width() // 2, sy - sprite.get_height() // 2))
            return
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
