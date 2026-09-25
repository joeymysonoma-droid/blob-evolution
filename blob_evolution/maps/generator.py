"""Map theme generation and level setup."""

from __future__ import annotations

import math
import random
from typing import List, Tuple

import pygame

from blob_evolution import config
from blob_evolution.entities.boss import Boss
from blob_evolution.entities.creature import Creature
from blob_evolution.utils.enums import CreatureType
from blob_evolution.utils.graphics import generate_map_texture
from blob_evolution.utils.vector2 import Vector2

# Act-weighted enemy pools: later acts unlock stranger forms
_ACT_WEIGHTS: List[List[Tuple[CreatureType, int]]] = [
    # 0 Rim
    [(CreatureType.BASIC, 50), (CreatureType.SHOOTER, 20), (CreatureType.CHARGER, 15),
     (CreatureType.SPLITTER, 10), (CreatureType.ORBITER, 5)],
    # 1 Rot
    [(CreatureType.BASIC, 30), (CreatureType.SHOOTER, 20), (CreatureType.SPLITTER, 20),
     (CreatureType.LEECH, 20), (CreatureType.BOMBER, 10)],
    # 2 Vaults
    [(CreatureType.SHOOTER, 25), (CreatureType.ORBITER, 25), (CreatureType.PHANTOM, 20),
     (CreatureType.BASIC, 20), (CreatureType.SHIELDER, 10)],
    # 3 Forge
    [(CreatureType.CHARGER, 30), (CreatureType.BOMBER, 25), (CreatureType.SHIELDER, 20),
     (CreatureType.SHOOTER, 15), (CreatureType.BASIC, 10)],
    # 4 Frost
    [(CreatureType.SHIELDER, 25), (CreatureType.SHOOTER, 25), (CreatureType.ORBITER, 20),
     (CreatureType.BASIC, 20), (CreatureType.PHANTOM, 10)],
    # 5 Mirage
    [(CreatureType.PHANTOM, 25), (CreatureType.ORBITER, 25), (CreatureType.LEECH, 20),
     (CreatureType.SHOOTER, 15), (CreatureType.BOMBER, 15)],
    # 6 Thicket
    [(CreatureType.SPLITTER, 25), (CreatureType.PHANTOM, 20), (CreatureType.LEECH, 20),
     (CreatureType.ORBITER, 20), (CreatureType.SHOOTER, 15)],
    # 7 Hollow
    [(CreatureType.PHANTOM, 30), (CreatureType.LEECH, 25), (CreatureType.BOMBER, 15),
     (CreatureType.CHARGER, 15), (CreatureType.SHIELDER, 15)],
    # 8 Strata
    [(CreatureType.ORBITER, 20), (CreatureType.SHIELDER, 20), (CreatureType.SHOOTER, 20),
     (CreatureType.PHANTOM, 15), (CreatureType.CHARGER, 15), (CreatureType.BOMBER, 10)],
    # 9 Divide
    [(CreatureType.BOMBER, 15), (CreatureType.PHANTOM, 15), (CreatureType.LEECH, 15),
     (CreatureType.SHIELDER, 15), (CreatureType.ORBITER, 15), (CreatureType.CHARGER, 15),
     (CreatureType.SPLITTER, 10)],
]


def _pick_type(rng: random.Random, weights: List[Tuple[CreatureType, int]]) -> CreatureType:
    roll = rng.randint(1, sum(w for _, w in weights))
    cumulative = 0
    for ctype, weight in weights:
        cumulative += weight
        if roll <= cumulative:
            return ctype
    return CreatureType.BASIC


