"""056b: spawn-director fixes found by QA t49 (BUG-151..156). The director is still inert in real fights (no kit queues
anything), so none of these change play today; they make it safe before the first boss uses it."""
from __future__ import annotations

import math
import random

import pytest

from blob_evolution import config
from blob_evolution.entities.boss import Boss
from blob_evolution.entities.boss_spawns import POOL, SpawnDirector, SpawnQueue, SpawnRequest
from blob_evolution.entities.player import Player
from blob_evolution.entities.projectile import Projectile
from blob_evolution.utils.enums import GameState
from blob_evolution.utils.vector2 import Vector2
from test_boss_spawns import _arena, _boss, _fight

DT = 1 / 60


# --------------------------------------------------------------------------- BUG-152: delays fire on their frame

@pytest.mark.parametrize("dt", [1 / 60, 1 / 144, 1 / 30])
def test_a_whole_frame_delay_fires_on_exactly_that_frame(dt):
    """k frames of delay fire on update k for every k up to 10 s (float sums used to make 455/600 a frame late)."""
    late = []
    for k in range(1, 601):
        q = SpawnQueue(cap=1)
        q.push(SpawnRequest(POOL, Vector2(), delay=k * dt))
        fired = next(i for i in range(1, k + 3) if q.update(dt))
        if fired != k:
            late.append((k, fired))
    assert late == []


def test_a_delay_that_reaches_exactly_zero_fires_then():
    """0.5 s in 0.25 s steps is exactly 0 after two updates: due then, not one update later."""
    q = SpawnQueue()
    q.push(SpawnRequest(POOL, Vector2(), delay=0.5))
    assert q.update(0.25) == [] and len(q.update(0.25)) == 1


# --------------------------------------------------------------------------- BUG-153: full lifetime on screen

def test_a_pool_stays_for_its_whole_lifetime_in_frames():
    """delay 0.5 s, lifetime 1.0 s at 60 fps: placed on update 30, on screen for exactly 60 updates."""
    b = _boss()
    game = _arena(b)
    d = SpawnDirector()
    b.queue_spawn(POOL, Vector2(900, 900), delay=0.5, lifetime=1.0)
    present = []
    for f in range(1, 121):
        d.update(DT, game)
        present.append(bool(game.hazards.zones))
    first = present.index(True) + 1
    assert first == 30 and sum(present) == 60 and all(present[29:89])


# --------------------------------------------------------------------------- BUG-154: dt spikes

def test_a_dt_spike_cannot_place_and_remove_a_pool_unseen():
    """A 10 s frame (window drag, breakpoint) used to place a delay-1 s / life-6 s pool and remove it in the same update."""
    b = _boss()
    game = _arena(b)
    d = SpawnDirector()
    b.queue_spawn(POOL, Vector2(900, 900), delay=1.0, lifetime=6.0)
    d.update(DT, game)
    seen = 0
    d.update(10.0, game)
    seen += bool(game.hazards.zones)
    for _ in range(600):
        d.update(DT, game)
        seen += bool(game.hazards.zones)
    assert seen >= 6.0 / DT - 1                                          # its whole lifetime, give or take a frame


def test_the_director_steps_at_most_max_dt():
    q_delay = 5.0
    b = _boss()
    game = _arena(b)
    d = SpawnDirector()
    req = b.queue_spawn(POOL, Vector2(), delay=q_delay)
    d.update(DT, game)
    left = req.delay
    d.update(10.0, game)
    assert left - req.delay == pytest.approx(config.BOSS_SPAWN_MAX_DT)


# --------------------------------------------------------------------------- BUG-155: no global RNG

def test_placing_a_pool_does_not_touch_the_global_random_stream():
    b = _boss()
    game = _arena(b)
    d = SpawnDirector()
    b.queue_spawn(POOL, Vector2(900, 900))
    random.seed(3)
    before = random.getstate()
    d.update(DT, game)
    assert len(game.hazards.zones) == 1 and random.getstate() == before


