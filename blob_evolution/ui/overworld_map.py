"""Overworld map UI rendering."""

from __future__ import annotations

from typing import List, Optional, Set, Tuple

import pygame

from blob_evolution import config
from blob_evolution.data.lore import get_act_lore, wrap_text
from blob_evolution.systems.overworld import OverworldMap, OverworldNode
from blob_evolution.ui import style
from blob_evolution.utils.enums import NodeType
from blob_evolution.utils.graphics import draw_star


NODE_COLORS = {
    NodeType.START: (90, 190, 120),
    NodeType.FIGHT: (210, 85, 85),
    NodeType.ELITE: (255, 150, 60),
    NodeType.REST: (70, 190, 140),
    NodeType.EVENT: (170, 130, 255),
    NodeType.SHOP: (220, 190, 90),
    NodeType.BLACKSMITH: (200, 150, 90),
    NodeType.MINIBOSS: (230, 80, 180),
    NodeType.BOSS: (255, 60, 70),
}

NODE_ICONS = {
    NodeType.START: "S",
    NodeType.FIGHT: "F",
    NodeType.ELITE: "E",
    NodeType.REST: "R",
    NodeType.EVENT: "?",
    NodeType.SHOP: "$",
    NodeType.BLACKSMITH: "B",
    NodeType.MINIBOSS: "M",
    NodeType.BOSS: "X",
}


def star_center(x: int, y: int, radius: int) -> Tuple[int, int]:
    """Return the elite/miniboss star center for a node drawn at (x, y) with radius."""
    return x - radius - 22, y


