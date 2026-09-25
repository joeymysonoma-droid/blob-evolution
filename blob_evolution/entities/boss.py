"""Boss encounter entities with act-unique phases."""

from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.data.lore import get_boss_name
from blob_evolution.entities.projectile import Projectile
from blob_evolution.utils.graphics import draw_blob, draw_health_bar, get_boss_palette
from blob_evolution.utils.vector2 import Vector2

Color = Tuple[int, int, int]


def _proj(
    pos: Vector2,
    direction: Vector2,
    speed: float,
    damage: float,
    color: Optional[Color] = None,
) -> Projectile:
    p = Projectile(pos.copy(), direction, speed, damage, from_player=False)
    if color:
        p.color = color
    return p


class Boss:
    """Multi-phase boss with act-specific attack kits."""

    def __init__(
        self,
        pos: Vector2,
        act_index: int = 0,
        diff_mult: dict | None = None,
        *,
        miniboss: bool = False,
        slot: int = 0,
    ) -> None:
        self.pos = pos.copy()
        self.vel = Vector2()
        diff = diff_mult or {"hp": 1.0, "damage": 1.0, "speed": 1.0}
        power_index = act_index + slot
        self.size = 50 + power_index * 10
        if miniboss:
            self.size = 35 + act_index * 2
        self.max_hp = (300 + power_index * 100) * diff["hp"]
        if miniboss:
            self.max_hp *= 0.55
        self.hp = self.max_hp
        self.damage = (20 + power_index * 5) * diff["damage"]
        self.speed = 60 * diff["speed"]
        self.active = True
        self.enraged = False
        self.phase = 1
        self.phase_announced = False
        self.xp_value = int(self.max_hp)
        self.shoot_cooldown = 1.5
        self.special_cooldown = 4.0
        self.angle = random.uniform(0, math.tau)
        self.hit_flash = 0.0
        self.telegraph = 0.0
        self.telegraph_type = ""
        self.pulse_time = 0.0
        self.slow_factor = 1.0
        self.act_index = act_index
        self.is_miniboss = miniboss
        self.slot = slot
        self.name = get_boss_name(act_index, miniboss=miniboss, slot=slot)
        self.move_mode = "orbit"
        self.dash_timer = 0.0
        self.dash_dir = Vector2()
        self.clone_timer = 0.0
        self.pull_pulse = 0.0
        self.spiral_index = 0
        # Visual telegraph rings for special arenas
        self.warning_rings: List[Tuple[float, float, Color]] = []  # radius, life, color

    def take_damage(self, amount: float, ignore_defense: float = 0.0) -> bool:
        """Take damage. Returns True if killed. Sets phase_announced when crossing thresholds."""
        actual = amount * (1.0 + ignore_defense)
        prev_ratio = self.hp / self.max_hp if self.max_hp else 0
        self.hp -= actual
        self.hit_flash = 0.2
        ratio = self.hp / self.max_hp if self.max_hp else 0

        if not self.enraged and ratio < 0.5:
            self.enraged = True
            self.phase = 2
            self.phase_announced = True
            self.special_cooldown = 1.5
        if self.act_index >= 8 and ratio < 0.25 and prev_ratio >= 0.25:
            self.phase = 3
            self.phase_announced = True
            self.special_cooldown = 1.0
        return self.hp <= 0

    def consume_phase_announce(self) -> bool:
        """Return True once when a new phase begins."""
        if self.phase_announced:
            self.phase_announced = False
            return True
        return False

    def update(
        self,
        dt: float,
        player_pos: Vector2,
        projectiles: List[Projectile],
    ) -> None:
        if not self.active:
            return
        self.pulse_time += dt
        if self.hit_flash > 0:
            self.hit_flash -= dt
        if self.telegraph > 0:
            self.telegraph -= dt
        self.warning_rings = [
            (r, life - dt, col) for r, life, col in self.warning_rings if life - dt > 0
        ]

        self._update_movement(dt, player_pos)
        self.pos.add(self.vel * dt)
        self.pos.clamp_to_rect(config.WORLD_WIDTH, config.WORLD_HEIGHT, self.size)

        self.shoot_cooldown -= dt
        self.special_cooldown -= dt

        if self.shoot_cooldown <= 0:
            self._basic_attack(player_pos, projectiles)
            base = 1.2 if self.enraged else 1.7
            if self.phase >= 3:
                base *= 0.75
            if self.is_miniboss:
                base *= 1.2
            self.shoot_cooldown = base

        if self.special_cooldown <= 0:
            self._special_attack(player_pos, projectiles)
            cd = 3.2 if self.enraged else 5.2
            if self.phase >= 3:
                cd *= 0.7
            if self.is_miniboss:
                cd *= 1.15
            self.special_cooldown = cd

    def _update_movement(self, dt: float, player_pos: Vector2) -> None:
        act = self.act_index
        enrage_mult = 1.55 if self.enraged else 1.0
        speed = self.speed * enrage_mult * self.slow_factor

        if self.dash_timer > 0:
            self.dash_timer -= dt
            self.vel = self.dash_dir * speed * 4.5
            return

        if act in (0, 2, 8) or self.is_miniboss:
            self.angle += dt * (1.6 if self.enraged else 1.1)
            radius = 260 if self.enraged else 300
            target = player_pos + Vector2(math.cos(self.angle) * radius, math.sin(self.angle) * radius)
            self._steer_toward(target, speed)
        elif act == 1:
            # Rot: slow weave closer over time
            self.angle += dt * 0.9
            radius = 180 + 80 * math.sin(self.pulse_time)
            target = player_pos + Vector2(math.cos(self.angle) * radius, math.sin(self.angle) * radius)
            self._steer_toward(target, speed * 0.85)
        elif act == 3:
            # Ash: circle then occasional dash
            self.angle += dt * 1.3
            target = player_pos + Vector2(math.cos(self.angle) * 280, math.sin(self.angle) * 280)
            self._steer_toward(target, speed)
            if random.random() < dt * 0.35:
                to_p = (player_pos - self.pos).copy()
                if to_p.length() > 0:
                    to_p.normalize()
                    self.dash_dir = to_p
                    self.dash_timer = 0.35
                    self.telegraph = 0.35
                    self.telegraph_type = "dash"
        elif act == 4:
            # Frost: linger at distance
            to_p = (player_pos - self.pos).copy()
            dist = to_p.length()
            if dist > 0:
                to_p.normalize()
            if dist < 240:
                self.vel = to_p * -speed
            elif dist > 360:
                self.vel = to_p * speed * 0.7
            else:
                self.vel = Vector2(-to_p.y, to_p.x) * speed * 0.5
        elif act == 5:
            # Thirst: teleport-style jumps
            self.clone_timer -= dt
            if self.clone_timer <= 0:
                ang = random.uniform(0, math.tau)
                self.pos = player_pos + Vector2(math.cos(ang) * 320, math.sin(ang) * 320)
                self.clone_timer = 3.5 if self.enraged else 5.0
                self.telegraph = 0.4
                self.telegraph_type = "blink"
            self._steer_toward(player_pos, speed * 0.4)
        elif act == 6:
            # Masks: mirror player velocity-ish by strafing opposite
            self.angle += dt * 2.0
            radius = 200
            target = player_pos + Vector2(math.cos(self.angle) * radius, math.sin(self.angle) * radius)
            self._steer_toward(target, speed * 1.2)
        elif act == 7:
            # Silence: drift in, pulse pull visually
            self.pull_pulse = (math.sin(self.pulse_time * 2) + 1) * 0.5
            self._steer_toward(player_pos, speed * (0.5 + 0.4 * self.pull_pulse))
        else:
            # Core / default aggressive orbit
            self.angle += dt * (2.0 if self.enraged else 1.4)
            radius = 220 if self.phase >= 3 else 280
            target = player_pos + Vector2(math.cos(self.angle) * radius, math.sin(self.angle) * radius)
            self._steer_toward(target, speed * 1.15)

    def _steer_toward(self, target: Vector2, speed: float) -> None:
        direction = (target - self.pos).copy()
        if direction.length() > 5:
            direction.normalize()
            self.vel = direction * speed
        else:
            self.vel = Vector2()

    def _basic_attack(self, player_pos: Vector2, projectiles: List[Projectile]) -> None:
        to_player = (player_pos - self.pos).copy()
        if to_player.length() <= 0:
            return
        to_player.normalize()
        act = self.act_index
        dmg = self.damage
        speed = 260 if self.enraged else 210

        if act == 0:
            # Spiral seed
            ang = self.spiral_index * 0.7
            self.spiral_index += 1
            direction = Vector2(math.cos(ang), math.sin(ang))
            projectiles.append(_proj(self.pos, direction, speed, dmg * 0.7, (80, 200, 100)))
        elif act == 1:
            for spread in (-0.25, 0.25):
                a = to_player.angle() + spread
                projectiles.append(_proj(
                    self.pos, Vector2(math.cos(a), math.sin(a)), speed * 0.85, dmg * 0.75, (120, 180, 50),
                ))
        elif act == 2:
            # Echo: shot + delayed ghost (simulated as slower second)
            projectiles.append(_proj(self.pos, to_player, speed, dmg, (140, 190, 255)))
            delayed = _proj(self.pos, to_player, speed * 0.55, dmg * 0.7, (100, 140, 220))
            delayed.lifetime = 4.0
            projectiles.append(delayed)
        elif act == 4:
            for spread in (-0.35, 0, 0.35):
                a = to_player.angle() + spread
                projectiles.append(_proj(
                    self.pos, Vector2(math.cos(a), math.sin(a)), speed * 0.9, dmg * 0.65, (200, 230, 255),
                ))
        elif act == 7:
            # Void bolts that pull visually (slower, heavier)
            projectiles.append(_proj(self.pos, to_player, speed * 0.7, dmg * 1.1, (80, 50, 120)))
        elif act == 9 or (act == 8 and self.slot == 0):
            for spread in (-0.2, 0, 0.2):
                a = to_player.angle() + spread
                projectiles.append(_proj(
                    self.pos, Vector2(math.cos(a), math.sin(a)), speed, dmg, (255, 80, 180),
                ))
        else:
            projectiles.append(_proj(self.pos, to_player, speed, dmg))

    def _special_attack(self, player_pos: Vector2, projectiles: List[Projectile]) -> None:
        act = self.act_index
        self.telegraph = 0.7
        dmg = self.damage

        if self.is_miniboss:
            self._radial(projectiles, 6, 200, dmg * 0.7, (200, 160, 255))
            self.telegraph_type = "radial"
            return

        if act == 0:
            self.telegraph_type = "bloom"
            self._radial(projectiles, 10, 190, dmg * 0.65, (90, 210, 110))
        elif act == 1:
            self.telegraph_type = "rot"
            self._radial(projectiles, 8, 170, dmg * 0.7, (140, 200, 60))
            # Secondary slower ring
            self._radial(projectiles, 8, 110, dmg * 0.5, (100, 150, 40), offset=math.pi / 8)
        elif act == 2:
            self.telegraph_type = "echo"
            for i in range(12):
                ang = i * math.tau / 12
                direction = Vector2(math.cos(ang), math.sin(ang))
                projectiles.append(_proj(self.pos, direction, 240, dmg * 0.6, (160, 210, 255)))
                ghost = _proj(self.pos, direction, 140, dmg * 0.5, (90, 130, 200))
                ghost.lifetime = 4.5
                projectiles.append(ghost)
        elif act == 3:
            self.telegraph_type = "erupt"
            self._radial(projectiles, 12, 230, dmg * 0.75, (255, 120, 40))
            to_p = (player_pos - self.pos).copy()
            if to_p.length() > 0:
                to_p.normalize()
                self.dash_dir = to_p
                self.dash_timer = 0.4
        elif act == 4:
            self.telegraph_type = "frost"
            self.warning_rings.append((180.0, 0.9, (180, 220, 255)))
            for i in range(16):
                ang = i * math.tau / 16
                direction = Vector2(math.cos(ang), math.sin(ang))
                projectiles.append(_proj(self.pos, direction, 160, dmg * 0.55, (210, 235, 255)))
        elif act == 5:
            self.telegraph_type = "mirage"
            # Fake angles + real targeted volley
            for _ in range(3):
                ang = random.uniform(0, math.tau)
                fake_dir = Vector2(math.cos(ang), math.sin(ang))
                projectiles.append(_proj(self.pos, fake_dir, 200, dmg * 0.4, (230, 200, 100)))
            to_p = (player_pos - self.pos).copy()
            if to_p.length() > 0:
                to_p.normalize()
                for spread in (-0.3, -0.1, 0.1, 0.3):
                    a = to_p.angle() + spread
                    projectiles.append(_proj(
                        self.pos, Vector2(math.cos(a), math.sin(a)), 300, dmg, (255, 210, 80),
                    ))
        elif act == 6:
            self.telegraph_type = "mask"
            # Orbiting burst from boss toward player-relative ring
            for i in range(8):
                ang = self.angle + i * math.tau / 8
                origin = self.pos + Vector2(math.cos(ang) * 60, math.sin(ang) * 60)
                to_p = (player_pos - origin).copy()
                if to_p.length() > 0:
                    to_p.normalize()
                    projectiles.append(_proj(origin, to_p, 250, dmg * 0.7, (190, 120, 255)))
        elif act == 7:
            self.telegraph_type = "void"
            self.warning_rings.append((220.0, 1.0, (120, 80, 180)))
            self._radial(projectiles, 10, 150, dmg * 0.8, (90, 60, 140))
            # Inward-looking second wave from far out (simulate by reverse dirs from offset)
            for i in range(8):
                ang = i * math.tau / 8
                origin = player_pos + Vector2(math.cos(ang) * 280, math.sin(ang) * 280)
                inward = (player_pos - origin).copy()
                if inward.length() > 0:
                    inward.normalize()
                    projectiles.append(_proj(origin, inward, 180, dmg * 0.65, (60, 40, 100)))
        elif act == 8:
            self.telegraph_type = "verdict"
            patterns = ["radial", "targeted", "cross"]
            pick = patterns[self.slot % len(patterns)]
            if pick == "radial":
                self._radial(projectiles, 10, 220, dmg * 0.7, (180, 200, 255))
            elif pick == "targeted":
                to_p = (player_pos - self.pos).copy()
                if to_p.length() > 0:
                    to_p.normalize()
                    for spread in (-0.4, -0.2, 0, 0.2, 0.4):
                        a = to_p.angle() + spread
                        projectiles.append(_proj(
                            self.pos, Vector2(math.cos(a), math.sin(a)), 280, dmg, (200, 220, 255),
                        ))
            else:
                for ang in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                    for dist_off in (0, 0.15, -0.15):
                        a = ang + dist_off
                        projectiles.append(_proj(
                            self.pos, Vector2(math.cos(a), math.sin(a)), 240, dmg * 0.7, (220, 230, 255),
                        ))
        else:
            # First Divide — everything
            self.telegraph_type = "divide"
            self._radial(projectiles, 14, 210, dmg * 0.7, (255, 80, 180))
            to_p = (player_pos - self.pos).copy()
            if to_p.length() > 0:
                to_p.normalize()
                for spread in (-0.35, 0, 0.35):
                    a = to_p.angle() + spread
                    projectiles.append(_proj(
                        self.pos, Vector2(math.cos(a), math.sin(a)), 320, dmg, (255, 120, 200),
                    ))
            if self.phase >= 3:
                self._radial(projectiles, 8, 140, dmg * 0.5, (200, 50, 150), offset=0.4)

    def _radial(
        self,
        projectiles: List[Projectile],
        count: int,
        speed: float,
        damage: float,
        color: Color,
        offset: float = 0.0,
    ) -> None:
        for i in range(count):
            ang = offset + i * math.tau / count
            direction = Vector2(math.cos(ang), math.sin(ang))
            projectiles.append(_proj(self.pos, direction, speed, damage, color))

    def draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        sx = int(self.pos.x - camera.x + config.SCREEN_WIDTH // 2 + shake.x)
        sy = int(self.pos.y - camera.y + config.SCREEN_HEIGHT // 2 + shake.y)
        pulse = 0.1 * math.sin(self.pulse_time * 3)
        color, core = get_boss_palette(self.act_index, enraged=self.enraged)
        if self.is_miniboss:
            color = tuple(max(0, c - 30) for c in color)
            core = tuple(min(255, c + 20) for c in core)
        if self.hit_flash > 0:
            color = (255, 255, 255)
            core = (255, 200, 200)
        look = (self.vel.x, self.vel.y) if self.vel.length() > 1 else None
        draw_blob(
            surface, (sx, sy), self.size, color, core, self.vel,
            pulse=pulse, glow=True, look=look,
            variant="crown" if not self.is_miniboss else "orbs",
            rotation=self.pulse_time,
        )

        for radius, life, col in self.warning_rings:
            alpha = max(30, int(180 * life))
            ring = pygame.Surface((int(radius * 2 + 4), int(radius * 2 + 4)), pygame.SRCALPHA)
            pygame.draw.circle(
                ring, (*col, alpha),
                (ring.get_width() // 2, ring.get_height() // 2),
                int(radius), 2,
            )
            surface.blit(ring, (sx - ring.get_width() // 2, sy - ring.get_height() // 2))

        if self.act_index == 7 and self.pull_pulse > 0.3:
            pr = int(self.size * (1.5 + self.pull_pulse))
            pygame.draw.circle(surface, (90, 60, 140), (sx, sy), pr, 1)

        bar_width = int(self.size * 2.5)
        bar_x = sx - bar_width // 2
        bar_y = sy - int(self.size) - 20
        draw_health_bar(surface, bar_x, bar_y, bar_width, 8, self.hp, self.max_hp)

        font = pygame.font.SysFont("segoeui", 13, bold=True)
        name = font.render(self.name, True, (230, 210, 180) if not self.enraged else (255, 140, 120))
        surface.blit(name, (sx - name.get_width() // 2, bar_y - 18))

        phase_label = ""
        if self.phase >= 3:
            phase_label = "FINAL PHASE"
        elif self.enraged:
            phase_label = "PHASE 2"
        if phase_label:
            text = font.render(phase_label, True, (255, 120, 120))
            surface.blit(text, (sx - text.get_width() // 2, bar_y - 34))

        if self.telegraph > 0:
            ring_r = int(self.size * (1.5 + (0.8 - min(0.8, self.telegraph))))
            pygame.draw.circle(surface, (255, 200, 100), (sx, sy), ring_r, 2)

    @property
    def radius(self) -> float:
        return self.size
