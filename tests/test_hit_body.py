"""BUG-163 / BUG-176 (058b): the hit-body disc under five anchors and its flash copy. Kept out of test_boss_visuals.py
so 058b and 058 can both add tests without touching the same lines."""

from __future__ import annotations

import itertools
import math

import pygame
import pytest

from blob_evolution.utils import boss_shapes as bs

import test_boss_visuals as V

GRAY = V.GRAY
contrast = V.contrast
_all_bosses = V._all_bosses
_outside_mask = V._outside_mask
_art_on = V._art_on                                       # the same autouse art-on / cache-reset fixture
# ---- BUG-163: hit-body disc under five anchors -----------------------------------------------------------------------

def _anchor(key):
    return next(b for b in _all_bosses() if b.art_key == key)


def _closest_pair(gray):
    bosses = [b for b in _all_bosses() if b.is_miniboss]
    n = int(2 * 1.95 * max(b.size for b in bosses)) + 24
    masks = {b.art_key: _outside_mask(b, n, gray) for b in bosses}
    worst = (9.0, None)
    for a, c in itertools.combinations(masks, 2):
        A, B = masks[a], masks[c]
        m = min(A.count(), B.count())
        if m:
            worst = min(worst, ((A.count() + B.count() - 2 * A.overlap_area(B, (0, 0))) / m, (a, c)))
    return worst


@pytest.mark.parametrize("gray", [False, True], ids=["colour", "grayscale"])
def test_bug_163_anchor_silhouettes_with_the_disc_as_body_closest_pair_at_least_0_35(gray):
    worst = _closest_pair(gray)
    assert worst[0] >= 0.35, worst


