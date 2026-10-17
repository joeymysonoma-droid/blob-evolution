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
