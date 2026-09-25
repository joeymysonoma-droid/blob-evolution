"""Game enumerations."""

from __future__ import annotations

from enum import Enum, auto


class GameState(Enum):
    """High-level game states."""

    MAIN_MENU = auto()
    STORY = auto()
    OVERWORLD = auto()
    PLAYING = auto()
    PAUSED = auto()
    SKILLS = auto()
    SHOP = auto()
    REST = auto()
    EVENT = auto()
    BLACKSMITH = auto()
    META_SHOP = auto()
    ARCHIVE = auto()
    CORE_CHOICE = auto()
    GAME_OVER = auto()
    VICTORY = auto()
    OPTIONS = auto()
    HELP = auto()


class Difficulty(Enum):
    """Difficulty levels."""

    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    EXTREME = "extreme"


class CreatureType(Enum):
    """Enemy creature archetypes."""

    BASIC = "basic"
    SHOOTER = "shooter"
    SPLITTER = "splitter"
    CHARGER = "charger"
    SHIELDER = "shielder"
    ORBITER = "orbiter"
    BOMBER = "bomber"
    PHANTOM = "phantom"
    LEECH = "leech"
    BOSS = "boss"


class HazardType(Enum):
    """Environmental hazard types."""

    LAVA = "lava"
    ICE = "ice"
    TOXIC = "toxic"


class ParticleType(Enum):
    """Particle effect categories."""

    EXPLOSION = auto()
    SPARKLE = auto()
    TRAIL = auto()
    AMBIENT = auto()


class NodeType(Enum):
    """Overworld map node types."""

    START = "start"
    FIGHT = "fight"
    ELITE = "elite"
    REST = "rest"
    EVENT = "event"
    SHOP = "shop"
    BLACKSMITH = "blacksmith"
    MINIBOSS = "miniboss"
    BOSS = "boss"
