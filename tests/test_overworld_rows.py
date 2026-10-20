"""TASK-069: every layer has OVERWORLD_MIN_ROWS..MAX_ROWS (6-8) encounter rows; maps stay well formed; old maps load."""
from __future__ import annotations

from collections import Counter

import pytest

from blob_evolution import config
from blob_evolution.systems.overworld import OverworldMap
from blob_evolution.utils.enums import NodeType

SEEDS = range(600)
ACTS = range(len(config.MAP_THEMES))


def _reachable(ow: OverworldMap, start: str) -> set:
    """Node ids reachable from start along connections."""
    seen, todo = {start}, [start]
    while todo:
        for nxt in ow.nodes[todo.pop()].connections:
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def test_row_counts_stay_6_to_8_over_many_seeds():
    """6000 maps (600 seeds x 10 layers): rows in 6..8, and each of 6, 7, 8 occurs."""
    counts = Counter(OverworldMap(act, seed).encounter_rows for act in ACTS for seed in SEEDS)
    assert set(counts) == {6, 7, 8}
    assert min(counts.values()) > 1500


@pytest.mark.parametrize("act", ACTS)
def test_boss_and_start_placement_valid(act):
    """One start at layer 0, one boss at rows+1 (last layer), every node on a start-to-boss path."""
    for seed in range(150):
        ow = OverworldMap(act, seed)
        boss = [n for n in ow.nodes.values() if n.node_type == NodeType.BOSS]
        start = [n for n in ow.nodes.values() if n.node_type == NodeType.START]
        assert len(boss) == 1 and len(start) == 1
        assert boss[0].layer == ow.encounter_rows + 1 == ow.num_layers - 1
        assert start[0].layer == 0 and not boss[0].connections
        reach = _reachable(ow, start[0].id)
        assert reach == set(ow.nodes)
        for nid in ow.nodes:
            assert boss[0].id in _reachable(ow, nid)
        layers = Counter(n.layer for n in ow.nodes.values())
        assert all(2 <= layers[r] <= 4 for r in range(1, ow.encounter_rows + 1))
        assert all(n.node_type in (NodeType.FIGHT, NodeType.EVENT) for n in ow.nodes.values() if n.layer == 1)


def test_map_rows_follow_config():
    """The module aliases read the config constants."""
    from blob_evolution.systems import overworld
    assert (overworld.MIN_ROUNDS, overworld.MAX_ROUNDS) == (config.OVERWORLD_MIN_ROWS, config.OVERWORLD_MAX_ROWS) == (6, 8)


def _old_11_row_map() -> dict:
    """A map as main generated it (8-11 rows): an 11-row layout written out with to_dict."""
    ow = OverworldMap(0, 1)
    for nid in list(ow.nodes):
        del ow.nodes[nid]
    from blob_evolution.systems.overworld import OverworldNode
    rows = 11
    prev = ["n_0_0"]
    ow.nodes["n_0_0"] = OverworldNode("n_0_0", NodeType.START, 0, 0, completed=True)
    for r in range(1, rows + 1):
        cur = [f"n_{r}_{c}" for c in range(3)]
        for c, nid in enumerate(cur):
            ow.nodes[nid] = OverworldNode(nid, NodeType.FIGHT, r, c)
        for p in prev:
            ow.nodes[p].connections = list(cur)
        prev = cur
    ow.nodes[f"n_{rows + 1}_0"] = OverworldNode(f"n_{rows + 1}_0", NodeType.BOSS, rows + 1, 0)
    for p in prev:
        ow.nodes[p].connections = [f"n_{rows + 1}_0"]
    ow.encounter_rows, ow.num_layers, ow.current_node_id = rows, rows + 2, "n_3_1"
    return ow.to_dict()


def test_in_progress_old_map_still_loads():
    """An 11-row map saved mid-layer reloads with all 11 rows, its position and its boss."""
    data = _old_11_row_map()
    ow = OverworldMap.from_dict(data)
    assert ow.encounter_rows == 11 and ow.num_layers == 13 and ow.current_node_id == "n_3_1"
    assert ow.to_dict() == data
    assert ow.nodes["n_12_0"].node_type == NodeType.BOSS


def test_old_map_without_rows_key_keeps_main_default():
    """A saved map with no encounter_rows key reads 8, as on main (not the new minimum)."""
    data = _old_11_row_map()
    del data["encounter_rows"], data["num_layers"]
    assert OverworldMap.from_dict(data).encounter_rows == 8
