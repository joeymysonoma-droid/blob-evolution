"""F3: telegraph objects, the attack kit and game-side damage resolution (main's kits are covered by the boss traces)."""
from __future__ import annotations

import dataclasses
import math
import random

import pygame
import pytest

from blob_evolution import config
from blob_evolution.data import bosses as data
from blob_evolution.entities import boss as boss_module
from blob_evolution.entities import boss_attacks
from blob_evolution.entities.boss import Boss
from blob_evolution.entities.boss_telegraphs import (ATTACKS, Telegraph, draw_telegraphs, element_for,
                                                     resolve_landed)
from blob_evolution.utils import boss_shapes
from blob_evolution.utils.enums import GameState
from blob_evolution.utils.vector2 import Vector2

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def _display():
    pygame.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))


# --- timings are data ---------------------------------------------------------------------------------------------

def test_main_s_timings_live_in_data_with_main_s_values():
    t = data.TELEGRAPH
    assert (t.special, t.dash, t.blink, t.ring_grow, t.frost_ring, t.void_ring) == (0.7, 0.35, 0.4, 0.8, 0.9, 1.0)
    assert set(data.TELEGRAPH_WARN) == {"zone", "lane", "mark", "fan", "ring", "safe"}


def test_the_special_telegraph_follows_the_data_table(monkeypatch):
    monkeypatch.setattr(boss_module, "TELEGRAPH", dataclasses.replace(data.TELEGRAPH, special=1.25))
    b = Boss(Vector2(1000, 1000), 2, None)
    random.seed(1)
    b._special_attack(Vector2(1300, 1000), [])
    assert b.telegraph == 1.25


@pytest.mark.parametrize("field,mover", [("dash", boss_attacks.move_circle_dash), ("blink", boss_attacks.move_blink)])
def test_dash_and_blink_warnings_follow_the_data_table(monkeypatch, field, mover):
    monkeypatch.setattr(boss_attacks, "TELEGRAPH", dataclasses.replace(data.TELEGRAPH, **{field: 0.93}))
    b = Boss(Vector2(1000, 1000), 3, None)
    b.clone_timer = 0.0
    monkeypatch.setattr(boss_attacks.random, "random", lambda: 0.0)       # the dash chance always passes
    mover(b, DT, Vector2(1300, 1000), 60.0)
    assert (b.telegraph, b.telegraph_type) == (0.93, field)


def test_kit_warning_defaults_come_from_telegraph_warn(monkeypatch):
    monkeypatch.setitem(data.TELEGRAPH_WARN, "mark", 0.55)
    assert Telegraph("mark", (0, 0, 10)).warn == 0.55
    assert Telegraph("mark", (0, 0, 10), warn=0.2).warn == 0.2


# --- telegraph geometry and lifetime ------------------------------------------------------------------------------

@pytest.mark.parametrize("kind,geom,inside,outside", [
    ("zone", (100, 100, 50), (140, 100), (200, 100)),
    ("mark", (100, 100, 20), (100, 115), (100, 150)),
    ("ring", (0, 0, 100, 140), (120, 0), (60, 0)),
    ("lane", (0, 0, 300, 0, 40), (150, 15), (150, 60)),
    ("fan", (0, 0, 0.0, 0.6, 300), (200, 30), (200, 150)),
    ("safe", (0, 0, 200, 200), (300, 300), (100, 100)),
])
def test_each_kind_hits_inside_and_misses_outside(kind, geom, inside, outside):
    t = Telegraph(kind, geom)
    assert t.hits(Vector2(*inside), 5) and not t.hits(Vector2(*outside), 5)


def test_a_player_overlapping_the_edge_is_hit():
    assert Telegraph("zone", (0, 0, 50)).hits(Vector2(60, 0), 12)
    assert not Telegraph("zone", (0, 0, 50)).hits(Vector2(70, 0), 12)


def test_unknown_kind_is_refused():
    with pytest.raises(ValueError):
        Telegraph("cone", (0, 0, 1))


def test_a_telegraph_lands_on_exactly_one_update_then_is_done():
    t = Telegraph("zone", (0, 0, 10), warn=0.1)
    seen = []
    for _ in range(12):
        t.update(DT)
        seen.append(t.landed)
    assert seen.count(True) == 1 and t.done and t.progress == 1.0


# --- the kit on the boss ------------------------------------------------------------------------------------------

def test_starting_and_running_kit_attacks_leaves_the_global_rng_alone():
    b = Boss(Vector2(1000, 1000), 4, None)
    state = random.getstate()
    for kind in ("zone", "lane", "mark", "fan", "ring", "safe"):
        b.start_attack("telegraph_strike", Vector2(1200, 1000), [], kind=kind)
    for _ in range(120):
        b._update_kit(DT, Vector2(1200, 1000), [])
    assert random.getstate() == state and not b.attacks and not b.telegraphs


