"""Skill upgrade system."""

from __future__ import annotations

from typing import Dict, List, Optional

from blob_evolution import config


SKILL_DEFINITIONS: Dict[str, dict] = {
    "speed": {
        "name": "Speed",
        "description": "Increases movement speed",
        "multiplier_per_level": 0.08,
        "base_cost": 1,
    },
    "size": {
        "name": "Size",
        "description": "Increases blob size and absorption range",
        "multiplier_per_level": 0.1,
        "base_cost": 1,
    },
    "damage": {
        "name": "Damage",
        "description": "Increases projectile damage",
        "multiplier_per_level": 0.12,
        "base_cost": 1,
    },
    "health": {
        "name": "Health",
        "description": "Increases maximum health",
        "multiplier_per_level": 0.15,
        "base_cost": 1,
    },
    "regen": {
        "name": "Regeneration",
        "description": "Passive health recovery",
        "multiplier_per_level": 0.0,
        "base_cost": 2,
    },
    "projectile": {
        "name": "Projectile",
        "description": "Faster fire rate and shot speed",
        "multiplier_per_level": 0.0,
        "base_cost": 1,
    },
    "armor": {
        "name": "Armor",
        "description": "Reduces damage taken",
        "multiplier_per_level": 0.0,
        "base_cost": 2,
    },
    "magnet": {
        "name": "Magnetism",
        "description": "Pulls XP orbs from farther away",
        "multiplier_per_level": 0.0,
        "base_cost": 1,
    },
    "lifesteal": {
        "name": "Lifesteal",
        "description": "Heal on enemy kills",
        "multiplier_per_level": 0.0,
        "base_cost": 2,
    },
}

SKILL_ORDER = ["speed", "size", "damage", "health", "regen", "projectile", "armor", "magnet", "lifesteal"]


class SkillManager:
    """Manages player skill levels and upgrades."""

    def __init__(self) -> None:
        self.levels: Dict[str, int] = {skill: 0 for skill in SKILL_DEFINITIONS}

    def get_level(self, skill: str) -> int:
        """Get current level of a skill."""
        return self.levels.get(skill, 0)

    def get_multiplier(self, skill: str) -> float:
        """Get stat multiplier for a skill."""
        level = self.get_level(skill)
        if skill == "regen" or skill == "projectile" or skill == "armor" or skill == "magnet" or skill == "lifesteal":
            return 1.0
        per_level = SKILL_DEFINITIONS[skill]["multiplier_per_level"]
        return 1.0 + level * per_level

    def is_maxed(self, skill: str) -> bool:
        """Check if a skill is at the max level."""
        return self.get_level(skill) >= config.MAX_SKILL_LEVEL

    def get_upgrade_cost(self, skill: str) -> Optional[int]:
        """Calculate cost to upgrade a skill; None once it is at max level (nothing to buy)."""
        if self.is_maxed(skill):
            return None
        base = SKILL_DEFINITIONS[skill]["base_cost"]
        return base + self.get_level(skill)

    def can_upgrade(self, skill: str, skill_points: int) -> bool:
        """Check if skill can be upgraded (known, below max level, affordable)."""
        if skill not in SKILL_DEFINITIONS:
            return False
        cost = self.get_upgrade_cost(skill)
        return cost is not None and skill_points >= cost

    def upgrade(self, skill: str) -> int:
        """Upgrade skill and return cost. Returns -1 if failed (unknown or already max level)."""
        cost = self.get_upgrade_cost(skill) if skill in SKILL_DEFINITIONS else None
        if cost is None:
            return -1
        self.levels[skill] += 1
        return cost

    def get_all_skills(self) -> List[dict]:
        """Return skill info for UI."""
        result = []
        for key in SKILL_ORDER:
            defn = SKILL_DEFINITIONS[key]
            result.append({
                "key": key,
                "name": defn["name"],
                "description": defn["description"],
                "level": self.get_level(key),
                "max_level": config.MAX_SKILL_LEVEL,
                "maxed": self.is_maxed(key),
                "cost": self.get_upgrade_cost(key),
            })
        return result

    def to_dict(self) -> Dict[str, int]:
        """Serialize skill levels."""
        return dict(self.levels)

    def from_dict(self, data: Dict[str, int]) -> None:
        """Load skill levels."""
        for key, level in data.items():
            if key in self.levels:
                self.levels[key] = min(level, config.MAX_SKILL_LEVEL)
