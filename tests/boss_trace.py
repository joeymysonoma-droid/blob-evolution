"""Scripted boss fights hashed frame by frame (TASK-054): runs on old and new builds, so the hashes compare them."""
from __future__ import annotations

import hashlib
import math
import random
from typing import Dict, List, Tuple

import pygame

from blob_evolution import config
from blob_evolution.entities.boss import Boss
from blob_evolution.utils.vector2 import Vector2

KINDS = ("warden", "slot1", "slot2", "mini", "mini_b")
SLOTS = {"warden": 0, "slot1": 1, "slot2": 2, "mini": 0, "mini_b": 0}
MINIS = {"mini": 0, "mini_b": 1}           # mini-boss kinds -> anchor variant (the layer's first / second anchor)
SEEDS = (3, 17, 202, 4711)
DIFFS = (
    {"hp": 1.0, "damage": 1.0, "speed": 1.0},
    {"hp": 2.6, "damage": 1.3, "speed": 1.15},
    {"hp": 0.8, "damage": 0.9, "speed": 0.85},
)
FRAMES = 900
DRAW_EVERY = 45
STATE_FIELDS = (
    "size", "max_hp", "hp", "damage", "speed", "active", "enraged", "phase", "phase_announced", "xp_value",
    "shoot_cooldown", "special_cooldown", "angle", "hit_flash", "telegraph", "telegraph_type", "pulse_time",
    "slow_factor", "act_index", "is_miniboss", "slot", "name", "move_mode", "dash_timer", "clone_timer",
    "pull_pulse", "spiral_index", "warning_rings", "radius",
)


def _v(v: Vector2) -> Tuple[float, float]:
    """Vector as an exact float pair."""
    return (v.x, v.y)


def _shot(p) -> tuple:
    """Every field of a spawned projectile."""
    return (p.kind, p.color, _v(p.pos), _v(p.vel), p.damage, p.radius, p.lifetime, p.from_player, p.piercing, p.active)


def boss_state(b: Boss) -> tuple:
    """The boss fields the trace compares (plus position, velocity and dash direction)."""
    return tuple(repr(getattr(b, f)) for f in STATE_FIELDS) + (_v(b.pos), _v(b.vel), _v(b.dash_dir))


def _rng_digest() -> str:
    """Digest of the global random module state (attack choices, blinks, dashes all draw from it)."""
    return hashlib.sha1(repr(random.getstate()).encode()).hexdigest()[:16]


def trace(act: int, kind: str, seed: int, frames: int = FRAMES, draw: object = True) -> List[str]:
    """Run one scripted fight; one digest per frame (boss state, RNG, shots spawned, phase announces, draws)."""
    random.seed(seed)
    diff = DIFFS[seed % len(DIFFS)]
    b = Boss(Vector2(1200, 1100), act, diff, miniboss=kind in MINIS, slot=SLOTS[kind], variant=MINIS.get(kind, 0))
    surf = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT)) if draw else None
    cam, shake = Vector2(1200, 1100), Vector2(0, 0)
    shots: list = []
    out: List[str] = []
    t = 0.0
    for f in range(frames):
        dt = (1 / 30) if f % 53 == 0 else (0.05 if f % 211 == 7 else 1 / 60)
        t += dt
        player = Vector2(1000 + math.cos(t * 0.7) * 350, 1000 + math.sin(t * 1.1) * 250)
        if f % 97 == 0:
            player = b.pos.copy()                                  # zero distance: the attacks' early-out path
        b.slow_factor = 0.7 if f % 200 < 40 else 1.0               # Time Dilation writes this every frame
        rec: list = []
        if b.active and f % 7 == 3:
            frac = 0.2 if f == 620 else (0.02 if f > 620 else (0.004 if f % 3 else 0.012))
            killed = b.take_damage(b.max_hp * frac, 0.1 if f % 5 == 0 else 0.0)
            rec.append(("hit", killed))
            if killed:
                b.active = False
        rec.append(("announce", b.consume_phase_announce()))
        b.update(dt, player, shots)
        rec.append(("shots", tuple(_shot(p) for p in shots)))
        shots.clear()
        if draw and f % DRAW_EVERY == 0 and b.active:
            surf.fill((40, 40, 60))
            b.draw(surf, cam, shake)
            if draw != "blind":                                    # "blind": draw runs, pixels are not recorded
                rec.append(("draw", hashlib.sha1(pygame.image.tobytes(surf, "RGB")).hexdigest()[:16]))
        rec.append(("state", boss_state(b), _rng_digest()))
        out.append(hashlib.sha1(repr(rec).encode()).hexdigest()[:16])
    return out


def fight_digest(act: int, kind: str, seed: int, **kw) -> str:
    """One digest for the whole scripted fight."""
    return hashlib.sha1("".join(trace(act, kind, seed, **kw)).encode()).hexdigest()


def all_digests(**kw) -> Dict[str, str]:
    """Digest of every scripted fight: 10 acts x (warden, slots 1 and 2, both anchors) x the seeds."""
    return {f"{act}/{kind}/{seed}": fight_digest(act, kind, seed, **kw)
            for act in range(10) for kind in KINDS for seed in SEEDS}


# ---- TASK-058: fixed draw scene and stats table (recorded on 057 3d9e4d7, the pre-art Boss.draw) -----------------
ENTITIES = tuple((act, mini, var) for act in range(10) for mini, var in ((False, 0), (True, 0), (True, 1)))


def make_boss(act: int, mini: bool, var: int, slot: int = 0) -> Boss:
    return Boss(Vector2(1200, 1100), act, None, miniboss=mini, slot=slot, variant=var)


def stats_table() -> Dict[str, tuple]:
    """Size, HP, damage, speed, contact and phase thresholds of every warden slot and both anchors of every layer."""
    out = {}
    for act in range(10):
        for slot in range(3):
            b = make_boss(act, False, 0, slot)
            out[f"{act}/warden/{slot}"] = (b.size, b.radius, b.max_hp, b.damage, b.speed, b.xp_value,
                                           tuple((p.phase, p.below) for p in b.phase_defs))
        for var in range(2):
            b = make_boss(act, True, var)
            out[f"{act}/mini/{var}"] = (b.size, b.radius, b.max_hp, b.damage, b.speed, b.xp_value,
                                        tuple((p.phase, p.below) for p in b.phase_defs))
    return out


def scene_digest() -> str:
    """Every warden and anchor drawn in 4 states (fresh, phase 2, phase 3 + flash, warning ring + telegraph)."""
    random.seed(5)
    surf = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    h = hashlib.sha1()
    cam = Vector2(1200, 1100)
    for act, mini, var in ENTITIES:
        b = make_boss(act, mini, var)
        for step in range(4):
            if step == 1:
                b.take_damage(b.max_hp * 0.55)
            elif step == 2:
                b.take_damage(b.max_hp * 0.22)
            elif step == 3:
                b.warning_rings.append((180.0, 0.5, (180, 220, 255)))
                b.telegraph = 0.4
            b.update(1 / 60, Vector2(1000, 900), [])
            surf.fill((40, 40, 60))
            b.draw(surf, cam, Vector2(3, -2))
            h.update(pygame.image.tobytes(surf, "RGB"))
    return h.hexdigest()[:16]
