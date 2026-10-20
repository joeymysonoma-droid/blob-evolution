"""BUG-260 (option c): every map has at least 1 shop, every start-to-boss path at least 1 rest; deterministic per seed."""

from __future__ import annotations

from typing import Dict

import pytest

from blob_evolution.systems.overworld import OverworldMap
from blob_evolution.utils.enums import NodeType

ACTS = range(10)
DEFAULT_SEEDS = range(300)    # x 10 layers = 3,000 maps, default run
SLOW_SEEDS = range(300, 2000)  # x 10 layers, `slow` run


def _paths_lacking(ow: OverworldMap, ntype: NodeType) -> int:
    """Count start-to-boss paths with no `ntype` node (exact, by DP over the layered graph)."""
    order = sorted(ow.nodes.values(), key=lambda n: -n.layer)
    lacking: Dict[str, int] = {}
    for node in order:
        if node.node_type == ntype:
            lacking[node.id] = 0
        elif node.node_type == NodeType.BOSS:
            lacking[node.id] = 1
        else:
            lacking[node.id] = sum(lacking[c] for c in node.connections)
    return lacking["n_0_0"]


def _total_paths(ow: OverworldMap) -> int:
    count: Dict[str, int] = {}
    for node in sorted(ow.nodes.values(), key=lambda n: -n.layer):
        count[node.id] = 1 if not node.connections else sum(count[c] for c in node.connections)
    return count["n_0_0"]


def _check(seeds: range) -> None:
    bad = []
    for act in ACTS:
        for seed in seeds:
            ow = OverworldMap(act_index=act, seed=seed)
            if not any(n.node_type == NodeType.SHOP for n in ow.nodes.values()):
                bad.append((act + 1, seed, "no shop on map"))
            lacking = _paths_lacking(ow, NodeType.REST)
            if lacking:
                bad.append((act + 1, seed, f"{lacking} paths without a rest"))
    assert not bad, f"(layer, seed, problem): {bad[:20]}"


def test_map_has_shop_and_every_path_has_rest() -> None:
    _check(DEFAULT_SEEDS)


@pytest.mark.slow
def test_map_has_shop_and_every_path_has_rest_sweep() -> None:
    _check(SLOW_SEEDS)


def test_lacking_counter_catches_a_missing_rest() -> None:
    """The DP isn't vacuous: stripping every rest leaves every path lacking one."""
    ow = OverworldMap(act_index=0, seed=1)
    total = _total_paths(ow)
    for node in ow.nodes.values():
        if node.node_type == NodeType.REST:
            node.node_type = NodeType.FIGHT
    assert total > 1
    assert _paths_lacking(ow, NodeType.REST) == total


def test_switches_off_skip_the_repairs(monkeypatch) -> None:
    """With both config switches off, some maps lack a shop and some paths lack a rest (the repairs are what fix it)."""
    from blob_evolution import config
    monkeypatch.setattr(config, "OVERWORLD_GUARANTEE_SHOP_PER_MAP", False)
    monkeypatch.setattr(config, "OVERWORLD_GUARANTEE_REST_PER_PATH", False)
    maps = [OverworldMap(act_index=0, seed=s) for s in range(200)]
    assert any(not any(n.node_type == NodeType.SHOP for n in ow.nodes.values()) for ow in maps)
    assert any(_paths_lacking(ow, NodeType.REST) for ow in maps)


def test_row_one_untouched() -> None:
    for seed in range(300):
        ow = OverworldMap(act_index=seed % 10, seed=seed)
        assert all(n.node_type in (NodeType.FIGHT, NodeType.EVENT) for n in ow.nodes.values() if n.layer == 1)


@pytest.mark.parametrize("act", [0, 4, 9])
def test_guarantee_is_deterministic_per_seed(act: int) -> None:
    for seed in range(50):
        a = OverworldMap(act_index=act, seed=seed).to_dict()
        b = OverworldMap(act_index=act, seed=seed).to_dict()
        assert a == b


def test_saved_map_keeps_its_types() -> None:
    """A saved map round-trips as saved; the repair runs only at generation, never on load."""
    ow = OverworldMap(act_index=2, seed=77)
    data = ow.to_dict()
    data["nodes"]["n_2_0"]["node_type"] = NodeType.FIGHT.value
    assert OverworldMap.from_dict(data).to_dict() == data
