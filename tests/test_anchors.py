"""TASK-057: the 20 named mini-bosses (anchors): roster names, TASK-045 radii as hitbox, pick per mini-boss node."""

from __future__ import annotations

import collections
import random

import pytest

from blob_evolution import config
from blob_evolution.data import bosses
from blob_evolution.data.bosses import ANCHORS, anchor_def, anchor_variant, node_anchor_variant
from blob_evolution.data.lore import MINIBOSS_NAME, build_boss_intro_pages
from blob_evolution.entities import boss_attacks
from blob_evolution.entities.boss import Boss
from blob_evolution.systems.overworld import NodeType, OverworldMap
from blob_evolution.utils.vector2 import Vector2

# BOSS-ROSTER.md section 3 (Director-approved names) and TASK-045 section 3 radii, layer by layer.
ROSTER = (
    (("Cradle Husk", 35), ("First Sprout", 37)),
    (("Sinking Bloat", 37), ("Green Mourner", 37)),
    (("Glass Clerk", 39), ("Unfinished Entry", 39)),
    (("Cinder Anvil", 39), ("Ember Runner", 41)),
    (("Rime Sentinel", 43), ("Drift Sleeper", 43)),
    (("Oasis Lure", 45), ("Dry Maw", 45)),
    (("Borrowed Face", 49), ("Pollen Sleeper", 49)),
    (("Quiet Hollow", 51), ("Forgotten Shape", 51)),
    (("Updraft Herald", 47), ("Verdict Pillar", 47)),
    (("First Split", 53), ("Last Whole", 53)),
)


@pytest.mark.parametrize("act", range(10))
def test_each_layer_has_its_two_roster_anchors_with_the_spec_radius_as_hitbox(act):
    """Name plate and hitbox: the roster name and the TASK-045 radius (L7 49, L8 51, L9 47)."""
    for variant, (name, radius) in enumerate(ROSTER[act]):
        random.seed(1)
        m = Boss(Vector2(500, 500), act, None, miniboss=True, variant=variant)
        assert (m.name, m.size, m.radius, m.anchor.act) == (name, radius, radius, act)
        assert m.anchor.key == name.lower().replace(" ", "_")
    assert anchor_def(act, 2) is anchor_def(act, 0)                     # variants wrap


def test_twenty_unique_anchors_with_their_card_lines():
    """20 anchors, unique names and keys, none named like a creature, each with its roster section 5 card line."""
    assert len(ANCHORS) == 20 and len({a.name for a in ANCHORS}) == 20 and len({a.key for a in ANCHORS}) == 20
    assert collections.Counter(a.act for a in ANCHORS) == {act: 2 for act in range(10)}
    assert all(a.card_line.endswith(".") for a in ANCHORS)
    assert anchor_def(6, 0).radius == 49 and anchor_def(7, 0).radius == 51 and anchor_def(8, 0).radius == 47
    creatures = {"Driftling", "Spine Caste", "Divide Brood", "Rush Membrane", "Bulwark Seed", "Halo Drift",
                 "Burst Sac", "Hollow Echo", "Siphon Tick"}
    assert not {a.name for a in ANCHORS} & creatures


@pytest.mark.parametrize("act", range(10))
def test_anchors_keep_main_s_kit_phases_and_card(act):
    """Behaviour comes later: orbit, the layer's basic shot, the 6-way radial, main's mini phases; card unchanged."""
    for variant in (0, 1):
        m = Boss(Vector2(500, 500), act, None, miniboss=True, variant=variant)
        assert m.mover is boss_attacks.move_orbit and m.special.key == "anchor_radial"
        assert m.basic_shot.key == bosses.WARDENS[act].basic and m.phase_defs == bosses.mini_phases(act)
    (page,) = build_boss_intro_pages(act, miniboss=True)
    assert MINIBOSS_NAME in repr(page)                                  # the "Lattice Anchor" class card stays


@pytest.mark.parametrize("act", [-1, 10])
def test_acts_outside_the_table_keep_the_generic_lattice_anchor(act):
    """No anchor for unknown acts: main's name and 35 + 2 * act radius."""
    m = Boss(Vector2(500, 500), act, None, miniboss=True, variant=1)
    assert (m.anchor, m.name, m.size) == (None, MINIBOSS_NAME, 35 + 2 * act)


