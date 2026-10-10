"""Animation clocks driven by the game's frame dt instead of the wall clock (BUG-140, BUG-144).

`game` advances only while gameplay updates (so enemy-shape animation freezes while paused or in the skill menu);
`ui` advances every frame in every state (menu pulses, ambient backgrounds, story cards). Both are plain seconds and
reproducible: the same sequence of dt gives the same frames. Nothing here touches gameplay state or the RNG.
"""
from __future__ import annotations

_t = {"game": 0.0, "ui": 0.0}


def advance(dt: float, gameplay: bool) -> None:
    """Called once per frame from Game._update; `gameplay` is True while the fight / exploration logic ran."""
    _t["ui"] += dt
    if gameplay:
        _t["game"] += dt


def game_time() -> float:
    return _t["game"]


def game_ms() -> int:
    return int(_t["game"] * 1000.0)


def ui_time() -> float:
    return _t["ui"]


def reset(game: float = 0.0, ui: float = 0.0) -> None:
    """Tests and harnesses: start both clocks from a known time."""
    _t["game"], _t["ui"] = float(game), float(ui)