class OverworldRenderer:
    """Renders the branching overworld map."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("segoeui", 14)
        self.font_large = pygame.font.SysFont("segoeui", 22, bold=True)
        self.font_small = pygame.font.SysFont("segoeui", 12)
        self.node_rects: List[Tuple[str, pygame.Rect]] = []  # draw order: later entries are on top
        self.available_ids: Set[str] = set()
        self.hovered_node: Optional[str] = None

    def draw(
        self,
        surface: pygame.Surface,
        overworld: OverworldMap,
        shards: int,
        essence: int,
        selected_node_id: Optional[str] = None,
    ) -> None:
        """Draw the full overworld map."""
        self.node_rects.clear()
        self.available_ids = {n.id for n in overworld.nodes.values() if n.available}
        theme = config.MAP_THEMES[overworld.act_index % len(config.MAP_THEMES)]
        style.draw_ambient_bg(surface, seed_offset=overworld.act_index, accent=theme["accent"])

        style.draw_stat_chip(surface, self.font, "Shards", str(shards), 80, config.SCREEN_HEIGHT - 48, style.SHARD)
        style.draw_stat_chip(
            surface, self.font, "Essence", str(essence),
            config.SCREEN_WIDTH - 200, config.SCREEN_HEIGHT - 48, style.ESSENCE,
        )

        # Draw connections under nodes
        for node in overworld.nodes.values():
            for conn_id in node.connections:
                target = overworld.nodes.get(conn_id)
                if target:
                    self._draw_connection(surface, node, target)

        # Selected node last so no neighbour paints over its ring
        sel = overworld.nodes.get(selected_node_id) if selected_node_id else None
        for node in overworld.nodes.values():
            if node is not sel:
                self._draw_node(surface, node, overworld.current_node_id, selected_node_id)
        if sel is not None:
            self._draw_node(surface, sel, overworld.current_node_id, selected_node_id)

        # Header after nodes so it always draws on top
        lore = get_act_lore(overworld.act_index)
        header = pygame.Rect(*config.OVERWORLD_HEADER_RECT)
        style.draw_panel(surface, header, alpha=200)

        title = self.font_large.render(
            f"Layer {overworld.act_index + 1}: {lore['lore_name']}", True, style.TEXT,
        )
        surface.blit(title, (config.SCREEN_WIDTH // 2 - title.get_width() // 2, 16))

        intro_lines = wrap_text(lore["intro"], self.font_small, config.SCREEN_WIDTH - 160)
        intro_y = 46
        for line in intro_lines[:2]:
            intro = self.font_small.render(line, True, style.TEXT_DIM)
            surface.blit(intro, (config.SCREEN_WIDTH // 2 - intro.get_width() // 2, intro_y))
            intro_y += 15

        rounds_text = self.font_small.render(
            f"{overworld.encounter_rows} encounters to {lore['warden']}", True, style.TEXT_MUTED,
        )
        surface.blit(rounds_text, (config.SCREEN_WIDTH // 2 - rounds_text.get_width() // 2, intro_y + 2))

        style.draw_hint(
            surface, self.font_small,
            "Click a glowing node to travel  ·  WASD / Arrows + SPACE",
            y=config.SCREEN_HEIGHT - 22,
        )

    def _draw_connection(self, surface: pygame.Surface, a: OverworldNode, b: OverworldNode) -> None:
        """Draw path line between nodes."""
        ax, ay = int(a.screen_x), int(a.screen_y)
        bx, by = int(b.screen_x), int(b.screen_y)
        if a.completed and b.available:
            color = (70, 140, 100)
            width = 3
        elif a.completed and b.completed:
            color = (40, 55, 70)
            width = 2
        elif a.available or b.available:
            color = (55, 70, 90)
            width = 2
        else:
            color = (35, 45, 60)
            width = 1

        pygame.draw.line(surface, color, (ax, ay), (bx, by), width)
        if a.completed and b.available:
            mx, my = (ax + bx) // 2, (ay + by) // 2
            pulse_r = 3 + int(style.pulse(3.0, 0, 2))
            pygame.draw.circle(surface, (100, 200, 140), (mx, my), pulse_r)

    def _draw_node(
        self,
        surface: pygame.Surface,
        node: OverworldNode,
        current_id: Optional[str],
        selected_id: Optional[str] = None,
    ) -> None:
        """Draw a single map node."""
        x, y = int(node.screen_x), int(node.screen_y)
        radius = 16 if node.node_type not in (NodeType.BOSS, NodeType.MINIBOSS) else 22
        base_color = NODE_COLORS.get(node.node_type, (150, 150, 150))

        if node.completed:
            color = tuple(c // 2 for c in base_color)
            alpha = 140
        elif node.available:
            color = base_color
            alpha = 255
        else:
            color = tuple(max(20, c // 3) for c in base_color)
            alpha = 90

        # Outer rings for current / selected / available
        if node.id == current_id:
            pygame.draw.circle(surface, (255, 255, 210), (x, y), radius + 8, 2)
        elif node.available and node.id == selected_id:
            ring = 5 + int(style.pulse(4.0, 0, 3))
            pygame.draw.circle(surface, style.SELECT, (x, y), radius + ring, 2)
            pygame.draw.circle(surface, style.SELECT, (x, y), radius + ring + 3, 1)
        elif node.available:
            pygame.draw.circle(surface, style.lerp_color(color, (255, 255, 255), 0.3), (x, y), radius + 4, 1)

        # Soft glow for available nodes
        if node.available and not node.completed:
            glow = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*color, 45), (radius * 2, radius * 2), radius * 2)
            surface.blit(glow, (x - radius * 2, y - radius * 2))

        node_surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
        cx = radius + 2
        pygame.draw.circle(node_surf, (*color, alpha), (cx, cx), radius)
        pygame.draw.circle(node_surf, (255, 255, 255, 40 if node.available else 15), (cx - radius // 3, cx - radius // 3), max(2, radius // 4))
        if node.available:
            pygame.draw.circle(node_surf, (*color, 220), (cx, cx), radius, 2)
        surface.blit(node_surf, (x - radius - 2, y - radius - 2))

        icon = NODE_ICONS.get(node.node_type, "?")
        icon_text = self.font.render(icon, True, (255, 255, 255))
        surface.blit(icon_text, (x - icon_text.get_width() // 2, y - icon_text.get_height() // 2))

        if node.is_elite_marked and not node.completed:
            sx, sy = star_center(x, y, radius)
            draw_star(surface, (sx, sy), 8, 3.6, style.BG_DEEP)  # dark backing, (8,14,24)
            draw_star(surface, (sx, sy), 6, 2.6, style.SELECT)  # (255,214,110)

        if node.available or node.completed:
            label_color = style.TEXT if node.available else style.TEXT_DIM
            label = self.font_small.render(node.label, True, label_color)
            lx = x + radius + 16
            ly = y - label.get_height() // 2
            plate = pygame.Rect(lx - 4, ly - 1, label.get_width() + 8, label.get_height() + 2)
            style.draw_panel(surface, plate, fill=style.BG_DEEP, edge=style.BG_DEEP, radius=4, alpha=200)
            surface.blit(label, (lx, ly))

        rect = pygame.Rect(x - radius - 6, y - radius - 6, radius * 2 + 12, radius * 2 + 12)
        self.node_rects.append((node.id, rect))

    def hit_test(self, pos: tuple) -> Optional[str]:
        """Return the node at pos: available nodes win overlaps, then the one drawn on top."""
        hits = [
            (nid in self.available_ids, i, nid)  # i = draw order, so a higher i is on top
            for i, (nid, rect) in enumerate(self.node_rects)
            if rect.collidepoint(pos)
        ]
        return max(hits)[2] if hits else None

    def get_available_index(self, overworld: OverworldMap, selected: int) -> Optional[str]:
        """Get node id by selection index among available nodes."""
        available = overworld.get_available_nodes()
        if not available:
            return None
        available.sort(key=lambda n: (n.layer, n.col))
        return available[selected % len(available)].id