def test_wardens_are_not_anchors():
    """Only mini-bosses get an anchor; wardens ignore `variant`."""
    b = Boss(Vector2(500, 500), 3, None, variant=1)
    assert b.anchor is None and b.size == 80 and b.name == "Warden of Ash"


# --------------------------------------------------------------------------- selection

def test_the_pick_is_fixed_by_seed_act_and_node_and_uses_no_global_random():
    """Same inputs, same anchor, in any process; the global RNG is not touched."""
    random.seed(5)
    state = random.getstate()
    picks = [anchor_variant(seed, act, f"{r}_{c}", ["1_0", "2_1", "3_0"]) for seed in range(50) for act in range(10)
             for r, c in ((1, 0), (2, 1), (3, 0))]
    assert random.getstate() == state
    assert set(picks) == {0, 1}
    assert anchor_variant(12345, 4, "2_1", ["1_0", "2_1"]) == anchor_variant(12345, 4, "2_1", ["1_0", "2_1"])


def test_alternate_gives_both_anchors_once_a_layer_has_two_mini_nodes():
    """config.BOSS_ANCHOR_PICK "alternate": consecutive mini nodes take turns from a seeded start."""
    assert config.BOSS_ANCHOR_PICK == "alternate"
    starts = set()
    for seed in range(40):
        ids = ["2_0", "4_1", "5_2"]
        got = [anchor_variant(seed, 3, i, ids) for i in ids]
        assert got[0] != got[1] and got[1] != got[2]
        starts.add(got[0])
    assert starts == {0, 1}


def test_random_pick_is_per_node_and_stable():
    """"random": each node draws from its own seeded stream; both anchors occur."""
    got = [anchor_variant(seed, 2, "3_1", [], pick="random") for seed in range(60)]
    assert set(got) == {0, 1} and got == [anchor_variant(seed, 2, "3_1", [], pick="random") for seed in range(60)]


def _walk(ow: OverworldMap, rng: random.Random) -> list:
    """Play a random path through the map the way the game does (pick an available node, complete it); return the
    anchor each mini-boss node gets when its encounter loads, in visit order."""
    got = []
    while True:
        nodes = ow.get_available_nodes()
        if not nodes:
            return got
        n = rng.choice(nodes)
        ow.select_node(n.id)
        if n.node_type == NodeType.MINIBOSS:
            got.append(node_anchor_variant(ow, n))
        ow.complete_current_node()


def test_bug_158_anchors_alternate_in_visit_order_along_the_path():
    """Whatever path the player takes, consecutive mini-bosses of a layer alternate, from the layer's seeded start;
    any two mini-bosses on one path are both anchors (QA t50: map order gave both only 230/344 times)."""
    two_plus = 0
    for seed in range(60):
        for walk in range(3):
            ow = OverworldMap(act_index=2, seed=seed)
            got = _walk(ow, random.Random(seed * 10 + walk))
            assert all(a != b for a, b in zip(got, got[1:])), (seed, walk, got)
            if got:
                assert got[0] == anchor_variant(seed, 2, "", rank=0)
            two_plus += len(got) >= 2
    assert two_plus >= 30


def test_the_rank_counts_completed_mini_nodes_only():
    ow = OverworldMap(act_index=4, seed=7)
    minis = [n for n in ow.nodes.values() if n.node_type == NodeType.MINIBOSS]
    if len(minis) < 2:
        pytest.skip("map has fewer than two mini nodes")
    a, b = minis[:2]
    first = node_anchor_variant(ow, b)
    a.completed = True
    assert node_anchor_variant(ow, b) == 1 - first                      # one mini done -> the other anchor
    for n in ow.nodes.values():
        if n.node_type != NodeType.MINIBOSS:
            n.completed = True
    assert node_anchor_variant(ow, b) == 1 - first                      # other node types do not count


