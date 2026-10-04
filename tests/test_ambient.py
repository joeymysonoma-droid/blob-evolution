"""TASK-040: per-act ambient mote field (systems/ambient.py).

Checks the plan's acceptance: caps never exceeded, no mote bigger than 4 px, nothing faster than 1 Hz, front motes
capped at alpha 90, only updated in PLAYING, never over the HUD, and that the field is purely visual: own seeded rng
(the global random stream is never touched), no gameplay state changed, nothing saved.
"""
from __future__ import annotations

import json
import random
import time
from typing import List

import pygame
import pytest

from blob_evolution import config
from blob_evolution.systems import ambient
from blob_evolution.systems.ambient import AmbientField
from blob_evolution.utils.enums import GameState, NodeType
from blob_evolution.utils.vector2 import Vector2

ACTS = range(len(config.MAP_THEMES))
PLAN_CAPS = [70, 66, 60, 90, 120, 70, 80, 40, 90, 80]
W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
CAM = Vector2(1000, 1000)
NO_SHAKE = Vector2(0, 0)


def _settled(act: int, seed: int = 1, seconds: float = 3.0, cam: Vector2 = CAM) -> AmbientField:
    field = AmbientField(act, seed)
    for _ in range(int(seconds * 60)):
        field.update(1 / 60, cam)
    return field


def _snapshot(field: AmbientField) -> List[list]:
    return [list(m) for m in field.motes]


# --- config / plan table ---------------------------------------------------------------------------------

def test_one_layer_set_per_act_and_caps_match_the_plan_table():
    assert len(config.AMBIENT_LAYERS) == len(config.MAP_THEMES) == 10
    assert [sum(layer["cap"] for layer in layers) for layers in config.AMBIENT_LAYERS] == PLAN_CAPS
    assert max(PLAN_CAPS) <= config.AMBIENT_MAX_MOTES == 200


@pytest.mark.parametrize("act", ACTS)
def test_no_mote_is_bigger_than_4_px_and_nothing_flickers_faster_than_1_hz(act):
    for layer in config.AMBIENT_LAYERS[act]:
        if layer["shape"] == "disc":
            assert 1 <= layer["size"][0] <= layer["size"][1] <= 4
        else:   # streaks: 10x2 dust, 3x8 light, wisps at most 16x3
            w, h = layer["size"]
            assert min(w, h) <= 3 and max(w, h) <= 16
        assert layer.get("mod", (1, 0))[1] <= 1.0          # R5: blink / twinkle / flicker / pulse
        assert layer.get("sway", (0, 0))[1] <= 1.0
        assert 0 < layer["peak"] <= 255
    assert all(ring["every"][0] >= 3.0 for ring in config.AMBIENT_RINGS.values())   # a ring at most every 3 s


def test_plan_values_for_a_few_acts():
    pollen = config.AMBIENT_LAYERS[0][0]
    assert (pollen["cap"], pollen["vx"], pollen["vy"], pollen["life"], pollen["sway"]) == (70, (8, 16), (-12, -6), (6, 9), (10, 0.7))
    fireflies = config.AMBIENT_LAYERS[1][1]
    assert fireflies["cap"] == 6 and fireflies["mod"][1] == pytest.approx(1 / 2.5)           # blink period 2.5 s
    embers = config.AMBIENT_LAYERS[3][0]
    assert embers["end_color"] == (120, 40, 20) and embers["mod"] == (0.8, 0.8) and embers["blend"] == "add"
    snow = config.AMBIENT_LAYERS[4][0]
    assert snow["blend"] == "alpha" and snow["gust"] == (0.6, 0.3) and snow["cap"] == 120
    assert config.AMBIENT_LAYERS[5][0]["blend"] == "alpha" and config.AMBIENT_LAYERS[5][0]["size"] == (10, 2)
    assert config.AMBIENT_LAYERS[8][1]["size"] == (3, 8)
    assert config.AMBIENT_RINGS[7] == {"color": (90, 70, 140), "every": (3.0, 5.0), "radius": 90, "life": 2.0, "alpha": 60, "max": 2}
    assert config.AMBIENT_FRONT_MAX_ALPHA == 90 and config.AMBIENT_FRONT_EVERY == 4


