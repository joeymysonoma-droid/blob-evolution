"""Entity package."""

from blob_evolution.entities.particle import ParticleSystem, Particle
from blob_evolution.entities.projectile import Projectile
from blob_evolution.entities.pickups import XPOrb
from blob_evolution.entities.player import Player
from blob_evolution.entities.creature import Creature
from blob_evolution.entities.boss import Boss

__all__ = [
    "ParticleSystem",
    "Particle",
    "Projectile",
    "XPOrb",
    "Player",
    "Creature",
    "Boss",
]
