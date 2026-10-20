"""Layer-start checkpoint (TASK-070): the run state written as the optional "checkpoint" save field."""

from __future__ import annotations

from typing import Any, Dict, Optional

from blob_evolution import config
from blob_evolution.entities.player import Player
from blob_evolution.systems import savefile
from blob_evolution.systems.artifacts import ARTIFACT_DEFINITIONS
from blob_evolution.systems.overworld import OverworldMap
from blob_evolution.systems.skills import SKILL_DEFINITIONS
from blob_evolution.utils.enums import Difficulty
from blob_evolution.utils.vector2 import Vector2

VERSION = 1
RUN_BONUS_NUMBERS = ("run_damage_boost", "run_speed_boost", "run_xp_boost", "run_magnet_flat", "run_size_boost")


def _counts(value: object) -> list:
    """The whole numbers 0..INT_MAX of a saved list (anything else gives [])."""
    return [int(v) for v in value if savefile._is_count(v)] if isinstance(value, list) else []


def capture(game: Any) -> dict:
    """Snapshot the run at a layer start (overworld just built, nothing on it entered)."""
    p, eco = game.player, game.economy
    bonuses: Dict[str, Any] = {k: float(getattr(eco, k)) for k in RUN_BONUS_NUMBERS}
    bonuses["run_piercing"] = bool(eco.run_piercing)
    return {
        "version": VERSION,
        "act_index": game.overworld.act_index,
        "overworld_seed": game.overworld.seed,
        "difficulty": game.difficulty.value,
        "ng_plus_level": int(game.ng_plus.ng_plus_level),
        "maps_cleared": game.maps_cleared,
        "run_shards_earned": game.run_shards_earned,
        "seen_acts": sorted(game._seen_acts),
        "essence": int(eco.essence),
        "run_bonuses": bonuses,
        "player": {
            "level": p.level, "xp": int(p.xp), "xp_to_next": int(p.xp_to_next), "total_xp": int(p.total_xp),
            "skill_points": p.skill_points, "kills": p.kills, "hp": float(p.hp),
            "skills": p.skills.to_dict(),
            "artifacts": p.artifacts.to_list(),
            "artifact_upgrades": dict(p.artifacts.upgrade_levels),
            "evolution": {"current_form": p.evolution.current_form, "unlocked_forms": list(p.evolution.unlocked_forms),
                          "checked_levels": sorted(p.evolution._checked_levels)},
            "run_modifiers": {k: float(v) for k, v in p.run_modifiers.items()},
            "ng_mult": {k: float(v) for k, v in p.ng_mult.items()},
            "shop_max_hp_bonus": float(p.shop_max_hp_bonus),
            "shop_size_boost": float(p.shop_size_boost),
            "has_shield": bool(p.has_shield),
            "has_revived": bool(p.has_revived),
        },
    }


# BUG-265: keys a checkpoint must carry (a missing one rejects it); player keys are under "player"
REQUIRED_KEYS = ("version", "act_index", "overworld_seed", "difficulty", "ng_plus_level", "essence", "player")
REQUIRED_PLAYER_KEYS = ("hp", "skills", "level", "artifacts")
_ABSENT = object()


