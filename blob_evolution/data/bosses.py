"""Boss and mini-boss definitions (TASK-054): stats, phases, cadence, movement and attack keys as data, no pygame."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class PhaseDef:
    """A phase that starts when the HP ratio drops below `below`."""

    phase: int
    below: float
    special_cooldown: float        # the special cooldown is reset to this when the phase starts
    enrage: bool = False           # starts once, while the boss is not enraged yet, and sets `enraged`
    crossing: bool = False         # starts only on the hit that crosses `below`


@dataclass(frozen=True)
class Cadence:
    """Seconds between basic shots and between specials, and their phase / mini-boss multipliers."""

    basic: float = 1.7
    basic_enraged: float = 1.2
    basic_final_mult: float = 0.75     # phase 3 and later
    basic_mini_mult: float = 1.2
    special: float = 5.2
    special_enraged: float = 3.2
    special_final_mult: float = 0.7
    special_mini_mult: float = 1.15
    first_basic: float = 1.5           # cooldowns right after spawning
    first_special: float = 4.0


@dataclass(frozen=True)
class BossStats:
    """Stat formulas: wardens scale with power = act + slot, mini-bosses with the act."""

    size_base: int = 50
    size_per_power: int = 10
    mini_size_base: int = 35
    mini_size_per_act: int = 2
    hp_base: int = 300
    hp_per_power: int = 100
    mini_hp_mult: float = 0.55
    damage_base: int = 20
    damage_per_power: int = 5
    speed: int = 60


@dataclass(frozen=True)
class BossDef:
    """One warden: Archive id, movement, basic shot, special attack and phases (keys into entities/boss_attacks.py)."""

    key: str
    act: int
    archive_id: Optional[str]
    move: str
    basic: str
    special: str
    phases: Tuple[PhaseDef, ...]
    basic_other_slots: Optional[str] = None      # basic shot for slots > 0 when it differs (layer 9 today)


@dataclass(frozen=True)
class MiniDef:
    """The generic Lattice Anchor mini-boss: it keeps its layer's basic shot and phases."""

    key: str = "lattice_anchor"
    move: str = "orbit"
    special: str = "anchor_radial"


STATS = BossStats()
CADENCE = Cadence()
MINI = MiniDef()

PHASE_2 = PhaseDef(2, 0.5, 1.5, enrage=True)
PHASE_3 = PhaseDef(3, 0.25, 1.0, crossing=True)
TWO_PHASES = (PHASE_2,)
THREE_PHASES = (PHASE_2, PHASE_3)
FINAL_PHASE_FROM_ACT = 8           # acts at or past this one have phase 3

WARDENS: Tuple[BossDef, ...] = (
    BossDef("sprouting", 0, "warden_0", "orbit", "spiral_seed", "bloom_ring", TWO_PHASES),
    BossDef("rot", 1, "warden_1", "weave", "weeping_twin", "rot_ring", TWO_PHASES),
    BossDef("echoes", 2, "warden_2", "orbit", "ghost_shot", "echo_ring", TWO_PHASES),
    BossDef("ash", 3, "warden_3", "circle_dash", "aimed", "erupt_ring", TWO_PHASES),
    BossDef("frost", 4, "warden_4", "linger", "shard_fan", "frost_ring", TWO_PHASES),
    BossDef("thirst", 5, "warden_5", "blink", "aimed", "mirage_volley", TWO_PHASES),
    BossDef("masks", 6, "warden_6", "strafe", "aimed", "mask_burst", TWO_PHASES),
    BossDef("silence", 7, "warden_7", "drift", "void_bolt", "void_ring", TWO_PHASES),
    BossDef("ascent", 8, "warden_8", "orbit", "pink_triple", "verdict", THREE_PHASES, basic_other_slots="aimed"),
    BossDef("anchor", 9, "warden_9", "assault", "pink_triple", "divide", THREE_PHASES),
)


def warden_def(act_index: int) -> BossDef:
    """Definition of an act's warden; acts outside 0-9 get the generic kit the old code fell back to."""
    if 0 <= act_index < len(WARDENS):
        return WARDENS[act_index]
    phases = THREE_PHASES if act_index >= FINAL_PHASE_FROM_ACT else TWO_PHASES
    return BossDef(f"act_{act_index}", act_index, None, "assault", "aimed", "divide", phases)
