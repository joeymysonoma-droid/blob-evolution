"""BUG-008: overworld nodes (boss ring included) stay clear of the header panel."""

from __future__ import annotations

import pytest

from blob_evolution import config
from blob_evolution.systems.overworld import OverworldMap

HEADER_BOTTOM = config.OVERWORLD_HEADER_RECT[1] + config.OVERWORLD_HEADER_RECT[3]
SEEDS = range(500)


def test_header_bottom_is_96() -> None:
    """The header rect in config still ends at y=96, the value BUG-008 was filed against."""
    assert HEADER_BOTTOM == 96


@pytest.mark.parametrize("act_index", range(len(config.MAP_THEMES)))
def test_node_rings_stay_below_header(act_index: int) -> None:
    """Across many seeds, the highest node's selected ring stays below the header."""
    for seed in SEEDS:
        ow = OverworldMap(act_index=act_index, seed=seed)
        top = min(node.screen_y for node in ow.nodes.values())
        assert top - config.OVERWORLD_NODE_TOP_REACH >= HEADER_BOTTOM, (act_index, seed, top)


def test_restored_map_keeps_layout() -> None:
    """from_dict re-runs the layout, so a loaded map is also clear of the header."""
    for seed in range(50):
        ow = OverworldMap.from_dict(OverworldMap(act_index=7, seed=seed).to_dict())
        top = min(node.screen_y for node in ow.nodes.values())
        assert top - config.OVERWORLD_NODE_TOP_REACH >= HEADER_BOTTOM, (seed, top)
