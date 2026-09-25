"""Menu screens and UI rendering."""

from __future__ import annotations

import math
import time
from typing import List, Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.data.lore import (
    ARCHIVE_TABS,
    ENDING_SUBTITLES,
    ENDING_TITLES,
    GAME_OVER_EPILOGUE,
    OPENING_BLURB,
    TAGLINE,
    archive_entries_for_tab,
    get_ending_epilogue,
    wrap_text,
)
from blob_evolution.ui import style
from blob_evolution.utils.enums import Difficulty
from blob_evolution.utils.graphics import draw_blob


class MenuRenderer:
    """Renders menu screens with clickable item tracking."""

    def __init__(self) -> None:
        self.title_font = pygame.font.SysFont("segoeui", 56, bold=True)
        self.menu_font = pygame.font.SysFont("segoeui", 24)
        self.small_font = pygame.font.SysFont("segoeui", 17)
        self.tiny_font = pygame.font.SysFont("segoeui", 13)
        self.item_rects: List[pygame.Rect] = []
        self.archive_tab_rects: List[pygame.Rect] = []
        self.archive_entry_rects: List[pygame.Rect] = []

    def hit_test(self, pos: Tuple[int, int]) -> Optional[int]:
        """Return index of menu item at screen position, or None."""
        for i, rect in enumerate(self.item_rects):
            if rect.collidepoint(pos):
                return i
        return None

    def _begin_items(self) -> None:
        """Clear tracked item rects before drawing a menu."""
        self.item_rects.clear()

    def _draw_wrapped(
        self,
        surface: pygame.Surface,
        text: str,
        font: pygame.font.Font,
        color: Tuple[int, int, int],
        center_y: int,
        max_width: int = 700,
        line_height: int = 22,
    ) -> int:
        """Draw centered wrapped text. Returns y after last line."""
        lines = wrap_text(text, font, max_width)
        total_h = len(lines) * line_height
        y = center_y - total_h // 2
        for line in lines:
            rendered = font.render(line, True, color)
            surface.blit(rendered, (config.SCREEN_WIDTH // 2 - rendered.get_width() // 2, y))
            y += line_height
        return y

    def draw_main_menu(self, surface: pygame.Surface, selected: int, difficulty: Difficulty) -> None:
        """Draw main menu."""
        self._begin_items()
        style.draw_ambient_bg(surface)
        self._draw_title(surface)

        panel = pygame.Rect(config.SCREEN_WIDTH // 2 - 190, 275, 380, 310)
        style.draw_panel(surface, panel, alpha=210)

        items = ["Play", "Upgrades", "Archive", "Options", "Help", "Quit"]
        start_y = panel.y + 18
        for i, item in enumerate(items):
            rect = style.draw_menu_row(
                surface, self.menu_font, item,
                panel.x + 30, start_y + i * 46, i == selected, width=320,
            )
            self.item_rects.append(rect)

        diff = self.small_font.render(
            f"Difficulty: {difficulty.value.title()}", True, style.TEXT_DIM,
        )
        surface.blit(diff, (config.SCREEN_WIDTH // 2 - diff.get_width() // 2, panel.bottom + 16))
        style.draw_hint(
            surface, self.tiny_font,
            "WASD navigate  ·  SPACE select  ·  Click items  ·  A/D difficulty",
        )

    def draw_pause_menu(self, surface: pygame.Surface, selected: int) -> None:
        """Draw pause overlay."""
        self._begin_items()
        overlay = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((4, 8, 16, 190))
        surface.blit(overlay, (0, 0))

        panel = pygame.Rect(config.SCREEN_WIDTH // 2 - 180, 200, 360, 280)
        style.draw_panel(surface, panel, alpha=240)
        style.draw_title_block(surface, self.menu_font, self.small_font, "PAUSED", y=panel.y + 24, color=style.TEXT)

        items = ["Resume", "Restart", "Quit to Menu"]
        for i, item in enumerate(items):
            rect = style.draw_menu_row(
                surface, self.menu_font, item,
                panel.x + 30, panel.y + 90 + i * 50, i == selected, width=300,
            )
            self.item_rects.append(rect)

    def draw_options(self, surface: pygame.Surface, selected: int, difficulty: Difficulty,
                     show_fps: bool, show_minimap: bool, sound_on: bool = True) -> None:
        """Draw options menu."""
        self._begin_items()
        style.draw_ambient_bg(surface, seed_offset=2.0)
        style.draw_title_block(surface, self.menu_font, self.small_font, "OPTIONS", y=70)

        panel = pygame.Rect(config.SCREEN_WIDTH // 2 - 220, 140, 440, 340)
        style.draw_panel(surface, panel)

        items = [
            f"Difficulty: {difficulty.value.title()}",
            f"Show FPS: {'ON' if show_fps else 'OFF'}",
            f"Show Minimap: {'ON' if show_minimap else 'OFF'}",
            f"Sound: {'ON' if sound_on else 'OFF'}",
            "Back",
        ]
        for i, item in enumerate(items):
            rect = style.draw_menu_row(
                surface, self.menu_font, item,
                panel.x + 40, panel.y + 28 + i * 52, i == selected, width=360,
            )
            self.item_rects.append(rect)

        style.draw_hint(surface, self.small_font, "WASD navigate  ·  A/D change  ·  SPACE select")

    def draw_help(self, surface: pygame.Surface) -> None:
        """Draw help screen."""
        style.draw_ambient_bg(surface, seed_offset=1.5)
        style.draw_title_block(surface, self.menu_font, self.small_font, "HOW TO PLAY", y=36)

        panel = pygame.Rect(80, 90, config.SCREEN_WIDTH - 160, 620)
        style.draw_panel(surface, panel)

        lines = [
            ("Move", "WASD / Arrow keys"),
            ("Shoot", "Left click toward cursor"),
            ("Dash", "Right click"),
            ("Skills", "TAB — press 1–9 to upgrade"),
            ("Pause", "P or ESC"),
            ("Minimap / FPS", "M  ·  F3"),
            ("", ""),
            ("Overworld", "Choose a glowing path after each encounter."),
            ("Absorb", "Touch smaller creatures to consume them."),
            ("Grow", "Collect XP orbs — level up for skill points."),
            ("Wardens", "One guards each layer, with unique attacks and phases."),
            ("Enemies", "Shielders block front hits — flank them."),
            ("Bombers", "Explode on death or when they close in."),
            ("Phantoms", "Invulnerable while faded — wait them out."),
            ("Stops", "Shops, rest sites, events, and the Reforger."),
            ("Memory", "Shards buy permanent upgrades between runs."),
            ("Archive", "Defeat Wardens and find artifacts to remember."),
            ("Sound", "Toggle audio in Options."),
            ("Core", "Reopen evolution, merge, or (later) become the Broker."),
        ]
        y = panel.y + 28
        for label, detail in lines:
            if not label and not detail:
                y += 12
                continue
            if detail and label in ("Move", "Shoot", "Dash", "Skills", "Pause", "Minimap / FPS"):
                lab = self.small_font.render(label, True, style.ACCENT)
                det = self.small_font.render(detail, True, style.TEXT)
                surface.blit(lab, (panel.x + 40, y))
                surface.blit(det, (panel.x + 200, y))
            else:
                lab = self.small_font.render(label, True, style.SELECT_DIM if label else style.TEXT_DIM)
                det = self.small_font.render(detail, True, style.TEXT_DIM)
                surface.blit(lab, (panel.x + 40, y))
                surface.blit(det, (panel.x + 200, y))
            y += 32

        style.draw_hint(surface, self.tiny_font, "ESC or SPACE to return")

    def draw_game_over(self, surface: pygame.Surface, stats: dict, selected: int) -> None:
        """Draw game over screen."""
        self._begin_items()
        style.draw_ambient_bg(surface, seed_offset=4.0, accent=(120, 40, 50))
        style.draw_title_block(
            surface, self.title_font, self.small_font,
            "DISSOLVED", "Your shape fades — the Lattice keeps a shard.",
            y=70, color=style.DANGER,
        )

        panel = pygame.Rect(config.SCREEN_WIDTH // 2 - 260, 200, 520, 320)
        style.draw_panel(surface, panel)

        stat_lines = [
            ("Level", str(stats.get("level", 1))),
            ("Kills", str(stats.get("kills", 0))),
            ("Maps", str(stats.get("maps_cleared", 0))),
            ("XP", str(stats.get("total_xp", 0))),
            ("Essence", str(stats.get("essence", 0))),
        ]
        y = panel.y + 28
        for label, value in stat_lines:
            lab = self.small_font.render(label, True, style.TEXT_MUTED)
            val = self.menu_font.render(value, True, style.TEXT)
            surface.blit(lab, (panel.x + 48, y + 4))
            surface.blit(val, (panel.x + 280, y))
            y += 36

        self._draw_wrapped(
            surface, GAME_OVER_EPILOGUE, self.small_font, style.TEXT_DIM,
            panel.bottom + 40, max_width=680, line_height=20,
        )

        for i, item in enumerate(["Restart", "Main Menu"]):
            rect = style.draw_menu_row(
                surface, self.menu_font, item,
                config.SCREEN_WIDTH // 2 - 160, config.SCREEN_HEIGHT - 130 + i * 48,
                i == selected, width=320,
            )
            self.item_rects.append(rect)

    def draw_victory(
        self,
        surface: pygame.Surface,
        stats: dict,
        selected: int,
        ng_plus: int,
        ending: str = "reopen",
    ) -> None:
        """Draw victory screen for a Core ending."""
        self._begin_items()
        if ending == "merge":
            accent = (140, 190, 255)
            bg_accent = (40, 60, 110)
        elif ending == "broker":
            accent = (220, 180, 120)
            bg_accent = (90, 60, 40)
        else:
            accent = (255, 214, 110)
            bg_accent = (40, 90, 70)

        style.draw_ambient_bg(surface, seed_offset=3.0, accent=bg_accent)
        title_text = ENDING_TITLES.get(ending, "VICTORY!")
        subtitle = ENDING_SUBTITLES.get(ending, "The First Divide opens.")
        style.draw_title_block(
            surface, self.title_font, self.menu_font, title_text, subtitle,
            y=50, color=accent,
        )

        panel = pygame.Rect(config.SCREEN_WIDTH // 2 - 240, 175, 480, 220)
        style.draw_panel(surface, panel)
        stat_lines = [
            f"Final Level  {stats.get('level', 1)}",
            f"Total Kills  {stats.get('kills', 0)}",
            f"Essence  {stats.get('essence', 0)}",
            f"Artifacts  {stats.get('artifacts', 0)}",
            f"NG+ Level  {ng_plus}",
        ]
        y = panel.y + 24
        for line in stat_lines:
            text = self.small_font.render(line, True, style.TEXT)
            surface.blit(text, (config.SCREEN_WIDTH // 2 - text.get_width() // 2, y))
            y += 34

        y = self._draw_wrapped(
            surface, get_ending_epilogue(ending), self.small_font, style.TEXT_DIM,
            panel.bottom + 50, max_width=680, line_height=20,
        )

        for i, item in enumerate(["New Game Plus", "Main Menu"]):
            rect = style.draw_menu_row(
                surface, self.menu_font, item,
                config.SCREEN_WIDTH // 2 - 160,
                min(y + 16 + i * 48, config.SCREEN_HEIGHT - 120 + i * 48),
                i == selected, width=320,
            )
            self.item_rects.append(rect)

    def draw_core_choice(
        self,
        surface: pygame.Surface,
        selected: int,
        broker_unlocked: bool,
    ) -> None:
        """Draw the final Core ending choice."""
        self._begin_items()
        style.draw_ambient_bg(surface, seed_offset=5.0, accent=(90, 50, 120))
        style.draw_title_block(
            surface, self.menu_font, self.small_font,
            "THE FIRST DIVIDE",
            "The Prime Anchor falters. The wound that made the world waits for your answer.",
            y=60, color=(220, 160, 255),
        )

        choices = [
            ("Reopen the Divide", "Evolution resumes. Change — and grief — return."),
            ("Merge with the Anchor", "Seal the wound. Choose stillness forever."),
        ]
        if broker_unlocked:
            choices.append(
                ("Become the Broker", "Leave the pilgrimage. Trade in what others become."),
            )

        for i, (label, desc) in enumerate(choices):
            yy = 220 + i * 100
            rect = pygame.Rect(config.SCREEN_WIDTH // 2 - 320, yy, 640, 84)
            edge = style.SELECT if i == selected else style.PANEL_EDGE
            style.draw_panel(surface, rect, edge=edge, alpha=220)
            color = style.SELECT if i == selected else style.TEXT
            text = self.menu_font.render(label, True, color)
            surface.blit(text, (rect.centerx - text.get_width() // 2, yy + 16))
            d = self.small_font.render(desc, True, style.TEXT_DIM)
            surface.blit(d, (rect.centerx - d.get_width() // 2, yy + 48))
            self.item_rects.append(rect)

        style.draw_hint(surface, self.tiny_font, "WASD select  ·  SPACE confirm")

    def draw_archive(
        self,
        surface: pygame.Surface,
        tab: int,
        selected: int,
        unlocked_wardens: List[str],
        unlocked_artifacts: List[str],
        endings_seen: Optional[List[str]] = None,
    ) -> None:
        """Draw the Archive / codex screen."""
        self._begin_items()
        self.archive_tab_rects.clear()
        self.archive_entry_rects.clear()
        style.draw_ambient_bg(surface, seed_offset=6.0, accent=(60, 50, 100))
        style.draw_title_block(surface, self.menu_font, self.small_font, "THE ARCHIVE", y=20, color=(180, 160, 255))

        tab_x = config.SCREEN_WIDTH // 2 - 240
        for i, name in enumerate(ARCHIVE_TABS):
            color = style.SELECT if i == tab else style.TEXT_MUTED
            label = self.small_font.render(name, True, color)
            x = tab_x + i * 120
            tab_rect = pygame.Rect(x - 8, 68, label.get_width() + 16, 28)
            if i == tab:
                style.draw_panel(surface, tab_rect, edge=style.SELECT, radius=6, alpha=180)
            surface.blit(label, (x, 72))
            self.archive_tab_rects.append(tab_rect.inflate(8, 6))

        entries = archive_entries_for_tab(
            tab, unlocked_wardens, unlocked_artifacts, endings_seen,
        )
        list_panel = pygame.Rect(36, 110, 360, 620)
        detail_panel = pygame.Rect(412, 110, 752, 620)
        style.draw_panel(surface, list_panel)
        style.draw_panel(surface, detail_panel)

        if not entries:
            empty = self.small_font.render("Nothing recorded yet.", True, style.TEXT_DIM)
            surface.blit(empty, (list_panel.centerx - empty.get_width() // 2, 200))
        else:
            selected = max(0, min(selected, len(entries) - 1))
            list_x = list_panel.x + 16
            list_top = list_panel.y + 16
            visible = 20
            scroll = max(0, min(selected - visible // 2, max(0, len(entries) - visible)))
            for i, (_eid, etitle, _body, unlocked) in enumerate(entries):
                if i < scroll or i >= scroll + visible:
                    self.archive_entry_rects.append(pygame.Rect(0, 0, 0, 0))
                    continue
                row = i - scroll
                y = list_top + row * 28
                row_rect = pygame.Rect(list_x - 4, y - 2, list_panel.width - 28, 26)
                if i == selected:
                    style.draw_panel(surface, row_rect, edge=style.SELECT, radius=4, alpha=160)
                if unlocked:
                    color = style.SELECT if i == selected else style.TEXT
                    mark = ""
                else:
                    color = style.WARN if i == selected else style.TEXT_MUTED
                    mark = "  ···"
                text = self.small_font.render(f"{etitle}{mark}", True, color)
                surface.blit(text, (list_x + 8, y))
                self.archive_entry_rects.append(row_rect)

            _eid, etitle, body, unlocked = entries[selected]
            head_color = (200, 180, 255) if unlocked else style.TEXT_MUTED
            head = self.menu_font.render(etitle, True, head_color)
            surface.blit(head, (detail_panel.x + 28, detail_panel.y + 24))
            body_color = style.TEXT_DIM if unlocked else style.TEXT_MUTED
            y = detail_panel.y + 70
            for paragraph in body.split("\n"):
                for line in wrap_text(paragraph, self.small_font, detail_panel.width - 56):
                    rendered = self.small_font.render(line, True, body_color)
                    surface.blit(rendered, (detail_panel.x + 28, y))
                    y += 24
                y += 8
            if not unlocked:
                hint = self.tiny_font.render(
                    "Defeat wardens and collect artifacts to unlock memories.",
                    True, style.TEXT_MUTED,
                )
                surface.blit(hint, (detail_panel.x + 28, detail_panel.bottom - 40))

        unlocked_count = sum(1 for e in entries if e[3]) if entries else 0
        total = len(entries)
        style.draw_hint(
            surface, self.tiny_font,
            f"{unlocked_count}/{total} recovered  ·  TAB tabs  ·  WASD browse  ·  ESC back",
        )

    def archive_hit_test(self, pos: Tuple[int, int]) -> Tuple[Optional[str], Optional[int]]:
        """Return ('tab'|'entry', index) for Archive click, or (None, None)."""
        for i, rect in enumerate(self.archive_tab_rects):
            if rect.collidepoint(pos):
                return "tab", i
        for i, rect in enumerate(self.archive_entry_rects):
            if rect.width > 0 and rect.collidepoint(pos):
                return "entry", i
        return None, None

    def _draw_title(self, surface: pygame.Surface) -> None:
        """Draw animated title with orbiting blobs."""
        title = self.title_font.render("BLOB EVOLUTION", True, style.ACCENT)
        shadow = self.title_font.render("BLOB EVOLUTION", True, (12, 40, 28))
        cx = config.SCREEN_WIDTH // 2
        surface.blit(shadow, (cx - title.get_width() // 2 + 3, 78))
        surface.blit(title, (cx - title.get_width() // 2, 75))

        subtitle = self.small_font.render(TAGLINE, True, style.TEXT_DIM)
        surface.blit(subtitle, (cx - subtitle.get_width() // 2, 145))

        blurb_y = 172
        for line in wrap_text(OPENING_BLURB, self.tiny_font, 720):
            rendered = self.tiny_font.render(line, True, style.TEXT_MUTED)
            surface.blit(rendered, (cx - rendered.get_width() // 2, blurb_y))
            blurb_y += 16

        t = time.time()
        for i in range(5):
            angle = t * 0.55 + i * 1.25
            bx = cx + math.cos(angle) * (140 + i * 22)
            by = 248 + math.sin(angle) * 22
            r = 12 + i * 2.5
            color = style.lerp_color(style.ACCENT_SOFT, style.ACCENT, i / 5)
            core = style.lerp_color(color, (255, 255, 255), 0.35)
            draw_blob(surface, (bx, by), r, color, core, pulse=math.sin(t * 2 + i) * 0.04)