def read(raw: object = _ABSENT) -> Optional[dict]:
    """Validate a saved checkpoint; None when absent (old saves) or unusable (one warning, never blocks the save).

    Call with no argument when the save has no "checkpoint" key. A present null (BUG-266), a missing required
    field (BUG-265) or a dead player (hp <= 0) is unusable.
    """
    if raw is _ABSENT:
        return None
    if raw is None:
        savefile.warn(f"{config.SAVE_FILE} has a null checkpoint; it is ignored")
        return None
    top = savefile.SaveSection(raw)
    pl = savefile.SaveSection(top.data.get("player", None))
    bon = savefile.SaveSection(top.data.get("run_bonuses", {}))
    evo = savefile.SaveSection(pl.data.get("evolution", {}))
    data = {
        "version": top.integer("version", -1),
        "act_index": top.integer("act_index", -1),
        "overworld_seed": top.integer("overworld_seed", 0),
        "difficulty": top.text("difficulty", ""),
        "ng_plus_level": top.integer("ng_plus_level", 0),
        "maps_cleared": top.integer("maps_cleared", 0),
        "run_shards_earned": top.integer("run_shards_earned", 0),
        "seen_acts": _counts(top.data.get("seen_acts")),
        "essence": top.integer("essence", 0),
        "run_bonuses": {**{k: bon.number(k, 0.0) for k in RUN_BONUS_NUMBERS},
                        "run_piercing": bon.boolean("run_piercing", False)},
        "player": {
            "level": pl.integer("level", 1), "xp": pl.integer("xp", 0), "xp_to_next": pl.integer("xp_to_next", 1),
            "total_xp": pl.integer("total_xp", 0), "skill_points": pl.integer("skill_points", 0),
            "kills": pl.integer("kills", 0), "hp": pl.number("hp", 1.0),
            "skills": pl.integer_dict("skills", {}, {k: config.MAX_SKILL_LEVEL for k in SKILL_DEFINITIONS}),
            "artifacts": [a for a in pl.str_list("artifacts", []) if a in ARTIFACT_DEFINITIONS],
            "artifact_upgrades": pl.integer_dict("artifact_upgrades", {}),
            "evolution": {"current_form": evo.text("current_form", "Base Form"),
                          "unlocked_forms": evo.str_list("unlocked_forms", ["Base Form"]),
                          "checked_levels": _counts(evo.data.get("checked_levels"))},
            "run_modifiers": pl.number_dict("run_modifiers", {}),
            "ng_mult": pl.number_dict("ng_mult", {}),
            "shop_max_hp_bonus": pl.number("shop_max_hp_bonus", 0.0),
            "shop_size_boost": pl.number("shop_size_boost", 0.0),
            "has_shield": pl.boolean("has_shield", False),
            "has_revived": pl.boolean("has_revived", False),
        },
    }
    ok = all(k in top.data for k in REQUIRED_KEYS) and all(k in pl.data for k in REQUIRED_PLAYER_KEYS)
    ok = ok and all(s.valid for s in (top, pl, bon, evo))
    ok = ok and all(isinstance(v, list) for v in (top.data.get("seen_acts", []), evo.data.get("checked_levels", [])))
    ok = ok and data["version"] == VERSION and 0 <= data["act_index"] < len(config.MAP_THEMES)
    ok = ok and data["difficulty"] in {d.value for d in Difficulty}
    ok = ok and data["player"]["hp"] > 0                     # a 0-HP checkpoint is a dead run, never resumed at 1 HP
    if not ok:
        savefile.warn(f"{config.SAVE_FILE} has an unusable checkpoint; it is ignored")
        return None
    return data


def restore(game: Any, data: dict) -> None:
    """Rebuild the run from a checkpoint: the layer's map from its seed, the player as the layer began."""
    game.difficulty = Difficulty(data["difficulty"])
    p = Player(Vector2(config.WORLD_WIDTH // 2, config.WORLD_HEIGHT // 2))
    game.player = p
    game._apply_permanent_bonuses()
    s = data["player"]
    p.level, p.xp, p.xp_to_next, p.total_xp = s["level"], s["xp"], s["xp_to_next"], s["total_xp"]
    p.skill_points, p.kills = s["skill_points"], s["kills"]
    p.skills.from_dict(s["skills"])
    p.artifacts.from_list(s["artifacts"])
    p.artifacts.upgrade_levels = dict(s["artifact_upgrades"])
    p.evolution.from_dict(s["evolution"])
    p.run_modifiers.update({k: v for k, v in s["run_modifiers"].items() if k in p.run_modifiers})
    p.ng_mult.update({k: v for k, v in s["ng_mult"].items() if k in p.ng_mult})
    p.shop_max_hp_bonus, p.shop_size_boost = s["shop_max_hp_bonus"], s["shop_size_boost"]
    p.has_shield, p.has_revived = s["has_shield"], s["has_revived"]
    p._update_stats()
    p.hp = min(s["hp"], p.max_hp)                       # read() guarantees hp > 0
    eco = game.economy
    eco.reset_run_bonuses()
    for k in RUN_BONUS_NUMBERS:
        setattr(eco, k, data["run_bonuses"][k])
    eco.run_piercing = data["run_bonuses"]["run_piercing"]
    eco.essence = data["essence"]
    game.maps_cleared, game.run_shards_earned = data["maps_cleared"], data["run_shards_earned"]
    game._seen_acts = set(data["seen_acts"]) | {data["act_index"]}
    game.overworld = OverworldMap(act_index=data["act_index"], seed=data["overworld_seed"])
    game.overworld_selected = 0
