"""F4 (BOSS-FEASIBILITY.md): boss-shot cap, behaviours (homing, delay, lob, fade), reflectors and the on-hit hook.

F4 ships inert: no kit attaches a behaviour or places a reflector, so every boss_trace fight still hashes as on main
(checked by the existing GOLDEN tests in tests/test_boss_framework.py)."""
from __future__ import annotations

import math

import pygame
import pytest

from blob_evolution import config
from blob_evolution.data import bosses
from blob_evolution.entities.boss import Boss
from blob_evolution.entities.boss_attacks import _proj
from blob_evolution.entities.projectile import Projectile
from blob_evolution.systems import boss_shots as bs
from blob_evolution.utils.vector2 import Vector2

import hitfx_scene

DT = 1 / 60


def _boss_shot(x=0.0, y=0.0):
    return _proj(Vector2(x, y), Vector2(1, 0), 100, 5)


# ---- constants -------------------------------------------------------------------------------------------------------

def test_the_ruled_constants():
    assert config.BOSS_SHOT_CAP == 120 and config.MAX_PROJECTILES == 200
    assert config.BOSS_HOMING_TURN_DEG == 90.0
    assert config.BOSS_LOB_TIME == 0.8 and config.BOSS_LOB_PEAK == 120.0
    assert config.BOSS_SHOT_FADE == 0.25
    assert bosses.REFLECT_HURTS_PLAYER is True                     # Director, question 7


def test_a_new_projectile_carries_no_behaviour():
    p = Projectile(Vector2(0, 0), Vector2(1, 0), 10, 1)
    assert (p.behaviour, p.element, p.effect, p.fade, p.reflected) == (None, None, None, False, False)


# ---- cap -------------------------------------------------------------------------------------------------------------

def test_cap_skips_new_boss_shots_and_never_culls_existing_ones():
    shots = [_boss_shot(i) for i in range(118)]
    before = list(shots)
    shots += [_boss_shot(1000 + i) for i in range(5)]
    assert bs.cap_new_boss_shots(shots, 118) == 3
    assert shots[:118] == before and len(shots) == 120
    assert [p.pos.x for p in shots[118:]] == [1000, 1001]           # the first new ones are kept, the rest skipped


def test_cap_counts_only_live_boss_shots():
    dead = [_boss_shot() for _ in range(130)]
    for p in dead:
        p.active = False
    other = [Projectile(Vector2(0, 0), Vector2(1, 0), 10, 1, from_player=False) for _ in range(30)]   # creature shots
    shots = dead + other + [_boss_shot() for _ in range(10)]
    assert bs.cap_new_boss_shots(shots, 160) == 0 and len(shots) == 170


def test_cap_also_respects_the_overall_total():
    shots = [Projectile(Vector2(0, 0), Vector2(1, 0), 10, 1) for _ in range(199)] + [_boss_shot(), _boss_shot()]
    assert bs.cap_new_boss_shots(shots, 199) == 1 and len(shots) == 200


def test_cap_leaves_non_boss_new_entries_alone():
    shots = [_boss_shot() for _ in range(120)]
    shots.append(Projectile(Vector2(0, 0), Vector2(1, 0), 10, 1))
    assert bs.cap_new_boss_shots(shots, 120) == 0 and len(shots) == 121


def test_boss_update_applies_the_cap(monkeypatch):
    b = Boss(Vector2(1200, 1100), 0, None)
    shots = [_boss_shot() for _ in range(config.BOSS_SHOT_CAP)]
    b.shoot_cooldown = b.special_cooldown = 0.0
    b.update(DT, Vector2(1000, 1000), shots)
    assert len(shots) == config.BOSS_SHOT_CAP


def test_boss_update_below_the_cap_keeps_every_shot():
    b = Boss(Vector2(1200, 1100), 0, None)
    shots: list = []
    b.shoot_cooldown = b.special_cooldown = 0.0
    b.update(DT, Vector2(1000, 1000), shots)
    assert shots and all(p.kind == "boss" for p in shots)


# ---- behaviours ------------------------------------------------------------------------------------------------------

def test_homing_turns_at_most_the_turn_rate():
    p = _boss_shot()
    p.behaviour = bs.Homing(lambda: Vector2(0, 500), duration=4.0)
    p.update(0.5)
    ang = math.degrees(math.atan2(p.vel.y, p.vel.x))
    assert ang == pytest.approx(45.0, abs=1e-6) and p.vel.length() == pytest.approx(100)


def test_homing_stops_turning_after_its_duration():
    p = _boss_shot()
    p.behaviour = bs.Homing(lambda: Vector2(0, 500), duration=0.1)
    for _ in range(60):
        p.update(DT)
    ang = math.degrees(math.atan2(p.vel.y, p.vel.x))
    assert ang == pytest.approx(9.0, abs=1.6)                       # ~0.1 s at 90 deg/s, then straight


def test_delayed_holds_still_then_moves():
    p = _boss_shot()
    p.behaviour = bs.Delayed(0.5)
    p.update(0.5)
    assert p.pos.x == 0
    p.update(0.1)
    assert p.pos.x == pytest.approx(10)


