"""Boss movement and attack kits (TASK-054): small classes and functions picked by the keys in data/bosses.py."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from blob_evolution import config
from blob_evolution.entities.projectile import Projectile
from blob_evolution.utils.vector2 import Vector2

if TYPE_CHECKING:
    from blob_evolution.entities.boss import Boss

Color = Tuple[int, int, int]


def _proj(
    pos: Vector2,
    direction: Vector2,
    speed: float,
    damage: float,
    color: Optional[Color] = None,
) -> Projectile:
    """A boss shot: kind "boss", with the attack's colour."""
    p = Projectile(pos.copy(), direction, speed, damage, from_player=False)
    p.kind = "boss"
    if color:
        p.color = color
    return p


# --------------------------------------------------------------------------- movement
Mover = Callable[["Boss", float, Vector2, float], None]


def _orbit_around(b: Boss, player_pos: Vector2, radius: float, speed: float) -> None:
    """Steer toward the point at `b.angle` on a circle of `radius` around the player."""
    target = player_pos + Vector2(math.cos(b.angle) * radius, math.sin(b.angle) * radius)
    b._steer_toward(target, speed)


def move_orbit(b: Boss, dt: float, player_pos: Vector2, speed: float) -> None:
    """Wide orbit around the player (Rim, Vaults, Strata, every mini-boss)."""
    b.angle += dt * (1.6 if b.enraged else 1.1)
    radius = 260 if b.enraged else 300
    _orbit_around(b, player_pos, radius, speed)


def move_weave(b: Boss, dt: float, player_pos: Vector2, speed: float) -> None:
    """Rot: slow weave that closes in and backs off."""
    b.angle += dt * 0.9
    radius = 180 + 80 * math.sin(b.pulse_time)
    _orbit_around(b, player_pos, radius, speed * 0.85)


def move_circle_dash(b: Boss, dt: float, player_pos: Vector2, speed: float) -> None:
    """Ash: circle the player, now and then dash at them."""
    b.angle += dt * 1.3
    _orbit_around(b, player_pos, 280, speed)
    if random.random() < dt * 0.35:
        to_p = (player_pos - b.pos).copy()
        if to_p.length() > 0:
            to_p.normalize()
            b.dash_dir = to_p
            b.dash_timer = 0.35
            b.telegraph = 0.35
            b.telegraph_type = "dash"


def move_linger(b: Boss, dt: float, player_pos: Vector2, speed: float) -> None:
    """Frost: keep a middle distance, strafing sideways inside it."""
    to_p = (player_pos - b.pos).copy()
    dist = to_p.length()
    if dist > 0:
        to_p.normalize()
    if dist < 240:
        b.vel = to_p * -speed
    elif dist > 360:
        b.vel = to_p * speed * 0.7
    else:
        b.vel = Vector2(-to_p.y, to_p.x) * speed * 0.5


def move_blink(b: Boss, dt: float, player_pos: Vector2, speed: float) -> None:
    """Thirst: blink to a random point around the player, drift in between."""
    b.clone_timer -= dt
    if b.clone_timer <= 0:
        ang = random.uniform(0, math.tau)
        b.pos = player_pos + Vector2(math.cos(ang) * 320, math.sin(ang) * 320)
        b.clone_timer = 3.5 if b.enraged else 5.0
        b.telegraph = 0.4
        b.telegraph_type = "blink"
    b._steer_toward(player_pos, speed * 0.4)


def move_strafe(b: Boss, dt: float, player_pos: Vector2, speed: float) -> None:
    """Masks: fast tight strafe around the player."""
    b.angle += dt * 2.0
    _orbit_around(b, player_pos, 200, speed * 1.2)


def move_drift(b: Boss, dt: float, player_pos: Vector2, speed: float) -> None:
    """Silence: drift in with a pulsing pull."""
    b.pull_pulse = (math.sin(b.pulse_time * 2) + 1) * 0.5
    b._steer_toward(player_pos, speed * (0.5 + 0.4 * b.pull_pulse))


