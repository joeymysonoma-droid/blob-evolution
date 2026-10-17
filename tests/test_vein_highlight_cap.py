"""BUG-205 (TASK-065): act 9's 1 px vein highlight is dimmed where it is dense, at bake time only."""
import pygame
import pytest

from blob_evolution.utils import terrain

LIGHT = (200, 50, 140)


def _layer_with(lines):
    layer = pygame.Surface((200, 200), pygame.SRCALPHA)
    for y in lines:
        pygame.draw.line(layer, (*LIGHT, 255), (20, y), (180, y), 1)
    return layer


def test_constants_are_the_ruled_ones():
    assert (terrain.VEIN_HL_GREY, terrain.VEIN_HL_WINDOW, terrain.VEIN_HL_CAP, terrain.VEIN_HL_DIM_ALPHA,
            terrain.VEIN_HL_FALLOFF) == (88, 32, 0.11, 0.55, 8)


def test_sparse_highlight_is_left_alone():
    layer = _layer_with([60, 100, 140])                 # 1 line per 32 px window: ~3 % coverage
    before = pygame.image.tobytes(layer, "RGBA")
    assert terrain._cap_vein_highlights(layer, LIGHT) == 0
    assert pygame.image.tobytes(layer, "RGBA") == before


def test_a_window_one_pixel_over_the_cap_is_found_and_one_at_it_is_not():
    limit = int(terrain.VEIN_HL_CAP * 32 * 32)          # 112 pixels may be highlight
    for n, over in ((limit, False), (limit + 1, True)):
        layer = pygame.Surface((100, 100), pygame.SRCALPHA)
        for i in range(n):
            layer.set_at((34 + i % 32, 34 + i // 32), (*LIGHT, 255))
        assert (terrain._vein_highlight_over_cap(layer, LIGHT)[1] > 0) is over, n


def test_dense_highlight_is_dimmed_to_55_percent_and_ramps_back_over_8_px():
    layer = _layer_with(range(90, 110, 3))              # 7 lines in 20 px: dense in the middle
    layer.fill((0, 0, 0, 0), (0, 0, 200, 60))
    pygame.draw.line(layer, (*LIGHT, 255), (100, 0), (100, 89), 1)   # a lone line running out of the dense patch
    over, _ = terrain._vein_highlight_over_cap(layer, LIGHT)
    assert terrain._cap_vein_highlights(layer, LIGHT) > 0
    assert layer.get_at((100, 99)) == (*LIGHT, round(255 * 0.55))   # inside
    top = min(y for y in range(200) if over.get_at((100, y)))
    ramp = [layer.get_at((100, top - k)).a for k in range(0, 10)]
    assert ramp[0] == round(255 * 0.55) and ramp[-1] == 255 and ramp == sorted(ramp)
    assert all(layer.get_at((x, y))[:3] == LIGHT for x, y in ((100, 99), (100, top - 4)))     # colour unchanged


def test_a_colour_at_or_under_the_grey_threshold_is_never_dimmed():
    dark = (60, 60, 60)
    layer = pygame.Surface((64, 64), pygame.SRCALPHA)
    layer.fill((*dark, 255))
    assert terrain._cap_vein_highlights(layer, dark) == 0


# --- the fast pass is pixel-identical to the full 32 px scan ----------------------------------------------------------

from blob_evolution import config  # noqa: E402
from blob_evolution.utils.graphics import generate_map_texture  # noqa: E402

SEEDS_70 = tuple(dict.fromkeys((0, 7, 145, 999, *range(1, 21), 31, 77, 123, 500, 1234, 4242, 2026, 31337, 3018, *range(21, 60))))


def _both(seed):
    """The act 9 ground baked with the fast pass and with the reference full scan (same rng, same everything else)."""
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    th = config.MAP_THEMES[9]
    fast = pygame.image.tobytes(generate_map_texture(config.WORLD_WIDTH, config.WORLD_HEIGHT, th["color"], th["accent"], seed, 9), "RGB")
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(terrain, "_draw_capped_vein_highlight", terrain._draw_capped_vein_highlight_full)
        full = pygame.image.tobytes(generate_map_texture(config.WORLD_WIDTH, config.WORLD_HEIGHT, th["color"], th["accent"], seed, 9), "RGB")
    finally:
        mp.undo()
    return fast, full


@pytest.mark.parametrize("seed", [3018, 2026, 7, 2])     # most over-cap windows, merged patches, the budget seed, none
def test_fast_pass_is_pixel_identical_to_the_full_scan(seed):
    fast, full = _both(seed)
    assert fast == full


@pytest.mark.slow
def test_fast_pass_is_pixel_identical_to_the_full_scan_on_70_seeds():
    assert len(SEEDS_70) == 70
    assert [s for s in SEEDS_70 if len(set(_both(s))) != 1] == []


def test_fast_pass_matches_on_patches_that_merge_across_tile_corners():
    """Two dense patches whose merged rect reaches tiles neither one loaded (seed 2026 found this)."""
    base = pygame.Surface((300, 300))
    base.fill((40, 10, 30))
    segs = [(40, y, 100, y) for y in range(40, 60, 3)] + [(130, y, 190, y) for y in range(100, 120, 3)] + [(0, 150, 299, 20)]
    a, b = base.copy(), base.copy()
    terrain._draw_capped_vein_highlight(a, segs, LIGHT)
    terrain._draw_capped_vein_highlight_full(b, segs, LIGHT)
    assert pygame.image.tobytes(a, "RGB") == pygame.image.tobytes(b, "RGB")
