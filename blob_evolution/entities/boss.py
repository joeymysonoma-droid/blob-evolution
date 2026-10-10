"""Boss encounter entities with act-unique phases."""

from __future__ import annotations

import math
import random
from typing import List, Tuple

import pygame

from blob_evolution import config
from blob_evolution.data.bosses import CADENCE, MINI, STATS, BossDef, PhaseDef, warden_def
from blob_evolution.data.lore import get_boss_name
from blob_evolution.entities.boss_attacks import BASIC_SHOTS, MOVERS, SPECIALS, BasicShot, Mover, Special, _proj
from blob_evolution.entities.projectile import Projectile
from blob_evolution.utils.graphics import draw_blob, draw_contact_shadow, draw_health_bar, get_boss_palette
from blob_evolution.utils.vector2 import Vector2

Color = Tuple[int, int, int]


class Boss:
    """Multi-phase boss; stats, phases, movement and attacks come from data/bosses.py (TASK-054)."""

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
        self.defn: BossDef = warden_def(act_index)
        self.phase_defs: Tuple[PhaseDef, ...] = self.defn.phases
        st = STATS
        power_index = act_index + slot
        self.size = st.size_base + power_index * st.size_per_power
        if miniboss:
            self.size = st.mini_size_base + act_index * st.mini_size_per_act
        self.max_hp = (st.hp_base + power_index * st.hp_per_power) * diff["hp"]
        if miniboss:
            self.max_hp *= st.mini_hp_mult
        self.hp = self.max_hp
        self.damage = (st.damage_base + power_index * st.damage_per_power) * diff["damage"]
        self.speed = st.speed * diff["speed"]
        self.active = True
        self.enraged = False
        self.phase = 1
        self.phase_announced = False
        self.xp_value = int(self.max_hp)
        self.shoot_cooldown = CADENCE.first_basic
        self.special_cooldown = CADENCE.first_special
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
        basic_key = self.defn.basic if slot == 0 or not self.defn.basic_other_slots else self.defn.basic_other_slots
        self.basic_shot: BasicShot = BASIC_SHOTS[basic_key]
        self.special: Special = SPECIALS[MINI.special if miniboss else self.defn.special]
        self.mover: Mover = MOVERS[MINI.move if miniboss else self.defn.move]
        # Visual telegraph rings for special arenas
        self.warning_rings: List[Tuple[float, float, Color]] = []  # radius, life, color

    def take_damage(self, amount: float, ignore_defense: float = 0.0) -> bool:
        """Take damage. Returns True if killed. Sets phase_announced when crossing thresholds."""
        actual = amount * (1.0 + ignore_defense)
        prev_ratio = self.hp / self.max_hp if self.max_hp else 0
        self.hp -= actual
        self.hit_flash = 0.2
        ratio = self.hp / self.max_hp if self.max_hp else 0
        for pd in self.phase_defs:
            self._check_phase(pd, prev_ratio, ratio)
        return self.hp <= 0

    def _check_phase(self, pd: PhaseDef, prev_ratio: float, ratio: float) -> None:
        """Start phase `pd` if this hit meets its rule (once-only enrage, or crossing the threshold)."""
        if ratio >= pd.below:
            return
        if pd.enrage:
            if self.enraged:
                return
            self.enraged = True
        elif pd.crossing and prev_ratio < pd.below:
            return
        self.phase = pd.phase
        self.phase_announced = True
        self.special_cooldown = pd.special_cooldown

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
        """Advance timers, move, and fire the basic shot and the special when their cooldowns run out."""
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

        cad = CADENCE
        if self.shoot_cooldown <= 0:
            self._basic_attack(player_pos, projectiles)
            base = cad.basic_enraged if self.enraged else cad.basic
            if self.phase >= 3:
                base *= cad.basic_final_mult
            if self.is_miniboss:
                base *= cad.basic_mini_mult
            self.shoot_cooldown = base

        if self.special_cooldown <= 0:
            self._special_attack(player_pos, projectiles)
            cd = cad.special_enraged if self.enraged else cad.special
            if self.phase >= 3:
                cd *= cad.special_final_mult
            if self.is_miniboss:
                cd *= cad.special_mini_mult
            self.special_cooldown = cd

    def _update_movement(self, dt: float, player_pos: Vector2) -> None:
        """Keep dashing while a dash runs, else move with this boss's mover."""
        enrage_mult = 1.55 if self.enraged else 1.0
        speed = self.speed * enrage_mult * self.slow_factor

        if self.dash_timer > 0:
            self.dash_timer -= dt
            self.vel = self.dash_dir * speed * 4.5
            return
        self.mover(self, dt, player_pos, speed)

    def _steer_toward(self, target: Vector2, speed: float) -> None:
        """Head straight for `target` at `speed`; stop when within 5 px."""
        direction = (target - self.pos).copy()
        if direction.length() > 5:
            direction.normalize()
            self.vel = direction * speed
        else:
            self.vel = Vector2()

    def _basic_attack(self, player_pos: Vector2, projectiles: List[Projectile]) -> None:
        """Fire this boss's basic shot at the player (nothing at zero distance)."""
        to_player = (player_pos - self.pos).copy()
        if to_player.length() <= 0:
            return
        to_player.normalize()
        self.basic_shot.fire(self, to_player, projectiles)

    def _special_attack(self, player_pos: Vector2, projectiles: List[Projectile]) -> None:
        """Start the 0.7 s telegraph and fire this boss's special."""
        self.telegraph = 0.7
        self.special.fire(self, player_pos, projectiles)

    def _radial(
        self,
        projectiles: List[Projectile],
        count: int,
        speed: float,
        damage: float,
        color: Color,
        offset: float = 0.0,
    ) -> None:
        """Ring of `count` shots evenly spaced, starting at `offset` radians."""
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
        if config.GFX_READABILITY:
            draw_contact_shadow(surface, sx, sy, self.size)
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