# --- construction, counts, sprites -----------------------------------------------------------------------

@pytest.mark.parametrize("act", ACTS)
def test_field_has_exactly_the_cap_and_a_quarter_are_front(act):
    field = AmbientField(act, 3)
    assert field.count == len(field.motes) == PLAN_CAPS[act]
    assert len(field._front) + len(field._back) == field.count
    assert abs(len(field._front) - field.count / 4) <= 1
    assert set(map(id, field._front)).isdisjoint(map(id, field._back))
    assert all(len(m) == 12 for m in field.motes)


@pytest.mark.parametrize("act", ACTS)
def test_sprite_ladders_are_prebuilt_with_six_alphas_and_small_sizes(act):
    field = AmbientField(act, 3)
    for layer in field.layers:
        assert layer.sprites
        for rows in layer.sprites:
            for ladder in rows:
                assert len(ladder) == len(config.AMBIENT_ALPHA_LADDER) == 6
                for sprite in ladder:
                    assert max(sprite.get_size()) <= 16
    assert len(field.layers) == len(config.AMBIENT_LAYERS[act])


def test_ember_colour_ladder_has_lerp_steps_toward_the_end_colour():
    layer = AmbientField(3, 1).layers[0]
    assert layer.steps == config.AMBIENT_COLOR_STEPS and len(layer.sprites) == 3 * layer.steps


def test_unknown_act_indices_clamp():
    assert AmbientField(99, 1).theme_index == 9 and AmbientField(-4, 1).theme_index == 0


# --- determinism / randomness ----------------------------------------------------------------------------

@pytest.mark.parametrize("act", [0, 3, 7])
def test_same_seed_same_motion_different_seed_differs(act):
    a, b, c = _settled(act, 5), _settled(act, 5), _settled(act, 6)
    assert _snapshot(a) == _snapshot(b)
    assert _snapshot(a) != _snapshot(c)


@pytest.mark.parametrize("act", ACTS)
def test_the_global_random_stream_is_never_touched(act):
    random.seed(1234)
    state = random.getstate()
    field = _settled(act, 9, seconds=2.0)
    surface = pygame.Surface((W, H))
    field.draw_back(surface, CAM, Vector2(3, -2))
    field.draw_front(surface, CAM, NO_SHAKE)
    assert random.getstate() == state


# --- bounds / wrapping / counts ---------------------------------------------------------------------------

def _inside(field: AmbientField, cam: Vector2) -> bool:
    ox = cam.x - W // 2 - config.AMBIENT_MARGIN
    oy = cam.y - H // 2 - config.AMBIENT_MARGIN
    return all(ox <= m[0] < ox + ambient.RECT_W and oy <= m[1] < oy + ambient.RECT_H for m in field.motes)


@pytest.mark.parametrize("act", ACTS)
def test_motes_stay_inside_the_camera_rect_and_the_count_never_changes(act):
    field = AmbientField(act, 2)
    cam = Vector2(1000, 1000)
    for i in range(900):
        cam.x += 6.0          # the player runs; the rect follows the camera
        cam.y += 2.0 if i < 450 else -2.0
        field.update(1 / 60, cam)
        assert len(field.motes) == PLAN_CAPS[act]
    assert _inside(field, cam)


def test_motes_wrap_to_the_far_edge_when_the_camera_moves():
    field = _settled(4, 3)
    cam = Vector2(1000, 1000)
    before = [m[0] for m in field.motes]
    cam.x += 400
    field.update(1 / 60, cam)
    assert _inside(field, cam)
    wrapped = sum(1 for b, m in zip(before, field.motes) if abs(m[0] - b) > 600)
    assert wrapped > 0           # those that fell off the left edge came back on the right


