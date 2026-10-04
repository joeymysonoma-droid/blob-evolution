"""Deterministic single-creature scenes shared by tests/test_enemy_shapes.py (no import of the new shapes module, so the same scenes run on older builds)."""
from __future__ import annotations

import hashlib
from typing import Optional

import pygame

from blob_evolution import config
from blob_evolution.entities.creature import Creature
from blob_evolution.utils.enums import CreatureType
from blob_evolution.utils.vector2 import Vector2

CX, CY = config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2
CAM = Vector2(CX, CY)
NO_SHAKE = Vector2(0, 0)
BG = (128, 128, 128)
ENEMY_TYPES = [t for t in CreatureType if t != CreatureType.BOSS]
FACE = (0.96, 0.29)


def make(kind: CreatureType, size: float = 20.0, *, face: tuple = FACE, fuse: float = 4.0, orbit: float = 0.3,
         phased: bool = False, flash: bool = False, charging: bool = False, shield_frac: Optional[float] = None) -> Creature:
    """Build a creature in a fully fixed state (no random fields left)."""
    c = Creature(Vector2(CX, CY), kind, size)
    c.face_dir = Vector2(*face)
    c.fuse_timer = fuse if kind == CreatureType.BOMBER else 0.0
    c.orbit_angle = orbit
    c.wander_timer = 1.0
    c.phased = phased
    c.hit_flash = 0.15 if flash else 0.0
    if charging:
        c.charge_telegraph = 0.4
        c.charge_dir = Vector2(0.0, 1.0)
    if shield_frac is not None and c.shield_hp:
        c.shield_hp = c.shield_hp * shield_frac
    return c


def render(c: Creature, surface: Optional[pygame.Surface] = None, bg: tuple = BG) -> pygame.Surface:
    """Draw one creature at the screen centre of a flat-coloured full-size surface."""
    s = surface or pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    s.fill(bg)
    c.draw(s, CAM, NO_SHAKE)
    return s


def scene_hash(c: Creature) -> str:
    """md5 of the 240x240 pixels around the creature."""
    s = render(c)
    return hashlib.md5(pygame.image.tobytes(s.subsurface((CX - 120, CY - 120, 240, 240)), "RGB")).hexdigest()


SCENES = {
    "plain": dict(),
    "flash": dict(flash=True),
    "phased": dict(phased=True),
    "charging": dict(charging=True),
    "fuse1": dict(fuse=1.0),
    "shield_half": dict(shield_frac=0.4),
}
