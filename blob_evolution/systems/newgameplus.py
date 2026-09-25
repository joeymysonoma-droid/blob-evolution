"""New Game Plus progression system."""

from __future__ import annotations

from typing import Dict

from blob_evolution.data.lore import VICTORY_NG_PLUS_LINE
from blob_evolution.systems.savefile import SaveSection


def _is_number(value: object) -> bool:
    """True for int/float save values (bool excluded)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class NewGamePlus:
    """Manages loop progression with permanent bonuses."""

    def __init__(self) -> None:
        self.ng_plus_level = 0
        self.total_runs = 0
        self.best_map_reached = 0
        self.permanent_bonuses: Dict[str, float] = {
            "damage": 0.0,
            "health": 0.0,
            "speed": 0.0,
            "essence": 0.0,
        }

    def complete_run(self, maps_cleared: int) -> str:
        """Record a completed run and apply NG+ bonuses."""
        self.total_runs += 1
        if maps_cleared >= 10:
            # Full clear: the deepest layer reached is the last one cleared (Layer 10 = index 9).
            self.best_map_reached = max(self.best_map_reached, maps_cleared - 1)
            self.ng_plus_level += 1
            self._apply_bonuses()
            return VICTORY_NG_PLUS_LINE.format(n=self.ng_plus_level)
        self.best_map_reached = max(self.best_map_reached, maps_cleared)
        return f"Best progress: Layer {maps_cleared + 1}"

    def _apply_bonuses(self) -> None:
        """Increase permanent bonuses per NG+ level."""
        self.permanent_bonuses["damage"] = self.ng_plus_level * 0.05
        self.permanent_bonuses["health"] = self.ng_plus_level * 0.05
        self.permanent_bonuses["speed"] = self.ng_plus_level * 0.03
        self.permanent_bonuses["essence"] = self.ng_plus_level * 0.10

    def get_multiplier(self, stat: str) -> float:
        """Get NG+ multiplier for a stat."""
        return 1.0 + self.permanent_bonuses.get(stat, 0.0)

    def to_dict(self) -> dict:
        """Serialize NG+ state."""
        return {
            "ng_plus_level": self.ng_plus_level,
            "total_runs": self.total_runs,
            "best_map_reached": self.best_map_reached,
            "permanent_bonuses": self.permanent_bonuses,
        }

    def from_dict(self, data: object) -> bool:
        """Load NG+ state; bad fields use defaults. Returns False if any were bad."""
        section = SaveSection(data)
        self.ng_plus_level = section.number("ng_plus_level", 0)
        self.total_runs = section.number("total_runs", 0)
        self.best_map_reached = section.number("best_map_reached", 0)
        self.permanent_bonuses = section.number_dict("permanent_bonuses", self.permanent_bonuses)
        if _is_number(self.ng_plus_level) and _is_number(self.best_map_reached) and self.ng_plus_level >= 1:
            # Pre-TASK-013c full clears never recorded Layer 10 (index 9) as best.
            # Malformed values skip the clamp and load as they always did.
            self.best_map_reached = max(self.best_map_reached, 9)
        return section.valid