def test_bug_163_the_five_have_the_disc_at_the_hit_radius_and_no_other_anchor_does():
    assert set(bs.HIT_BODY) == {"first_split", "drift_sleeper", "verdict_pillar", "updraft_herald", "cinder_anvil"}
    for key in bs.MINIS:
        b = _anchor(key)
        R = int(b.size)
        assert b.radius == bs.entity(key)["R"] == R                      # hitbox unchanged
        back = bs.bake(key, 1, R)[0]
        if key not in bs.HIT_BODY:
            continue
        B, _C, K = bs.pal(key, 1)
        h = back.get_width() // 2
        edge = [tuple(back.get_at((round(h + math.cos(a) * (R - 1)), round(h + math.sin(a) * (R - 1)))))
                for a in (i * math.tau / 36 for i in range(36))]
        assert sum(px == (*K, bs.HIT_BODY_EDGE_ALPHA) for px in edge) >= 30, key
        assert tuple(back.get_at((h + R // 2, h + R // 2))) == (*B, bs.HIT_BODY_FILL_ALPHA), key
        assert back.get_at((h + R + 2, h))[3] == 0 and back.get_at((h, h + R + 2))[3] == 0, key   # nothing past R


def _over(c, g, a):
    return tuple(round(c[i] * a / 255 + g[i] * (1 - a / 255)) for i in range(3))


def test_bug_163_the_disc_edge_is_3_to_1_on_its_layer_ground():
    for key in bs.HIT_BODY:
        G = bs.GROUND[bs.entity(key)["layer"]]
        assert contrast(_over(bs.pal(key, 1)[2], G, bs.HIT_BODY_EDGE_ALPHA), G) >= 3.0, key


@pytest.mark.parametrize("key", ["first_split", "drift_sleeper", "verdict_pillar", "updraft_herald", "cinder_anvil"])
def test_bug_163_shape_draws_on_top_unchanged_and_the_disc_flashes(key):
    b = _anchor(key)
    R = int(b.size)
    n = 4 * R
    shot = {}
    for name, flash in (("plain", False), ("flash", True)):
        s = pygame.Surface((n, n))
        s.fill(bs.GROUND[b.act_index])
        bs.draw_boss(s, key, 1, n // 2, n // 2, R, 0.0, 0.0, glow=False, pulse=0.0, flash=flash)   # aim 0 = step 0
        shot[name] = s
    front = bs.bake(key, 1, R, step=0)[1]
    h = front.get_width() // 2
    # every opaque pixel of the front (shape) layer lands unchanged on top of the disc
    probes = [(x, y) for x in range(0, front.get_width(), 3) for y in range(0, front.get_height(), 3)
              if front.get_at((x, y))[3] == 255]
    assert probes
    for x, y in probes[:400]:
        assert tuple(shot["plain"].get_at((n // 2 - h + x, n // 2 - h + y)))[:3] == tuple(front.get_at((x, y)))[:3]
    # a disc pixel outside the shape: lighter when flashing (the disc is in the BUG-162 lifted copy)
    spot = next((n // 2 + round(math.cos(a) * (R - 1)), n // 2 + round(math.sin(a) * (R - 1)))
                for a in (i * math.tau / 72 for i in range(72))
                if front.get_at((h + round(math.cos(a) * (R - 1)), h + round(math.sin(a) * (R - 1))))[3] == 0)
    p, f = shot["plain"].get_at(spot), shot["flash"].get_at(spot)
    assert sum(f[:3]) > sum(p[:3]) and tuple(p[:3]) != tuple(bs.GROUND[b.act_index])


def test_bug_163_a_decoy_keeps_its_12_dash_rim_and_no_disc():
    for key in bs.HIT_BODY:
        b = _anchor(key)
        R, n = int(b.size), 4 * int(b.size)
        s = pygame.Surface((n, n))
        s.fill(GRAY)
        bs.draw_boss(s, key, 1, n // 2, n // 2, R, 0.0, 0.6, glow=False, pulse=0.0, decoy=True)
        K = bs.pal(key, 1)[2]
        ring = [tuple(s.get_at((n // 2 + round(math.cos(a) * (R - 3)), n // 2 + round(math.sin(a) * (R - 3)))))[:3]
                for a in (i * math.tau / 72 for i in range(72))]
        assert not any(px == _over(K, GRAY, bs.HIT_BODY_EDGE_ALPHA) for px in ring), key


@pytest.mark.parametrize("key", ["first_split", "drift_sleeper", "verdict_pillar", "updraft_herald", "cinder_anvil"])
def test_bug_176_the_flash_disc_has_fill_alpha_130_and_a_white_edge(key):
    """The hit flash swaps the disc for its baked flash copy: fill 55 % to white at alpha 130, a white 2 px edge.
    Works whichever way the shape's own flash copy is made (058's BUG-162 lift or BUG-176 lerp + outline)."""
    b = _anchor(key)
    R = int(b.size)
    bs.bake(key, 1, R)
    spr, ox, oy = bs._hb_flash[(key, 1, R)]
    B = bs.pal(key, 1)[0]
    h = -ox
    fill = tuple(int(round(c + (255 - c) * 0.55)) for c in B)
    assert tuple(spr.get_at((h + R // 2, h + R // 2))) == (*fill, bs.HIT_BODY_FLASH_FILL_ALPHA) == (*fill, 130)
    edge = [tuple(spr.get_at((round(h + math.cos(a) * (R - 1)), round(h + math.sin(a) * (R - 1)))))
            for a in (i * math.tau / 36 for i in range(36))]
    assert sum(px == (255, 255, 255, 255) for px in edge) >= 30
    n = 4 * R
    s = pygame.Surface((n, n))
    G = bs.GROUND[b.act_index]
    front = bs.bake(key, 1, R, step=0)[1]
    fh = front.get_width() // 2
    spot = next((round(math.cos(a) * (R - 1)), round(math.sin(a) * (R - 1))) for a in (i * math.tau / 72 for i in range(72))
                if all(front.get_at((fh + round(math.cos(a) * (R - 1)) + dx, fh + round(math.sin(a) * (R - 1))))[3] == 0
                       for dx in (-4, 0, 4)))
    s.fill(G)
    bs.draw_boss(s, key, 1, n // 2, n // 2, R, 0.0, 0.0, glow=False, pulse=0.0, flash=True)
    assert tuple(s.get_at((n // 2 + spot[0], n // 2 + spot[1])))[:3] == (255, 255, 255), key
    s.fill(G)
    bs.draw_boss(s, key, 1, n // 2, n // 2, R, 0.0, 0.0, glow=False, pulse=0.0, flash=False)
    assert tuple(s.get_at((n // 2 + spot[0], n // 2 + spot[1])))[:3] != (255, 255, 255), key
    assert bs.cache_bytes()["hit_body_flash"] > 0
