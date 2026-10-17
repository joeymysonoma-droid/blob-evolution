"""F3: telegraph objects, the attack kit they come from, and their game-side damage resolution.

A Telegraph is pure data plus geometry: it warns for `warn` seconds, then lands once (`landed`), and the game checks
the player against its shape and applies `damage` (resolve_landed). Nothing here draws except draw_telegraphs, a minimal
debug renderer over the cached utils/boss_shapes kit. No current boss uses the kit yet, so main's fights are unchanged:
a boss with no running attacks and no telegraphs pays one empty-list check per frame.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from blob_evolution import config
from blob_evolution.data.bosses import TELEGRAPH_WARN
from blob_evolution.utils.vector2 import Vector2

KINDS = ("zone", "lane", "mark", "fan", "ring", "safe")
_LAYER_ELEMENTS = ("growth", "toxic", "echo", "fire", "frost", "mirage", "dream", "void", "lightning", "anchor")


def element_for(layer: int) -> str:
    """The element (boss_shapes.ELEMENTS key) of a layer 0-9; layers outside clamp."""
    return _LAYER_ELEMENTS[max(0, min(layer, len(_LAYER_ELEMENTS) - 1))]


@dataclass
class Telegraph:
    """One warning on the ground.

    geom by kind (world px / radians):
      zone (cx, cy, r) | mark (x, y, r)           a disc
      lane (x0, y0, x1, y1, width)                a thick segment
      fan  (cx, cy, angle, spread, length)        a sector
      ring (cx, cy, r_in, r_out)                  an annulus
      safe (x, y, w, h)                           everything not strictly inside the rect is hit
    """

    kind: str
    geom: Tuple[float, ...]
    element: str = "growth"           # boss_shapes.ELEMENTS key (element_for(layer) gives a layer's own)
    warn: Optional[float] = None      # None -> TELEGRAPH_WARN[kind]
    damage: float = 0.0
    effect: Optional[Any] = None      # StatusSpec once F5 lands; carried, not applied, here
    left: float = field(init=False)
    landed: bool = field(init=False, default=False)
    done: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown telegraph kind {self.kind!r}")
        if self.warn is None:
            self.warn = TELEGRAPH_WARN[self.kind]
        self.left = self.warn

    @property
    def progress(self) -> float:
        """Warning progress 0..1 (1 = lands now)."""
        return 1.0 if self.warn <= 0 else min(1.0, max(0.0, 1.0 - self.left / self.warn))

    def update(self, dt: float) -> None:
        """Count down; `landed` is True for exactly the update in which the warning runs out, then `done`."""
        if self.landed:
            self.landed, self.done = False, True
            return
        if self.done:
            return
        self.left -= dt
        if self.left <= 0:
            self.left, self.landed = 0.0, True

    def hits(self, pos: Vector2, radius: float = 0.0) -> bool:
        """Does a circle at `pos` with `radius` overlap the dangerous area?"""
        g, x, y = self.geom, pos.x, pos.y
        if self.kind in ("zone", "mark"):
            return math.hypot(x - g[0], y - g[1]) <= g[2] + radius
        if self.kind == "ring":
            d = math.hypot(x - g[0], y - g[1])
            return g[2] - radius <= d <= g[3] + radius
        if self.kind == "lane":
            x0, y0, x1, y1, w = g
            dx, dy = x1 - x0, y1 - y0
            ll = dx * dx + dy * dy
            t = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / ll))
            return math.hypot(x - (x0 + t * dx), y - (y0 + t * dy)) <= w / 2 + radius
        if self.kind == "fan":
            cx, cy, ang, spread, length = g
            d = math.hypot(x - cx, y - cy)
            if d > length + radius:
                return False
            if d <= radius:
                return True
            off = (math.atan2(y - cy, x - cx) - ang + math.pi) % math.tau - math.pi
            return abs(off) <= spread / 2 + math.asin(min(1.0, radius / d))
        rx, ry, rw, rh = g          # safe: hit unless the circle is strictly inside the rect; touching the rect's
        # edge counts as inside the danger, as a circle touching a zone's edge does (BUG-211)
        return not (rx + radius < x < rx + rw - radius and ry + radius < y < ry + rh - radius)


@dataclass
class BossContext:
    """What an Attack may touch. rng is the attack's own generator (never the global one)."""

    player_pos: Vector2
    projectiles: list
    telegraphs: List[Telegraph]
    rng: random.Random
    t: float = 0.0


