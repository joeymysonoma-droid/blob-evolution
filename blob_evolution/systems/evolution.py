"""Evolution transformation system."""

from __future__ import annotations

from typing import List, Optional

from blob_evolution.systems.skills import SkillManager


EVOLUTION_MILESTONES = {
    5: "Adept Form",
    7: "Enhanced Form",
    10: "Perfect Form",
}


class EvolutionManager:
    """Tracks evolution state from skill milestones."""

    def __init__(self) -> None:
        self.current_form = "Base Form"
        self.unlocked_forms: List[str] = ["Base Form"]
        self._checked_levels: set = set()

    def check_evolution(self, skills: SkillManager) -> Optional[str]:
        """Check if any skill hit a milestone and evolve."""
        max_level = max(skills.get_level(s) for s in skills.levels)
        for milestone, form_name in sorted(EVOLUTION_MILESTONES.items()):
            if max_level >= milestone and milestone not in self._checked_levels:
                self._checked_levels.add(milestone)
                self.current_form = form_name
                if form_name not in self.unlocked_forms:
                    self.unlocked_forms.append(form_name)
                return f"Evolution: {form_name}!"
        return None

    def get_bonuses(self) -> dict:
        """Get passive bonuses from current form."""
        bonuses = {"damage": 1.0, "speed": 1.0, "size": 1.0}
        if self.current_form == "Adept Form":
            bonuses["damage"] = 1.1
        elif self.current_form == "Enhanced Form":
            bonuses["damage"] = 1.2
            bonuses["speed"] = 1.1
        elif self.current_form == "Perfect Form":
            bonuses["damage"] = 1.3
            bonuses["speed"] = 1.15
            bonuses["size"] = 1.1
        return bonuses

    def to_dict(self) -> dict:
        """Serialize evolution state."""
        return {
            "current_form": self.current_form,
            "unlocked_forms": self.unlocked_forms,
            "checked_levels": list(self._checked_levels),
        }

    def from_dict(self, data: dict) -> None:
        """Load evolution state."""
        self.current_form = data.get("current_form", "Base Form")
        self.unlocked_forms = data.get("unlocked_forms", ["Base Form"])
        self._checked_levels = set(data.get("checked_levels", []))