def test_lob_arcs_to_the_target_and_lands_once():
    landed = []
    p = _boss_shot()
    p.behaviour = bs.Lob(Vector2(0, 0), Vector2(200, 0), land=landed.append)
    p.update(config.BOSS_LOB_TIME / 2)
    assert p.behaviour.height == pytest.approx(config.BOSS_LOB_PEAK) and p.pos.x == pytest.approx(100)
    assert not p.collides_with(p.pos, 50)                           # airborne: hits nothing
    p.update(config.BOSS_LOB_TIME / 2)
    assert not p.active and len(landed) == 1 and landed[0].x == pytest.approx(200)


def test_fade_ramps_over_the_last_quarter_second():
    p = _boss_shot()
    assert bs.fade_alpha(p) == 255
    p.fade = True
    p.lifetime = 1.0
    assert bs.fade_alpha(p) == 255
    p.lifetime = config.BOSS_SHOT_FADE / 2
    assert bs.fade_alpha(p) == 127
    p.lifetime = 0.0
    assert bs.fade_alpha(p) == 0


def test_faded_sprites_are_cached():
    s = pygame.Surface((8, 8), pygame.SRCALPHA)
    assert bs.faded_sprite(s, 100) is bs.faded_sprite(s, 100)


# ---- reflectors ------------------------------------------------------------------------------------------------------

def test_reflector_turns_a_shot_once():
    p = _boss_shot(10, 0)
    r = bs.Reflector(Vector2(10, 0), 5, damage_mult=0.5)
    assert bs.reflect_shots([p], [r]) == 1
    assert p.vel.x == -100 and p.damage == 2.5 and p.reflected and not p.from_player
    assert bs.reflect_shots([p], [r]) == 0


def test_reflected_player_shot_turns_hostile_by_default_and_stays_friendly_when_off():
    p = Projectile(Vector2(0, 0), Vector2(1, 0), 10, 1, from_player=True)
    bs.reflect_shots([p], [bs.Reflector(Vector2(0, 0), 5)])
    assert not p.from_player
    q = Projectile(Vector2(0, 0), Vector2(1, 0), 10, 1, from_player=True)
    bs.reflect_shots([q], [bs.Reflector(Vector2(0, 0), 5)], hurts_player=False)
    assert q.from_player


# ---- reflected player shot vs the player: the normal enemy-shot rules ----------------------------------------------

@pytest.fixture
def g(make_game):
    pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    game = hitfx_scene.make_scene_game(0)
    game.creatures, game.bosses, game.projectiles, game.xp_orbs = [], [], [], []
    game.player.max_hp = game.player.hp = 1e9
    game.player.invulnerable = 0.0
    game.player.has_shield = False
    return game


def _reflected_at_player(game):
    p = Projectile(game.player.pos.copy(), Vector2(1, 0), 0, 7, from_player=True)
    game.projectiles = [p]
    game.reflectors = [bs.Reflector(game.player.pos.copy(), 4)]
    return p


def _hurts(game, n0):
    return sum(1 for n, _v in game.sounds[n0:] if n == "hurt")


def test_a_reflected_player_shot_hurts_the_player_with_one_hurt_sound(g):
    n0, hp0 = len(g.sounds), g.player.hp
    p = _reflected_at_player(g)
    g._update_projectiles(DT)
    g._update_projectiles(DT)
    assert g.player.hp < hp0 and not p.active and _hurts(g, n0) == 1


def test_a_reflected_shot_respects_invulnerability(g):
    g.player.invulnerable = 0.5
    n0, hp0 = len(g.sounds), g.player.hp
    p = _reflected_at_player(g)
    g._update_projectiles(DT)
    assert g.player.hp == hp0 and not p.active and _hurts(g, n0) == 0


def test_a_reflected_shot_is_eaten_by_the_shield(g):
    g.player.has_shield = True
    n0, hp0 = len(g.sounds), g.player.hp
    p = _reflected_at_player(g)
    g._update_projectiles(DT)
    assert g.player.hp == hp0 and not g.player.has_shield and not p.active and _hurts(g, n0) == 0


def test_two_reflected_shots_in_one_frame_give_one_hit_and_one_hurt_sound(g):
    n0, hp0 = len(g.sounds), g.player.hp
    a, b = _reflected_at_player(g), Projectile(g.player.pos.copy(), Vector2(1, 0), 0, 7, from_player=True)
    g.projectiles.append(b)
    g._update_projectiles(DT)
    assert hp0 - g.player.hp > 0 and _hurts(g, n0) == 1             # the second lands in the i-frames


def test_on_hit_effect_runs_only_when_the_hit_lands(g):
    seen = []
    p = Projectile(g.player.pos.copy(), Vector2(1, 0), 0, 3, from_player=False)
    p.effect = seen.append
    g.projectiles = [p]
    g._update_projectiles(DT)
    assert seen == [g.player]
    g.player.invulnerable = 0.5
    q = Projectile(g.player.pos.copy(), Vector2(1, 0), 0, 3, from_player=False)
    q.effect = seen.append
    g.projectiles = [q]
    g._update_projectiles(DT)
    assert len(seen) == 1


def test_no_kit_places_a_reflector_or_attaches_a_behaviour():
    for act in range(10):
        b = Boss(Vector2(1200, 1100), act, None)
        shots: list = []
        for _ in range(600):
            b.update(DT, Vector2(1000, 1000), shots)
        assert all(p.behaviour is None and p.effect is None and not p.fade for p in shots), act
