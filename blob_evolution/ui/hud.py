"""In-game HUD and overlays."""

from __future__ import annotations

import re
from collections import deque
from typing import Deque, List, Tuple

import pygame

from blob_evolution import config
from blob_evolution.data.lore import SKILL_MAX_LABEL
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


_LEVEL_UP = re.compile(r"Level \d+!")
PRIORITY_WAIT = 1.0     # BUG-167 ruling: a priority notice (phase banner) lets the notice on screen keep at most this


def _notice_group(text: str) -> str:
    """Notices of one group replace each other instead of queueing: a burst of level-ups shows only the latest level."""
    return "level-up" if _LEVEL_UP.fullmatch(text) else text


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
        self._queue: Deque[Tuple[str, float, bool, bool]] = deque(maxlen=config.HUD_NOTICE_QUEUE)   # (text, s, now, prio)
        self._now = False                                 # the notice on screen is menu / shop feedback
        self._prio = False                                # BUG-167: the notice on screen is a priority one (phase banner)
        self._dur = 0.0                                   # BUG-167: the full duration of the notice on screen
        self._yielded = False                             # BUG-167: it is counting down its <= 1.0 s before a banner
        self.shop_item_rects: list = []

    def show_notification(self, text: str, duration: float = 2.0, now: bool = False, priority: bool = False) -> None:
        """Show a temporary notification. One slot (BUG-145): while another notice is showing, the new one waits in a small
        queue and then gets its full duration. A notice of the same group as the one on screen (the same text, or another
        "Level N!") replaces it in place; one of the same group as a waiting notice replaces that one.

        now=True is menu / shop feedback (the answer to a key press): it jumps the queue and shows at once, and the
        gameplay notice it interrupts goes back to the front of the queue with the time it had left. Feedback that arrives
        while other feedback is showing waits behind it, still ahead of every gameplay notice.

        priority=True is a phase banner (BUG-167 ruling): it replaces a banner on screen at once (the game times that,
        BUG-166); any other notice on screen keeps at most PRIORITY_WAIT (1.0 s) and the banner shows next, ahead of
        everything waiting. A gameplay notice it cuts short shows again afterwards for its full duration."""
        if priority:
            self._show_priority(text, duration)
            return
        group = _notice_group(text)
        if self.notification_timer <= 0:
            self._show(text, duration, now)
        elif group == _notice_group(self.notification) and not self._yielded:
            self.notification, self.notification_timer = text, max(self.notification_timer, duration)
            self._dur = max(self._dur, duration)
            self._now = self._now or now
        else:
            for k, (t, _d, n, p) in enumerate(self._queue):
                if _notice_group(t) == group:
                    self._queue[k] = (text, duration, n or now, p)  # e.g. "Level 3!" waiting becomes "Level 4!"
                    return
            if not now:
                self._queue.append((text, duration, False, False))
            elif not self._now:                                   # interrupt a gameplay notice; it resumes next
                self._push_front((self.notification, self.notification_timer, False, self._prio))
                self._show(text, duration, True)
            else:                                                 # behind the feedback already waiting, before gameplay
                k = next((k for k, e in enumerate(self._queue) if not e[2] and not e[3]), len(self._queue))
                self._insert(k, (text, duration, True, False))

    def _show_priority(self, text: str, duration: float) -> None:
        """BUG-167 ruling: see show_notification(priority=True)."""
        if self.notification_timer <= 0 or self._prio:
            self._show(text, duration, False, True)
            return
        k = next((k for k, e in enumerate(self._queue) if not e[3]), len(self._queue))   # behind banners already waiting
        self._insert(k, (text, duration, False, True))
        if self._yielded:
            return                                                # already counting down its 1.0 s, already re-queued
        if self.notification_timer > PRIORITY_WAIT and not self._now:
            self._insert(k + 1, (self.notification, self._dur, False, False))   # cut short: its full time afterwards
        self.notification_timer = min(self.notification_timer, PRIORITY_WAIT)
        self._yielded = True

    def withdraw(self, text: str) -> None:
        """Drop waiting notices with this text (a phase banner whose boss is gone, or a fight that was left)."""
        kept = [e for e in self._queue if e[0] != text]
        if len(kept) != len(self._queue):
            self._queue.clear()
            self._queue.extend(kept)

    def _show(self, text: str, duration: float, now: bool, prio: bool = False) -> None:
        self.notification, self.notification_timer, self._now = text, duration, now
        self._prio, self._dur, self._yielded = prio, duration, False

    def _push_front(self, entry: Tuple[str, float, bool, bool]) -> None:
        self._insert(0, entry)

    def _insert(self, k: int, entry: Tuple[str, float, bool, bool]) -> None:
        if len(self._queue) == self._queue.maxlen:
            self._queue.pop()                                     # full: the newest waiting notice drops
        self._queue.insert(min(k, len(self._queue)), entry)

    def update(self, dt: float) -> None:
        """Update notification timer; the next queued notice starts when the current one ends."""
        if self.notification_timer > 0:
            self.notification_timer -= dt
            if self.notification_timer <= 0 and self._queue:
                text, duration, now, prio = self._queue.popleft()
                self._show(text, duration + self.notification_timer, now, prio)   # carry the overshoot: full duration each
                self._dur = duration

    @property
    def pending_notifications(self) -> List[str]:
        """Texts waiting behind the one on screen (next first)."""
        return [e[0] for e in self._queue]

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
            cost_label = SKILL_MAX_LABEL if skill["maxed"] else f"{skill['cost']} SP"
            cost_text = self.font_small.render(cost_label, True, style.SELECT_DIM)
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
