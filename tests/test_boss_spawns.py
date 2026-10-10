"""TASK-056 framework: the boss spawn queue / director (timed pools via HazardZone) and hit direction on bosses."""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from blob_evolution import config
from blob_evolution.entities import boss_spawns
from blob_evolution.entities.boss import Boss
from blob_evolution.entities.boss_spawns import POOL, SpawnDirector, SpawnQueue, SpawnRequest
from blob_evolution.entities.player import Player
from blob_evolution.systems.hazards import HazardManager, HazardType
from blob_evolution.utils.enums import GameState
from blob_evolution.utils.vector2 import Vector2

DT = 1 / 60


def _boss(act: int = 0) -> Boss:
    """A layer warden at a fixed spot."""
    random.seed(7)
    return Boss(Vector2(1000, 1000), act, None)


def _arena(*bosses: Boss) -> SimpleNamespace:
    """The two things the director reads from the game: bosses and hazards."""
    return SimpleNamespace(bosses=list(bosses), hazards=HazardManager())


# --------------------------------------------------------------------------- queue

def test_queue_hands_out_due_requests_in_push_order_after_their_delay():
    """Each request waits its own delay; due ones come out together, oldest first."""
    q = SpawnQueue()
    a, b, c = (SpawnRequest("x", Vector2(i, 0), delay=d) for i, d in ((1, 0.0), (2, 0.04), (3, 0.0)))
    for r in (a, b, c):
        assert q.push(r)
    assert q.update(DT) == [a, c] and len(q) == 1
    assert q.update(DT) == [] and q.update(DT) == [b] and len(q) == 0


def test_queue_is_capped_and_counts_what_it_drops():
    """Past config.BOSS_SPAWN_QUEUE_MAX the push fails and is counted."""
    q = SpawnQueue()
    for i in range(config.BOSS_SPAWN_QUEUE_MAX):
        assert q.push(SpawnRequest("x", Vector2(i, 0), delay=1.0))
    assert not q.push(SpawnRequest("x", Vector2()))
    assert (len(q), q.dropped) == (config.BOSS_SPAWN_QUEUE_MAX, 1)
    assert SpawnQueue(cap=2).cap == 2


def test_queue_drops_one_owner_s_requests():
    """drop_owner forgets that boss's pending requests only."""
    b1, b2 = _boss(), _boss()
    q = SpawnQueue()
    for owner in (b1, b2, b1):
        q.push(SpawnRequest("x", Vector2(), owner, delay=1.0))
    assert q.drop_owner(b1) == 2 and [r.owner for r in q.pending] == [b2]


# --------------------------------------------------------------------------- director

def test_a_queued_pool_becomes_a_hazard_zone_then_expires():
    """Boss.queue_spawn("pool") -> a HazardZone with the request's type/radius, live for its lifetime, then gone.
    BUG-152/153: a 0.1 s delay at 60 fps places it on update 6 exactly (was 7, float drift), and a 0.5 s lifetime keeps
    it for exactly 30 frames (was 29: the placement frame's dt was counted)."""
    b = _boss()
    game = _arena(b)
    d = SpawnDirector()
    req = b.queue_spawn(POOL, Vector2(900, 900), delay=0.1, lifetime=0.5, hazard="lava", radius=40)
    assert req.owner is b and b.spawn_outbox == [req]
    for _ in range(5):
        d.update(DT, game)
    assert b.spawn_outbox == [] and len(d.queue) == 1 and game.hazards.zones == []
    d.update(DT, game)                                                  # update 6 = 0.1 s
    (zone,) = game.hazards.zones
    assert (zone.hazard_type, zone.radius, (zone.pos.x, zone.pos.y)) == (HazardType.LAVA, 40.0, (900, 900))
    assert zone._sprite is not None                                    # baked when placed, not in the first draw
    assert game.hazards.get_player_effects(Vector2(900, 900), DT)["speed_mult"] < 1.0
    for _ in range(29):
        d.update(DT, game)
    assert game.hazards.zones == [zone]                                 # 30 frames on screen (6..35)
    d.update(DT, game)
    assert game.hazards.zones == [] and d.live == []