def test_a_huge_camera_jump_and_a_huge_dt_keep_everything_bounded():
    field = _settled(5, 3)
    cam = Vector2(1000, 1000)
    cam.set(40000, -30000)
    field.update(5.0, cam)          # dt is clamped to 0.1 s
    assert _inside(field, cam)
    assert field.t <= 3.0 + 0.1 + 0.1


@pytest.mark.parametrize("act", ACTS)
def test_every_mote_is_alive_and_expired_ones_respawn(act):
    field = _settled(act, 4, seconds=40.0)          # longer than every life
    assert all(0 <= field.t - m[5] < m[4] + 1e-6 for m in field.motes)


def test_act_7_rings_are_limited_and_spaced():
    field = AmbientField(7, 1)
    cfg = config.AMBIENT_RINGS[7]
    seen = set()
    for _ in range(60 * 60):
        field.update(1 / 60, CAM)
        assert len(field.rings) <= cfg["max"]
        seen.update(r[2] for r in field.rings)      # a ring is identified by its start time
    starts = sorted(seen)
    assert len(starts) >= 10
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert min(gaps) >= cfg["every"][0] - 0.05
    assert not AmbientField(3, 1).rings and AmbientField(3, 1)._ring_cfg is None


# --- drawing -----------------------------------------------------------------------------------------------

def _changed(surface: pygame.Surface) -> int:
    """Number of non-black bytes (the test surfaces start black)."""
    return sum(1 for b in pygame.image.tobytes(surface, "RGB") if b)


@pytest.mark.parametrize("act", ACTS)
def test_draw_back_and_front_paint_something_and_never_change_the_field(act):
    field = _settled(act, 8, seconds=6.0)
    before = _snapshot(field)
    t = field.t
    back = pygame.Surface((W, H))
    front = pygame.Surface((W, H))
    field.draw_back(back, CAM, NO_SHAKE)
    field.draw_front(front, CAM, NO_SHAKE)
    assert _changed(back) > 0 and _changed(front) > 0
    assert _snapshot(field) == before and field.t == t


@pytest.mark.parametrize("act", [0, 3, 6, 8])
def test_front_motes_never_exceed_alpha_90(act):
    field = _settled(act, 8, seconds=6.0)
    black = pygame.Surface((W, H))
    field.draw_front(black, CAM, NO_SHAKE)
    brightest = max(max(black.get_at((x, y))[:3]) for x in range(0, W, 2) for y in range(0, H, 2))
    colours = max(max(c) for layer in config.AMBIENT_LAYERS[act] for c in layer["colors"])
    # additive sprites carry alpha as brightness: core <= colour * 80/255; halos are fainter, overlaps may add up
    assert brightest <= colours * 80 / 255 * 2.5 + 2


def test_front_sprites_use_at_most_the_80_rung():
    assert ambient.FRONT_TOP_RUNG == 1 and config.AMBIENT_ALPHA_LADDER[ambient.FRONT_TOP_RUNG] <= 90


def test_draw_moves_with_the_shake_like_entities():
    """A shake of (8, -5) is the same picture shifted by (8, -5), exactly like the entities."""
    field = _settled(4, 8, seconds=6.0)
    plain, shaken = pygame.Surface((W, H)), pygame.Surface((W, H))
    field.draw_back(plain, CAM, NO_SHAKE)
    field.draw_back(shaken, CAM, Vector2(8, -5))
    assert pygame.image.tobytes(plain, "RGB") != pygame.image.tobytes(shaken, "RGB")
    interior = pygame.Rect(20, 20, W - 40, H - 40)
    assert pygame.image.tobytes(plain.subsurface(interior).copy(), "RGB") == \
        pygame.image.tobytes(shaken.subsurface(interior.move(8, -5)).copy(), "RGB")