def test_pool_phase_comes_from_the_director_seed_and_restarts_each_fight():
    def phases(d):
        b = _boss()
        game = _arena(b)
        for k in range(3):
            b.queue_spawn(POOL, Vector2(900 + k, 900))
        d.update(DT, game)
        return [z.phase for z in game.hazards.zones]
    d = SpawnDirector()
    first = phases(d)
    assert first == phases(SpawnDirector()) and len(set(first)) == 3 and all(0 <= p < math.tau for p in first)
    d.clear()
    assert phases(d) == first
    b = _boss()
    game = _arena(b)
    b.queue_spawn(POOL, Vector2(), phase=1.25)
    d.update(DT, game)
    assert game.hazards.zones[0].phase == 1.25                           # a kit can pass its own phase


# --------------------------------------------------------------------------- BUG-151: nothing outlives its fight

def _loaded(g, b):
    b.queue_spawn(POOL, Vector2(1500, 1500), lifetime=30.0)
    b.queue_spawn(POOL, Vector2(1600, 1500), delay=20.0)
    g.player.hp = g.player.max_hp
    g._update(DT)
    assert len(g.boss_spawns.live) == 1 and len(g.boss_spawns.queue) == 1 and len(g.hazards.zones) == 1


def _empty(g):
    return not g.boss_spawns and g.hazards.zones == []


def test_boss_death_drops_its_spawns_in_the_same_frame(make_game):
    g, b = _fight(make_game)
    _loaded(g, b)
    g._on_boss_killed(b)
    assert _empty(g)


def test_a_killing_shot_drops_the_spawns_through_the_real_collision(make_game):
    g, b = _fight(make_game)
    _loaded(g, b)
    b.hp = 1.0
    g.projectiles = [Projectile(b.pos + Vector2(-5, 0), Vector2(1, 0), 0.0, 1e6)]
    g._update_collisions()
    assert not b.active and _empty(g)


@pytest.mark.parametrize("leave", ["game_over", "main_menu", "fight_won", "pause_to_menu"])
def test_leaving_the_fight_clears_the_director(make_game, leave):
    g, b = _fight(make_game)
    _loaded(g, b)
    if leave == "game_over":
        g._trigger_game_over()
    elif leave == "fight_won":
        g._complete_level()
    else:
        if leave == "pause_to_menu":
            g.state = GameState.PAUSED
            g._update(DT)
            assert g.boss_spawns                                         # pausing keeps the fight
        g.state = GameState.MAIN_MENU
        g._update(DT)
    assert _empty(g) or (leave == "fight_won" and not g.boss_spawns)


# --------------------------------------------------------------------------- BUG-156: QA's surviving mutants

def test_a_new_encounter_clears_the_director(make_game):
    """m01: _load_encounter must clear (pending and live)."""
    g, b = _fight(make_game)
    g._start_new_run()
    while g.state == GameState.STORY:
        g._advance_story()
    b2 = Boss(Vector2(1300, 1000), 2, None)
    g.bosses = [b2]
    g.state = GameState.PLAYING
    _loaded(g, b2)
    node = next(n for n in g.overworld.get_available_nodes())
    g._load_encounter(node)
    assert not g.boss_spawns


def test_the_director_does_not_tick_while_paused(make_game):
    """m03: a paused game leaves every delay where it was."""
    g, b = _fight(make_game)
    req = b.queue_spawn(POOL, Vector2(1500, 1500), delay=1.0)
    g.player.hp = g.player.max_hp
    g._update(DT)
    left = req.delay
    g.state = GameState.PAUSED
    for _ in range(120):
        g._update(DT)
    assert req.delay == left and len(g.boss_spawns.queue) == 1


def test_the_hit_direction_comes_from_the_projectile_not_the_player(make_game):
    """m04: a shot landing on the boss's top side sets last_hit_dir up, wherever the player stands."""
    g, b = _fight(make_game)
    g.player.pos = Vector2(b.pos.x - 400, b.pos.y)                        # player to the left
    g.projectiles = [Projectile(b.pos + Vector2(0, -b.radius * 0.5), Vector2(0, 1), 0.0, 1.0)]
    g._update_collisions()
    assert b.last_hit_dir is not None and (b.last_hit_dir.x, b.last_hit_dir.y) == pytest.approx((0.0, -1.0))


def test_a_dead_boss_s_outbox_is_not_queued():
    """m09: requests a boss made in the frame it died never reach the queue."""
    b = _boss()
    game = _arena(b)
    d = SpawnDirector()
    b.queue_spawn(POOL, Vector2(), delay=1.0)
    b.active = False
    d.update(DT, game)
    assert b.spawn_outbox == [] and len(d.queue) == 0 and game.hazards.zones == []
