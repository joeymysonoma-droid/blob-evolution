"""Boss-owned spawns (TASK-056): bosses queue sprouts, adds, decoys and timed pools; the game places them by kind."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from blob_evolution import config
from blob_evolution.systems.hazards import HazardType, HazardZone
from blob_evolution.utils.vector2 import Vector2

if TYPE_CHECKING:
    from blob_evolution.entities.boss import Boss
    from blob_evolution.game import Game

POOL = "pool"
HAZARD_TYPES = {"lava": HazardType.LAVA, "ice": HazardType.ICE, "toxic": HazardType.TOXIC}


@dataclass
class SpawnRequest:
    """One thing a boss wants in the arena: kind, where, after how long, for how long, and kind-specific params."""

    kind: str
    pos: Vector2
    owner: Optional[Boss] = None
    delay: float = 0.0                     # seconds until it is placed
    lifetime: Optional[float] = None       # seconds it stays once placed; None = until its owner dies (or for good)
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LiveSpawn:
    """A placed spawn the director still tracks (to expire it or remove it with its owner)."""

    kind: str
    obj: Any
    owner: Optional[Boss]
    left: Optional[float]


Place = Callable[[SpawnRequest, "Game"], Any]          # returns the placed object, or None if nothing was placed
Remove = Callable[[Any, "Game"], None]


class SpawnQueue:
    """FIFO of pending spawn requests, each with its own delay; capped at config.BOSS_SPAWN_QUEUE_MAX."""

    def __init__(self, cap: Optional[int] = None) -> None:
        self.cap = config.BOSS_SPAWN_QUEUE_MAX if cap is None else cap
        self.pending: List[SpawnRequest] = []
        self.dropped = 0

    def __len__(self) -> int:
        return len(self.pending)

    def push(self, req: SpawnRequest) -> bool:
        """Queue a request; False (and counted in `dropped`) when the queue is full."""
        if len(self.pending) >= self.cap:
            self.dropped += 1
            return False
        self.pending.append(req)
        return True

    def update(self, dt: float) -> List[SpawnRequest]:
        """Count delays down; return the requests now due, in the order they were pushed."""
        due: List[SpawnRequest] = []
        keep: List[SpawnRequest] = []
        for req in self.pending:
            req.delay -= dt
            (due if req.delay <= config.BOSS_SPAWN_EPS else keep).append(req)   # BUG-152: no 1-frame-late fire
        self.pending = keep
        return due

    def drop_owner(self, owner: Boss) -> int:
        """Forget every pending request of `owner`; return how many."""
        before = len(self.pending)
        self.pending = [r for r in self.pending if r.owner is not owner]
        return before - len(self.pending)


class SpawnDirector:
    """One per game: collects boss requests, places due ones through per-kind handlers, expires timed ones."""

    def __init__(self) -> None:
        self.queue = SpawnQueue()
        self.live: List[LiveSpawn] = []
        self.handlers: Dict[str, Tuple[Place, Optional[Remove]]] = {}
        self.unhandled = 0
        self.rng = random.Random(config.BOSS_SPAWN_SEED)   # BUG-155: spawns never draw from the global RNG
        self.register(POOL, place_pool, remove_pool)

    def __bool__(self) -> bool:
        """True while anything is pending or live."""
        return bool(self.queue.pending or self.live)

    def register(self, kind: str, place: Place, remove: Optional[Remove] = None) -> None:
        """Say how to place (and optionally remove) one kind; later boss tickets add sprouts, adds and decoys."""
        self.handlers[kind] = (place, remove)

    def collect(self, bosses: List[Boss]) -> None:
        """Move each active boss's outbox into the queue (a dead boss's outbox is dropped)."""
        for b in bosses:
            if b.spawn_outbox:
                if b.active:
                    for req in b.spawn_outbox:
                        self.queue.push(req)
                b.spawn_outbox.clear()

    def update(self, dt: float, game: Game) -> None:
        """Collect, place what is due, then expire timed spawns and those whose boss died. A spawn placed this frame
        starts its lifetime on the next one (BUG-153: a 1 s pool is on screen for 60 frames at 60 fps)."""
        self.collect(game.bosses)
        if not self.queue.pending and not self.live:
            return
        dt = min(dt, config.BOSS_SPAWN_MAX_DT)          # BUG-154: a dt spike cannot place and remove a pool unseen
        die_with_owner = config.BOSS_SPAWNS_DIE_WITH_OWNER
        placed: List[LiveSpawn] = []
        for req in self.queue.update(dt):
            if die_with_owner and req.owner is not None and not req.owner.active:
                continue
            handler = self.handlers.get(req.kind)
            if handler is None:
                self.unhandled += 1
                continue
            if "phase" not in req.params:
                req.params["phase"] = self.rng.uniform(0, math.tau)    # BUG-155: animation phase, not global random
            obj = handler[0](req, game)
            if obj is not None and (req.lifetime is not None or req.owner is not None):
                placed.append(LiveSpawn(req.kind, obj, req.owner, req.lifetime))
        keep: List[LiveSpawn] = []
        for ls in self.live:
            if ls.left is not None:
                ls.left -= dt
            gone = (ls.left is not None and ls.left <= config.BOSS_SPAWN_EPS) or (
                die_with_owner and ls.owner is not None and not ls.owner.active)
            if not gone:
                keep.append(ls)
                continue
            self._remove(ls, game)
        self.live = keep + placed

    def _remove(self, ls: LiveSpawn, game: Optional[Game]) -> None:
        remove = self.handlers.get(ls.kind, (None, None))[1]
        if remove is not None and game is not None:
            remove(ls.obj, game)

    def drop_owner(self, owner: Boss, game: Optional[Game] = None) -> int:
        """BUG-151: `owner` died: forget its pending requests and remove its live spawns now (if they die with it).
        Returns how many pending requests were dropped."""
        dropped = self.queue.drop_owner(owner)
        if config.BOSS_SPAWNS_DIE_WITH_OWNER and self.live:
            keep = []
            for ls in self.live:
                if ls.owner is owner:
                    self._remove(ls, game)
                else:
                    keep.append(ls)
            self.live = keep
        return dropped

    def clear(self, game: Optional[Game] = None) -> None:
        """Forget everything and reseed the RNG (new encounter, fight won, game over, main menu). With `game`, live
        spawns are also taken out of the arena (a new encounter rebuilds the hazards anyway)."""
        for ls in self.live:
            self._remove(ls, game)
        self.queue.pending.clear()
        self.live.clear()
        self.rng.seed(config.BOSS_SPAWN_SEED)


def place_pool(req: SpawnRequest, game: Game) -> HazardZone:
    """A timed pool is a HazardZone (lava / ice / toxic effects as on the map) added to the game's hazards."""
    if req.lifetime is None:
        req.lifetime = config.BOSS_POOL_LIFETIME
    hazard = HAZARD_TYPES[req.params.get("hazard", config.BOSS_POOL_HAZARD)]
    phase = float(req.params.get("phase", 0.0))         # the director fills it from its own RNG (BUG-155)
    zone = HazardZone(req.pos, float(req.params.get("radius", config.BOSS_POOL_RADIUS)), hazard, phase)
    zone.build()                                       # bake now, as the map does, not lazily in draw
    game.hazards.zones.append(zone)
    return zone


def remove_pool(zone: HazardZone, game: Game) -> None:
    """Take a pool out of the game's hazards (no-op if a new map already replaced them)."""
    if zone in game.hazards.zones:
        game.hazards.zones.remove(zone)
