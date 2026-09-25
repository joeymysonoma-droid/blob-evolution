"""In-game HUD and overlays."""

from __future__ import annotations

from typing import List, Tuple

import pygame

from blob_evolution import config
from blob_evolution.entities.boss import Boss
from blob_evolution.entities.creature import Creature
from blob_evolution.entities.pickups import XPOrb
from blob_evolution.entities.player import Player
from blob_evolution.systems.hazards import HazardManager
from blob_evolution.ui import style
from blob_evolution.utils.graphics import draw_health_bar
from blob_evolution.utils.vector2 import Vector2


def skills_overlay_layout(count: int) -> Tuple[pygame.Rect, List[pygame.Rect]]:
    """Return the TAB skills panel and one row rect per skill (rows shrink to fit)."""
    panel = pygame.Rect(config.SCREEN_WIDTH // 2 - 320, 50, 640, 680)
    start_y = panel.y + 90  # 140
    list_bottom = panel.bottom - 48  # 682, 12px above the Evolution label at 694
    pitch = min(60, (list_bottom - start_y + 6) // max(1, count))  # 60 for 9 skills
    row_h = pitch - 6  # 54
    rows = [pygame.Rect(panel.x + 28, start_y + i * pitch, panel.width - 56, row_h) for i in range(count)]
    return panel, rows


class HUD:
    """Renders in-game HUD elements."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("segoeui", 15)
        self.font_large = pygame.font.SysFont("segoeui", 20, bold=True)
        self.font_small = pygame.font.SysFont("segoeui", 13)
        self.show_minimap = True
        self.show_fps = False
        self.notification = ""
        self.notification_timer = 0.0
        self.shop_item_rects: list = []

    def show_notification(self, text: str, duration: float = 2.0) -> None:
        """Show temporary notification."""
        self.notification = text
        self.notification_timer = duration

    def update(self, dt: float) -> None:
        """Update notification timer."""
        if self.notification_timer > 0:
            self.notification_timer -= dt

    def draw(
        self,
        surface: pygame.Surface,
        player: Player,
        creatures: List[Creature],
        bosses: List[Boss],
        xp_orbs: List[XPOrb],
        hazards: HazardManager,
        camera: Vector2,
        fps: float,
        map_name: str,
        essence: int,
    ) -> None:
        """Draw full HUD."""
        self._draw_health_bar(surface, player)
        self._draw_xp_bar(surface, player)
        self._draw_stats(surface, player, map_name, essence)
        if self.show_minimap:
            self._draw_minimap(surface, player, creatures, bosses, hazards)
        if self.show_fps:
            fps_text = self.font_small.render(f"FPS: {int(fps)}", True, style.TEXT_MUTED)
            surface.blit(fps_text, (config.SCREEN_WIDTH - 80, 5))
        if self.notification_timer > 0:
            notif = self.font_large.render(self.notification, True, style.SELECT)
            rect = notif.get_rect(center=(config.SCREEN_WIDTH // 2, 56))
            bg = rect.inflate(28, 14)
            style.draw_panel(surface, bg, radius=8, alpha=200)
            surface.blit(notif, rect)

    def draw_skills_overlay(self, surface: pygame.Surface, player: Player) -> None:
        """Draw skills upgrade menu."""
        overlay = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((4, 8, 16, 190))
        surface.blit(overlay, (0, 0))

        skills = player.skills.get_all_skills()
        panel, rows = skills_overlay_layout(len(skills))
        style.draw_panel(surface, panel, alpha=235)

        title = self.font_large.render("SKILLS", True, style.TEXT)
        surface.blit(title, (panel.centerx - title.get_width() // 2, panel.y + 20))
        points_text = self.font.render(
            f"Skill Points: {player.skill_points}   ·   TAB to close   ·   1–9 to upgrade",
            True, style.SELECT,
        )
        surface.blit(points_text, (panel.centerx - points_text.get_width() // 2, panel.y + 52))

        for i, (skill, row) in enumerate(zip(skills, rows)):
            can_upgrade = player.skills.can_upgrade(skill["key"], player.skill_points)
            edge = style.PANEL_EDGE_HOT if can_upgrade else style.PANEL_EDGE
            style.draw_panel(surface, row, edge=edge, radius=8, alpha=180)
            color = style.ACCENT if can_upgrade else style.TEXT
            key_text = self.font.render(
                f"[{i + 1}]  {skill['name']}   Lv.{skill['level']}/{skill['max_level']}",
                True, color,
            )
            surface.blit(key_text, (row.x + 16, row.y + 8))
            desc = self.font_small.render(skill["description"], True, style.TEXT_DIM)
            surface.blit(desc, (row.x + 16, row.y + 31))
            cost_text = self.font_small.render(f"{skill['cost']} SP", True, style.SELECT_DIM)
            surface.blit(cost_text, (row.right - cost_text.get_width() - 16, row.y + 10))

        evo_text = self.font_small.render(
            f"Evolution: {player.evolution.current_form}", True, style.ESSENCE,
        )
        surface.blit(evo_text, (panel.centerx - evo_text.get_width() // 2, panel.bottom - 36))

    def draw_shop_overlay(self, surface: pygame.Surface, player: Player, essence: int, selected: int) -> None:
        """Draw between-level shop."""
        overlay = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((4, 8, 16, 200))
        surface.blit(overlay, (0, 0))

        panel = pygame.Rect(config.SCREEN_WIDTH // 2 - 300, 40, 600, 700)
        style.draw_panel(surface, panel, alpha=235)

        title = self.font_large.render("SHOP", True, style.ESSENCE)
        surface.blit(title, (panel.centerx - title.get_width() // 2, panel.y + 20))
        essence_text = self.font.render(f"Essence: {essence}", True, style.ESSENCE)
        surface.blit(essence_text, (panel.centerx - essence_text.get_width() // 2, panel.y + 52))

        from blob_evolution.systems.economy import SHOP_ITEMS
        self.shop_item_rects.clear()
        start_y = panel.y + 90
        row_height = 52
        for i, item in enumerate(SHOP_ITEMS):
            y = start_y + i * row_height
            row = pygame.Rect(panel.x + 30, y, panel.width - 60, 46)
            if i == selected:
                style.draw_panel(surface, row, edge=style.SELECT, radius=8, alpha=200)
            color = style.SELECT if i == selected else style.TEXT
            text = self.font.render(f"{item['name']}  —  {item['cost']} essence", True, color)
            surface.blit(text, (row.x + 14, row.y + 6))
            desc = self.font_small.render(item["description"], True, style.TEXT_MUTED)
            surface.blit(desc, (row.x + 14, row.y + 26))
            self.shop_item_rects.append(row)

        continue_idx = len(SHOP_ITEMS)
        y = start_y + continue_idx * row_height + 12
        row = pygame.Rect(panel.x + 30, y, panel.width - 60, 46)
        if selected == continue_idx:
            style.draw_panel(surface, row, edge=style.ACCENT, radius=8, alpha=200)
        color = style.ACCENT if selected == continue_idx else style.TEXT
        continue_text = self.font.render("Return to Overworld", True, color)
        surface.blit(continue_text, (row.x + 14, row.y + 12))
        self.shop_item_rects.append(row)

        hint = self.font_small.render(
            "WASD navigate  ·  SPACE buy/continue  ·  ENTER or ESC to leave", True, style.TEXT_MUTED,
        )
        surface.blit(hint, (panel.centerx - hint.get_width() // 2, panel.bottom - 36))

    def hit_test_shop(self, pos: tuple) -> int | None:
        """Return shop item index at screen position."""
        for i, rect in enumerate(self.shop_item_rects):
            if rect.collidepoint(pos):
                return i
        return None

    def _draw_health_bar(self, surface: pygame.Surface, player: Player) -> None:
        """Draw player health bar."""
        bar_width = 260
        bar_height = 18
        x, y = 18, 16
        frame = pygame.Rect(x - 6, y - 6, bar_width + 12, 58)
        style.draw_panel(surface, frame, radius=8, alpha=180)
        draw_health_bar(surface, x, y, bar_width, bar_height, player.hp, player.max_hp)
        hp_text = self.font_small.render(f"{int(player.hp)}/{int(player.max_hp)}", True, style.TEXT)
        surface.blit(hp_text, (x + 6, y + 1))

    def _draw_xp_bar(self, surface: pygame.Surface, player: Player) -> None:
        """Draw XP progress bar."""
        bar_width = 260
        bar_height = 10
        x, y = 18, 42
        ratio = player.xp / player.xp_to_next if player.xp_to_next > 0 else 0
        pygame.draw.rect(surface, config.COLOR_HEALTH_BG, (x, y, bar_width, bar_height), border_radius=4)
        fill = int(bar_width * ratio)
        if fill > 0:
            pygame.draw.rect(surface, config.COLOR_XP_BAR, (x, y, fill, bar_height), border_radius=4)
        pygame.draw.rect(surface, style.PANEL_EDGE, (x, y, bar_width, bar_height), 1, border_radius=4)
        level_text = self.font.render(f"Lv.{player.level}", True, style.TEXT)
        surface.blit(level_text, (x + bar_width + 14, y - 4))

    def _draw_stats(self, surface: pygame.Surface, player: Player, map_name: str, essence: int) -> None:
        """Draw stat readouts."""
        y = 78
        chips = [
            ("SP", str(player.skill_points), style.SELECT),
            ("Kills", str(player.kills), style.DANGER),
            ("Essence", str(essence), style.ESSENCE),
        ]
        x = 18
        for label, value, accent in chips:
            w = style.draw_stat_chip(surface, self.font_small, label, value, x, y, accent)
            x += w + 8

        map_text = self.font_small.render(map_name, True, style.TEXT_DIM)
        surface.blit(map_text, (18, y + 32))

        if player.artifacts.collected:
            art_text = self.font_small.render(
                f"Artifacts: {len(player.artifacts.collected)}", True, style.ESSENCE,
            )
            surface.blit(art_text, (18, y + 50))

    def _draw_minimap(
        self,
        surface: pygame.Surface,
        player: Player,
        creatures: List[Creature],
        bosses: List[Boss],
        hazards: HazardManager,
    ) -> None:
        """Draw minimap in corner."""
        size = config.MINIMAP_SIZE
        padding = config.MINIMAP_PADDING
        x = config.SCREEN_WIDTH - size - padding
        y = padding
        scale = size / config.WORLD_WIDTH

        frame = pygame.Rect(x - 4, y - 4, size + 8, size + 8)
        style.draw_panel(surface, frame, radius=6, alpha=200)
        pygame.draw.rect(surface, (16, 22, 34), (x, y, size, size))

        hazards.draw_minimap(surface, (x, y), scale)

        for creature in creatures:
            if creature.active:
                cx = int(x + creature.pos.x * scale)
                cy = int(y + creature.pos.y * scale)
                pygame.draw.circle(surface, (200, 70, 70), (cx, cy), 2)

        for boss in bosses:
            if boss.active:
                bx = int(x + boss.pos.x * scale)
                by = int(y + boss.pos.y * scale)
                pygame.draw.circle(surface, (255, 70, 70), (bx, by), 4)
                pygame.draw.circle(surface, (255, 180, 180), (bx, by), 6, 1)

        px = int(x + player.pos.x * scale)
        py = int(y + player.pos.y * scale)
        pygame.draw.circle(surface, style.ACCENT, (px, py), 3)
        pygame.draw.circle(surface, (200, 255, 210), (px, py), 5, 1)
