"""Shared visual style for Blob Evolution UI."""

from __future__ import annotations

import math
import time
from typing import List, Optional, Tuple

import pygame

from blob_evolution import config

# Palette — deep lattice membrane, seedling green, amber select
BG_DEEP = (8, 14, 24)
BG_MID = (14, 22, 36)
PANEL = (18, 28, 44)
PANEL_EDGE = (55, 78, 98)
PANEL_EDGE_HOT = (90, 160, 120)
TEXT = (220, 230, 240)
TEXT_DIM = (120, 135, 155)
TEXT_MUTED = (85, 95, 115)
ACCENT = (52, 200, 120)
ACCENT_SOFT = (34, 140, 90)
SELECT = (255, 214, 110)
SELECT_DIM = (180, 150, 70)
DANGER = (240, 90, 100)
ESSENCE = (170, 130, 255)
SHARD = (200, 180, 255)
WARN = (255, 180, 90)


def pulse(speed: float = 2.0, lo: float = 0.0, hi: float = 1.0) -> float:
    """Oscillate between lo and hi over time."""
    t = (math.sin(time.time() * speed) + 1.0) * 0.5
    return lo + (hi - lo) * t


def lerp_color(
    a: Tuple[int, int, int],
    b: Tuple[int, int, int],
    t: float,
) -> Tuple[int, int, int]:
    """Linearly interpolate two RGB colors."""
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def draw_ambient_bg(
    surface: pygame.Surface,
    seed_offset: float = 0.0,
    base: Tuple[int, int, int] = BG_DEEP,
    accent: Tuple[int, int, int] = ACCENT_SOFT,
) -> None:
    """Fill with deep color and drifting soft membrane blobs."""
    surface.fill(base)
    t = time.time() + seed_offset
    w, h = surface.get_size()
    for i in range(7):
        angle = t * (0.15 + i * 0.03) + i * 1.7
        cx = int(w * 0.5 + math.cos(angle) * (180 + i * 55))
        cy = int(h * 0.42 + math.sin(angle * 0.8) * (90 + i * 25))
        r = 70 + i * 28
        shade = lerp_color(base, accent, 0.15 + i * 0.04)
        blob = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(blob, (*shade, 28 + i * 3), (r, r), r)
        surface.blit(blob, (cx - r, cy - r))

    # Soft top vignette band
    band = pygame.Surface((w, 120), pygame.SRCALPHA)
    band.fill((0, 0, 0, 50))
    surface.blit(band, (0, 0))
    band2 = pygame.Surface((w, 100), pygame.SRCALPHA)
    band2.fill((0, 0, 0, 60))
    surface.blit(band2, (0, h - 100))


def draw_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    fill: Tuple[int, int, int] = PANEL,
    edge: Tuple[int, int, int] = PANEL_EDGE,
    radius: int = 12,
    alpha: int = 230,
) -> None:
    """Draw a rounded translucent panel with border."""
    panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(panel, (*fill, alpha), panel.get_rect(), border_radius=radius)
    pygame.draw.rect(panel, (*edge, min(255, alpha + 20)), panel.get_rect(), 1, border_radius=radius)
    surface.blit(panel, rect.topleft)


def draw_menu_row(
    surface: pygame.Surface,
    font: pygame.font.Font,
    label: str,
    x: int,
    y: int,
    selected: bool,
    width: int = 320,
) -> pygame.Rect:
    """Draw a selectable menu row; returns clickable rect."""
    height = 42
    rect = pygame.Rect(x, y, width, height)
    if selected:
        glow = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(glow, (*SELECT, 35), glow.get_rect(), border_radius=8)
        pygame.draw.rect(glow, (*SELECT, 120), glow.get_rect(), 1, border_radius=8)
        surface.blit(glow, rect.topleft)
        bar = pygame.Rect(x + 6, y + 8, 4, height - 16)
        pygame.draw.rect(surface, SELECT, bar, border_radius=2)
        color = SELECT
        prefix = ""
    else:
        color = TEXT
        prefix = ""

    text = font.render(f"{prefix}{label}", True, color)
    surface.blit(text, (x + 22, y + (height - text.get_height()) // 2))
    return rect


def draw_hint(surface: pygame.Surface, font: pygame.font.Font, text: str, y: Optional[int] = None) -> None:
    """Draw centered footer hint."""
    rendered = font.render(text, True, TEXT_MUTED)
    yy = y if y is not None else config.SCREEN_HEIGHT - 28
    surface.blit(rendered, (config.SCREEN_WIDTH // 2 - rendered.get_width() // 2, yy))


def draw_title_block(
    surface: pygame.Surface,
    title_font: pygame.font.Font,
    subtitle_font: pygame.font.Font,
    title: str,
    subtitle: str = "",
    y: int = 80,
    color: Tuple[int, int, int] = ACCENT,
) -> int:
    """Draw centered title + optional subtitle. Returns y below block."""
    shadow = title_font.render(title, True, (10, 40, 25))
    main = title_font.render(title, True, color)
    cx = config.SCREEN_WIDTH // 2
    surface.blit(shadow, (cx - main.get_width() // 2 + 2, y + 2))
    surface.blit(main, (cx - main.get_width() // 2, y))
    next_y = y + main.get_height() + 12
    if subtitle:
        sub = subtitle_font.render(subtitle, True, TEXT_DIM)
        surface.blit(sub, (cx - sub.get_width() // 2, next_y))
        next_y += sub.get_height() + 8
    return next_y


def draw_stat_chip(
    surface: pygame.Surface,
    font: pygame.font.Font,
    label: str,
    value: str,
    x: int,
    y: int,
    accent: Tuple[int, int, int] = ACCENT,
) -> int:
    """Draw a small labeled chip; returns width used."""
    lab = font.render(label, True, TEXT_MUTED)
    val = font.render(value, True, accent)
    pad = 8
    w = lab.get_width() + val.get_width() + pad * 3
    h = max(lab.get_height(), val.get_height()) + 8
    chip = pygame.Rect(x, y, w, h)
    draw_panel(surface, chip, fill=PANEL, edge=PANEL_EDGE, radius=6, alpha=200)
    surface.blit(lab, (x + pad, y + 4))
    surface.blit(val, (x + pad + lab.get_width() + pad, y + 4))
    return w


def register_items(item_rects: List[pygame.Rect], rect: pygame.Rect) -> None:
    """Append an inflated clickable rect."""
    r = rect.inflate(8, 4)
    item_rects.append(r)