def move_assault(b: Boss, dt: float, player_pos: Vector2, speed: float) -> None:
    """Divide (and any act without its own kit): aggressive orbit, tighter in phase 3."""
    b.angle += dt * (2.0 if b.enraged else 1.4)
    radius = 220 if b.phase >= 3 else 280
    _orbit_around(b, player_pos, radius, speed * 1.15)


MOVERS: Dict[str, Mover] = {
    "orbit": move_orbit, "weave": move_weave, "circle_dash": move_circle_dash, "linger": move_linger,
    "blink": move_blink, "strafe": move_strafe, "drift": move_drift, "assault": move_assault,
}


# --------------------------------------------------------------------------- basic shots
class BasicShot:
    """A basic shot fired every few seconds toward the player (`to_player` is already normalised)."""

    key = ""

    def fire(self, b: Boss, to_player: Vector2, projectiles: List[Projectile]) -> None:
        """Spawn the shot(s)."""
        raise NotImplementedError

    @staticmethod
    def speed(b: Boss) -> float:
        """Base shot speed (faster once enraged)."""
        return 260 if b.enraged else 210

    @staticmethod
    def _spread(b: Boss, to_player: Vector2, spreads: Tuple[float, ...], speed: float, damage: float, color: Color,
                projectiles: List[Projectile]) -> None:
        """One shot per angle offset from the aim direction."""
        for spread in spreads:
            a = to_player.angle() + spread
            projectiles.append(_proj(b.pos, Vector2(math.cos(a), math.sin(a)), speed, damage, color))


class AimedShot(BasicShot):
    """One plain shot at the player."""

    key = "aimed"

    def fire(self, b: Boss, to_player: Vector2, projectiles: List[Projectile]) -> None:
        """Spawn the shot."""
        projectiles.append(_proj(b.pos, to_player, self.speed(b), b.damage))


class SpiralSeed(BasicShot):
    """Rim: seeds along a slow spiral, ignoring the player."""

    key = "spiral_seed"

    def fire(self, b: Boss, to_player: Vector2, projectiles: List[Projectile]) -> None:
        """Spawn the next seed of the spiral."""
        ang = b.spiral_index * 0.7
        b.spiral_index += 1
        direction = Vector2(math.cos(ang), math.sin(ang))
        projectiles.append(_proj(b.pos, direction, self.speed(b), b.damage * 0.7, (80, 200, 100)))


class WeepingTwin(BasicShot):
    """Rot: two shots either side of the player."""

    key = "weeping_twin"

    def fire(self, b: Boss, to_player: Vector2, projectiles: List[Projectile]) -> None:
        """Spawn the twin shots."""
        self._spread(b, to_player, (-0.25, 0.25), self.speed(b) * 0.85, b.damage * 0.75, (120, 180, 50), projectiles)


class GhostShot(BasicShot):
    """Echoes: a shot and a slower, longer-lived ghost behind it."""

    key = "ghost_shot"

    def fire(self, b: Boss, to_player: Vector2, projectiles: List[Projectile]) -> None:
        """Spawn the shot and its ghost."""
        speed, dmg = self.speed(b), b.damage
        projectiles.append(_proj(b.pos, to_player, speed, dmg, (140, 190, 255)))
        delayed = _proj(b.pos, to_player, speed * 0.55, dmg * 0.7, (100, 140, 220))
        delayed.lifetime = 4.0
        projectiles.append(delayed)


class ShardFan(BasicShot):
    """Frost: a three-shot fan."""

    key = "shard_fan"

    def fire(self, b: Boss, to_player: Vector2, projectiles: List[Projectile]) -> None:
        """Spawn the fan."""
        self._spread(b, to_player, (-0.35, 0, 0.35), self.speed(b) * 0.9, b.damage * 0.65, (200, 230, 255), projectiles)


class VoidBolt(BasicShot):
    """Silence: one slow heavy bolt."""

    key = "void_bolt"

    def fire(self, b: Boss, to_player: Vector2, projectiles: List[Projectile]) -> None:
        """Spawn the bolt."""
        projectiles.append(_proj(b.pos, to_player, self.speed(b) * 0.7, b.damage * 1.1, (80, 50, 120)))


