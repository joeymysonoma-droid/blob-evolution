"""F4 boss-shot behaviours (homing, delay, lob, fade), reflectors, on-hit hook and the boss-shot cap.

Inert until a kit uses it: no current attack attaches a behaviour or places a reflector, so shot streams match main.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.data import bosses
from blob_evolution.utils.vector2 import Vector2



def live_boss_shots(projectiles: List) -> int:
    """Active boss shots in the list."""
    return sum(1 for p in projectiles if p.active and p.kind == "boss")


def cap_new_boss_shots(projectiles: List, start: int) -> int:
    """Drop the boss shots appended since index `start` that would pass BOSS_SHOT_CAP or MAX_PROJECTILES; return dropped.

    Existing shots are never culled: only the new ones past the cap are skipped (removed before they ever update).
    """
    if len(projectiles) <= start:
        return 0
    boss = live_boss_shots(projectiles[:start])
    total = sum(1 for p in projectiles[:start] if p.active)
    kept, dropped = [], 0
    for p in projectiles[start:]:
        if p.kind == "boss" and (boss >= config.BOSS_SHOT_CAP or total >= config.MAX_PROJECTILES):
            dropped += 1
            continue
        kept.append(p)
        if p.active:
            total += 1
            boss += p.kind == "boss"
    if dropped:
        projectiles[start:] = kept
    return dropped


class Behaviour:
    """A shot behaviour: step() moves the shot instead of the straight-line default and returns False when it is done."""

    def step(self, p, dt: float) -> bool:
        p.pos.add(p.vel * dt)
        return True


@dataclass
class Homing(Behaviour):
    """Turn toward target() at most turn_rate deg/s for `duration` s, then fly straight."""
    target: Callable[[], Vector2]
    duration: float
    turn_rate: float = field(default_factory=lambda: config.BOSS_HOMING_TURN_DEG)

    def step(self, p, dt: float) -> bool:
        if self.duration > 0:
            self.duration -= dt
            to = self.target() - p.pos
            if to.length() > 0:
                speed = p.vel.length()
                cur = math.atan2(p.vel.y, p.vel.x)
                want = math.atan2(to.y, to.x)
                diff = (want - cur + math.pi) % (2 * math.pi) - math.pi
                limit = math.radians(self.turn_rate) * dt
                cur += max(-limit, min(limit, diff))
                p.vel = Vector2(math.cos(cur), math.sin(cur)) * speed
        p.pos.add(p.vel * dt)
        return True


@dataclass
class Delayed(Behaviour):
    """Hold still for `delay` s, then fly straight."""
    delay: float

    def step(self, p, dt: float) -> bool:
        if self.delay > 0:
            self.delay -= dt
            return True
        p.pos.add(p.vel * dt)
        return True


@dataclass
class Lob(Behaviour):
    """Arc from `start` to `target` over `time` s with a `peak` px rise (height drawn only); land() at the target."""
    start: Vector2
    target: Vector2
    time: float = field(default_factory=lambda: config.BOSS_LOB_TIME)
    peak: float = field(default_factory=lambda: config.BOSS_LOB_PEAK)
    land: Optional[Callable[[Vector2], None]] = None
    t: float = 0.0
    height: float = 0.0

    def step(self, p, dt: float) -> bool:
        self.t = min(self.time, self.t + dt)
        u = self.t / self.time if self.time > 0 else 1.0
        p.pos = self.start + (self.target - self.start) * u
        self.height = 4 * self.peak * u * (1 - u)
        if u >= 1.0:
            if self.land is not None:
                self.land(self.target.copy())
            return False
        return True

    @property
    def airborne(self) -> bool:
        """A lobbed shot cannot hit anything until it lands."""
        return self.t < self.time


def fade_alpha(p) -> int:
    """Draw alpha of a shot with fade=True: 255, ramping to 0 over its last BOSS_SHOT_FADE s of lifetime."""
    if not getattr(p, "fade", False) or p.lifetime >= config.BOSS_SHOT_FADE:
        return 255
    return max(0, int(255 * p.lifetime / config.BOSS_SHOT_FADE))


_FADED: Dict[Tuple[int, int], pygame.Surface] = {}
FADE_STEPS = 4


def faded_sprite(sprite: pygame.Surface, alpha: int) -> pygame.Surface:
    """A cached copy of `sprite` at `alpha`, quantised to FADE_STEPS levels (no per-frame Surface)."""
    level = max(1, round(alpha / 255 * FADE_STEPS))
    key = (id(sprite), level)
    s = _FADED.get(key)
    if s is None:
        if len(_FADED) > 160:
            _FADED.clear()
        s = sprite.copy()
        s.set_alpha(int(255 * level / FADE_STEPS))
        _FADED[key] = s
    return s


@dataclass
class Reflector:
    """A circle that sends shots back once (crystal pillars, Dream Door). Nothing places one yet."""
    pos: Vector2
    radius: float
    damage_mult: float = 1.0


def reflect_shots(projectiles: List, reflectors: List[Reflector], hurts_player: Optional[bool] = None) -> int:
    """Reverse every live, not yet reflected shot touching a reflector; return how many turned.

    With hurts_player (default data/bosses.REFLECT_HURTS_PLAYER) a player shot comes back hostile and hits the player through the
    game's normal enemy-shot path (invulnerability, shield, one hurt sound per hit). Boss shots come back unchanged.
    """
    if not reflectors:
        return 0
    hurts = bosses.REFLECT_HURTS_PLAYER if hurts_player is None else hurts_player
    turned = 0
    for p in projectiles:
        if not p.active or p.reflected:
            continue
        for r in reflectors:
            if p.collides_with(r.pos, r.radius):
                p.vel = p.vel * -1
                p.damage *= r.damage_mult
                p.reflected = True
                if p.from_player and hurts:
                    p.from_player = False
                turned += 1
                break
    return turned


def on_hit(p, player) -> None:
    """F4 on-hit hook: run the shot's effect (F5 statuses plug in here) after it hit the player."""
    if p.effect is not None:
        p.effect(player)
