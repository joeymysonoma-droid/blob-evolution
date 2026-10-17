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
# Visual Designer ruling (BUG-184, Oct 17), option (a): acts 3 and 8 keep player contrast >= 3.3 (QA sg_sweep t39) on every
# over-cap seed, so their caps become the 32-seed worst + 1 point. Act 2 (seeds < 3.3) took option (b) instead: crystals
# capped per cluster in terrain.decals_act_2. Act 2 ruling (Oct 17): cluster centres >= 1.5 x cluster radius apart,
# crystals >= 1.1 x diameter apart; 3 per cluster left seeds 5 and 19 under 3.3, so 2 per cluster. All 32 seeds >= 3.3;
# its cap is the 32-seed worst (seed 19) + 1 point.
# BUG-206 (TASK-064): act 2's cap tightened to 6.55 %: its 32-seed worst on 806a7ce is 5.55 % (seed 19 is 4.18 %; the
# 6.57 % it was fitted to came from 2cebbe9, before TASK-063's fillers).
HELD = {2: 0.0655, 3: 0.1203 + 0.01, 8: 0.0546 + 0.01, 9: 0.1015 + 0.01}


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


# BUG-184 (TASK-060): re-fit over 32 seeds (0/7/145/999, 1-20, 31, 77, 123, 500, 1234, 4242, 2026, 31337) on e222d44.
# Worst share per act (%), old 4-seed worst -> 32-seed worst, against the cap above:
#   0: 1.28 -> 1.28   1: 0.00 -> 0.00   4: 0.09 -> 0.43   5: 0.00 -> 0.00   6: 3.92 -> 4.10   7: 0.68 -> 1.02  (all < 5)
#   9: 10.15 -> 10.67 (< 11.15)
#   2: 9.47 -> 18.17 (seeds 3, 4, 8, 9, 12, 15 over 10.47)   3: 9.73 -> 12.03 (seeds 14, 500 over 10.73)
#   8: 3.50 -> 5.46 (seed 18 over 5)
# Acts 3 and 8: caps raised with Visual Designer sign-off (option a), back in the wide test. Act 2 after option (b)
# (2 crystals per cluster, spaced clusters and crystals): 18.17 -> 6.57 (seed 19), back in the wide test.
SEEDS_WIDE = (0, 7, 145, 999, *range(1, 21), 31, 77, 123, 500, 1234, 4242, 2026, 31337)
WIDE_ACTS = tuple(range(10))


@pytest.mark.slow
@pytest.mark.parametrize("act", WIDE_ACTS)
def test_bug_184_bright_decal_share_holds_over_32_seeds(act):
    worst = max(_worst_share(act, s) for s in SEEDS_WIDE)
    assert worst < HELD.get(act, LIMIT), (act, round(worst, 4))


# BUG-205 (TASK-065, Visual Designer option a): act 9 dims its vein highlight in every 32 px window over 11 % (see
# terrain.VEIN_HL_*). Over 70 seeds (SEEDS_WIDE + 3018 + 21..59) the worst share went 12.88 % (seed 3018) -> 10.67 %
# (seeds 3 and 123, which have no over-cap window), so the 11.15 % cap holds without a raise.
SEEDS_70 = tuple(dict.fromkeys((*SEEDS_WIDE, 3018, *range(21, 60))))


@pytest.mark.slow
def test_bug_205_act_9_bright_decal_share_holds_over_70_seeds():
    assert len(SEEDS_70) == 70
    worst = max((_worst_share(9, s), s) for s in SEEDS_70)
    assert worst[0] < HELD[9], (round(worst[0], 4), worst[1])
