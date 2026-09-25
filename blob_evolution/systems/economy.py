"""Economy and shop system."""

from __future__ import annotations

from typing import Dict, List, Optional

SHOP_ITEMS: List[dict] = [
    {"id": "health_potion", "name": "Health Potion", "cost": 50,
     "description": "Restore 25 HP", "type": "consumable"},
    {"id": "skill_point", "name": "Skill Point", "cost": 100,
     "description": "+1 Skill Point", "type": "skill_point"},
    {"id": "essence_cache", "name": "Essence Cache", "cost": 60,
     "description": "+30 essence instantly", "type": "essence_cache"},
    {"id": "speed_boost", "name": "Swift Serum", "cost": 90,
     "description": "+12% speed this run", "type": "speed_boost"},
    {"id": "xp_boost", "name": "Mind Crystal", "cost": 100,
     "description": "+20% XP this run", "type": "xp_boost"},
    {"id": "magnet_boost", "name": "Magnet Coil", "cost": 80,
     "description": "+40 magnet radius", "type": "magnet_boost"},
    {"id": "size_boost", "name": "Growth Serum", "cost": 120,
     "description": "+12% size this run", "type": "size_boost"},
    {"id": "shield", "name": "Barrier Membrane", "cost": 110,
     "description": "Block the next hit", "type": "shield"},
    {"id": "cleanse", "name": "Purify", "cost": 95,
     "description": "Remove curse debuffs", "type": "cleanse"},
    {"id": "max_health", "name": "Max Health +20", "cost": 150,
     "description": "Permanent +20 max HP", "type": "max_health"},
    {"id": "damage_boost", "name": "Damage Boost", "cost": 175,
     "description": "+10% damage this run", "type": "damage_boost"},
    {"id": "artifact_roll", "name": "Mystery Artifact", "cost": 200,
     "description": "Random artifact", "type": "artifact"},
    {"id": "pierce_boost", "name": "Piercing Cells", "cost": 185,
     "description": "Projectiles pierce this run", "type": "pierce_boost"},
]


class EconomyManager:
    """Manages essence currency and shop transactions."""

    def __init__(self) -> None:
        self.essence = 0
        self.total_earned = 0
        self.run_damage_boost = 0.0
        self.run_speed_boost = 0.0
        self.run_xp_boost = 0.0
        self.run_magnet_flat = 0.0
        self.run_size_boost = 0.0
        self.run_piercing = False

    def add_essence(self, amount: int, multiplier: float = 1.0) -> None:
        """Add essence currency."""
        gained = int(amount * multiplier)
        self.essence += gained
        self.total_earned += gained

    def can_afford(self, cost: int) -> bool:
        """Check if player can afford item."""
        return self.essence >= cost

    def purchase(self, item_id: str) -> Optional[dict]:
        """Purchase shop item. Returns item data or None."""
        item = next((i for i in SHOP_ITEMS if i["id"] == item_id), None)
        if not item or not self.can_afford(item["cost"]):
            return None
        self.essence -= item["cost"]
        return item

    def reset_run_bonuses(self) -> None:
        """Reset per-run shop boosts."""
        self.run_damage_boost = 0.0
        self.run_speed_boost = 0.0
        self.run_xp_boost = 0.0
        self.run_magnet_flat = 0.0
        self.run_size_boost = 0.0
        self.run_piercing = False

    def get_shop_items(self) -> List[dict]:
        """Return shop catalog."""
        return SHOP_ITEMS

    def to_dict(self) -> dict:
        """Serialize economy state."""
        return {
            "essence": self.essence,
            "total_earned": self.total_earned,
            "run_damage_boost": self.run_damage_boost,
        }

    def from_dict(self, data: dict) -> None:
        """Load economy state."""
        self.essence = data.get("essence", 0)
        self.total_earned = data.get("total_earned", 0)
        self.run_damage_boost = data.get("run_damage_boost", 0.0)