def test_pool_defaults_come_from_config():
    """A bare pool request gets config's hazard, radius and lifetime."""
    b = _boss()
    game = _arena(b)
    d = SpawnDirector()
    b.queue_spawn(POOL, Vector2(500, 500))
    d.update(DT, game)
    (zone,) = game.hazards.zones
    want = boss_spawns.HAZARD_TYPES[config.BOSS_POOL_HAZARD]
    assert (zone.hazard_type, zone.radius) == (want, config.BOSS_POOL_RADIUS)
    assert d.live[0].left == config.BOSS_POOL_LIFETIME                  # BUG-153: counts from the next frame


def test_spawns_go_with_their_boss():
    """A dead boss's outbox, pending requests and live pools are all removed (BOSS_SPAWNS_DIE_WITH_OWNER)."""
    assert config.BOSS_SPAWNS_DIE_WITH_OWNER
    b = _boss()
    game = _arena(b)
    d = SpawnDirector()
    b.queue_spawn(POOL, Vector2(500, 500), lifetime=30.0)
    b.queue_spawn(POOL, Vector2(600, 500), delay=5.0)
    d.update(DT, game)
    assert len(game.hazards.zones) == 1 and len(d.queue) == 1
    b.queue_spawn(POOL, Vector2(700, 500))
    b.active = False
    d.update(DT, game)
    assert b.spawn_outbox == [] and game.hazards.zones == [] and d.live == []
    for _ in range(400):
        d.update(DT, game)
    assert game.hazards.zones == [] and len(d.queue) == 0


def test_other_kinds_use_registered_handlers_and_unknown_kinds_are_counted():
    """Later tickets register sprouts/adds/decoys; until then an unknown kind places nothing."""
    b = _boss()
    game = _arena(b)
    d = SpawnDirector()
    placed, removed = [], []
    d.register("sprout", lambda req, g: placed.append(req.params["heal"]) or req.params["heal"],
               lambda obj, g: removed.append(obj))
    b.queue_spawn("sprout", Vector2(), lifetime=DT * 1.5, heal=12)
    b.queue_spawn("decoy", Vector2())
    d.update(DT, game)
    assert placed == [12] and d.unhandled == 1 and removed == []
    d.update(DT, game)
    assert removed == [] and d.live[0].left == pytest.approx(DT * 0.5)   # BUG-153: the placement frame is not counted
    d.update(DT, game)
    assert removed == [12] and d.live == []


def test_unowned_untimed_spawns_are_not_tracked():
    """A request with no owner and no lifetime is placed and forgotten."""
    game = _arena()
    d = SpawnDirector()
    d.register("rock", lambda req, g: "rock")
    d.queue.push(SpawnRequest("rock", Vector2()))
    d.update(DT, game)
    assert d.live == [] and len(d.queue) == 0


def test_clear_forgets_everything_and_an_idle_director_touches_nothing():
    """clear() empties queue and live list; with nothing queued update leaves the hazards alone."""
    b = _boss()
    game = _arena(b)
    d = SpawnDirector()
    b.queue_spawn(POOL, Vector2(), lifetime=9.0)
    b.queue_spawn(POOL, Vector2(), delay=9.0)
    d.update(DT, game)
    d.clear()
    assert d.live == [] and len(d.queue) == 0
    game.hazards = None                                                 # would raise if touched
    d.update(DT, game)


def _fight(make_game, act: int = 2) -> tuple:
    """A real Game in a boss fight: one warden at (1300, 1000), the player at (1000, 1000)."""
    g = make_game()
    random.seed(11)
    g.player = Player(Vector2(1000, 1000))
    g.map_gen.load_map(act, 11)
    g.creatures, g.projectiles, g.xp_orbs = [], [], []
    g.hazards.generate_for_map(g.map_gen.hazard_types, count=0, seed=11)
    b = Boss(Vector2(1300, 1000), act, None)
    g.bosses = [b]
    g.state = GameState.PLAYING
    return g, b


