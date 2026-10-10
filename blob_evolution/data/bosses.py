"""Boss and mini-boss definitions (TASK-054/055/057): stats, phases, cadence, movers, attacks and anchors; no pygame."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Optional, Sequence, Tuple

from blob_evolution import config
from blob_evolution.data.lore import ACT_LORE


@dataclass(frozen=True)
class PhaseDef:
    """A phase that starts when the HP ratio drops below `below`."""

    phase: int
    below: float
    special_cooldown: float        # the special cooldown is reset to this when the phase starts
    enrage: bool = False           # starts once, while the boss is not enraged yet, and sets `enraged`
    crossing: bool = False         # starts only on the hit that crosses `below`
    name: Optional[str] = None     # display name from this phase on (layer 9's triad)


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


@dataclass(frozen=True)
class AnchorDef:
    """One named mini-boss (BOSS-ROSTER section 3, Director-approved): identity and radius; kit stays MINI's for now."""

    key: str
    name: str
    act: int
    radius: int                  # TASK-045 section 3 value; also the hitbox (Producer ruling)
    card_line: str               # roster section 5 card body (not shown yet: needs the card / narration ticket)


STATS = BossStats()
CADENCE = Cadence()
MINI = MiniDef()

_P2_CD = config.BOSS_PHASE2_SPECIAL_COOLDOWN
_P3_CD = config.BOSS_PHASE3_SPECIAL_COOLDOWN
_TRIAD = ACT_LORE[8]["triad_names"]     # Warden of Ascent / Echoes / Stillness: one body, three phases

PHASE_2 = PhaseDef(2, 0.5, _P2_CD, enrage=True)
PHASE_3 = PhaseDef(3, 0.25, _P3_CD, crossing=True)
TWO_PHASES = (PHASE_2,)                                      # roster layers 1-3
THREE_PHASES = (PHASE_2, PHASE_3)                            # roster layers 4-8: 50 % / 25 %
ASCENT_PHASES = (PhaseDef(2, 0.66, _P2_CD, enrage=True, name=_TRIAD[1]),
                 PhaseDef(3, 0.33, _P3_CD, crossing=True, name=_TRIAD[2]))     # layer 9: 66 % / 33 %
DIVIDE_PHASES = (PhaseDef(2, 0.66, _P2_CD, enrage=True), PHASE_3)              # layer 10: 66 % / 25 % (Producer ruling)
FINAL_PHASE_FROM_ACT = 8           # main's rule, still used by mini-bosses and acts outside the table


def mini_phases(act_index: int) -> Tuple[PhaseDef, ...]:
    """Mini-boss phases stay as on main: 50 %, plus 25 % from act 8 on (the roster's table is for wardens)."""
    return THREE_PHASES if act_index >= FINAL_PHASE_FROM_ACT else TWO_PHASES


WARDENS: Tuple[BossDef, ...] = (
    BossDef("sprouting", 0, "warden_0", "orbit", "spiral_seed", "bloom_ring", TWO_PHASES),
    BossDef("rot", 1, "warden_1", "weave", "weeping_twin", "rot_ring", TWO_PHASES),
    BossDef("echoes", 2, "warden_2", "orbit", "ghost_shot", "echo_ring", TWO_PHASES),
    BossDef("ash", 3, "warden_3", "circle_dash", "aimed", "erupt_ring", THREE_PHASES),
    BossDef("frost", 4, "warden_4", "linger", "shard_fan", "frost_ring", THREE_PHASES),
    BossDef("thirst", 5, "warden_5", "blink", "aimed", "mirage_volley", THREE_PHASES),
    BossDef("masks", 6, "warden_6", "strafe", "aimed", "mask_burst", THREE_PHASES),
    BossDef("silence", 7, "warden_7", "drift", "void_bolt", "void_ring", THREE_PHASES),
    BossDef("ascent", 8, "warden_8", "orbit", "pink_triple", "verdict", ASCENT_PHASES, basic_other_slots="aimed"),
    BossDef("anchor", 9, "warden_9", "assault", "pink_triple", "divide", DIVIDE_PHASES),
)


