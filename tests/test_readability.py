"""TASK-043 readability pass: contact shadows, outlined shots, XP orbs by value, hit sparks at the impact point.

Visual only: hitboxes, speeds, damage and spawns are untouched. Covers the ten acceptance tests of
handoffs/TASK-043-readability.md (the tenth, "all existing tests pass", is the rest of the suite) plus the toggle:
GFX_READABILITY = False draws exactly what main (ad075e2) drew.
"""
from __future__ import annotations

import colorsys
import hashlib
import math
import random
import time
from typing import Callable, List, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.entities import creature as creature_module
from blob_evolution.entities import pickups as pickups_module
from blob_evolution.entities import projectile as projectile_module
from blob_evolution.entities.boss import Boss, _proj
from blob_evolution.entities.creature import Creature
from blob_evolution.entities.pickups import XPOrb, get_xp_sprite, xp_sprite_count, xp_tier
from blob_evolution.entities.player import Player
from blob_evolution.entities.projectile import Projectile, get_shot_sprite, shot_sprite_count
from blob_evolution.maps.generator import MapGenerator
from blob_evolution.systems.ambient import AmbientField
from blob_evolution.systems.overworld import OverworldMap
from blob_evolution.utils import graphics, layers
from blob_evolution.utils.enums import CreatureType, GameState, NodeType
from blob_evolution.utils.graphics import draw_contact_shadow, get_graphics_cache, get_shadow_sprite
from blob_evolution.utils.vector2 import Vector2

CAM = Vector2(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2)      # with this camera a world point lands on the same screen point
NO_SHAKE = Vector2(0, 0)
BOSS_COLOURS = [None, (80, 200, 100), (140, 190, 255), (100, 140, 220), (80, 50, 120), (160, 210, 255),
                (90, 130, 200), (210, 235, 255), (230, 200, 100), (190, 120, 255), (60, 40, 100)]


@pytest.fixture(scope="module", autouse=True)
def _display():
    pygame.init()
    pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    yield


def _blank() -> pygame.Surface:
    surf = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    surf.fill((110, 110, 110))
    return surf


def _shot(kind: str, x: float = 600, y: float = 400, colour=None) -> Projectile:
    if kind == "boss":
        p = _proj(Vector2(x, y), Vector2(1, 0), 0, 1, colour)
    else:
        p = Projectile(Vector2(x, y), Vector2(1, 0), 0, 1, from_player=(kind == "player"))
    return p


def _luma(rgb) -> float:
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0


# --- 1. hitboxes unchanged ---------------------------------------------------------------------------------------

