"""Artifact collection and effects system."""

from __future__ import annotations

import random
from typing import Dict, List, Optional

ARTIFACT_DEFINITIONS: Dict[str, dict] = {
    # Common (40%)
    "swift_membrane": {"name": "Swift Membrane", "rarity": "common", "effect": "speed", "value": 1.25},
    "thick_skin": {"name": "Thick Skin", "rarity": "common", "effect": "damage_reduction", "value": 1.15},
    "growth_catalyst": {"name": "Growth Catalyst", "rarity": "common", "effect": "size", "value": 1.20},
    "acidic_core": {"name": "Acidic Core", "rarity": "common", "effect": "damage", "value": 1.30},
    "vital_essence": {"name": "Vital Essence", "rarity": "common", "effect": "max_health", "value": 40},
    # Rare (35%)
    "magnetic_field": {"name": "Magnetic Field", "rarity": "rare", "effect": "magnet", "value": 1.50},
    "piercing_shots": {"name": "Piercing Shots", "rarity": "rare", "effect": "piercing", "value": 1},
    "perfect_absorption": {"name": "Perfect Absorption", "rarity": "rare", "effect": "absorption_heal", "value": 10},
    "skill_enhancer": {"name": "Skill Enhancer", "rarity": "rare", "effect": "skill_boost", "value": 1},
    "xp_chain": {"name": "XP Chain", "rarity": "rare", "effect": "xp_chain", "value": 1},
    # Epic (20%)
    "explosive_death": {"name": "Explosive Death", "rarity": "epic", "effect": "explosion", "value": 1},
    "dash_trail": {"name": "Dash Trail", "rarity": "epic", "effect": "dash_trail", "value": 1},
    "multi_shot": {"name": "Multi-Shot", "rarity": "epic", "effect": "multi_shot", "value": 2},
    "regenerative_matrix": {"name": "Regenerative Matrix", "rarity": "epic", "effect": "regen_percent", "value": 0.01},
    # Legendary (5%)
    "reality_tear": {"name": "Reality Tear", "rarity": "legendary", "effect": "ignore_defense", "value": 0.30},
    "quantum_split": {"name": "Quantum Split", "rarity": "legendary", "effect": "clone_kill", "value": 1},
    "time_dilation": {"name": "Time Dilation", "rarity": "legendary", "effect": "slow_enemies", "value": 0.50},
    # Additional artifacts
    "essence_magnet": {"name": "Essence Magnet", "rarity": "common", "effect": "essence_bonus", "value": 1.25},
    "hardened_shell": {"name": "Hardened Shell", "rarity": "rare", "effect": "damage_reduction", "value": 1.10},
    "rapid_fire": {"name": "Rapid Fire", "rarity": "epic", "effect": "fire_rate", "value": 1.30},
    "void_core": {"name": "Void Core", "rarity": "legendary", "effect": "damage", "value": 1.50},
    "phoenix_heart": {"name": "Phoenix Heart", "rarity": "epic", "effect": "revive", "value": 1},
    "gravity_well": {"name": "Gravity Well", "rarity": "rare", "effect": "magnet", "value": 1.30},
}

RARITY_WEIGHTS = {"common": 40, "rare": 35, "epic": 20, "legendary": 5}
RARITY_COLORS = {
    "common": (180, 180, 180),
    "rare": (80, 150, 255),
    "epic": (180, 80, 255),
    "legendary": (255, 180, 50),
}


class ArtifactManager:
    """Manages collected artifacts and their effects."""

    def __init__(self) -> None:
        self.collected: List[str] = []
        self.upgrade_levels: Dict[str, int] = {}

    def _upgrade_mult(self, artifact_id: str) -> float:
        """Multiplier from blacksmith upgrades."""
        level = self.upgrade_levels.get(artifact_id, 0)
        return 1.0 + level * 0.10

    def upgrade_artifact(self, artifact_id: str) -> bool:
        """Upgrade artifact at blacksmith. Max 3 levels."""
        if artifact_id not in self.collected:
            return False
        current = self.upgrade_levels.get(artifact_id, 0)
        if current >= 3:
            return False
        self.upgrade_levels[artifact_id] = current + 1
        return True

    def get_upgrade_level(self, artifact_id: str) -> int:
        """Get blacksmith upgrade level for artifact."""
        return self.upgrade_levels.get(artifact_id, 0)

    def has(self, artifact_id: str) -> bool:
        """Check if artifact is collected."""
        return artifact_id in self.collected

    def add(self, artifact_id: str) -> Optional[dict]:
        """Add artifact if not already owned."""
        if artifact_id in self.collected or artifact_id not in ARTIFACT_DEFINITIONS:
            return None
        self.collected.append(artifact_id)
        return ARTIFACT_DEFINITIONS[artifact_id]

    def get_regen_bonus(self) -> float:
        """Get flat regen percent of max HP per tick."""
        total = 0.0
        for aid in self.collected:
            art = ARTIFACT_DEFINITIONS.get(aid, {})
            if art.get("effect") == "regen_percent":
                total += art["value"] * self._upgrade_mult(aid)
        return total

    def get_skill_boost(self) -> float:
        """Bonus multiplier for skill effectiveness."""
        if self.has("skill_enhancer"):
            return 1.0 + 0.15 * self._upgrade_mult("skill_enhancer")
        return 1.0

    def get_multiplier(self, effect: str) -> float:
        """Get combined multiplier for an effect type."""
        total = 1.0
        for aid in self.collected:
            art = ARTIFACT_DEFINITIONS.get(aid, {})
            if art.get("effect") == effect and isinstance(art["value"], float) and art["value"] < 10:
                if effect in ("speed", "size", "damage", "magnet", "damage_reduction", "essence_bonus", "fire_rate"):
                    bonus = (art["value"] - 1.0) * self._upgrade_mult(aid) + 1.0
                    total *= bonus
        return total

    def get_flat(self, effect: str) -> float:
        """Get flat bonus for an effect."""
        total = 0.0
        for aid in self.collected:
            art = ARTIFACT_DEFINITIONS.get(aid, {})
            if art.get("effect") == effect:
                if effect == "multi_shot":
                    total += art["value"]
                elif isinstance(art["value"], (int, float)) and art["value"] >= 10:
                    total += art["value"]
        return total

    def get_ignore_defense(self) -> float:
        """Get armor ignore chance."""
        for aid in self.collected:
            art = ARTIFACT_DEFINITIONS.get(aid, {})
            if art.get("effect") == "ignore_defense":
                return art["value"]
        return 0.0

    def get_slow_radius(self) -> float:
        """Get enemy slow factor from time dilation."""
        if self.has("time_dilation"):
            return ARTIFACT_DEFINITIONS["time_dilation"]["value"]
        return 0.0

    @staticmethod
    def random_drop() -> str:
        """Roll a random artifact by rarity."""
        roll = random.randint(1, 100)
        cumulative = 0
        chosen_rarity = "common"
        for rarity, weight in RARITY_WEIGHTS.items():
            cumulative += weight
            if roll <= cumulative:
                chosen_rarity = rarity
                break
        candidates = [k for k, v in ARTIFACT_DEFINITIONS.items() if v["rarity"] == chosen_rarity]
        return random.choice(candidates) if candidates else "swift_membrane"

    def to_list(self) -> List[str]:
        """Serialize collected artifacts."""
        return list(self.collected)

    def from_list(self, data: List[str]) -> None:
        """Load collected artifacts."""
        self.collected = [a for a in data if a in ARTIFACT_DEFINITIONS]
