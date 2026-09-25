"""Enemy creature AI and behavior."""

from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.entities.projectile import Projectile
from blob_evolution.utils.enums import CreatureType
from blob_evolution.utils.graphics import draw_blob
from blob_evolution.utils.vector2 import Vector2


class Creature:
    """Enemy creature with type-specific AI."""

    COLORS = {
        CreatureType.BASIC: ((220, 60, 60), (255, 120, 120)),
        CreatureType.SHOOTER: ((200, 100, 50), (255, 160, 80)),
        CreatureType.SPLITTER: ((180, 50, 180), (220, 100, 220)),
        CreatureType.CHARGER: ((200, 50, 50), (255, 80, 80)),
        CreatureType.SHIELDER: ((90, 130, 200), (160, 200, 255)),
        CreatureType.ORBITER: ((220, 180, 60), (255, 230, 120)),
        CreatureType.BOMBER: ((230, 90, 40), (255, 160, 60)),
        CreatureType.PHANTOM: ((120, 100, 160), (180, 160, 220)),
        CreatureType.LEECH: ((60, 160, 100), (120, 230, 160)),
    }

    def __init__(
        self,
        pos: Vector2,
        creature_type: CreatureType = CreatureType.BASIC,
        size: float = 15.0,
        hp_mult: float = 1.0,
        diff_mult: Optional[dict] = None,
    ) -> None:
        self.pos = pos.copy()
        self.vel = Vector2()
        self.ctype = creature_type
        self.size = size
        diff = diff_mult or {"hp": 1.0, "damage": 1.0, "speed": 1.0}
        self.max_hp = self._base_hp() * hp_mult * diff["hp"]
        self.hp = self.max_hp
        self.damage = self._base_damage() * diff["damage"]
        self.speed = self._base_speed() * diff["speed"]
        self.active = True
        self.xp_value = int(self.max_hp * 0.3 + self.size)
        self.wander_timer = random.uniform(0.5, 2.0)
        self.wander_dir = Vector2(random.uniform(-1, 1), random.uniform(-1, 1)).normalize()
        self.shoot_cooldown = random.uniform(1.0, 3.0)
        self.charge_timer = random.uniform(2.0, 5.0)
        self.charging = False
        self.charge_dir = Vector2()
        self.charge_telegraph = 0.0
        self.hit_flash = 0.0
        self.slow_factor = 1.0
        self.face_dir = Vector2(1, 0)
        self.shield_hp = 40.0 * diff["hp"] if creature_type == CreatureType.SHIELDER else 0.0
        self.orbit_angle = random.uniform(0, math.tau)
        self.phase_timer = random.uniform(1.5, 3.0)
        self.phased = False
        self.fuse_timer = random.uniform(4.0, 7.0) if creature_type == CreatureType.BOMBER else 0.0
        self.armed = False
        self.pending_explosion = False
        self.explosion_radius = self.size * 3.5
        self.explosion_damage = self.damage * 1.8
        self.kills_awarded = False

    def _base_hp(self) -> float:
        return {
            CreatureType.BASIC: 30,
            CreatureType.SHOOTER: 40,
            CreatureType.SPLITTER: 60,
            CreatureType.CHARGER: 50,
            CreatureType.SHIELDER: 55,
            CreatureType.ORBITER: 35,
            CreatureType.BOMBER: 28,
            CreatureType.PHANTOM: 45,
            CreatureType.LEECH: 38,
        }.get(self.ctype, 30)

    def _base_damage(self) -> float:
        return {
            CreatureType.BASIC: 10,
            CreatureType.SHOOTER: 8,
            CreatureType.SPLITTER: 12,
            CreatureType.CHARGER: 25,
            CreatureType.SHIELDER: 12,
            CreatureType.ORBITER: 9,
            CreatureType.BOMBER: 18,
            CreatureType.PHANTOM: 11,
            CreatureType.LEECH: 7,
        }.get(self.ctype, 10)

    def _base_speed(self) -> float:
        return {
            CreatureType.BASIC: 100,
            CreatureType.SHOOTER: 80,
            CreatureType.SPLITTER: 70,
            CreatureType.CHARGER: 120,
            CreatureType.SHIELDER: 70,
            CreatureType.ORBITER: 90,
            CreatureType.BOMBER: 110,
            CreatureType.PHANTOM: 95,
            CreatureType.LEECH: 105,
        }.get(self.ctype, 100)

    def take_damage(self, amount: float, ignore_defense: float = 0.0,
                    hit_from: Optional[Vector2] = None) -> bool:
        """Take damage. Returns True if killed."""
        if self.phased and self.ctype == CreatureType.PHANTOM:
            return False

        actual = amount * (1.0 + ignore_defense)

        if self.ctype == CreatureType.SHIELDER and self.shield_hp > 0 and hit_from is not None:
            to_hit = (hit_from - self.pos).copy()
            if to_hit.length() > 0:
                to_hit.normalize()
            # Hits from the front (aligned with face) are heavily reduced
            if self.face_dir.dot(to_hit) > 0.25:
                blocked = min(self.shield_hp, actual * 0.85)
                self.shield_hp -= blocked
                actual -= blocked
                self.hit_flash = 0.1
                if actual <= 0.5:
                    return False

        self.hp -= actual
        self.hit_flash = 0.15
        if self.hp <= 0:
            if self.ctype == CreatureType.BOMBER:
                self.pending_explosion = True
            return True
        return False

    def update(
        self,
        dt: float,
        player_pos: Vector2,
        player_size: float,
        projectiles: List[Projectile],
    ) -> None:
        """Update AI behavior."""
        if not self.active:
            return
        if self.hit_flash > 0:
            self.hit_flash -= dt

        dist = self.pos.distance_to(player_pos)
        direction = (player_pos - self.pos).copy()
        if direction.length() > 0:
            direction.normalize()
            self.face_dir = direction.copy()

        speed = self.speed * self.slow_factor

        if self.ctype == CreatureType.BASIC:
            self._ai_basic(dt, player_pos, player_size, direction, dist, speed)
        elif self.ctype == CreatureType.SHOOTER:
            self._ai_shooter(dt, player_pos, player_size, direction, dist, speed, projectiles)
        elif self.ctype == CreatureType.SPLITTER:
            self._ai_basic(dt, player_pos, player_size, direction, dist, speed * 0.8)
        elif self.ctype == CreatureType.CHARGER:
            self._ai_charger(dt, direction, dist, speed)
        elif self.ctype == CreatureType.SHIELDER:
            self._ai_shielder(dt, direction, dist, speed)
        elif self.ctype == CreatureType.ORBITER:
            self._ai_orbiter(dt, player_pos, direction, dist, speed, projectiles)
        elif self.ctype == CreatureType.BOMBER:
            self._ai_bomber(dt, direction, dist, speed)
        elif self.ctype == CreatureType.PHANTOM:
            self._ai_phantom(dt, direction, dist, speed)
        elif self.ctype == CreatureType.LEECH:
            self._ai_leech(dt, direction, dist, speed)

        self.pos.add(self.vel * dt)
        self.pos.clamp_to_rect(config.WORLD_WIDTH, config.WORLD_HEIGHT, self.size)
        self.vel.scale(0.9)

    def _ai_basic(
        self, dt: float, player_pos: Vector2, player_size: float,
        direction: Vector2, dist: float, speed: float,
    ) -> None:
        if self.size < player_size * 0.9:
            self.vel = direction * speed
        elif self.size > player_size * 1.1:
            self.vel = direction * -speed * 0.8
        else:
            self.wander_timer -= dt
            if self.wander_timer <= 0:
                self.wander_timer = random.uniform(1.0, 3.0)
                self.wander_dir = Vector2(random.uniform(-1, 1), random.uniform(-1, 1)).normalize()
            self.vel = self.wander_dir * speed * 0.5

    def _ai_shooter(
        self, dt: float, player_pos: Vector2, player_size: float,
        direction: Vector2, dist: float, speed: float,
        projectiles: List[Projectile],
    ) -> None:
        ideal_dist = 250
        if dist < ideal_dist - 50:
            self.vel = direction * -speed
        elif dist > ideal_dist + 50:
            self.vel = direction * speed * 0.6
        else:
            self.vel = Vector2(-direction.y, direction.x) * speed * 0.4

        self.shoot_cooldown -= dt
        if self.shoot_cooldown <= 0 and dist < 500:
            projectiles.append(Projectile(
                self.pos.copy(), direction, 300, self.damage, from_player=False,
            ))
            self.shoot_cooldown = random.uniform(1.5, 3.0)

    def _ai_charger(self, dt: float, direction: Vector2, dist: float, speed: float) -> None:
        if self.charging:
            self.vel = self.charge_dir * speed * 4
            self.charge_timer -= dt
            if self.charge_timer <= 0:
                self.charging = False
                self.charge_timer = random.uniform(2.0, 4.0)
        else:
            self.charge_timer -= dt
            if self.charge_timer <= 0 and dist < 400:
                self.charging = True
                self.charge_telegraph = 0.5
                self.charge_dir = direction.copy()
                self.charge_timer = 0.4
            else:
                self.vel = direction * speed * 0.5
        if self.charge_telegraph > 0:
            self.charge_telegraph -= dt

    def _ai_shielder(self, dt: float, direction: Vector2, dist: float, speed: float) -> None:
        """Advance while keeping shield facing the player."""
        if dist > 90:
            self.vel = direction * speed
        else:
            self.vel = direction * speed * 0.2
        if self.shield_hp <= 0:
            self.vel = direction * speed * 1.3

    def _ai_orbiter(
        self, dt: float, player_pos: Vector2, direction: Vector2, dist: float,
        speed: float, projectiles: List[Projectile],
    ) -> None:
        self.orbit_angle += dt * 1.4
        radius = 220
        target = player_pos + Vector2(math.cos(self.orbit_angle) * radius,
                                      math.sin(self.orbit_angle) * radius)
        to_t = (target - self.pos).copy()
        if to_t.length() > 0:
            to_t.normalize()
            self.vel = to_t * speed * 1.2
        self.shoot_cooldown -= dt
        if self.shoot_cooldown <= 0 and dist < 450:
            projectiles.append(Projectile(
                self.pos.copy(), direction, 280, self.damage, from_player=False,
            ))
            self.shoot_cooldown = random.uniform(1.2, 2.2)

    def _ai_bomber(self, dt: float, direction: Vector2, dist: float, speed: float) -> None:
        self.vel = direction * speed * 1.15
        self.fuse_timer -= dt
        if dist < 70 or self.fuse_timer <= 0:
            self.armed = True
            self.pending_explosion = True
            self.hp = 0
            self.active = False

    def _ai_phantom(self, dt: float, direction: Vector2, dist: float, speed: float) -> None:
        self.phase_timer -= dt
        if self.phase_timer <= 0:
            self.phased = not self.phased
            self.phase_timer = 1.2 if self.phased else 2.2
        if self.phased:
            self.vel = direction * speed * 1.4
        else:
            self.vel = direction * speed * 0.7

    def _ai_leech(self, dt: float, direction: Vector2, dist: float, speed: float) -> None:
        if dist > 60:
            self.vel = direction * speed
        else:
            self.vel = direction * speed * 0.15
            # Siphon: heal while near
            self.hp = min(self.max_hp, self.hp + 8 * dt)

    def draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw creature."""
        sx = self.pos.x - camera.x + config.SCREEN_WIDTH // 2 + shake.x
        sy = self.pos.y - camera.y + config.SCREEN_HEIGHT // 2 + shake.y
        colors = self.COLORS.get(self.ctype, ((200, 60, 60), (255, 120, 120)))
        if self.hit_flash > 0:
            colors = ((255, 255, 255), (255, 200, 200))
        if self.phased:
            colors = (
                tuple(max(0, c - 60) for c in colors[0]),
                tuple(max(0, c - 40) for c in colors[1]),
            )
        variant = {
            CreatureType.BASIC: "default",
            CreatureType.SHOOTER: "orbs",
            CreatureType.SPLITTER: "split",
            CreatureType.CHARGER: "spikes",
            CreatureType.SHIELDER: "shield",
            CreatureType.ORBITER: "orbs",
            CreatureType.BOMBER: "bomb",
            CreatureType.PHANTOM: "ghost",
            CreatureType.LEECH: "default",
        }.get(self.ctype, "default")
        look = (self.face_dir.x, self.face_dir.y)
        alpha_eyes = not self.phased
        draw_blob(
            surface, (sx, sy), self.size, colors[0], colors[1], self.vel,
            look=look, variant=variant, rotation=self.wander_timer + self.orbit_angle,
            eyes=alpha_eyes, glow=self.ctype == CreatureType.PHANTOM and self.phased,
        )

        if self.ctype == CreatureType.SHIELDER and self.shield_hp > 0:
            ang = self.face_dir.angle()
            shield_x = int(sx + math.cos(ang) * self.size * 1.1)
            shield_y = int(sy + math.sin(ang) * self.size * 1.1)
            pygame.draw.circle(surface, (160, 200, 255), (shield_x, shield_y), int(self.size * 0.55), 2)

        if self.ctype == CreatureType.BOMBER and self.fuse_timer < 2.0:
            pulse = 0.5 + 0.5 * math.sin(self.fuse_timer * 12)
            pygame.draw.circle(
                surface, (255, int(100 + 100 * pulse), 40),
                (int(sx), int(sy)), int(self.size * (1.2 + pulse * 0.3)), 2,
            )

        if self.charge_telegraph > 0:
            warn = pygame.Surface((int(self.size * 4), int(self.size * 4)), pygame.SRCALPHA)
            wr = warn.get_width() // 2
            pygame.draw.circle(warn, (255, 80, 80, 90), (wr, wr), int(self.size * 1.6), 3)
            surface.blit(warn, (int(sx) - wr, int(sy) - wr))
            tip_x = int(sx + self.charge_dir.x * self.size * 2.2)
            tip_y = int(sy + self.charge_dir.y * self.size * 2.2)
            pygame.draw.line(surface, (255, 120, 100), (int(sx), int(sy)), (tip_x, tip_y), 2)

    @property
    def radius(self) -> float:
        return self.size

    def can_split(self) -> bool:
        return self.ctype == CreatureType.SPLITTER and self.size > 10

    def create_splits(self) -> List[Creature]:
        children = []
        for angle_offset in (-0.5, 0.5):
            offset = Vector2(math.cos(angle_offset) * 30, math.sin(angle_offset) * 30)
            child = Creature(self.pos + offset, CreatureType.BASIC,
                             size=self.size * 0.6, hp_mult=0.4)
            children.append(child)
        return children