class PinkTriple(BasicShot):
    """Divide (and the layer 9 warden in slot 0): three pink shots."""

    key = "pink_triple"

    def fire(self, b: Boss, to_player: Vector2, projectiles: List[Projectile]) -> None:
        """Spawn the triple shot."""
        self._spread(b, to_player, (-0.2, 0, 0.2), self.speed(b), b.damage, (255, 80, 180), projectiles)


BASIC_SHOTS: Dict[str, BasicShot] = {
    cls.key: cls() for cls in (AimedShot, SpiralSeed, WeepingTwin, GhostShot, ShardFan, VoidBolt, PinkTriple)
}


# --------------------------------------------------------------------------- specials
class Special:
    """A special attack; the boss has already set its 0.7 s telegraph when fire() runs."""

    key = ""
    telegraph_type = ""

    def fire(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile]) -> None:
        """Set the telegraph type and spawn the attack."""
        b.telegraph_type = self.telegraph_type
        self.spawn(b, player_pos, projectiles, b.damage)

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn the shots."""
        raise NotImplementedError


def _aim(b: Boss, player_pos: Vector2) -> Optional[Vector2]:
    """Normalised direction from the boss to the player, None at zero distance."""
    to_p = (player_pos - b.pos).copy()
    if to_p.length() > 0:
        to_p.normalize()
        return to_p
    return None


def _fan(b: Boss, aim: Vector2, spreads: Tuple[float, ...], speed: float, damage: float, color: Color,
         projectiles: List[Projectile]) -> None:
    """One shot per angle offset from `aim`."""
    for spread in spreads:
        a = aim.angle() + spread
        projectiles.append(_proj(b.pos, Vector2(math.cos(a), math.sin(a)), speed, damage, color))


class AnchorRadial(Special):
    """Lattice Anchor (every mini-boss): a 6-way radial burst."""

    key, telegraph_type = "anchor_radial", "radial"

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn the burst."""
        b._radial(projectiles, 6, 200, dmg * 0.7, (200, 160, 255))


class BloomRing(Special):
    """Rim: a 10-way seed ring."""

    key, telegraph_type = "bloom_ring", "bloom"

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn the ring."""
        b._radial(projectiles, 10, 190, dmg * 0.65, (90, 210, 110))


class RotRing(Special):
    """Rot: an 8-way ring and a slower offset second ring."""

    key, telegraph_type = "rot_ring", "rot"

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn both rings."""
        b._radial(projectiles, 8, 170, dmg * 0.7, (140, 200, 60))
        b._radial(projectiles, 8, 110, dmg * 0.5, (100, 150, 40), offset=math.pi / 8)


class EchoRing(Special):
    """Echoes: a 12-way ring, each shot with a slow ghost."""

    key, telegraph_type = "echo_ring", "echo"

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn the ring and its ghosts."""
        for i in range(12):
            ang = i * math.tau / 12
            direction = Vector2(math.cos(ang), math.sin(ang))
            projectiles.append(_proj(b.pos, direction, 240, dmg * 0.6, (160, 210, 255)))
            ghost = _proj(b.pos, direction, 140, dmg * 0.5, (90, 130, 200))
            ghost.lifetime = 4.5
            projectiles.append(ghost)


class EruptRing(Special):
    """Ash: a 12-way eruption ring, then a dash at the player."""

    key, telegraph_type = "erupt_ring", "erupt"

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn the ring and start the dash."""
        b._radial(projectiles, 12, 230, dmg * 0.75, (255, 120, 40))
        to_p = _aim(b, player_pos)
        if to_p is not None:
            b.dash_dir = to_p
            b.dash_timer = 0.4