def test_the_game_places_boss_pools_each_frame(make_game):
    """Game._update drains the bosses' outboxes through its SpawnDirector into its own hazards."""
    g, b = _fight(make_game)
    assert isinstance(g.boss_spawns, SpawnDirector)
    b.queue_spawn(POOL, Vector2(1500, 1500), lifetime=1.0, hazard="ice")
    g.player.hp = g.player.max_hp
    g._update(DT)
    assert [z.hazard_type for z in g.hazards.zones] == [HazardType.ICE]


# --------------------------------------------------------------------------- hit direction and multipliers

def test_hit_direction_is_a_unit_vector_from_the_boss_to_the_hit():
    """hit_from sets last_hit_dir; a centre hit or no hit_from keeps the previous one."""
    b = _boss()
    assert b.last_hit_dir is None
    b.take_damage(1.0, hit_from=Vector2(1000, 1300))
    assert (b.last_hit_dir.x, b.last_hit_dir.y) == (0.0, 1.0)
    b.take_damage(1.0, hit_from=Vector2(1000, 1000))
    b.take_damage(1.0)
    assert (b.last_hit_dir.x, b.last_hit_dir.y) == (0.0, 1.0)
    b.take_damage(1.0, hit_from=Vector2(970, 960))
    assert (b.last_hit_dir.x, b.last_hit_dir.y) == pytest.approx((-0.6, -0.8))


def test_default_damage_is_main_s_formula_exactly():
    """With mult 1 and no filter, HP drops by amount * (1 + ignore_defense), bit for bit."""
    b = _boss()
    hp = b.hp
    b.take_damage(13.37, 0.1, hit_from=Vector2(1, 2))
    assert b.hp == hp - 13.37 * (1.0 + 0.1)


def test_damage_taken_mult_and_hit_filter_scale_the_hit():
    """damage_taken_mult and the hit filter (given the hit direction) multiply the damage; phases see it."""
    b = _boss()
    seen = []

    def front_guard(boss, hit_dir):
        seen.append(hit_dir)
        return 0.25 if hit_dir is not None and hit_dir.x > 0 else 1.0

    b.damage_taken_mult, b.hit_filter = 0.5, front_guard
    hp = b.hp
    b.take_damage(100.0, hit_from=Vector2(1100, 1000))
    assert b.hp == pytest.approx(hp - 12.5)
    b.take_damage(100.0, hit_from=Vector2(900, 1000))
    assert b.hp == pytest.approx(hp - 62.5)
    b.take_damage(100.0)
    assert seen[-1] is None and b.hp == pytest.approx(hp - 112.5)
    b.damage_taken_mult, b.hit_filter = 2.0, None
    b.take_damage(b.max_hp * 0.3)
    assert b.phase == 2                                                 # 0.6 of max HP through the mult: phase 2


def test_heal_clamps_and_never_undoes_a_phase():
    """heal() returns the HP gained, stops at max HP and leaves the phase alone."""
    b = _boss()
    b.take_damage(b.max_hp * 0.6)
    assert b.phase == 2
    assert b.heal(b.max_hp * 0.1) == pytest.approx(b.max_hp * 0.1)
    assert b.heal(-50.0) == 0.0
    assert b.heal(b.max_hp) == pytest.approx(b.max_hp * 0.5)
    assert b.hp == b.max_hp and b.phase == 2 and b.enraged


def test_the_game_passes_the_shot_position_as_hit_direction(make_game):
    """Player shots that hit a boss give it hit_from=shot position, so last_hit_dir points back at the player."""
    g, b = _fight(make_game)
    b.speed = 0.0
    for _ in range(90):
        g.player.hp = g.player.max_hp
        g.state = GameState.PLAYING
        g.player.shoot(b.pos, g.projectiles)
        g._update(DT)
        if b.last_hit_dir is not None:
            break
    to_player = (g.player.pos - b.pos).normalize()
    assert b.hp < b.max_hp and b.last_hit_dir.dot(to_player) > 0.8
