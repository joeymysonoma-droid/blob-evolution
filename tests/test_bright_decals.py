"""BUG-119 guard: thin bright decal strokes must not crowd the ground around the player.

QA's act 4 player-contrast minimum (3.12) came from frost-fern and crack-highlight strokes covering ~11 % of the
23-30 px annulus around the player (TASK-053-BUG-119.md). After the Visual Designer's fix (ferns capped like acts 5-9,
crack highlight alpha 170 -> 110) QA's sweep gives act 4 >= 3.3 on both passes.

"Bright" here: Rec.601 grey >= 2 x the act's LIGHT-tone grey (pygame grayscale, so no numpy). The share is taken over
the player-sized annulus (r 23-30 px, player R = 20) at every 6 px of the baked ground, worst position reported.
Per-act targets (Producer / Visual Designer, Oct 10): acts 0, 1 and 4-8 < 5 %. Acts 2, 3 and 9 have designed bright
landmarks (glass crystals, lava seams, the lattice); each is capped at its measured worst share (seeds 0/7/145/999 on
8ccf54c) + 1 point. ANY INCREASE OF THESE CAPS NEEDS VISUAL SIGN-OFF.
"""
from __future__ import annotations

import functools
import math

import pygame
import pytest

from blob_evolution import config
from blob_evolution.utils import graphics
from blob_evolution.utils.graphics import generate_map_texture

W, H = config.WORLD_WIDTH, config.WORLD_HEIGHT
R0, R1, STEP = 23, 30, 6
LIMIT = 0.05
# measured worst share + 1 point; raising any of these needs Visual Designer sign-off
HELD = {2: 0.0947 + 0.01, 3: 0.0973 + 0.01, 9: 0.1015 + 0.01}


def _grey(c) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


@functools.lru_cache(maxsize=None)
def _annulus() -> pygame.mask.Mask:
    m = pygame.mask.Mask((2 * R1 + 1, 2 * R1 + 1))
    for x in range(2 * R1 + 1):
        for y in range(2 * R1 + 1):
            if R0 * R0 <= (x - R1) ** 2 + (y - R1) ** 2 <= R1 * R1:
                m.set_at((x, y))
    return m


def _worst_share(act: int, seed: int) -> float:
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    orig = graphics._make_vignette
    graphics._make_vignette = lambda w, h: pygame.Surface((w, h), pygame.SRCALPHA)
    try:
        th = config.MAP_THEMES[act]
        surf = generate_map_texture(W, H, th["color"], th["accent"], seed, act).convert()
    finally:
        graphics._make_vignette = orig
    grey = pygame.transform.grayscale(surf)
    t = min(255, math.ceil(_grey(config.GROUND_RAMPS[act][2]) * 2.0))
    c = (255 + t) // 2
    bright = pygame.mask.from_threshold(grey, (c, c, c), (256 - c,) * 3)
    ann = _annulus()
    worst = max(ann.overlap_area(bright, (-x, -y)) for y in range(0, H - 2 * R1, STEP) for x in range(0, W - 2 * R1, STEP))
    return worst / ann.count()


@pytest.mark.parametrize("act", range(10))
def test_bright_decal_share_around_any_player_position_stays_under_5_percent(act):
    share = _worst_share(act, 7)
    assert share < HELD.get(act, LIMIT), (act, round(share, 3))


def test_act_4_ferns_and_cracks_stay_dim():
    """The BUG-119 fix itself: act 4 was 6-9 % before (seeds 0/7/145), now <= 0.1 %."""
    assert max(_worst_share(4, s) for s in (0, 7, 145)) < 0.01


@pytest.mark.slow
@pytest.mark.parametrize("seed", [0, 145, 999])
def test_bright_decal_share_other_seeds(seed):
    for act in range(10):
        assert _worst_share(act, seed) < HELD.get(act, LIMIT), (act, seed)
