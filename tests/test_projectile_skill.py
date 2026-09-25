"""TASK-015: Projectile levels change fire rate and shot speed, not magnet radius."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from pygame.math import Vector2

from blob_evolution import config
from blob_evolution.entities.player import Player
from blob_evolution.systems.skills import SKILL_DEFINITIONS


def _player_with(projectile: int = 0, magnet: int = 0) -> Player:
    """Build a player with the given Projectile and Magnetism levels."""
    player = Player(Vector2(0, 0))
    player.skills.levels["projectile"] = projectile
    player.skills.levels["magnet"] = magnet
    player._update_stats()
    return player


def test_projectile_levels_do_not_change_magnet_radius():
    """Magnet radius is the same at Projectile level 0 and max level."""
    base = _player_with(projectile=0)
    maxed = _player_with(projectile=config.MAX_SKILL_LEVEL)
    assert maxed.magnet_radius == base.magnet_radius


def test_projectile_levels_still_lower_fire_cooldown():
    """Projectile levels still shorten the time between shots."""
    base = _player_with(projectile=0)
    maxed = _player_with(projectile=config.MAX_SKILL_LEVEL)
    assert maxed.shoot_rate < base.shoot_rate


def test_magnetism_is_the_skill_that_adds_magnet_radius():
    """Each Magnetism level still adds magnet radius, even with Projectile maxed."""
    base = _player_with(projectile=config.MAX_SKILL_LEVEL, magnet=0)
    one = _player_with(projectile=config.MAX_SKILL_LEVEL, magnet=1)
    assert one.magnet_radius > base.magnet_radius


def test_projectile_description_matches_narrative_copy():
    """The Projectile skill text no longer mentions the magnet."""
    assert SKILL_DEFINITIONS["projectile"]["description"] == "Faster fire rate and shot speed"