# Two per layer, in roster order. Stats are main's mini formulas: the roster gives no numbers.
ANCHORS: Tuple[AnchorDef, ...] = (
    AnchorDef("cradle_husk", "Cradle Husk", 0, 35, "A husk of the nursery, still shaped like a hug."),
    AnchorDef("first_sprout", "First Sprout", 0, 37, "The first thing the Rim ever grew. It has not moved since."),
    AnchorDef("sinking_bloat", "Sinking Bloat", 1, 37, "A mercy that swelled until it could not hold itself."),
    AnchorDef("green_mourner", "Green Mourner", 1, 37, "It weeps for names no one finished."),
    AnchorDef("glass_clerk", "Glass Clerk", 2, 39, "It records everything that crosses the glass."),
    AnchorDef("unfinished_entry", "Unfinished Entry", 2, 39,
                "A Seedling that stopped halfway. It remembers your last step."),
    AnchorDef("cinder_anvil", "Cinder Anvil", 3, 39, "A shape forged to test the next shape."),
    AnchorDef("ember_runner", "Ember Runner", 3, 41, "It runs until there is nothing left to burn."),
    AnchorDef("rime_sentinel", "Rime Sentinel", 4, 43, "A guard who agreed to stay."),
    AnchorDef("drift_sleeper", "Drift Sleeper", 4, 43, "It slows you the way sleep does."),
    AnchorDef("oasis_lure", "Oasis Lure", 5, 45, "The water you were promised."),
    AnchorDef("dry_maw", "Dry Maw", 5, 45, "What the mirage hides underneath."),
    AnchorDef("borrowed_face", "Borrowed Face", 6, 49, "It wears the last shape it saw."),
    AnchorDef("pollen_sleeper", "Pollen Sleeper", 6, 49, "A dream that learned to walk."),
    AnchorDef("quiet_hollow", "Quiet Hollow", 7, 51, "Nothing here wants to be remembered. This is how."),
    AnchorDef("forgotten_shape", "Forgotten Shape", 7, 51, "A form you already ended, returned without a name."),
    AnchorDef("updraft_herald", "Updraft Herald", 8, 47, "It carries the verdict upward."),
    AnchorDef("verdict_pillar", "Verdict Pillar", 8, 47, "A judgment that no longer needs a judge."),
    AnchorDef("first_split", "First Split", 9, 53, "The moment one became two."),
    AnchorDef("last_whole", "Last Whole", 9, 53, "The last shape that stayed whole."),
)
ANCHORS_PER_LAYER = 2


def anchor_def(act_index: int, variant: int) -> Optional[AnchorDef]:
    """The layer's anchor number `variant` (0 or 1, wraps); None outside layers 1-10 (main's generic one)."""
    pair = [a for a in ANCHORS if a.act == act_index]
    return pair[variant % len(pair)] if pair else None


def anchor_variant(seed: int, act_index: int, node_id: str, mini_node_ids: Sequence[str],
                   pick: Optional[str] = None) -> int:
    """Which anchor a mini-boss node spawns: fixed by the map seed, act and node id, so a reload picks the same one.

    Own Random (string-seeded, stable across runs), so the game's global RNG stream is untouched.
    """
    pick = pick or config.BOSS_ANCHOR_PICK
    if pick == "random":
        return random.Random(f"anchor:{seed}:{act_index}:{node_id}").randrange(ANCHORS_PER_LAYER)
    start = random.Random(f"anchor:{seed}:{act_index}").randrange(ANCHORS_PER_LAYER)
    rank = list(mini_node_ids).index(node_id) if node_id in mini_node_ids else 0      # ids in map order
    return (start + rank) % ANCHORS_PER_LAYER


def node_anchor_variant(overworld: Any, node: Any) -> int:
    """anchor_variant for an overworld node (reads seed, act and the map's nodes of the same type; writes nothing)."""
    in_order = sorted(overworld.nodes.values(), key=lambda n: (n.layer, n.col))
    same = [n.id for n in in_order if n.node_type == node.node_type]
    return anchor_variant(overworld.seed, overworld.act_index, node.id, same)


def warden_def(act_index: int) -> BossDef:
    """Definition of an act's warden; acts outside 0-9 get the generic kit the old code fell back to."""
    if 0 <= act_index < len(WARDENS):
        return WARDENS[act_index]
    phases = THREE_PHASES if act_index >= FINAL_PHASE_FROM_ACT else TWO_PHASES
    return BossDef(f"act_{act_index}", act_index, None, "assault", "aimed", "divide", phases)
