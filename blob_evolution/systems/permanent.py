"""Permanent meta-progression: Shards, upgrades, and skins."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

PERMANENT_UPGRADES: List[dict] = [
    {"id": "perm_damage", "name": "Eternal Fury", "description": "+5% base damage",
     "cost_base": 30, "cost_scale": 1.5, "max_level": 5, "stat": "damage", "value": 0.05, "bonus_type": "mult"},
    {"id": "perm_health", "name": "Eternal Vitality", "description": "+5% base health",
     "cost_base": 30, "cost_scale": 1.5, "max_level": 5, "stat": "health", "value": 0.05, "bonus_type": "mult"},
    {"id": "perm_speed", "name": "Eternal Swiftness", "description": "+3% base speed",
     "cost_base": 25, "cost_scale": 1.4, "max_level": 5, "stat": "speed", "value": 0.03, "bonus_type": "mult"},
    {"id": "perm_xp", "name": "Wisdom Core", "description": "+8% XP gained",
     "cost_base": 35, "cost_scale": 1.5, "max_level": 5, "stat": "xp", "value": 0.08, "bonus_type": "mult"},
    {"id": "perm_magnet", "name": "Orb Attraction", "description": "+10% magnet radius",
     "cost_base": 30, "cost_scale": 1.4, "max_level": 5, "stat": "magnet", "value": 0.10, "bonus_type": "mult"},
    {"id": "perm_armor", "name": "Hardened Membrane", "description": "-3% damage taken",
     "cost_base": 40, "cost_scale": 1.6, "max_level": 5, "stat": "armor", "value": 0.03, "bonus_type": "flat"},
    {"id": "perm_lifesteal", "name": "Vampiric Tissue", "description": "+2% lifesteal on kill",
     "cost_base": 45, "cost_scale": 1.7, "max_level": 4, "stat": "lifesteal", "value": 0.02, "bonus_type": "flat"},
    {"id": "perm_crit", "name": "Precision Glands", "description": "+5% crit chance",
     "cost_base": 50, "cost_scale": 1.8, "max_level": 4, "stat": "crit", "value": 0.05, "bonus_type": "flat"},
    {"id": "perm_luck", "name": "Fortune Blob", "description": "+5% artifact drop rate",
     "cost_base": 55, "cost_scale": 1.8, "max_level": 4, "stat": "luck", "value": 0.05, "bonus_type": "flat"},
    {"id": "perm_essence", "name": "Essence Affinity", "description": "+10% essence earned",
     "cost_base": 40, "cost_scale": 1.6, "max_level": 3, "stat": "essence", "value": 0.10, "bonus_type": "mult"},
    {"id": "perm_shards", "name": "Shard Magnet", "description": "+15% shards earned",
     "cost_base": 50, "cost_scale": 1.8, "max_level": 3, "stat": "shards", "value": 0.15, "bonus_type": "mult"},
    {"id": "perm_start_sp", "name": "Head Start", "description": "+1 skill point at run start",
     "cost_base": 80, "cost_scale": 2.0, "max_level": 2, "stat": "start_sp", "value": 1, "bonus_type": "flat"},
    {"id": "perm_start_essence", "name": "Deep Pockets", "description": "+20 starting essence",
     "cost_base": 60, "cost_scale": 1.8, "max_level": 3, "stat": "start_essence", "value": 20, "bonus_type": "flat"},
]

SKINS: List[dict] = [
    {"id": "default", "name": "Verdant", "cost": 0,
     "color": (34, 197, 94), "core": (74, 222, 128),
     "lore": "Default Seedling green of the Verdant Rim."},
    {"id": "crimson", "name": "Crimson", "cost": 75,
     "color": (220, 50, 50), "core": (255, 120, 120),
     "require_warden": "warden_3",
     "lock_hint": "Remember the Warden of Ash",
     "lore": "Forge Veins survivor — heat still stains the membrane."},
    {"id": "azure", "name": "Azure", "cost": 75,
     "color": (50, 130, 220), "core": (120, 180, 255),
     "require_warden": "warden_2",
     "lock_hint": "Remember the Warden of Echoes",
     "lore": "Memory Vaults echo — cool with archived light."},
    {"id": "golden", "name": "Golden", "cost": 150,
     "color": (220, 180, 40), "core": (255, 230, 120),
     "require_warden": "warden_8",
     "lock_hint": "Remember the Warden of Ascent",
     "lore": "Ascending Strata blessing — judged and still shining."},
    {"id": "void", "name": "Void", "cost": 250,
     "color": (80, 40, 140), "core": (160, 100, 220),
     "require_warden": "warden_7",
     "lock_hint": "Remember the Warden of Silence",
     "lore": "Hollow Undermembrane stain — almost forgotten."},
    {"id": "prismatic", "name": "Prismatic", "cost": 500,
     "color": (200, 100, 200), "core": (255, 200, 255),
     "require_ending": "reopen",
     "lock_hint": "Reopen the First Divide",
     "lore": "Post-Core expression — every color the Divide released."},
]


class PermanentProgress:
    """Manages shards and permanent unlocks."""

    def __init__(self) -> None:
        self.shards = 0
        self.total_shards_earned = 0
        self.upgrade_levels: Dict[str, int] = {u["id"]: 0 for u in PERMANENT_UPGRADES}
        self.unlocked_skins: List[str] = ["default"]
        self.equipped_skin = "default"
        self.unlocked_wardens: List[str] = []
        self.unlocked_artifacts: List[str] = []
        self.endings_seen: List[str] = []

    def add_shards(self, amount: int) -> None:
        """Add shard currency."""
        mult = 1.0 + self.get_bonus("shards")
        gained = max(0, int(amount * mult))
        self.shards += gained
        self.total_shards_earned += gained

    def get_bonus(self, stat: str) -> float:
        """Get permanent bonus multiplier for a stat."""
        total = 0.0
        for upgrade in PERMANENT_UPGRADES:
            if upgrade["stat"] == stat and upgrade.get("bonus_type", "mult") == "mult":
                level = self.upgrade_levels.get(upgrade["id"], 0)
                total += level * upgrade["value"]
        return total

    def get_flat(self, stat: str) -> float:
        """Get permanent flat bonus for a stat."""
        total = 0.0
        for upgrade in PERMANENT_UPGRADES:
            if upgrade["stat"] == stat and upgrade.get("bonus_type") == "flat":
                level = self.upgrade_levels.get(upgrade["id"], 0)
                total += level * upgrade["value"]
        return total

    def get_upgrade_cost(self, upgrade_id: str) -> int:
        """Calculate cost for next upgrade level."""
        upgrade = next((u for u in PERMANENT_UPGRADES if u["id"] == upgrade_id), None)
        if not upgrade:
            return 9999
        level = self.upgrade_levels.get(upgrade_id, 0)
        if level >= upgrade["max_level"]:
            return 9999
        return int(upgrade["cost_base"] * (upgrade["cost_scale"] ** level))

    def can_upgrade(self, upgrade_id: str) -> bool:
        """Check if upgrade can be purchased."""
        cost = self.get_upgrade_cost(upgrade_id)
        level = self.upgrade_levels.get(upgrade_id, 0)
        upgrade = next((u for u in PERMANENT_UPGRADES if u["id"] == upgrade_id), None)
        if not upgrade or level >= upgrade["max_level"]:
            return False
        return self.shards >= cost

    def purchase_upgrade(self, upgrade_id: str) -> bool:
        """Buy permanent upgrade. Returns True on success."""
        if not self.can_upgrade(upgrade_id):
            return False
        cost = self.get_upgrade_cost(upgrade_id)
        self.shards -= cost
        self.upgrade_levels[upgrade_id] = self.upgrade_levels.get(upgrade_id, 0) + 1
        return True

    def get_purchase_failure_reason(self, upgrade_id: str) -> str:
        """Explain why a permanent upgrade cannot be purchased."""
        upgrade = next((u for u in PERMANENT_UPGRADES if u["id"] == upgrade_id), None)
        if not upgrade:
            return "Unknown upgrade."
        level = self.upgrade_levels.get(upgrade_id, 0)
        if level >= upgrade["max_level"]:
            return "Already at max level!"
        cost = self.get_upgrade_cost(upgrade_id)
        if self.shards < cost:
            return f"Not enough shards! Need {cost}."
        return "Cannot purchase upgrade."

    def can_buy_skin(self, skin_id: str) -> bool:
        """Check if skin can be purchased."""
        skin = next((s for s in SKINS if s["id"] == skin_id), None)
        if not skin or skin_id in self.unlocked_skins:
            return False
        if not self.skin_requirement_met(skin):
            return False
        return self.shards >= skin["cost"]

    def skin_requirement_met(self, skin: dict) -> bool:
        """Check lore gate for a skin."""
        req_w = skin.get("require_warden")
        if req_w and req_w not in self.unlocked_wardens:
            return False
        req_e = skin.get("require_ending")
        if req_e and req_e not in self.endings_seen:
            return False
        return True

    def get_skin_lock_reason(self, skin_id: str) -> str:
        """Explain why a skin cannot be bought yet."""
        skin = next((s for s in SKINS if s["id"] == skin_id), None)
        if not skin:
            return "Unknown skin."
        if skin_id in self.unlocked_skins:
            return "Already owned."
        if not self.skin_requirement_met(skin):
            return skin.get("lock_hint", "Lore requirement not met.")
        if self.shards < skin["cost"]:
            return f"Not enough shards! Need {skin['cost']}."
        return "Cannot unlock skin."

    def purchase_skin(self, skin_id: str) -> bool:
        """Unlock a skin."""
        if not self.can_buy_skin(skin_id):
            return False
        skin = next(s for s in SKINS if s["id"] == skin_id)
        self.shards -= skin["cost"]
        self.unlocked_skins.append(skin_id)
        return True

    def record_ending(self, ending: str) -> None:
        """Record a Core ending for lore gates and Archive."""
        if ending and ending not in self.endings_seen:
            self.endings_seen.append(ending)

    def broker_ending_available(self) -> bool:
        """Secret Ending C unlock conditions."""
        return (
            bool(self.endings_seen)
            and len(self.unlocked_wardens) >= 8
            and self.total_shards_earned >= 200
            and "void_core" in self.unlocked_artifacts
        )

    def equip_skin(self, skin_id: str) -> bool:
        """Equip an unlocked skin."""
        if skin_id in self.unlocked_skins:
            self.equipped_skin = skin_id
            return True
        return False

    def get_skin_colors(self) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
        """Return (color, core) for equipped skin."""
        skin = next((s for s in SKINS if s["id"] == self.equipped_skin), SKINS[0])
        return skin["color"], skin["core"]

    def unlock_warden(self, fragment_id: str) -> bool:
        """Unlock a warden memory fragment. Returns True if newly unlocked."""
        if fragment_id in self.unlocked_wardens:
            return False
        self.unlocked_wardens.append(fragment_id)
        return True

    def unlock_artifact_lore(self, artifact_id: str) -> bool:
        """Unlock artifact Archive entry. Returns True if newly unlocked."""
        if artifact_id in self.unlocked_artifacts:
            return False
        self.unlocked_artifacts.append(artifact_id)
        return True

    def to_dict(self) -> dict:
        """Serialize permanent progress."""
        return {
            "shards": self.shards,
            "total_shards_earned": self.total_shards_earned,
            "upgrade_levels": self.upgrade_levels,
            "unlocked_skins": self.unlocked_skins,
            "equipped_skin": self.equipped_skin,
            "unlocked_wardens": self.unlocked_wardens,
            "unlocked_artifacts": self.unlocked_artifacts,
            "endings_seen": self.endings_seen,
        }

    def from_dict(self, data: dict) -> None:
        """Load permanent progress."""
        self.shards = data.get("shards", 0)
        self.total_shards_earned = data.get("total_shards_earned", 0)
        for key, level in data.get("upgrade_levels", {}).items():
            if key not in self.upgrade_levels:
                self.upgrade_levels[key] = 0
            self.upgrade_levels[key] = level
        self.unlocked_skins = data.get("unlocked_skins", ["default"])
        self.equipped_skin = data.get("equipped_skin", "default")
        self.unlocked_wardens = list(data.get("unlocked_wardens", []))
        self.unlocked_artifacts = list(data.get("unlocked_artifacts", []))
        self.endings_seen = list(data.get("endings_seen", []))
