"""Boss encounter entities with act-unique phases."""

from __future__ import annotations

import math
import random
from typing import Callable, List, Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.data.bosses import (CADENCE, MINI, STATS, AnchorDef, BossDef, PhaseDef, anchor_def, mini_phases,
                                         warden_def)
from blob_evolution.data.lore import get_boss_name
from blob_evolution.entities.boss_attacks import BASIC_SHOTS, MOVERS, SPECIALS, BasicShot, Mover, Special, _proj
from blob_evolution.entities.boss_spawns import SpawnRequest
from blob_evolution.entities.projectile import Projectile
from blob_evolution.utils import boss_shapes
from blob_evolution.utils.boss_shapes import draw_blob_cached
from blob_evolution.utils.graphics import (draw_blob, draw_contact_shadow, draw_health_bar, get_boss_palette,
                                           get_shadow_sprite)
from blob_evolution.utils.vector2 import Vector2

Color = Tuple[int, int, int]
HitFilter = Callable[["Boss", Optional[Vector2]], float]     # (boss, unit direction to the hit or None) -> damage mult


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
        variant: int = 0,
    ) -> None:
        self.pos = pos.copy()
        self.vel = Vector2()
        diff = diff_mult or {"hp": 1.0, "damage": 1.0, "speed": 1.0}
        self.defn: BossDef = warden_def(act_index)
        self.phase_defs: Tuple[PhaseDef, ...] = mini_phases(act_index) if miniboss else self.defn.phases
        st = STATS
        power_index = act_index + slot
        self.size = st.size_base + power_index * st.size_per_power
        # Mini-bosses are one of the layer's two named anchors (TASK-057): name and radius; kit stays MINI's
        self.anchor: Optional[AnchorDef] = anchor_def(act_index, variant) if miniboss else None
        if miniboss:
            self.size = self.anchor.radius if self.anchor else st.mini_size_base + act_index * st.mini_size_per_act
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
        self.name = self.anchor.name if self.anchor else get_boss_name(act_index, miniboss=miniboss, slot=slot)
        self.move_mode = "orbit"
        self.dash_timer = 0.0
        self.dash_dir = Vector2()
        self.clone_timer = 0.0
        self.pull_pulse = 0.0
        self.spiral_index = 0
        self.specials_fired = 0                 # count of specials so far (layer 9 cycles its verdicts by it)
        basic_key = self.defn.basic if slot == 0 or not self.defn.basic_other_slots else self.defn.basic_other_slots
        self.basic_shot: BasicShot = BASIC_SHOTS[basic_key]
        self.special: Special = SPECIALS[MINI.special if miniboss else self.defn.special]
        self.mover: Mover = MOVERS[MINI.move if miniboss else self.defn.move]
        # TASK-056 framework (unused by today's kits): spawn outbox, hit direction, damage-taken multipliers
        self.spawn_outbox: List[SpawnRequest] = []
        self.last_hit_dir: Optional[Vector2] = None     # unit vector boss -> where the last directed hit landed
        self.damage_taken_mult = 1.0
        self.hit_filter: Optional[HitFilter] = None
        # TASK-058 art state (draw only; never read by update / AI): boss_shapes key, look target, phase fade, flash
        if miniboss:
            self.art_key: Optional[str] = self.anchor.key if self.anchor else None
        else:
            self.art_key = self.defn.key if self.defn.archive_id else None      # acts outside 0-9 keep main's draw
        self._look_at: Optional[Vector2] = None
        self._art_warm = False
        self._art_phase = self._art_prev_phase = 1
        self._art_phase_t0 = -1e9
        self._flash_t0 = -1e9
        self._flash_seen = 0.0
        # Visual telegraph rings for special arenas
        self.warning_rings: List[Tuple[float, float, Color]] = []  # radius, life, color

    def take_damage(self, amount: float, ignore_defense: float = 0.0, hit_from: Optional[Vector2] = None) -> bool:
        """Take damage (landing at `hit_from` if given). Returns True if killed; starts phases on threshold hits."""
        actual = amount * (1.0 + ignore_defense)
        hit_dir = None
        if hit_from is not None:
            hit_dir = (hit_from - self.pos).normalize()
            if hit_dir.x or hit_dir.y:
                self.last_hit_dir = hit_dir
            else:
                hit_dir = None                          # a hit at the centre has no direction
        mult = self.damage_taken_mult
        if self.hit_filter is not None:
            mult *= self.hit_filter(self, hit_dir)
        if mult != 1.0:
            actual *= mult
        prev_ratio = self.hp / self.max_hp if self.max_hp else 0
        self.hp -= actual
        self.hit_flash = 0.2
        ratio = self.hp / self.max_hp if self.max_hp else 0
        for pd in self.phase_defs:
            self._check_phase(pd, prev_ratio, ratio)
        return self.hp <= 0

    def _check_phase(self, pd: PhaseDef, prev_ratio: float, ratio: float) -> None:
        """Start phase `pd` if this hit meets its rule (once-only enrage, or crossing the threshold); maybe rename."""
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
        if pd.name:
            self.name = pd.name

    def heal(self, amount: float) -> float:
        """Heal up to max HP (phases already started stay started); return the HP gained."""
        before = self.hp
        self.hp = min(self.max_hp, self.hp + max(0.0, amount))
        return self.hp - before

    def queue_spawn(self, kind: str, pos: Vector2, *, delay: float = 0.0, lifetime: Optional[float] = None,
                    **params) -> SpawnRequest:
        """Ask the game to place a `kind` spawn (see entities/boss_spawns.py); it is owned by this boss."""
        req = SpawnRequest(kind, pos.copy(), self, delay, lifetime, params)
        self.spawn_outbox.append(req)
        return req

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
        self._look_at = player_pos                      # draw-only (eyes / aimed sprites face the player)
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
        self.specials_fired += 1

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

    def warm_art(self) -> None:
        """Bake this boss's sprites, plates and bar now (at spawn), so no fight frame allocates (spec rule 5)."""
        if self._art_warm or not self.art_key or not config.GFX_BOSS_ART:
            return
        self._art_warm = True
        key = self.art_key
        names = boss_shapes.ASCENT_NAMES if key == "ascent" and not self.is_miniboss else (self.name,)
        colours = (config.BOSS_NAME_COLOUR,) + tuple(boss_shapes.pal(key, ph)[2] for ph in range(1, 4))
        boss_shapes.warm_entity(key, int(self.size), names, colours, int(self.size * 2.5), 8,
                                boss_shapes.entity_element_colour(key))
        get_shadow_sprite(self.size)                    # the contact shadow's sprite for this radius

    def _aim_angle(self) -> float:
        """Screen angle toward the player (last update), else along the velocity, else 0."""
        if self._look_at is not None:
            dx, dy = self._look_at.x - self.pos.x, self._look_at.y - self.pos.y
            if dx or dy:
                return math.atan2(dy, dx)
        if self.vel.x or self.vel.y:
            return math.atan2(self.vel.y, self.vel.x)
        return 0.0

    def _flash_now(self, t: float) -> bool:
        """Rate-limited hit flash (spec rule 3): a new flash starts only BOSS_FLASH_MIN_GAP after the last start."""
        if self.hit_flash > self._flash_seen and t - self._flash_t0 >= config.BOSS_FLASH_MIN_GAP:
            self._flash_t0 = t
        self._flash_seen = self.hit_flash
        return t - self._flash_t0 < config.BOSS_FLASH_TIME

    def _draw_art(self, surface: pygame.Surface, sx: int, sy: int) -> None:
        """TASK-045 look: shadow, back, cached body, rim, front, phase fade + ring, cached plate / pips / bar."""
        key, t, R = self.art_key, self.pulse_time, int(self.size)
        ent = boss_shapes.entity(key)
        self.warm_art()
        w, h = surface.get_size()
        m = 1.9 * R + 60                                # spec 2.1 cull: nothing of the boss (plate included) shows
        if sx < -m or sx > w + m or sy < -m or sy > h + m:
            return
        if self.phase != self._art_phase:
            self._art_prev_phase, self._art_phase, self._art_phase_t0 = self._art_phase, self.phase, t
        since = t - self._art_phase_t0
        if config.GFX_READABILITY:
            draw_contact_shadow(surface, sx, sy, self.size)
        boss_shapes.draw_boss(surface, key, self.phase, sx, sy, R, t, self._aim_angle(), flash=self._flash_now(t),
                              blob_fn=draw_blob_cached, fade_from=self._art_prev_phase,
                              fade=min(1.0, since / config.BOSS_PHASE_FADE))
        if since < config.BOSS_PHASE_RING_TIME:
            p = since / config.BOSS_PHASE_RING_TIME
            boss_shapes.ring_out(surface, sx, sy, R + (boss_shapes.phase_ring_end(R) - R) * p,
                                 boss_shapes.entity_element_colour(key),
                                 config.BOSS_PHASE_RING_ALPHA * (1 - p), style="phase")
        for radius, life, col in self.warning_rings:
            boss_shapes.ring_out(surface, sx, sy, radius, col, max(30, int(180 * life)), quant=1)
        if self.act_index == 7 and self.pull_pulse > 0.3:
            pygame.draw.circle(surface, (90, 60, 140), (sx, sy), int(self.size * (1.5 + self.pull_pulse)), 1)
        bar_w = int(self.size * 2.5)
        bar_y = sy - int(self.size) - 20
        ratio = self.hp / self.max_hp if self.max_hp > 0 else 0.0
        boss_shapes.health_bar(surface, sx - bar_w // 2, bar_y, bar_w, 8, ratio,
                               tuple(pd.below for pd in self.phase_defs), config.BOSS_BAR_NOTCH)
        colour = config.BOSS_NAME_COLOUR if self.phase == 1 else boss_shapes.pal(key, self.phase)[2]
        plate = boss_shapes.name_plate(self.name, colour)
        surface.blit(plate, (sx - plate.get_width() // 2, bar_y - 18))
        if ent["phases"] > 1:
            pips = boss_shapes.phase_pips(ent["phases"], min(self.phase, ent["phases"]),
                                          boss_shapes.entity_element_colour(key))
            surface.blit(pips, (sx - pips.get_width() // 2, bar_y - 32))
        if self.telegraph > 0:
            ring_r = int(self.size * (1.5 + (0.8 - min(0.8, self.telegraph))))
            pygame.draw.circle(surface, (255, 200, 100), (sx, sy), ring_r, 2)

    def draw(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw the boss: the TASK-045 art (GFX_BOSS_ART), else main's drawing unchanged."""
        sx = int(self.pos.x - camera.x + config.SCREEN_WIDTH // 2 + shake.x)
        sy = int(self.pos.y - camera.y + config.SCREEN_HEIGHT // 2 + shake.y)
        if config.GFX_BOSS_ART and self.art_key:
            self._draw_art(surface, sx, sy)
            return
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
