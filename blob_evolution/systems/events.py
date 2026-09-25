"""Random event system with boons and curses."""

from __future__ import annotations

import copy
import random
from typing import Dict, List, Optional, Tuple

# act_min / act_max inclusive when set; omitted = any act
RANDOM_EVENTS: List[dict] = [
    {
        "id": "living_well",
        "title": "Living Well",
        "description": "Lattice fluid pools here — concentrated potential. Drinking borrows mass from your future self.",
        "choices": [
            {"label": "Drink", "boon": "damage_up", "curse": "hp_down"},
            {"label": "Walk away", "boon": None, "curse": None},
        ],
    },
    {
        "id": "ancestor_node",
        "title": "Ancestor Node",
        "description": "An old membrane shrine hums with one lineage's devotion. Alignment brings peace — and rigidity.",
        "choices": [
            {"label": "Pray", "boon": "heal_full", "curse": "slow"},
            {"label": "Leave", "boon": None, "curse": None},
        ],
    },
    {
        "id": "the_broker",
        "title": "The Broker",
        "description": "A hooded blob trades fossilized organs. It smiles like it has met you before.",
        "choices": [
            {"label": "Trade HP for artifact", "boon": "random_artifact", "curse": "hp_down"},
            {"label": "Decline", "boon": None, "curse": None},
        ],
    },
    {
        "id": "stillness_whisper",
        "title": "Stillness Whisper",
        "description": "A cold shadow promises speed if you stop changing in all the ways that matter.",
        "choices": [
            {"label": "Accept", "boon": "speed_up", "curse": "fragile"},
            {"label": "Refuse", "boon": "small_heal", "curse": None},
        ],
    },
    {
        "id": "fossil_heart",
        "title": "Fossil Heart",
        "description": "Crystals pulse with extinct life. Absorbing them accelerates growth — and dulls your healing.",
        "choices": [
            {"label": "Absorb power", "boon": "xp_boost", "curse": "regen_down"},
            {"label": "Ignore", "boon": None, "curse": None},
        ],
    },
    {
        "id": "prior_pilgrim",
        "title": "Prior Pilgrim",
        "description": "The remains of a great blob lie before you — a pilgrim who almost reached the Core.",
        "choices": [
            {"label": "Inherit strength", "boon": "skill_point", "curse": "slow"},
            {"label": "Pay respects", "boon": "heal_partial", "curse": None},
        ],
    },
    # Act-flavored / late-layer events
    {
        "id": "rim_nursery",
        "title": "Nursery Drift",
        "description": "Soft young forms cluster around you, mistaking hunger for kinship.",
        "act_max": 1,
        "choices": [
            {"label": "Absorb them", "boon": "heal_partial", "curse": "fragile"},
            {"label": "Shepherd them away", "boon": "small_heal", "curse": None},
        ],
    },
    {
        "id": "toxic_bloom",
        "title": "Toxic Bloom",
        "description": "A flower of preserved corpses opens. Its pollen remembers every failed shape.",
        "act_min": 1,
        "act_max": 2,
        "choices": [
            {"label": "Breathe it in", "boon": "essence_bonus", "curse": "regen_down"},
            {"label": "Seal the bloom", "boon": None, "curse": None},
        ],
    },
    {
        "id": "forge_bargain",
        "title": "Forge Bargain",
        "description": "Heat offers to burn away a weakness — and some of what you still are.",
        "act_min": 3,
        "act_max": 4,
        "choices": [
            {"label": "Step into the vein", "boon": "damage_up", "curse": "hp_down"},
            {"label": "Stay cool", "boon": None, "curse": None},
        ],
    },
    {
        "id": "mirror_pool",
        "title": "Mirror Pool",
        "description": "The pool shows every Seedling you have been. Some smile. Some starve.",
        "act_min": 6,
        "choices": [
            {"label": "Touch your reflection", "boon": "skill_point", "curse": "fragile"},
            {"label": "Shatter the surface", "boon": "xp_boost", "curse": "slow"},
            {"label": "Look away", "boon": None, "curse": None},
        ],
    },
    {
        "id": "the_unsplit",
        "title": "The Unsplit",
        "description": "A rare blob that never divided waits in the dark. Merge — or release it.",
        "act_min": 7,
        "choices": [
            {"label": "Merge", "boon": "heal_full", "curse": "slow"},
            {"label": "Release it", "boon": "random_artifact", "curse": None},
            {"label": "Pass by", "boon": None, "curse": None},
        ],
    },
    {
        "id": "lattice_scar",
        "title": "Lattice Scar",
        "description": "A wound in the membrane bleeds hazard from another layer. Bind it — or drink it.",
        "act_min": 4,
        "choices": [
            {"label": "Drink the scar", "boon": "damage_up", "curse": "fragile"},
            {"label": "Bind the wound", "boon": "heal_partial", "curse": None},
        ],
    },
    {
        "id": "triad_whisper",
        "title": "Triad Whisper",
        "description": "Three voices argue whether you deserve the Core. One offers a bribe.",
        "act_min": 8,
        "act_max": 9,
        "choices": [
            {"label": "Take the bribe", "boon": "essence_bonus", "curse": "hp_down"},
            {"label": "Refuse all three", "boon": "skill_point", "curse": None},
        ],
    },
]

