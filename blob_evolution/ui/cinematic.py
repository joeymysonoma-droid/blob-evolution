"""Full-screen story / cinematic cards."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pygame

from blob_evolution import config
from blob_evolution.data.lore import wrap_text
from blob_evolution.ui import style
from blob_evolution.utils.graphics import draw_blob


@dataclass
class StoryPage:
    """One page of a cinematic sequence."""

    title: str
    body: str
    accent: Tuple[int, int, int] = style.ACCENT
    eyebrow: str = ""
    blob_color: Tuple[int, int, int] = style.ACCENT
    blob_core: Tuple[int, int, int] = (120, 255, 170)
    hint: str = "Press SPACE / ENTER to continue"


@dataclass
class StorySequence:
    """Queued story pages shown before returning to a resume state."""

    pages: List[StoryPage] = field(default_factory=list)
    index: int = 0
    resume_state: object = None
    age: float = 0.0

    @property
    def current(self) -> Optional[StoryPage]:
        if 0 <= self.index < len(self.pages):
            return self.pages[self.index]
        return None

    def advance(self) -> bool:
        """Advance page. Returns True if sequence finished."""
        self.index += 1
        self.age = 0.0
        return self.index >= len(self.pages)


class CinematicRenderer:
    """Renders story cards over a themed ambient background."""

    def __init__(self) -> None:
        self.title_font = pygame.font.SysFont("segoeui", 36, bold=True)
        self.eyebrow_font = pygame.font.SysFont("segoeui", 14, bold=True)
        self.body_font = pygame.font.SysFont("segoeui", 18)
        self.hint_font = pygame.font.SysFont("segoeui", 14)
        self.page_font = pygame.font.SysFont("segoeui", 13)

    def update(self, sequence: StorySequence, dt: float) -> None:
        sequence.age += dt

    def draw(self, surface: pygame.Surface, sequence: StorySequence) -> None:
        page = sequence.current
        if not page:
            return

        style.draw_ambient_bg(surface, seed_offset=sequence.index * 3.1, accent=page.accent)
        t = time.time()

        # Decorative orbiting blobs
        cx = config.SCREEN_WIDTH // 2
        for i in range(4):
            ang = t * 0.4 + i * 1.6
            bx = cx + math.cos(ang) * (260 + i * 18)
            by = 160 + math.sin(ang * 0.85) * 28
            draw_blob(
                surface, (bx, by), 10 + i * 2,
                page.blob_color, page.blob_core,
                pulse=math.sin(t * 2 + i) * 0.05,
                glow=(i == 0),
            )

        panel = pygame.Rect(config.SCREEN_WIDTH // 2 - 380, 150, 760, 460)
        style.draw_panel(surface, panel, alpha=240, edge=page.accent)

        # Accent bar
        pygame.draw.rect(
            surface, page.accent,
            (panel.x + 24, panel.y + 28, 6, panel.height - 56),
            border_radius=3,
        )

        y = panel.y + 36
        if page.eyebrow:
            eye = self.eyebrow_font.render(page.eyebrow.upper(), True, page.accent)
            surface.blit(eye, (panel.x + 48, y))
            y += 28

        title = self.title_font.render(page.title, True, style.TEXT)
        surface.blit(title, (panel.x + 48, y))
        y += title.get_height() + 18

        fade = min(1.0, sequence.age * 2.5)
        body_color = style.lerp_color(style.PANEL, style.TEXT_DIM, fade)
        for paragraph in page.body.split("\n"):
            for line in wrap_text(paragraph, self.body_font, panel.width - 100):
                rendered = self.body_font.render(line, True, body_color)
                surface.blit(rendered, (panel.x + 48, y))
                y += 26
            y += 10

        # Center hero blob
        hero_y = panel.bottom - 110
        draw_blob(
            surface, (cx, hero_y), 28,
            page.blob_color, page.blob_core,
            pulse=math.sin(t * 2.2) * 0.06,
            glow=True,
            variant="crown" if "Warden" in page.title or "Anchor" in page.title or "Prime" in page.title else "default",
        )

        page_label = self.page_font.render(
            f"{sequence.index + 1} / {len(sequence.pages)}", True, style.TEXT_MUTED,
        )
        surface.blit(page_label, (panel.right - page_label.get_width() - 28, panel.bottom - 36))
        style.draw_hint(surface, self.hint_font, page.hint)