def test_collision_radii_and_formulas_are_unchanged():
    assert _shot("player").radius == 5 and _shot("enemy").radius == 6 and _shot("boss").radius == 6
    for value in (0, 5, 19, 20, 59, 60, 119, 120, 160, 400, 5000):
        assert XPOrb(Vector2(), value).radius == 6 + min(value // 20, 8)


def test_hit_tests_match_main_for_1000_random_positions():
    rng = random.Random(1043)
    hits = {True: 0, False: 0}
    for _ in range(1000):
        pos = Vector2(rng.uniform(-40, 40), rng.uniform(-40, 40))
        other = Vector2(rng.uniform(-40, 40), rng.uniform(-40, 40))
        other_r = rng.uniform(4, 30)
        kind = rng.choice(("player", "enemy", "boss"))
        shot = _shot(kind)
        shot.pos.set(pos.x, pos.y)
        want = math.hypot(pos.x - other.x, pos.y - other.y) < {"player": 5, "enemy": 6, "boss": 6}[kind] + other_r
        assert shot.collides_with(other, other_r) == want
        hits[want] += 1
        orb = XPOrb(pos, rng.choice((5, 25, 70, 150, 400)))
        want_orb = math.hypot(pos.x - other.x, pos.y - other.y) < 6 + min(orb.value // 20, 8) + other_r
        assert orb.collides_with(other, other_r) == want_orb
    assert hits[True] > 100 and hits[False] > 100          # both outcomes really occur


def test_boss_shots_get_kind_boss_and_keep_their_colour():
    for colour in BOSS_COLOURS[1:]:
        p = _shot("boss", colour=colour)
        assert p.kind == "boss" and p.color == colour and p.radius == 6
    assert _shot("boss").color == config.COLOR_PROJECTILE_ENEMY
    assert _shot("player").kind == "player" and _shot("enemy").kind == "enemy"


# --- 2. no per-frame Surface allocation -------------------------------------------------------------------------

def _surface_counter(monkeypatch) -> List[int]:
    made = [0]
    real = pygame.Surface

    class Counting(real):                                   # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            made[0] += 1
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(pygame, "Surface", Counting)
    return made


def _alloc_workload(screen) -> Tuple[List[Callable[[], None]], List[Callable[[], None]], List[Callable[[], None]]]:
    shots = []
    for i, colour in enumerate(BOSS_COLOURS):
        for kind in ("player", "enemy", "boss"):
            p = _shot(kind, 300 + 7 * i, 300 + 3 * i, colour if kind == "boss" else None)
            shots.append(lambda p=p: p.draw(screen, CAM, NO_SHAKE))
    orbs = []
    for value in (5, 25, 70, 150, 400):
        for life in (30.0, 2.0, 0.5):                       # normal and blinking
            o = XPOrb(Vector2(500, 500), value)
            o.lifetime = life
            orbs.append(lambda o=o: o.draw(screen, CAM, NO_SHAKE))
    shadows = [lambda r=r: draw_contact_shadow(screen, 600, 400, r) for r in (4, 9, 15, 20, 35, 50, 80, 100)]
    return shots, orbs, shadows


def test_shot_orb_and_shadow_draws_allocate_no_surfaces_after_warmup(monkeypatch):
    screen = _blank()
    shots, orbs, shadows = _alloc_workload(screen)
    for fn in shots + orbs + shadows:                       # warm-up: builds the caches
        fn()
    made = _surface_counter(monkeypatch)
    for i in range(200):
        shots[i % len(shots)]()
    for i in range(100):
        orbs[i % len(orbs)]()
    for i in range(100):
        shadows[i % len(shadows)]()
    assert made[0] == 0


def test_the_legacy_path_still_allocates_so_the_counter_is_meaningful(monkeypatch):
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    screen = _blank()
    made = _surface_counter(monkeypatch)
    _shot("player").draw(screen, CAM, NO_SHAKE)
    XPOrb(Vector2(500, 500), 30).draw(screen, CAM, NO_SHAKE)
    assert made[0] == 2


def test_sprites_are_built_once_and_reused():
    a, b = get_shot_sprite("enemy", config.COLOR_PROJECTILE_ENEMY), get_shot_sprite("enemy", config.COLOR_PROJECTILE_ENEMY)
    assert a is b
    assert get_xp_sprite(3, 10) is get_xp_sprite(3, 10) and get_xp_sprite(3, 10) is not get_xp_sprite(4, 10)
    assert get_shadow_sprite(20) is get_shadow_sprite(20) and get_shadow_sprite(20) is get_shadow_sprite(21)   # 2 px quantised
    assert get_shadow_sprite(20) is not get_shadow_sprite(24)


# --- contact shadow ---------------------------------------------------------------------------------------------

def test_shadow_sprite_follows_the_spec_geometry():
    for radius in (4, 9, 15, 20, 47, 100):
        r_q = max(4, 2 * round(radius / 2))
        sprite = get_shadow_sprite(radius)
        assert sprite.get_size() == (int(2.3 * r_q) + 4, int(1.2 * r_q) + 4)
        assert sprite.get_flags() & pygame.SRCALPHA
        cx, cy = sprite.get_width() // 2, sprite.get_height() // 2
        assert sprite.get_at((cx, cy))[:4] == (0, 0, 0, 90)                         # inner ellipse
        assert sprite.get_at((0, 0))[3] == 0                                         # corners stay clear
        alphas = {sprite.get_at((x, y))[3] for x in range(sprite.get_width()) for y in range(sprite.get_height())}
        assert alphas == {0, 38, 90}                                                 # soft outer ring + inner, only black
        assert all(sprite.get_at((x, y))[:3] == (0, 0, 0) for x in range(0, sprite.get_width(), 3) for y in range(0, sprite.get_height(), 3)
                   if sprite.get_at((x, y))[3] > 0)


def test_shadow_cache_stays_within_fifty_entries_for_radii_4_to_100():
    cache = get_graphics_cache()
    for radius in range(1, 101):
        get_shadow_sprite(radius)
    assert 1 <= cache.shadow_count() <= 50
    cache.clear()
    assert cache.shadow_count() == 0


def test_shadow_is_a_crescent_below_the_body_and_never_lightens():
    screen = _blank()
    before = screen.copy()
    draw_contact_shadow(screen, 600, 400, 20)
    changed = [(x, y) for x in range(540, 660) for y in range(380, 450) if screen.get_at((x, y)) != before.get_at((x, y))]
    assert changed
    assert all(_luma(screen.get_at(p)) <= _luma(before.get_at(p)) for p in changed)
    ys = [y for _, y in changed]
    assert min(ys) < 400 + 20 * 0.78 < max(ys) and sum(ys) / len(ys) > 400 + 8       # centred about 0.78 r below the entity
    assert abs(sum(x for x, _ in changed) / len(changed) - 600) < 1.5


def test_shadow_is_skipped_far_off_screen_and_drawn_near_the_edge():
    screen = _blank()
    before = screen.copy()
    draw_contact_shadow(screen, -20 - 21, 400, 20)                                    # centre more than radius + 20 outside
    draw_contact_shadow(screen, 600, config.SCREEN_HEIGHT + 20 + 21, 20)
    assert pygame.image.tobytes(screen, "RGB") == pygame.image.tobytes(before, "RGB")
    draw_contact_shadow(screen, 5, 400, 20)
    assert pygame.image.tobytes(screen, "RGB") != pygame.image.tobytes(before, "RGB")


class _Spy:
    def __init__(self):
        self.calls: List[tuple] = []

    def shadow(self, surface, x, y, radius):
        self.calls.append(("shadow", round(float(x), 3), round(float(y), 3), radius))


def test_entities_draw_their_shadow_with_the_base_radius_before_the_blob(monkeypatch):
    order: List[str] = []
    spy = _Spy()
    for module in ("creature", "boss", "player"):
        mod = __import__(f"blob_evolution.entities.{module}", fromlist=["x"])
        monkeypatch.setattr(mod, "draw_contact_shadow", lambda s, x, y, r, _spy=spy: (order.append("shadow"), _spy.shadow(s, x, y, r)))
        monkeypatch.setattr(mod, "draw_blob", lambda *a, **k: order.append("blob"))
    screen = _blank()
    random.seed(7)
    c = Creature(Vector2(600, 400), CreatureType.BASIC, size=17.0)
    c.draw(screen, CAM, NO_SHAKE)
    b = Boss(Vector2(600, 400), 3, None)
    b.draw(screen, CAM, NO_SHAKE)
    p = Player(Vector2(600, 400))
    p.draw(screen, CAM, NO_SHAKE)
    assert order == ["shadow", "blob"] * 3
    assert [c_[3] for c_ in spy.calls] == [17.0, b.size, p.size]                        # the same base radius draw_blob gets
    assert all(c_[1] == 600 and c_[2] == 400 for c_ in spy.calls)


def test_phased_creatures_have_no_shadow(monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(creature_module, "draw_contact_shadow", lambda s, x, y, r: spy.shadow(s, x, y, r))
    screen = _blank()
    random.seed(8)
    c = Creature(Vector2(600, 400), CreatureType.PHANTOM, size=15.0)
    c.draw(screen, CAM, NO_SHAKE)
    assert len(spy.calls) == 1
    c.phased = True
    c.draw(screen, CAM, NO_SHAKE)
    assert len(spy.calls) == 1


def test_toggle_off_draws_no_shadows(monkeypatch):
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    spy = _Spy()
    for mod in (creature_module, __import__("blob_evolution.entities.boss", fromlist=["x"]),
                __import__("blob_evolution.entities.player", fromlist=["x"])):
        monkeypatch.setattr(mod, "draw_contact_shadow", lambda s, x, y, r: spy.shadow(s, x, y, r))
    screen = _blank()
    random.seed(9)
    Creature(Vector2(600, 400)).draw(screen, CAM, NO_SHAKE)
    Boss(Vector2(600, 400), 0, None).draw(screen, CAM, NO_SHAKE)
    Player(Vector2(600, 400)).draw(screen, CAM, NO_SHAKE)
    assert spy.calls == []


# --- shots and orbs: look ----------------------------------------------------------------------------------------

def test_new_colours_and_constants():
    assert config.COLOR_PROJECTILE_PLAYER == (120, 255, 170) and config.COLOR_PROJECTILE_ENEMY == (255, 150, 50)
    assert config.XP_TIER_THRESHOLDS == (20, 60, 120) and config.GFX_READABILITY is True
    assert config.SHOT_DRAW_RADIUS == {"player": 5, "enemy": 6, "boss": 8}


@pytest.mark.parametrize("kind,r", [("player", 5), ("player", 6), ("enemy", 5), ("enemy", 6)])
def test_grayscale_centre_of_a_player_shot_is_bright_and_of_an_enemy_shot_dark(kind, r):
    sprite = projectile_module._build_shot_sprite(kind, r, config.COLOR_PROJECTILE_PLAYER if kind == "player" else config.COLOR_PROJECTILE_ENEMY)
    screen = pygame.Surface((60, 60))
    screen.fill((128, 128, 128))
    screen.blit(sprite, (30 - sprite.get_width() // 2, 30 - sprite.get_height() // 2))
    centre = [_luma(screen.get_at((30 + dx, 30 + dy))) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
    if kind == "player":
        assert min(centre) >= 0.9
    else:
        assert max(centre) <= 0.15


def test_player_and_enemy_shots_differ_by_shape_not_only_colour():
    screen = pygame.Surface((60, 60))
    screen.fill((128, 128, 128))
    out = {}
    for kind in ("player", "enemy"):
        s = screen.copy()
        sprite = get_shot_sprite(kind, config.COLOR_PROJECTILE_PLAYER if kind == "player" else config.COLOR_PROJECTILE_ENEMY)
        s.blit(sprite, (30 - sprite.get_width() // 2, 30 - sprite.get_height() // 2))
        out[kind] = (_luma(s.get_at((30, 30))), _luma(s.get_at((30 + 4, 30))))
    assert out["player"][0] > 0.9 > 0.15 > out["enemy"][0]                              # centre: bright dot vs dark eye
    assert out["enemy"][1] > out["enemy"][0] + 0.2                                       # the enemy shot is a ring around the eye


def test_shot_sprite_layout_matches_the_spec():
    r = 6
    sprite = get_shot_sprite("enemy", (200, 100, 40))
    assert sprite.get_size() == (4 * 6 + 4, 4 * 6 + 4) and sprite.get_flags() & pygame.SRCALPHA
    c = sprite.get_width() // 2
    assert sprite.get_at((c + r + 1, c))[:3] == config.XP_OUTLINE and sprite.get_at((c + r + 1, c))[3] == 215       # dark ring at R + 2
    assert sprite.get_at((c + 2 * r - 1, c))[:4] == (200, 100, 40, config.SHOT_HALO_ALPHA)                          # halo
    assert sprite.get_at((c + r - 3, c))[:3] == (200, 100, 40)                                                        # body
    boss = get_shot_sprite("boss", (200, 100, 40))
    assert boss.get_width() == 4 * 8 + 4


def test_shot_cache_is_bounded_and_keyed_by_kind_and_colour():
    start = shot_sprite_count()
    for colour in BOSS_COLOURS[1:]:
        get_shot_sprite("boss", colour)
        get_shot_sprite("boss", colour)
    assert shot_sprite_count() - start <= len(BOSS_COLOURS)
    for i in range(80):                                                                  # a runaway colour set cannot grow the cache past its cap
        get_shot_sprite("boss", (i, 3, 4))
    assert shot_sprite_count() <= projectile_module.SPRITE_CACHE_MAX


def test_xp_tiers_follow_the_thresholds():
    expect = {0: 1, 19: 1, 20: 2, 59: 2, 60: 3, 119: 3, 120: 4, 5000: 4}
    assert {v: xp_tier(v) for v in expect} == expect


def test_tier_body_colours_have_no_orange_or_red():
    for style in config.XP_TIER_STYLE:
        hue, sat, _ = colorsys.rgb_to_hsv(*(c / 255 for c in style["body"]))
        assert not ((hue * 360 < 40 or hue * 360 > 345) and sat > 0.4), style
        assert _luma(style["core"]) > _luma(style["body"]) - 0.01                                      # the core is the brightest part
    hue, sat, _ = colorsys.rgb_to_hsv(*(c / 255 for c in config.COLOR_PROJECTILE_ENEMY))
    assert hue * 360 < 40 and sat > 0.4                                                               # while the enemy shot is orange


def _silhouette_area(tier: int, r: int) -> int:
    sprite = get_xp_sprite(tier, r)
    return sum(1 for x in range(sprite.get_width()) for y in range(sprite.get_height()) if sprite.get_at((x, y))[3] >= 100)


def test_the_four_tiers_have_pairwise_different_mask_areas_at_r10():
    areas = [_silhouette_area(t, 10) for t in (1, 2, 3, 4)]
    for i in range(4):
        for j in range(i + 1, 4):
            assert abs(areas[i] - areas[j]) / max(areas[i], areas[j]) >= 0.12, areas


def test_tier_shapes_and_cores():
    r = 10
    s1, s2, s3, s4 = (get_xp_sprite(t, r) for t in (1, 2, 3, 4))
    c = s1.get_width() // 2
    assert s1.get_at((c + r + 1, c))[:3] == config.XP_OUTLINE                                      # outline ring at r + 2
    assert s2.get_at((c + r + 2, c))[:4] == (255, 255, 255, 200)                                    # tier 2: 1 px white ring just outside the outline (r + 3)
    assert s1.get_at((c + r + 2, c))[3] <= config.SHOT_HALO_ALPHA                                  # ...which tier 1 does not have
    reach = int(config.XP_DIAMOND_REACH * r)
    assert s3.get_at((c, c - reach + 1))[:3] == config.XP_TIER_STYLE[2]["body"]                     # diamond tip
    assert s3.get_at((c + r, c + r))[3] <= config.SHOT_HALO_ALPHA                                   # ...but not the square corner
    assert s4.get_at((c, c - int(config.XP_STAR_REACH[0] * r) + 1))[:3] == config.XP_TIER_STYLE[3]["body"]       # star tip
    assert s4.get_at((c + 5, c + 5))[3] <= config.SHOT_HALO_ALPHA                                     # ...and a notch between the points
    for tier, sprite in ((1, s1), (2, s2), (3, s3), (4, s4)):
        core = config.XP_TIER_STYLE[tier - 1]["core"]
        assert sprite.get_at((c - r // 4, c - r // 4))[:3] == core                                  # core offset up and left
        assert sprite.get_at((c + 2 * r - 3, c))[3] <= config.SHOT_HALO_ALPHA                       # halo only out there


def test_xp_sprite_cache_has_at_most_36_entries():
    for value in range(0, 400, 7):
        orb = XPOrb(Vector2(), value)
        get_xp_sprite(xp_tier(value), orb.radius)
    assert xp_sprite_count() <= 36


# --- 7. blink ---------------------------------------------------------------------------------------------------

def _orb_alpha(orb: XPOrb) -> int:
    sprite = get_xp_sprite(xp_tier(orb.value), orb.radius)
    orb.draw(_blank(), CAM, NO_SHAKE)
    return sprite.get_alpha()


def test_expiry_blink_toggles_at_most_0_9_hz_and_only_in_the_last_3_seconds():
    orb = XPOrb(Vector2(500, 500), 30)
    orb.lifetime = 5.0
    assert _orb_alpha(orb) == 255                                                          # not blinking yet
    samples = []
    orb.lifetime = 3.0
    dt = 1 / 60
    for _ in range(180):
        orb.lifetime -= dt
        samples.append(_orb_alpha(orb))
    assert min(samples) >= 150 and max(samples) <= 255 and max(samples) - min(samples) > 80
    mid = (min(samples) + max(samples)) / 2
    crossings = sum(1 for i in range(1, len(samples)) if (samples[i - 1] - mid) * (samples[i] - mid) < 0)
    assert crossings <= 2 * 0.9 * 3.0 + 1                                                  # at most 0.9 cycles per second (2 crossings per cycle)
    assert crossings >= 4                                                                  # and it really does blink


def test_a_shared_sprite_is_reset_to_opaque_for_the_next_orb():
    blinking, steady = XPOrb(Vector2(500, 500), 30), XPOrb(Vector2(600, 500), 30)
    blinking.lifetime = 1.0
    steady.lifetime = 20.0
    screen = _blank()
    blinking.draw(screen, CAM, NO_SHAKE)
    steady.draw(screen, CAM, NO_SHAKE)
    assert get_xp_sprite(2, steady.radius).get_alpha() == 255


# --- 8. toggle: GFX_READABILITY = False draws exactly what main drew -------------------------------------------

def _scene_digest() -> str:
    """Seeded scene: every entity drawn by its own draw(); the digest of the frame."""
    random.seed(4343)
    screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    screen.fill((90, 110, 70))
    kinds = [CreatureType.BASIC, CreatureType.SHOOTER, CreatureType.SPLITTER, CreatureType.CHARGER, CreatureType.SHIELDER,
             CreatureType.ORBITER, CreatureType.BOMBER, CreatureType.PHANTOM, CreatureType.LEECH]
    for i, value in enumerate((5, 25, 70, 150, 400)):
        orb = XPOrb(Vector2(100 + i * 40, 100), value)
        orb.bob_phase = 0.7 * i
        orb.draw(screen, CAM, NO_SHAKE)
    for i, ctype in enumerate(kinds):
        c = Creature(Vector2(150 + i * 90, 250), ctype, size=12.0 + 2 * i)
        c.phased = (ctype == CreatureType.PHANTOM)
        c.hit_flash = 0.1 if ctype == CreatureType.LEECH else 0.0
        c.draw(screen, CAM, NO_SHAKE)
    for slot, act in enumerate((0, 5, 9)):
        Boss(Vector2(250 + slot * 300, 480), act, None).draw(screen, CAM, NO_SHAKE)
    i = 0
    for kind in ("player", "enemy", "boss"):
        for colour in (None, (80, 200, 100), (190, 120, 255)):
            if kind != "boss" and colour:
                continue
            _shot(kind, 120 + 60 * i, 640, colour).draw(screen, CAM, NO_SHAKE)
            i += 1
    Player(Vector2(900, 650)).draw(screen, CAM, NO_SHAKE, look_target=(1000, 600))
    return hashlib.sha1(pygame.image.tobytes(screen, "RGB")).hexdigest()


# sha1 of the frame above rendered by main (ad075e2), taken from a git archive of that commit
MAIN_SCENE_DIGEST = "0fda1e820191a165c3515982009120fce681cf59"


def test_toggle_off_renders_the_same_frame_as_main(monkeypatch):
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    assert _scene_digest() == MAIN_SCENE_DIGEST


def test_toggle_on_renders_a_different_frame_and_off_is_repeatable(monkeypatch):
    on = _scene_digest()
    assert on != MAIN_SCENE_DIGEST and on == _scene_digest()
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    assert _scene_digest() == _scene_digest()


def test_toggle_off_uses_the_old_shot_colours_and_touches_no_cache(monkeypatch):
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    shots, xps, shadows = projectile_module.shot_sprite_count(), xp_sprite_count(), get_graphics_cache().shadow_count()
    assert _shot("player").color == (34, 197, 94) and _shot("enemy").color == (249, 115, 22)
    _scene_digest()
    assert (projectile_module.shot_sprite_count(), xp_sprite_count(), get_graphics_cache().shadow_count()) == (shots, xps, shadows)


# --- game integration (spark position, caches, contrast) --------------------------------------------------------

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


def _enter(game, act: int) -> None:
    game.overworld = OverworldMap(act_index=act, seed=7)
    node = next(n for n in game.overworld.nodes.values() if n.node_type == NodeType.FIGHT)
    game._load_encounter(node)
    game.state = GameState.PLAYING


def _hit(game, readability: bool, monkeypatch, proj_offset=(13.0, 9.0), size=20.0):
    monkeypatch.setattr(config, "GFX_READABILITY", readability)
    random.seed(99)
    game.creatures = [Creature(Vector2(1000, 1000), CreatureType.BASIC, size=size)]
    game.creatures[0].hp = game.creatures[0].max_hp = 25.0
    game.bosses = []
    game.player.pos.set(300, 300)
    game.projectiles = [Projectile(Vector2(1000 + proj_offset[0], 1000 + proj_offset[1]), Vector2(1, 0), 0, 10, from_player=True)]
    sparks: List[Vector2] = []
    monkeypatch.setattr(game.particles, "emit_sparkle", lambda pos, colour: sparks.append(pos.copy()))
    game._update_collisions()
    c = game.creatures[0]
    return sparks, (round(c.hp, 6), c.active, game.projectiles[0].active, game.player.kills, len(game.xp_orbs))


def test_hit_spark_is_on_the_creature_edge_along_the_line_to_the_shot(game, monkeypatch):
    _enter(game, 0)
    sparks, _ = _hit(game, True, monkeypatch)
    assert len(sparks) == 1
    d = Vector2(13.0, 9.0)
    want = Vector2(1000, 1000) + d.normalize() * 20.0
    assert math.hypot(sparks[0].x - want.x, sparks[0].y - want.y) < 1e-9
    assert abs(math.hypot(sparks[0].x - 1000, sparks[0].y - 1000) - 20.0) < 1e-9               # exactly creature.radius from the centre


def test_hit_spark_keeps_the_centre_when_the_shot_is_on_top_of_the_creature(game, monkeypatch):
    _enter(game, 0)
    sparks, _ = _hit(game, True, monkeypatch, proj_offset=(0.5, 0.5))
    assert (sparks[0].x, sparks[0].y) == (1000, 1000)


@pytest.mark.parametrize("hp_kills", (25.0, 4.0))
def test_hit_spark_change_does_not_alter_damage_or_kills(game, monkeypatch, hp_kills):
    _enter(game, 0)
    size = 20.0
    results = []
    for readability in (True, False):
        monkeypatch.setattr(config, "GFX_READABILITY", readability)
        random.seed(99)
        game.creatures = [Creature(Vector2(1000, 1000), CreatureType.BASIC, size=size)]
        game.creatures[0].hp = game.creatures[0].max_hp = hp_kills
        game.bosses, game.xp_orbs = [], []
        game.player.kills = 0
        game.player.pos.set(300, 300)
        game.projectiles = [Projectile(Vector2(1013, 1009), Vector2(1, 0), 0, 10, from_player=True)]
        sparks: List[Vector2] = []
        monkeypatch.setattr(game.particles, "emit_sparkle", lambda pos, colour: sparks.append(pos.copy()))
        game._update_collisions()
        c = game.creatures[0]
        results.append(((round(c.hp, 6), c.active), game.projectiles[0].active, game.player.kills, len(game.xp_orbs), len(sparks)))
    assert results[0] == results[1]
    sparks_off, _ = _hit(game, False, monkeypatch)
    assert (sparks_off[0].x, sparks_off[0].y) == (1000, 1000)                                  # toggle off: the old centre spark


def _autoplay(game, act: int, seconds: float) -> None:
    _enter(game, act)
    random.seed(5 + act)
    game.player.hp = game.player.max_hp
    dt = 1 / 60
    for frame in range(int(seconds * 60)):
        game.state = GameState.PLAYING
        game.player.hp = game.player.max_hp
        foes = [c for c in game.creatures if c.active] + [b for b in game.bosses if b.active]
        if not foes:
            _enter(game, act)
            continue
        tgt = min(foes, key=lambda c: c.pos.distance_to(game.player.pos))
        d = tgt.pos - game.player.pos
        if d.length() > 220:
            game.player.pos.add(d.normalize() * (game.player.speed * dt * 0.8))
        game.player.shoot(tgt.pos, game.projectiles)
        game._update(dt)
        if frame % 12 == 0:
            game._draw_game()


def _cache_bytes() -> int:
    surfaces = list(get_graphics_cache()._shadows.values()) + list(projectile_module._SPRITES.values()) + list(pickups_module._SPRITES.values())
    return sum(s.get_width() * s.get_height() * 4 for s in surfaces)


@pytest.mark.parametrize("act", (0, 9))
def test_caches_stay_within_their_bounds_in_a_headless_fight(game, act):
    _autoplay(game, act, 20.0)
    assert get_graphics_cache().shadow_count() <= 50
    assert shot_sprite_count() <= 40 and xp_sprite_count() <= 36
    assert _cache_bytes() < 1_000_000


@pytest.mark.slow
@pytest.mark.parametrize("act", (0, 9))
def test_caches_stay_within_their_bounds_over_a_three_minute_headless_run(game, act):
    _autoplay(game, act, 180.0)
    assert get_graphics_cache().shadow_count() <= 50
    assert shot_sprite_count() <= 40 and xp_sprite_count() <= 36
    assert _cache_bytes() < 1_000_000


# --- 4. contrast with everything on, all 10 acts ----------------------------------------------------------------

def _ring(r0: float, r1: float):
    n = int(r1) + 2
    return [(dx, dy) for dy in range(-n, n + 1) for dx in range(-n, n + 1) if r0 <= math.hypot(dx, dy) <= r1]


def _wcag(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb) -> float:
    return 0.2126 * _wcag(rgb[0]) + 0.7152 * _wcag(rgb[1]) + 0.0722 * _wcag(rgb[2])


def _contrast(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _mean(px) -> tuple:
    return tuple(sum(p[i] for p in px) / len(px) for i in range(3))


def _body_offsets(draw: Callable[[pygame.Surface, int, int], None], colour) -> Tuple[list, list]:
    """Offsets of the pixels an item draws in exactly its body colour (found on a key background), plus a ground ring around it."""
    key = pygame.Surface((300, 300))
    key.fill((1, 2, 3))
    draw(key, 150, 150)
    offs = [(x - 150, y - 150) for y in range(300) for x in range(300) if tuple(key.get_at((x, y)))[:3] == tuple(colour)]
    assert offs
    rmax = max(math.hypot(*o) for o in offs)
    return offs, _ring(rmax + 4, rmax + 11)


def _items():
    def shot(kind, colour=None):
        return lambda s, x, y: _shot(kind, x, y, colour).draw(s, CAM, NO_SHAKE)

    def orb(value):
        return lambda s, x, y: XPOrb(Vector2(x, y), value).draw(s, CAM, NO_SHAKE)

    style = config.XP_TIER_STYLE
    items = {
        "player shot": (shot("player"), config.COLOR_PROJECTILE_PLAYER),
        "enemy shot": (shot("enemy"), config.COLOR_PROJECTILE_ENEMY),
        "boss shot": (shot("boss"), config.COLOR_PROJECTILE_ENEMY),
    }
    for tier, value in enumerate((10, 30, 80, 150), start=1):
        items[f"xp tier {tier}"] = (orb(value), style[tier - 1]["body"])
    return {k: (draw, *_body_offsets(draw, colour)) for k, (draw, colour) in items.items()}


@pytest.mark.parametrize("act", range(10))
def test_player_shots_and_every_xp_tier_keep_3_to_1_contrast_in_all_acts_with_everything_on(act):
    screen = pygame.display.get_surface()
    items = _items()
    player = Player(Vector2(0, 0))
    p_ring, p_bg = _ring(player.size * 0.75, player.size * 0.95), _ring(player.size + 3, player.size + 10)
    gen = MapGenerator()
    gen.load_map(act, 7)
    depth = layers.DepthLayers(act, 7)
    red = layers.build_overlay(*config.LOW_HP_OVERLAY)
    rng = random.Random(100 + act)
    w, h = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    samples = [(1000, 1000, w // 2, h // 2), (1000, 1000, 80, 80), (1000, 1000, w - 80, h - 80)]
    samples += [(rng.randint(500, 1500), rng.randint(500, 1500), rng.randint(70, w - 70), rng.randint(70, h - 70)) for _ in range(5)]
    worst = {}
    for lowhp in (False, True):
        for cx, cy, px, py in samples:
            cam = Vector2(cx, cy)
            amb = AmbientField(act, 5)
            for _ in range(60):
                amb.update(1 / 60, cam)

            def base():
                gen.draw_background(screen, cam, NO_SHAKE)
                depth.blit_fog(screen, cam, NO_SHAKE)
                amb.draw_back(screen, cam, NO_SHAKE)
                screen.blit(red if lowhp else depth.vignette, (0, 0))

            base()
            amb.draw_front(screen, cam, NO_SHAKE)
            ground = screen.copy()
            base()
            player.pos.set(px, py)
            player.draw(screen, CAM, NO_SHAKE, look_target=(px + 10, py))
            amb.draw_front(screen, cam, NO_SHAKE)
            c = _contrast(_mean([screen.get_at((px + dx, py + dy)) for dx, dy in p_ring]), _mean([ground.get_at((px + dx, py + dy)) for dx, dy in p_bg]))
            worst["player"] = min(worst.get("player", 99.0), c)
            for name, (draw, offs, bg) in items.items():
                base()
                draw(screen, px, py)
                amb.draw_front(screen, cam, NO_SHAKE)
                c = _contrast(_mean([screen.get_at((px + dx, py + dy)) for dx, dy in offs]), _mean([ground.get_at((px + dx, py + dy)) for dx, dy in bg]))
                worst[name] = min(worst.get(name, 99.0), c)
    assert all(v >= 3.0 for v in worst.values()), worst


# --- 6. performance (slow: timing) -----------------------------------------------------------------------------

@pytest.mark.slow
def test_a_contact_shadow_costs_at_most_0_004_ms():
    screen = _blank()
    for r in (10, 20):
        draw_contact_shadow(screen, 600, 400, r)
    best = 1e9
    for _ in range(7):
        t = time.perf_counter()
        for i in range(5000):
            draw_contact_shadow(screen, 600 + (i % 5), 400, 14 + (i % 3) * 2)
        best = min(best, (time.perf_counter() - t) / 5000 * 1000)
    assert best <= 0.004, best


@pytest.mark.slow
def test_shots_and_orbs_are_no_slower_than_the_allocating_legacy_draws(monkeypatch):
    screen = _blank()
    shots = [_shot(k, 300 + 11 * i, 300) for i, k in enumerate(("player", "enemy", "boss") * 8)]
    orbs = [XPOrb(Vector2(500 + 9 * i, 500), v) for i, v in enumerate((5, 25, 70, 150) * 6)]

    def cost() -> float:
        best = 1e9
        for _ in range(7):
            t = time.perf_counter()
            for _ in range(40):
                for s in shots:
                    s.draw(screen, CAM, NO_SHAKE)
                for o in orbs:
                    o.draw(screen, CAM, NO_SHAKE)
            best = min(best, time.perf_counter() - t)
        return best

    new = cost()
    monkeypatch.setattr(config, "GFX_READABILITY", False)
    old = cost()
    assert new <= old * 1.05, (new, old)