def test_per_frame_cost_stays_small():
    """Loose guard (measured ~0.03 ms update + ~0.1 ms draw): the plan allows 0.25 ms in a fight frame."""
    field = _settled(4, 1, seconds=2.0)          # the largest field: 120 snow motes
    surface = pygame.Surface((W, H))
    best = 1e9
    for _ in range(5):
        t = time.perf_counter()
        for _ in range(100):
            field.update(1 / 60, CAM)
            field.draw_back(surface, CAM, NO_SHAKE)
            field.draw_front(surface, CAM, NO_SHAKE)
        best = min(best, (time.perf_counter() - t) / 100 * 1000)
    assert best < 1.0


# --- Game integration ---------------------------------------------------------------------------------------

@pytest.fixture
def game(make_game, isolated_save, monkeypatch):
    g = make_game()
    monkeypatch.setattr(g.audio, "play", lambda name, scale=1.0: None)
    monkeypatch.setattr(g.audio, "play_act_music", lambda act: None)
    monkeypatch.setattr(g.audio, "play_menu_music", lambda: None)
    g._start_new_run()
    g.story = None
    g.state = GameState.OVERWORLD
    return g


def _enter_fight(game) -> None:
    node = next(n for n in game.overworld.nodes.values() if n.node_type == NodeType.FIGHT)
    game._load_encounter(node)
    game.state = GameState.PLAYING


def test_no_field_until_an_encounter_loads_then_one_per_map_load(game):
    assert game.ambient is None
    game._draw_game()                       # drawing without a field is fine
    _enter_fight(game)
    assert isinstance(game.ambient, AmbientField) and game.ambient.theme_index == game.overworld.act_index
    first = game.ambient
    _enter_fight(game)
    assert game.ambient is not first       # a fresh field per map load


def test_the_field_only_advances_in_playing(game):
    _enter_fight(game)
    t = game.ambient.t
    game._update(1 / 60)
    assert game.ambient.t > t
    for state in (GameState.SKILLS, GameState.STORY, GameState.OVERWORLD, GameState.MAIN_MENU):
        game.state = state
        t = game.ambient.t
        game._update(1 / 60)
        assert game.ambient.t == t, state


def test_updating_and_drawing_the_field_changes_no_gameplay_state_and_no_global_random(game):
    _enter_fight(game)
    random.seed(77)
    state = random.getstate()
    creatures = [(c.pos.x, c.pos.y, c.hp) for c in game.creatures]
    bosses = [(b.pos.x, b.pos.y, b.hp) for b in game.bosses]
    hazards = [(z.pos.x, z.pos.y, z.radius) for z in game.hazards.zones]
    player = (game.player.pos.x, game.player.pos.y, game.player.hp)
    particles = game.particles.active_count
    shake = (game.shake.x, game.shake.y)
    for _ in range(120):
        game._update_ambient(1 / 60)
    game._draw_game()
    assert random.getstate() == state
    assert creatures == [(c.pos.x, c.pos.y, c.hp) for c in game.creatures]
    assert bosses == [(b.pos.x, b.pos.y, b.hp) for b in game.bosses]
    assert hazards == [(z.pos.x, z.pos.y, z.radius) for z in game.hazards.zones]
    assert player == (game.player.pos.x, game.player.pos.y, game.player.hp)
    assert game.particles.active_count == particles           # the old 0.35 s particle emitter is gone
    assert (game.shake.x, game.shake.y) == shake


def test_the_field_is_not_saved(game, isolated_save):
    _enter_fight(game)
    for _ in range(30):
        game._update_ambient(1 / 60)
    game._save_game()
    text = isolated_save.read_text()
    assert "ambient" not in text and "mote" not in text
    assert set(json.loads(text)) <= {"ng_plus", "permanent", "economy", "audio_enabled", "narration_volume"}


def test_the_hud_is_drawn_after_the_motes(game):
    """Order check: the motes are drawn before the HUD call, so they can never cover it."""
    _enter_fight(game)
    order: List[str] = []
    game.ambient.draw_back = lambda *a: order.append("back")
    game.ambient.draw_front = lambda *a: order.append("front")
    game.hud.draw = lambda *a, **k: order.append("hud")
    game.player.draw = lambda *a, **k: order.append("player")
    game._draw_game()
    assert order == ["back", "front", "player", "hud"]