class MapGenerator:
    """Generates map visuals and spawns entities."""

    def __init__(self) -> None:
        self.current_map_index = 0
        self.background: pygame.Surface | None = None
        self.theme: dict = config.MAP_THEMES[0]

    def load_map(self, map_index: int, seed: int | None = None) -> dict:
        """Load a map theme and generate background."""
        self.current_map_index = min(map_index, len(config.MAP_THEMES) - 1)
        self.theme = config.MAP_THEMES[self.current_map_index]
        if seed is None:
            seed = random.randint(0, 999999)
        self.background = generate_map_texture(
            config.WORLD_WIDTH, config.WORLD_HEIGHT,
            self.theme["color"], self.theme["accent"],
            seed, self.current_map_index,
        )
        return self.theme

    def _weights_for_act(self, elite: bool = False) -> List[Tuple[CreatureType, int]]:
        idx = min(self.current_map_index, len(_ACT_WEIGHTS) - 1)
        weights = list(_ACT_WEIGHTS[idx])
        if elite:
            # Bias toward dangerous types
            boost = {
                CreatureType.CHARGER: 20,
                CreatureType.BOMBER: 15,
                CreatureType.SHIELDER: 15,
                CreatureType.PHANTOM: 10,
                CreatureType.ORBITER: 10,
            }
            weights = [(ct, w + boost.get(ct, 0)) for ct, w in weights]
        return weights

    def spawn_creatures(self, diff_mult: dict, seed: int | None = None) -> List[Creature]:
        """Spawn creatures for current map."""
        rng = random.Random(seed)
        creatures: List[Creature] = []
        count = self.theme["creatures"]
        weights = self._weights_for_act()
        for _ in range(min(count, config.MAX_CREATURES)):
            pos = Vector2(
                rng.randint(100, config.WORLD_WIDTH - 100),
                rng.randint(100, config.WORLD_HEIGHT - 100),
            )
            ctype = _pick_type(rng, weights)
            size = rng.uniform(12, 25)
            hp_mult = 1.0 + self.current_map_index * 0.1
            creatures.append(Creature(pos, ctype, size, hp_mult, diff_mult))
        return creatures

    def spawn_encounter_creatures(
        self,
        count: int,
        diff_mult: dict,
        seed: int | None = None,
        elite: bool = False,
    ) -> List[Creature]:
        """Spawn a specific number of creatures for an overworld encounter."""
        rng = random.Random(seed)
        creatures: List[Creature] = []
        weights = self._weights_for_act(elite=elite)
        for _ in range(min(count, config.MAX_CREATURES)):
            pos = Vector2(
                rng.randint(100, config.WORLD_WIDTH - 100),
                rng.randint(100, config.WORLD_HEIGHT - 100),
            )
            ctype = _pick_type(rng, weights)
            size = rng.uniform(12, 28 if elite else 25)
            hp_mult = 1.0 + self.current_map_index * 0.1
            if elite:
                hp_mult *= 1.35
            creatures.append(Creature(pos, ctype, size, hp_mult, diff_mult))
        return creatures

    def spawn_bosses(self, diff_mult: dict, seed: int | None = None) -> List[Boss]:
        """Spawn bosses for current map."""
        rng = random.Random(seed)
        bosses: List[Boss] = []
        count = min(self.theme["bosses"], config.MAX_BOSSES)
        for i in range(count):
            angle = (i / max(1, count)) * math.tau
            dist = 400
            cx = config.WORLD_WIDTH // 2 + math.cos(angle) * dist
            cy = config.WORLD_HEIGHT // 2 + math.sin(angle) * dist
            pos = Vector2(
                rng.randint(int(max(100, cx - 200)), int(min(config.WORLD_WIDTH - 100, cx + 200))),
                rng.randint(int(max(100, cy - 200)), int(min(config.WORLD_HEIGHT - 100, cy + 200))),
            )
            bosses.append(Boss(pos, self.current_map_index + i, diff_mult))
        return bosses

    def draw_background(self, surface: pygame.Surface, camera: Vector2, shake: Vector2) -> None:
        """Draw map background with camera offset."""
        if not self.background:
            surface.fill(config.COLOR_BG)
            return
        cam_x = int(camera.x - config.SCREEN_WIDTH // 2 + shake.x)
        cam_y = int(camera.y - config.SCREEN_HEIGHT // 2 + shake.y)
        surface.blit(self.background, (-cam_x, -cam_y))

    @property
    def hazard_types(self) -> List[str]:
        """Hazard types for current map."""
        return self.theme.get("hazards", [])

    @property
    def map_name(self) -> str:
        """Current map name."""
        return self.theme["name"]