def test_a_map_rebuilt_from_its_dict_picks_the_same_anchors():
    """The pick reads only OverworldMap.to_dict fields (seed, act, node types, completed flags), so a map rebuilt with
    from_dict picks the same anchors and no key is added. (The game does not write the map today: a reload starts a new
    run; this keeps the pick safe if a mid-run save ever stores it.)"""
    for seed in (3, 99, 4242):
        ow = OverworldMap(act_index=5, seed=seed)
        _walk(ow, random.Random(seed)) if seed == 99 else None          # one map part-played (completed flags set)
        again = OverworldMap.from_dict(ow.to_dict())
        minis = [n for n in ow.nodes.values() if n.node_type == NodeType.MINIBOSS]
        assert [node_anchor_variant(ow, n) for n in minis] == [node_anchor_variant(again, again.nodes[n.id])
                                                                for n in minis]
        assert set(ow.to_dict()) == {"act_index", "seed", "encounter_rows", "num_layers", "current_node_id", "nodes"}


def test_a_mini_boss_node_spawns_its_picked_anchor(make_game):
    """Game._load_encounter on a mini-boss node spawns exactly one anchor: the one node_anchor_variant names."""
    g = make_game()
    g._start_new_run()
    for seed in range(8):
        ow = OverworldMap(act_index=6, seed=seed)
        minis = [n for n in ow.nodes.values() if n.node_type == NodeType.MINIBOSS]
        if not minis:
            continue
        g.overworld = ow
        g._load_encounter(minis[0])
        (m,) = [b for b in g.bosses if b.is_miniboss]
        assert m.anchor is anchor_def(6, node_anchor_variant(ow, minis[0])) and m.radius == 49
        return
    pytest.fail("no mini-boss node in 8 maps")


# --------------------------------------------------------------------------- BUG-159 / BUG-160

ROSTER_CARD_LINES = {
    "cradle_husk": "A husk of the nursery, still shaped like a hug.",
    "first_sprout": "The first thing the Rim ever grew. It has not moved since.",
    "sinking_bloat": "A mercy that swelled until it could not hold itself.",
    "green_mourner": "It weeps for names no one finished.",
    "glass_clerk": "It records everything that crosses the glass.",
    "unfinished_entry": "A Seedling that stopped halfway. It remembers your last step.",
    "cinder_anvil": "A shape forged to test the next shape.",
    "ember_runner": "It runs until there is nothing left to burn.",
    "rime_sentinel": "A guard who agreed to stay.",
    "drift_sleeper": "It slows you the way sleep does.",
    "oasis_lure": "The water you were promised.",
    "dry_maw": "What the mirage hides underneath.",
    "borrowed_face": "It wears the last shape it saw.",
    "pollen_sleeper": "A dream that learned to walk.",
    "quiet_hollow": "Nothing here wants to be remembered. This is how.",
    "forgotten_shape": "A form you already ended, returned without a name.",
    "updraft_herald": "It carries the verdict upward.",
    "verdict_pillar": "A judgment that no longer needs a judge.",
    "first_split": "The moment one became two.",
    "last_whole": "The last shape that stayed whole.",
}


def test_every_card_line_matches_the_roster_word_for_word():
    """BUG-159: roster section 5 card bodies, pinned exactly (a one-word edit fails)."""
    assert {a.key: a.card_line for a in ANCHORS} == ROSTER_CARD_LINES


def test_the_starting_anchor_depends_on_the_layer():
    """BUG-160: the alternation start is seeded by map seed AND act, so layers of one run do not all start alike."""
    mixed = sum(len({anchor_variant(seed, act, "", rank=0) for act in range(10)}) == 2 for seed in range(20))
    assert mixed >= 18
    assert {anchor_variant(seed, act, "", rank=0) for seed in range(20) for act in range(10)} == {0, 1}


@pytest.mark.parametrize("variant", [0, 1])
def test_the_game_spawns_the_picked_anchor_for_both_variants(make_game, variant):
    """BUG-159: Game._load_encounter spawns the anchor node_anchor_variant names, for maps where it is 0 and where it is 1
    (one map only hid a game that ignored or inverted the variant)."""
    g = make_game()
    g._start_new_run()
    for seed in range(40):
        ow = OverworldMap(act_index=6, seed=seed)
        minis = [n for n in ow.nodes.values() if n.node_type == NodeType.MINIBOSS]
        if not minis or node_anchor_variant(ow, minis[0]) != variant:
            continue
        g.overworld = ow
        g._load_encounter(minis[0])
        (m,) = [b for b in g.bosses if b.is_miniboss]
        assert m.anchor is anchor_def(6, variant) and m.name == anchor_def(6, variant).name
        return
    pytest.fail(f"no act 6 map in 40 seeds whose first mini node picks variant {variant}")
