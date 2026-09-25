"""Player character entity."""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.entities.projectile import Projectile
from blob_evolution.systems.skills import SkillManager
from blob_evolution.systems.artifacts import ArtifactManager
from blob_evolution.systems.evolution import EvolutionManager
from blob_evolution.utils.graphics import draw_blob
from blob_evolution.utils.vector2 import Vector2


class Player:
    """The player-controlled blob."""

    def __init__(self, pos: Vector2) -> None:
        self.pos = pos.copy()
        self.vel = Vector2()
        self.hp = float(config.PLAYER_BASE_HP)
        self.max_hp = float(config.PLAYER_BASE_HP)
        self.level = 1
        self.xp = 0
        self.xp_to_next = config.XP_BASE
        self.skill_points = 0
        self.skills = SkillManager()
        self.artifacts = ArtifactManager()
        self.evolution = EvolutionManager()
        self.size = float(config.PLAYER_BASE_SIZE)
        self.damage = float(config.PLAYER_BASE_DAMAGE)
        self.speed = config.PLAYER_BASE_SPEED
        self.shoot_cooldown = 0.0
        self.shoot_rate = 0.25
        self.dash_cooldown = 0.0
        self.dash_duration = 0.0
        self.invulnerable = 0.0
        self.magnet_radius = 80.0
        self.regen_timer = 0.0
        self.kills = 0
        self.kill_streak = 0
        self.kill_streak_timer = 0.0
        self.total_xp = 0
        self.rotation = 0.0
        self.skin_color = config.COLOR_PLAYER
        self.skin_core = config.COLOR_PLAYER_CORE
        self.run_modifiers = {
            "damage_mult": 1.0, "speed_mult": 1.0, "hp_mult": 1.0,
            "xp_mult": 1.0, "essence_mult": 1.0,
            "damage_taken_mult": 1.0, "regen_mult": 1.0,
        }
        self.perm_bonuses = {
            "damage": 1.0, "health": 1.0, "speed": 1.0, "essence": 1.0,
            "xp": 1.0, "magnet": 1.0, "armor": 0.0, "lifesteal": 0.0, "crit": 0.0, "luck": 0.0,
        }
        self.shop_max_hp_bonus = 0.0
        self.shop_size_boost = 0.0
        self.ng_mult = {"damage": 1.0, "health": 1.0, "speed": 1.0}
        self.has_shield = False
        self.has_revived = False
        self._update_stats()

    def _update_stats(self) -> None:
        """Recalculate stats from skills, artifacts, and evolution."""
        evo = self.evolution.get_bonuses()
        skill_boost = self.artifacts.get_skill_boost()

        def boosted_skill_mult(skill: str) -> float:
            mult = self.skills.get_multiplier(skill)
            return 1.0 + (mult - 1.0) * skill_boost

        self.speed = config.PLAYER_BASE_SPEED * boosted_skill_mult("speed")
        self.speed *= self.artifacts.get_multiplier("speed")
        self.speed *= self.perm_bonuses.get("speed", 1.0)
        self.speed *= self.run_modifiers["speed_mult"]
        self.speed *= evo.get("speed", 1.0)
        self.speed *= self.ng_mult.get("speed", 1.0)
        self.size = config.PLAYER_BASE_SIZE * boosted_skill_mult("size")
        self.size *= self.artifacts.get_multiplier("size")
        self.size *= evo.get("size", 1.0)
        self.size *= (1.0 + self.shop_size_boost)
        self.damage = config.PLAYER_BASE_DAMAGE * boosted_skill_mult("damage")
        self.damage *= self.artifacts.get_multiplier("damage")
        self.damage *= self.perm_bonuses.get("damage", 1.0)
        self.damage *= self.run_modifiers["damage_mult"]
        self.damage *= evo.get("damage", 1.0)
        self.damage *= self.ng_mult.get("damage", 1.0)
        base_hp = config.PLAYER_BASE_HP * boosted_skill_mult("health")
        base_hp *= self.perm_bonuses.get("health", 1.0)
        base_hp *= self.run_modifiers["hp_mult"]
        bonus_hp = self.artifacts.get_flat("max_health")
        old_max = self.max_hp
        self.max_hp = (base_hp + bonus_hp) * self.ng_mult.get("health", 1.0)
        self.max_hp += self.shop_max_hp_bonus
        if self.max_hp > old_max:
            self.hp += self.max_hp - old_max
        self.hp = min(self.hp, self.max_hp)
        self.shoot_rate = max(0.06, 0.25 - self.skills.get_level("projectile") * 0.02)
        self.shoot_rate /= self.artifacts.get_multiplier("fire_rate")
        self.magnet_radius = 80 + self.skills.get_level("magnet") * 15
        self.magnet_radius *= self.perm_bonuses.get("magnet", 1.0)
        self.magnet_radius *= self.artifacts.get_multiplier("magnet")

    def handle_input(self, keys: pygame.key.ScancodeWrapper, dt: float) -> Vector2:
        """Process movement input and return direction."""
        direction = Vector2()
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            direction.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            direction.y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            direction.x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            direction.x += 1
        if direction.length() > 0:
            direction.normalize()
            self.rotation = direction.angle()
        return direction

    def move(self, direction: Vector2, dt: float, speed_mult: float = 1.0) -> None:
        """Move player with smooth velocity."""
        target_speed = self.speed * speed_mult
        if self.dash_duration > 0:
            target_speed *= 3.0
        target_vel = direction * target_speed
        self.vel.lerp(target_vel, min(1.0, dt * 10))
        self.pos.add(self.vel * dt)
        self.pos.clamp_to_rect(config.WORLD_WIDTH, config.WORLD_HEIGHT, self.size)

    def shoot(self, target_world: Vector2, projectiles: List[Projectile]) -> None:
        """Fire projectile(s) toward target."""
        if self.shoot_cooldown > 0:
            return
        direction = target_world - self.pos
        if direction.length() < 1:
            return
        direction.normalize()
        speed = 500 + self.skills.get_level("projectile") * 30
        proj = Projectile(self.pos.copy(), direction, speed, self.damage, from_player=True,
                          piercing=self.artifacts.has("piercing_shots"))
        projectiles.append(proj)
        extra = int(self.artifacts.get_flat("multi_shot"))
        for i in range(extra):
            spread = 0.15 * (i + 1)
            angle = direction.angle() + spread * (1 if i % 2 == 0 else -1)
            d = Vector2(math.cos(angle), math.sin(angle))
            projectiles.append(Projectile(self.pos.copy(), d, speed, self.damage, True,
                                            self.artifacts.has("piercing_shots")))
        self.shoot_cooldown = self.shoot_rate

    def dash(self, direction: Vector2) -> None:
        """Perform dash if unlocked and off cooldown."""
        if self.dash_cooldown > 0 or self.dash_duration > 0:
            return
        if direction.length() < 0.1:
            direction = Vector2(math.cos(self.rotation), math.sin(self.rotation))
        self.dash_duration = 0.2
        self.dash_cooldown = 1.5
        self.invulnerable = 0.2
        self.vel = direction.normalize() * self.speed * 4

    def take_damage(self, amount: float) -> bool:
        """Apply damage. Returns True if player died."""
        if self.invulnerable > 0:
            return False
        if self.has_shield:
            self.has_shield = False
            return False
        reduction = self.artifacts.get_multiplier("damage_reduction")
        armor = self.perm_bonuses.get("armor", 0.0) + self.skills.get_level("armor") * 0.025
        armor = min(0.45, armor)
        actual = amount * (2.0 - reduction) * self.run_modifiers["damage_taken_mult"]
        actual *= (1.0 - armor)
        self.hp -= actual
        self.invulnerable = 0.5
        if self.hp <= 0 and self.artifacts.has("phoenix_heart") and not self.has_revived:
            self.has_revived = True
            self.hp = self.max_hp * 0.5
            self.invulnerable = 2.0
            return False
        return self.hp <= 0

    def get_lifesteal(self) -> float:
        """Total lifesteal ratio on kill."""
        return self.perm_bonuses.get("lifesteal", 0.0) + self.skills.get_level("lifesteal") * 0.015

    def get_crit_chance(self) -> float:
        """Crit chance for bonus damage."""
        return min(0.5, self.perm_bonuses.get("crit", 0.0))

    def heal(self, amount: float) -> None:
        """Heal player."""
        self.hp = min(self.max_hp, self.hp + amount)

    def add_xp(self, amount: int) -> List[str]:
        """Add XP and handle level-ups. Returns list of level-up messages."""
        messages: List[str] = []
        amount = int(amount * self.run_modifiers["xp_mult"])
        self.xp += amount
        self.total_xp += amount
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1
            self.skill_points += config.SKILL_POINTS_PER_LEVEL
            self.xp_to_next = int(config.XP_BASE * (config.XP_MULTIPLIER ** (self.level - 1)))
            messages.append(f"Level {self.level}!")
            evo_msg = self.evolution.check_evolution(self.skills)
            if evo_msg:
                messages.append(evo_msg)
            self._update_stats()
        return messages

    def absorb_creature(self, creature_size: float, creature_hp: float) -> None:
        """Absorb a smaller creature."""
        self.kills += 1
        if self.artifacts.has("perfect_absorption"):
            self.heal(10)
        xp_gain = int(creature_hp * 0.5 + creature_size)
        self.add_xp(xp_gain)

    def update(self, dt: float) -> None:
        """Update player timers and regeneration."""
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= dt
        if self.dash_cooldown > 0:
            self.dash_cooldown -= dt
        if self.dash_duration > 0:
            self.dash_duration -= dt
        if self.invulnerable > 0:
            self.invulnerable -= dt
        regen_level = self.skills.get_level("regen")
        if regen_level > 0:
            self.regen_timer += dt
            if self.regen_timer >= 2.0:
                self.regen_timer = 0.0
                regen_amount = regen_level * 0.5 + 0.5
                regen_amount += self.max_hp * self.artifacts.get_regen_bonus()
                regen_amount *= self.run_modifiers["regen_mult"]
                regen_amount = min(regen_amount, self.max_hp * 0.02)
                self.heal(regen_amount)

    def draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2,
             look_target: Optional[Tuple[float, float]] = None) -> None:
        """Draw player blob."""
        sx = self.pos.x - camera.x + config.SCREEN_WIDTH // 2 + shake.x
        sy = self.pos.y - camera.y + config.SCREEN_HEIGHT // 2 + shake.y
        glow = self.invulnerable > 0 or self.dash_duration > 0
        pulse = 0.0
        if self.invulnerable > 0:
            pulse = math.sin(self.invulnerable * 20) * 0.06
        look = look_target
        if look is None and self.vel.length() > 10:
            look = (self.vel.x, self.vel.y)
        draw_blob(
            surface, (sx, sy), self.size, self.skin_color,
            self.skin_core, self.vel, pulse=pulse, glow=glow,
            rotation=self.rotation, look=look, eyes=True,
        )

    @property
    def radius(self) -> float:
        """Collision radius."""
        return self.size