def test_a_boss_without_kit_attacks_never_builds_a_context(monkeypatch):
    b = Boss(Vector2(1000, 1000), 9, None)
    monkeypatch.setattr(b, "_update_kit", lambda *a: (_ for _ in ()).throw(AssertionError("kit ran")))
    for _ in range(60):
        b.update(DT, Vector2(1300, 1000), [])


def test_telegraph_strike_uses_the_boss_element_and_damage():
    b = Boss(Vector2(1000, 1000), 6, None)
    b.start_attack("telegraph_strike", Vector2(1100, 1000), [])
    t = b.telegraphs[0]
    assert t.element == element_for(6) == "dream" and t.damage == b.damage and t.warn == data.TELEGRAPH_WARN["zone"]
    assert "telegraph_strike" in ATTACKS


# --- the game resolves damage -------------------------------------------------------------------------------------

@pytest.fixture
def fight(make_game, monkeypatch):
    g = make_game()
    for name in ("play", "play_act_music", "play_menu_music"):
        monkeypatch.setattr(g.audio, name, lambda *a, **k: None)
    random.seed(77)
    g._start_new_run()
    g.story = None
    g.creatures, g.projectiles, g.xp_orbs = [], [], []
    g.hazards.zones = []
    b = Boss(Vector2(g.player.pos.x + 600, g.player.pos.y), 2, None)
    b.shoot_cooldown = b.special_cooldown = 1e9            # only the kit acts
    g.bosses = [b]
    g.state = GameState.PLAYING
    return g, b


def _run(g, seconds):
    for _ in range(int(seconds * 60)):
        g.state = GameState.PLAYING
        g._update_playing(DT)


def test_a_landed_zone_on_the_player_deals_its_damage_once(fight):
    g, b = fight
    g.player.invulnerable = 0
    hp, hits, real = g.player.hp, [], g.player.take_damage
    g.player.take_damage = lambda amount: (hits.append(amount), real(amount))[1]
    b.start_attack("telegraph_strike", g.player.pos.copy(), [], kind="zone", radius=80.0, damage=13.0, warn=0.3)
    _run(g, 0.2)
    assert hits == [] and g.player.hp == hp
    _run(g, 0.4)
    assert hits == [13.0] and g.player.hp < hp and not b.telegraphs
    _run(g, 1.0)
    assert hits == [13.0]


def test_a_landed_zone_away_from_the_player_deals_nothing(fight):
    g, b = fight
    hp = g.player.hp
    far = g.player.pos + Vector2(400, 0)
    b.start_attack("telegraph_strike", far, [], kind="zone", radius=60.0, damage=13.0, warn=0.2)
    _run(g, 0.5)
    assert g.player.hp == hp


def test_invulnerability_absorbs_a_landed_telegraph(fight):
    g, b = fight
    hp = g.player.hp
    b.start_attack("telegraph_strike", g.player.pos.copy(), [], kind="zone", radius=80.0, damage=13.0, warn=0.2)
    g.player.invulnerable = 5.0
    _run(g, 0.5)
    assert g.player.hp == hp


def test_resolve_counts_only_landed_touching_damage():
    a = Telegraph("zone", (0, 0, 50), warn=0.0, damage=5)
    b = Telegraph("zone", (0, 0, 50), warn=1.0, damage=7)
    c = Telegraph("zone", (500, 0, 50), warn=0.0, damage=9)
    for t in (a, b, c):
        t.update(DT)
    assert resolve_landed([a, b, c], Vector2(0, 0), 10) == 5


# --- debug renderer -----------------------------------------------------------------------------------------------

def test_every_kind_draws_and_redraws_from_the_kit_cache():
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    cam, shake = Vector2(1000, 1000), Vector2(0, 0)
    tgs = [Telegraph("zone", (1000, 1000, 60), "fire"), Telegraph("lane", (900, 900, 1100, 950, 50), "frost"),
           Telegraph("mark", (950, 1050, 30), "void"), Telegraph("fan", (1000, 1000, 0.5, 0.7, 200), "echo"),
           Telegraph("ring", (1000, 1000, 80, 120), "anchor"), Telegraph("safe", (900, 900, 200, 200), "growth")]
    for t in tgs:
        screen.fill((0, 0, 0))
        draw_telegraphs(screen, cam, shake, [t])
        black = pygame.mask.from_threshold(screen, (0, 0, 0), (1, 1, 1, 255)).count()
        assert black < screen.get_width() * screen.get_height(), t.kind
    draw_telegraphs(screen, cam, shake, tgs)
    cached = len(boss_shapes._kit)
    for _ in range(3):
        draw_telegraphs(screen, cam, shake, tgs)
    assert len(boss_shapes._kit) == cached