class Attack:
    """One kit attack: start() emits telegraphs and returns the warning time, update() runs it, fire() lands it."""

    key = ""

    def __init__(self, boss: Any, **params: Any) -> None:
        self.boss, self.params = boss, params
        self.elapsed, self.warn, self.fired = 0.0, 0.0, False

    def start(self, ctx: BossContext) -> float:
        return 0.0

    def update(self, dt: float, ctx: BossContext) -> bool:
        """Advance; fire once when the warning is over. True when finished."""
        self.elapsed += dt
        if not self.fired and self.elapsed >= self.warn:
            self.fired = True
            self.fire(ctx)
        return self.fired

    def fire(self, ctx: BossContext) -> None:
        pass


class TelegraphStrike(Attack):
    """The kit's generic strike: one telegraph of `kind` aimed at the player; its damage lands through the game."""

    key = "telegraph_strike"

    def start(self, ctx: BossContext) -> float:
        p = self.params
        kind = p.get("kind", "zone")
        x, y, b = ctx.player_pos.x, ctx.player_pos.y, self.boss
        if kind in ("zone", "mark"):
            geom: Tuple[float, ...] = (x, y, p.get("radius", 70.0))
        elif kind == "ring":
            geom = (b.pos.x, b.pos.y, p.get("r_in", 120.0), p.get("r_out", 180.0))
        elif kind == "lane":
            geom = (b.pos.x, b.pos.y, x, y, p.get("width", 60.0))
        elif kind == "fan":
            geom = (b.pos.x, b.pos.y, math.atan2(y - b.pos.y, x - b.pos.x), p.get("spread", 0.8), p.get("length", 420.0))
        else:
            s = p.get("size", 240.0)
            geom = (x - s / 2 + ctx.rng.uniform(-60, 60), y - s / 2 + ctx.rng.uniform(-60, 60), s, s)
        tg = Telegraph(kind, geom, p.get("element", element_for(b.act_index)), p.get("warn"), p.get("damage", b.damage), p.get("effect"))
        ctx.telegraphs.append(tg)
        self.warn = tg.warn
        return self.warn


ATTACKS: Dict[str, type] = {TelegraphStrike.key: TelegraphStrike}


def resolve_landed(telegraphs: Sequence[Telegraph], pos: Vector2, radius: float) -> float:
    """Damage of the ONE hit the telegraphs landing this frame deal to the player (BUG-210): overlapping telegraphs do
    not stack, the highest damage among those that touch counts (0 = no hit). The game applies it as a single hit, so a
    shield blocks it once."""
    return max((t.damage for t in telegraphs if t.landed and t.damage > 0 and t.hits(pos, radius)), default=0.0)


def draw_telegraphs(screen: Any, camera: Any, shake: Any, telegraphs: Sequence[Telegraph]) -> None:
    """Minimal debug renderer: the cached boss_shapes kit, warning progress as its p, landed ones in commit style."""
    from blob_evolution.utils import boss_shapes as bs       # art kit, read only
    ox = -camera.x + config.SCREEN_WIDTH // 2 + shake.x          # world -> screen, as Boss.draw
    oy = -camera.y + config.SCREEN_HEIGHT // 2 + shake.y
    for t in telegraphs:
        g, e, p = t.geom, t.element, t.progress
        if t.kind in ("zone", "mark"):
            (bs.zone if t.kind == "zone" else bs.mark)(screen, g[0] + ox, g[1] + oy, g[2], e, p, *((t.landed,) if t.kind == "zone" else ()))
        elif t.kind == "lane":
            bs.lane(screen, g[0] + ox, g[1] + oy, g[2] + ox, g[3] + oy, g[4], e, p, t.landed, fill="none")
        elif t.kind == "fan":
            bs.fan(screen, g[0] + ox, g[1] + oy, g[2], g[3], g[4], e)
        elif t.kind == "ring":
            col = bs.ELEMENTS[e][1]
            bs.ring_out(screen, g[0] + ox, g[1] + oy, g[3], col)
            bs.ring_out(screen, g[0] + ox, g[1] + oy, g[2], col)
        else:
            bs.safe_brackets(screen, (g[0] + ox, g[1] + oy, g[2], g[3]))