class FrostRing(Special):
    """Frost: a warning ring and a 16-way frost ring."""

    key, telegraph_type = "frost_ring", "frost"

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn the ring."""
        b.warning_rings.append((180.0, 0.9, (180, 220, 255)))
        for i in range(16):
            ang = i * math.tau / 16
            direction = Vector2(math.cos(ang), math.sin(ang))
            projectiles.append(_proj(b.pos, direction, 160, dmg * 0.55, (210, 235, 255)))


class MirageVolley(Special):
    """Thirst: three decoy shots at random angles, then the real four-shot volley."""

    key, telegraph_type = "mirage_volley", "mirage"

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn the decoys and the volley."""
        for _ in range(3):
            ang = random.uniform(0, math.tau)
            fake_dir = Vector2(math.cos(ang), math.sin(ang))
            projectiles.append(_proj(b.pos, fake_dir, 200, dmg * 0.4, (230, 200, 100)))
        to_p = _aim(b, player_pos)
        if to_p is not None:
            _fan(b, to_p, (-0.3, -0.1, 0.1, 0.3), 300, dmg, (255, 210, 80), projectiles)


class MaskBurst(Special):
    """Masks: eight aimed shots from points orbiting the boss."""

    key, telegraph_type = "mask_burst", "mask"

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn the burst."""
        for i in range(8):
            ang = b.angle + i * math.tau / 8
            origin = b.pos + Vector2(math.cos(ang) * 60, math.sin(ang) * 60)
            to_p = (player_pos - origin).copy()
            if to_p.length() > 0:
                to_p.normalize()
                projectiles.append(_proj(origin, to_p, 250, dmg * 0.7, (190, 120, 255)))


class VoidRing(Special):
    """Silence: a warning ring, a 10-way ring and an inward wave from around the player."""

    key, telegraph_type = "void_ring", "void"

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn the ring and the inward wave."""
        b.warning_rings.append((220.0, 1.0, (120, 80, 180)))
        b._radial(projectiles, 10, 150, dmg * 0.8, (90, 60, 140))
        for i in range(8):
            ang = i * math.tau / 8
            origin = player_pos + Vector2(math.cos(ang) * 280, math.sin(ang) * 280)
            inward = (player_pos - origin).copy()
            if inward.length() > 0:
                inward.normalize()
                projectiles.append(_proj(origin, inward, 180, dmg * 0.65, (60, 40, 100)))


class Verdict(Special):
    """Strata: radial, targeted and cross verdicts in turn (config.BOSS_VERDICT_ORDER), starting at the boss slot."""

    key, telegraph_type = "verdict", "verdict"

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn this special's verdict; the next special plays the next one (main always played the slot's)."""
        order = config.BOSS_VERDICT_ORDER
        pick = order[(b.slot + b.specials_fired) % len(order)]
        if pick == "radial":
            b._radial(projectiles, 10, 220, dmg * 0.7, (180, 200, 255))
        elif pick == "targeted":
            to_p = _aim(b, player_pos)
            if to_p is not None:
                _fan(b, to_p, (-0.4, -0.2, 0, 0.2, 0.4), 280, dmg, (200, 220, 255), projectiles)
        else:
            for ang in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                for dist_off in (0, 0.15, -0.15):
                    a = ang + dist_off
                    projectiles.append(_proj(b.pos, Vector2(math.cos(a), math.sin(a)), 240, dmg * 0.7, (220, 230, 255)))


class Divide(Special):
    """First Divide (and any act without its own kit): a 14-way ring, an aimed triple, a third ring in phase 3."""

    key, telegraph_type = "divide", "divide"

    def spawn(self, b: Boss, player_pos: Vector2, projectiles: List[Projectile], dmg: float) -> None:
        """Spawn everything."""
        b._radial(projectiles, 14, 210, dmg * 0.7, (255, 80, 180))
        to_p = _aim(b, player_pos)
        if to_p is not None:
            _fan(b, to_p, (-0.35, 0, 0.35), 320, dmg, (255, 120, 200), projectiles)
        if b.phase >= 3:
            b._radial(projectiles, 8, 140, dmg * 0.5, (200, 50, 150), offset=0.4)


SPECIALS: Dict[str, Special] = {
    cls.key: cls() for cls in (AnchorRadial, BloomRing, RotRing, EchoRing, EruptRing, FrostRing, MirageVolley,
                               MaskBurst, VoidRing, Verdict, Divide)
}
