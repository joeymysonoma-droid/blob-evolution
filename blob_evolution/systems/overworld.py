"""Branching overworld map generation and navigation."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from blob_evolution.utils.enums import NodeType

MIN_ROUNDS = 8
MAX_ROUNDS = 11


@dataclass
class OverworldNode:
    """A single node on the branching map."""

    id: str
    node_type: NodeType
    layer: int
    col: int
    screen_x: float = 0.0
    screen_y: float = 0.0
    connections: List[str] = field(default_factory=list)
    completed: bool = False
    available: bool = False
    is_elite_marked: bool = False

    @property
    def label(self) -> str:
        """Display label for node type."""
        labels = {
            NodeType.START: "Start",
            NodeType.FIGHT: "Fight",
            NodeType.ELITE: "Elite",
            NodeType.REST: "Rest",
            NodeType.EVENT: "Event",
            NodeType.SHOP: "Shop",
            NodeType.BLACKSMITH: "Blacksmith",
            NodeType.MINIBOSS: "Mini Boss",
            NodeType.BOSS: "Boss",
        }
        return labels.get(self.node_type, "?")


class OverworldMap:
    """Branching path map: start fans to 3-4 paths, converges at boss after 8-11 rounds."""

    def __init__(self, act_index: int = 0, seed: Optional[int] = None) -> None:
        self.act_index = act_index
        self.seed = seed if seed is not None else random.randint(0, 999999)
        self.nodes: Dict[str, OverworldNode] = {}
        self.current_node_id: Optional[str] = None
        self.encounter_rows = MIN_ROUNDS
        self.num_layers = MIN_ROUNDS + 2
        self._generate()

    def _generate(self) -> None:
        """Generate STS-style branching map."""
        rng = random.Random(self.seed)
        self.encounter_rows = rng.randint(MIN_ROUNDS, MAX_ROUNDS)
        boss_layer = self.encounter_rows + 1
        self.num_layers = boss_layer + 1

        layers: List[List[str]] = []
        widths = self._compute_widths(self.encounter_rows, rng)

        # Layer 0: start
        start_id = "n_0_0"
        self.nodes[start_id] = OverworldNode(start_id, NodeType.START, 0, 0)
        layers.append([start_id])

        # Encounter layers 1..encounter_rows
        for row in range(1, self.encounter_rows + 1):
            width = widths[row - 1]
            layer_ids: List[str] = []
            for col in range(width):
                nid = f"n_{row}_{col}"
                ntype = self._assign_node_type(row, self.encounter_rows, rng)
                node = OverworldNode(nid, ntype, row, col)
                if ntype in (NodeType.ELITE, NodeType.MINIBOSS):
                    node.is_elite_marked = True
                self.nodes[nid] = node
                layer_ids.append(nid)
            layers.append(layer_ids)

        # Boss layer (single node, all paths converge)
        boss_id = f"n_{boss_layer}_0"
        self.nodes[boss_id] = OverworldNode(boss_id, NodeType.BOSS, boss_layer, 0)
        layers.append([boss_id])

        # Connect consecutive layers
        for i in range(len(layers) - 1):
            self._connect_layers(layers[i], layers[i + 1], rng)

        self._layout_nodes(layers)
        self.current_node_id = start_id
        self.nodes[start_id].completed = True
        self._update_availability()

    def _compute_widths(self, encounter_rows: int, rng: random.Random) -> List[int]:
        """Compute node count per encounter row — fans out 3-4, then converges."""
        widths: List[int] = [rng.randint(3, 4)]

        for i in range(1, encounter_rows - 1):
            prev = widths[-1]
            progress = i / max(1, encounter_rows - 1)
            if progress < 0.4:
                w = min(4, max(3, prev + rng.choice([-1, 0, 1])))
            elif progress < 0.7:
                w = max(2, min(4, prev + rng.choice([-1, 0, 1])))
            else:
                w = max(2, prev - rng.choice([0, 1]))
            widths.append(w)

        if encounter_rows > 1:
            widths.append(rng.randint(2, 3))

        return widths

    def _connect_layers(
        self, prev_ids: List[str], next_ids: List[str], rng: random.Random,
    ) -> None:
        """Connect nodes between two layers with STS-style pathing."""
        n_prev = len(prev_ids)
        n_next = len(next_ids)

        for pi, prev_id in enumerate(prev_ids):
            if n_next == 1:
                self.nodes[prev_id].connections.append(next_ids[0])
                continue

            if n_prev == 1:
                for next_id in next_ids:
                    self.nodes[prev_id].connections.append(next_id)
                continue

            center = int(pi / max(1, n_prev - 1) * (n_next - 1))
            targets: Set[int] = {center}
            if center > 0:
                targets.add(center - 1)
            if center < n_next - 1:
                targets.add(center + 1)
            if rng.random() < 0.3 and len(targets) < n_next:
                extra = rng.randint(0, n_next - 1)
                targets.add(extra)

            for tc in sorted(targets):
                conn = next_ids[tc]
                if conn not in self.nodes[prev_id].connections:
                    self.nodes[prev_id].connections.append(conn)

        for ni, next_id in enumerate(next_ids):
            has_incoming = any(
                next_id in self.nodes[p].connections for p in prev_ids
            )
            if not has_incoming:
                pi = int(ni / max(1, n_next - 1) * (n_prev - 1)) if n_next > 1 else 0
                pi = min(pi, n_prev - 1)
                if next_id not in self.nodes[prev_ids[pi]].connections:
                    self.nodes[prev_ids[pi]].connections.append(next_id)

    def _assign_node_type(self, row: int, total_rows: int, rng: random.Random) -> NodeType:
        """Assign node type based on position in the path."""
        progress = row / total_rows
        roll = rng.random()

        if row == 1:
            return NodeType.FIGHT if roll < 0.85 else NodeType.EVENT

        if progress < 0.25:
            if roll < 0.55:
                return NodeType.FIGHT
            if roll < 0.70:
                return NodeType.EVENT
            if roll < 0.82:
                return NodeType.REST
            return NodeType.SHOP

        if progress < 0.55:
            if roll < 0.30:
                return NodeType.FIGHT
            if roll < 0.45:
                return NodeType.ELITE
            if roll < 0.58:
                return NodeType.EVENT
            if roll < 0.70:
                return NodeType.SHOP
            if roll < 0.80:
                return NodeType.REST
            if roll < 0.90:
                return NodeType.BLACKSMITH
            return NodeType.MINIBOSS

        if progress < 0.80:
            if roll < 0.25:
                return NodeType.ELITE
            if roll < 0.42:
                return NodeType.MINIBOSS
            if roll < 0.58:
                return NodeType.FIGHT
            if roll < 0.72:
                return NodeType.BLACKSMITH
            if roll < 0.85:
                return NodeType.REST
            return NodeType.EVENT

        # Last few rows before boss
        if roll < 0.30:
            return NodeType.ELITE
        if roll < 0.50:
            return NodeType.MINIBOSS
        if roll < 0.68:
            return NodeType.FIGHT
        if roll < 0.82:
            return NodeType.REST
        return NodeType.EVENT

    def _layout_nodes(self, layers: List[List[str]]) -> None:
        """Assign screen positions for drawing."""
        from blob_evolution import config
        map_top = config.OVERWORLD_MAP_TOP
        map_bottom = config.OVERWORLD_MAP_BOTTOM
        num_layers = len(layers)
        layer_height = (map_bottom - map_top) / max(1, num_layers - 1)

        for layer_idx, layer_ids in enumerate(layers):
            count = len(layer_ids)
            y = map_bottom - layer_idx * layer_height
            for i, nid in enumerate(layer_ids):
                x_spacing = config.SCREEN_WIDTH / (count + 1)
                x = x_spacing * (i + 1)
                self.nodes[nid].screen_x = x
                self.nodes[nid].screen_y = y

    def _update_availability(self) -> None:
        """Mark nodes reachable from current position."""
        for node in self.nodes.values():
            node.available = False
        if not self.current_node_id:
            return
        current = self.nodes[self.current_node_id]
        for conn_id in current.connections:
            conn = self.nodes.get(conn_id)
            if conn and not conn.completed:
                conn.available = True

    def get_path_length_to_boss(self) -> int:
        """Return min/max steps from start to boss for debug."""
        return self.encounter_rows

    def get_available_nodes(self) -> List[OverworldNode]:
        """Return nodes the player can travel to."""
        return [n for n in self.nodes.values() if n.available]

    def select_node(self, node_id: str) -> Optional[OverworldNode]:
        """Move to a node. Returns node if valid."""
        if node_id not in self.nodes:
            return None
        node = self.nodes[node_id]
        if not node.available:
            return None
        self.current_node_id = node_id
        return node

    def complete_current_node(self) -> Optional[OverworldNode]:
        """Mark current node done and unlock next paths."""
        if not self.current_node_id:
            return None
        node = self.nodes[self.current_node_id]
        node.completed = True
        node.available = False
        self._update_availability()
        return node

    def is_boss_defeated(self) -> bool:
        """Check if the boss node is completed."""
        for node in self.nodes.values():
            if node.node_type == NodeType.BOSS and node.completed:
                return True
        return False

    def get_encounter_params(self, node: OverworldNode) -> dict:
        """Return spawn parameters for a node type."""
        act = self.act_index
        base_creatures = 12 + act * 2
        params = {
            "creatures": base_creatures,
            "bosses": 0,
            "minibosses": 0,
            "hp_mult": 1.0 + act * 0.08,
            "elite": False,
            "shard_reward": 3,
        }
        if node.node_type == NodeType.FIGHT:
            params["creatures"] = base_creatures + 5
            params["shard_reward"] = 3
        elif node.node_type == NodeType.ELITE:
            params["creatures"] = int(base_creatures * 1.4) + 8
            params["hp_mult"] *= 1.5
            params["elite"] = True
            params["shard_reward"] = 6
        elif node.node_type == NodeType.MINIBOSS:
            params["creatures"] = base_creatures // 2
            params["minibosses"] = 1
            params["hp_mult"] *= 1.3
            params["shard_reward"] = 10
        elif node.node_type == NodeType.BOSS:
            params["creatures"] = base_creatures // 3
            params["bosses"] = 1
            params["hp_mult"] *= 2.0
            params["shard_reward"] = 20
        return params

    def to_dict(self) -> dict:
        """Serialize overworld state."""
        return {
            "act_index": self.act_index,
            "seed": self.seed,
            "encounter_rows": self.encounter_rows,
            "num_layers": self.num_layers,
            "current_node_id": self.current_node_id,
            "nodes": {
                nid: {
                    "node_type": n.node_type.value,
                    "layer": n.layer,
                    "col": n.col,
                    "connections": n.connections,
                    "completed": n.completed,
                    "available": n.available,
                    "is_elite_marked": n.is_elite_marked,
                }
                for nid, n in self.nodes.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OverworldMap":
        """Restore overworld from save data."""
        ow = cls.__new__(cls)
        ow.act_index = data["act_index"]
        ow.seed = data["seed"]
        ow.encounter_rows = data.get("encounter_rows", MIN_ROUNDS)
        ow.num_layers = data.get("num_layers", ow.encounter_rows + 2)
        ow.nodes = {}
        ow.current_node_id = data["current_node_id"]
        for nid, ndata in data["nodes"].items():
            node = OverworldNode(
                nid,
                NodeType(ndata["node_type"]),
                ndata["layer"],
                ndata["col"],
                connections=ndata["connections"],
                completed=ndata["completed"],
                available=ndata["available"],
                is_elite_marked=ndata.get("is_elite_marked", False),
            )
            ow.nodes[nid] = node
        layers_dict: Dict[int, List[str]] = {}
        for nid, n in ow.nodes.items():
            layers_dict.setdefault(n.layer, []).append(nid)
        for layer_nodes in layers_dict.values():
            layer_nodes.sort(key=lambda x: ow.nodes[x].col)
        max_layer = max(layers_dict.keys()) if layers_dict else 0
        layer_list = [layers_dict.get(i, []) for i in range(max_layer + 1)]
        ow._layout_nodes(layer_list)
        return ow