BOON_EFFECTS: Dict[str, dict] = {
    "damage_up": {"damage_mult": 1.15, "desc": "+15% damage"},
    "speed_up": {"speed_mult": 1.12, "desc": "+12% speed"},
    "heal_full": {"heal_percent": 1.0, "desc": "Full heal"},
    "heal_partial": {"heal_percent": 0.35, "desc": "Heal 35% HP"},
    "small_heal": {"heal_percent": 0.15, "desc": "Heal 15% HP"},
    "random_artifact": {"artifact": True, "desc": "Random artifact"},
    "xp_boost": {"xp_mult": 1.25, "desc": "+25% XP"},
    "skill_point": {"skill_point": 1, "desc": "+1 skill point"},
    "essence_bonus": {"essence_mult": 1.3, "desc": "+30% essence"},
}

CURSE_EFFECTS: Dict[str, dict] = {
    "hp_down": {"hp_mult": 0.88, "desc": "-12% max HP"},
    "slow": {"speed_mult": 0.88, "desc": "-12% speed"},
    "fragile": {"damage_taken_mult": 1.15, "desc": "+15% damage taken"},
    "regen_down": {"regen_mult": 0.5, "desc": "-50% regeneration"},
}


def _event_allowed(event: dict, act_index: int) -> bool:
    """Return True if event can appear on this act."""
    if "act_min" in event and act_index < event["act_min"]:
        return False
    if "act_max" in event and act_index > event["act_max"]:
        return False
    return True


def _flavor_event(event: dict, ng_plus_level: int, total_runs: int) -> dict:
    """Apply NG+/memory flavor text to a copied event."""
    ev = copy.deepcopy(event)
    eid = ev["id"]
    if eid == "prior_pilgrim" and (ng_plus_level >= 1 or total_runs >= 2):
        ev["title"] = "Your Prior Self"
        ev["description"] = (
            "The remains wear your colors — a Seedling who almost reached the Core. "
            "The Lattice kept the shard warm."
        )
        ev["choices"][0]["label"] = "Inherit your strength"
        ev["choices"][1]["label"] = "Mourn yourself"
    elif eid == "the_broker" and ng_plus_level >= 2:
        ev["description"] = (
            "The Broker greets you by a name you have not chosen yet. "
            "Its tray of organs includes one that looks like yours."
        )
    elif eid == "stillness_whisper" and ng_plus_level >= 5:
        ev["description"] = (
            "Stillness speaks with the Prime Anchor's patience. "
            "It has watched you reopen the wound before."
        )
    elif eid == "mirror_pool" and ng_plus_level >= 1:
        n = max(1, ng_plus_level)
        ev["description"] = (
            f"The pool shows {n} prior Seedling{'s' if n != 1 else ''}. "
            "One of them almost chose Stillness."
        )
    return ev


class EventManager:
    """Handles random event selection and effect application."""

    def __init__(self) -> None:
        self.current_event: Optional[dict] = None

    def roll_event(
        self,
        seed: Optional[int] = None,
        act_index: int = 0,
        ng_plus_level: int = 0,
        total_runs: int = 0,
    ) -> dict:
        """Pick a random event filtered by act, with NG+ flavor."""
        rng = random.Random(seed)
        pool = [e for e in RANDOM_EVENTS if _event_allowed(e, act_index)]
        if not pool:
            pool = list(RANDOM_EVENTS)
        chosen = rng.choice(pool)
        self.current_event = _flavor_event(chosen, ng_plus_level, total_runs)
        return self.current_event

    @staticmethod
    def apply_choice(
        choice: dict,
        player,
        artifacts_manager,
    ) -> Tuple[List[str], List[str]]:
        """Apply event choice effects. Returns (boon messages, curse messages)."""
        boon_msgs: List[str] = []
        curse_msgs: List[str] = []

        boon_id = choice.get("boon")
        curse_id = choice.get("curse")

        if boon_id and boon_id in BOON_EFFECTS:
            effect = BOON_EFFECTS[boon_id]
            boon_msgs.append(f"Boon: {effect['desc']}")
            if "damage_mult" in effect:
                player.run_modifiers["damage_mult"] *= effect["damage_mult"]
            if "speed_mult" in effect:
                player.run_modifiers["speed_mult"] *= effect["speed_mult"]
            if "xp_mult" in effect:
                player.run_modifiers["xp_mult"] *= effect["xp_mult"]
            if "essence_mult" in effect:
                player.run_modifiers["essence_mult"] *= effect["essence_mult"]
            if "heal_percent" in effect:
                player.heal(player.max_hp * effect["heal_percent"])
            if effect.get("artifact"):
                from blob_evolution.systems.artifacts import ArtifactManager
                art_id = ArtifactManager.random_drop()
                art = artifacts_manager.add(art_id)
                if art:
                    boon_msgs.append(f"Received: {art['name']}")
                    player._update_stats()
            if effect.get("skill_point"):
                player.skill_points += effect["skill_point"]

        if curse_id and curse_id in CURSE_EFFECTS:
            effect = CURSE_EFFECTS[curse_id]
            curse_msgs.append(f"Curse: {effect['desc']}")
            if "hp_mult" in effect:
                player.run_modifiers["hp_mult"] *= effect["hp_mult"]
                player.max_hp *= effect["hp_mult"]
                player.hp = min(player.hp, player.max_hp)
            if "speed_mult" in effect:
                player.run_modifiers["speed_mult"] *= effect["speed_mult"]
            if "damage_taken_mult" in effect:
                player.run_modifiers["damage_taken_mult"] *= effect["damage_taken_mult"]
            if "regen_mult" in effect:
                player.run_modifiers["regen_mult"] *= effect["regen_mult"]

        player._update_stats()
        return boon_msgs, curse_msgs
