"""TASK-059 (spec /workspace/handoffs/TASK-044-hit-effects.md, section 5): hit effects and juice.

Acceptance tests 1-13 against blob_evolution/systems/hitfx.py and the integrated game. Test 8 (microbenchmarks) is a
timing run: it only runs with HITFX_TIMING=1 (timing is deferred while QA owns the machine)."""
from __future__ import annotations

import json
import math
import os
import random

import pygame
import pytest

from blob_evolution import config
from blob_evolution.entities.boss import Boss
from blob_evolution.entities.creature import Creature
from blob_evolution.entities.particle import ParticleSystem
from blob_evolution.entities.projectile import Projectile
from blob_evolution.systems import hitfx as hx
from blob_evolution.utils.enums import CreatureType, GameState, ParticleType
from blob_evolution.utils.vector2 import Vector2

import hitfx_scene

DT = 1 / 60
CANVAS = 520
CTR = CANVAS // 2
GRAY = (128, 128, 128)
CAM = Vector2(CTR, CTR)
NOSHAKE = Vector2(0, 0)
EVENTS = ["player_hit", "creature_hit", "creature_block", "creature_kill", "absorb", "bomber_blast", "boss_hit", "boss_kill",
          "xp_pickup", "level_up", "evolution", "skill_up"]
DURATION = {"player_hit": 0.45, "creature_hit": 0.32, "creature_block": 0.32, "creature_kill": 0.45, "absorb": 0.32,
            "bomber_blast": 0.60, "boss_hit": 0.35, "boss_kill": 1.85, "xp_pickup": 0.40, "level_up": 0.95, "evolution": 1.40,
            "skill_up": 0.80}
PLAYER_R, CREATURE_R, BOSS_R = 20.0, 20.0, 70.0
# pixel digests of hitfx_scene.run_scene(act) recorded on the pre-059 build (merge08-fixes d38cc49, pygame-ce 2.5.8)
PRE_059_SCENE = {0: "56dd58274e4a6598", 5: "6f76f00ec8d675c1", 9: "ff3e6bcb1fd8d917"}


@pytest.fixture(autouse=True)
def _hitfx_on(monkeypatch):
    pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    monkeypatch.setattr(config, "GFX_HITFX", True)
    monkeypatch.setattr(config, "REDUCED_MOTION", False)
    monkeypatch.setattr(config, "GFX_DAMAGE_NUMBERS", False)


class Ent:
    def __init__(self, x, y, size=24.0):
        self.pos = Vector2(x, y)
        self.size = size


def make_fx(reduced=False, seed=1, fade=GRAY):
    fx = hx.HitFx(reduced=reduced, seed=seed, W=CANVAS, H=CANVAS)
    fx.fade_to = fade
    return fx


def trigger(fx, name, player=None):
    c = Vector2(CTR, CTR)
    player = player or Ent(CTR, CTR)
    {"player_hit": lambda: fx.player_hit(player, PLAYER_R),
     "creature_hit": lambda: fx.creature_hit(Vector2(CTR + CREATURE_R, CTR), CREATURE_R, 0.0),
     "creature_block": lambda: fx.creature_hit(Vector2(CTR + CREATURE_R, CTR), CREATURE_R, 0.0, blocked=True),
     "creature_kill": lambda: fx.creature_kill(c, CREATURE_R),
     "absorb": lambda: fx.absorb(Vector2(CTR + 30, CTR - 8), CREATURE_R, Vector2(CTR, CTR)),
     "bomber_blast": lambda: fx.bomber_blast(c, 20.0 * 3.5),
     "boss_hit": lambda: fx.boss_hit(Vector2(CTR + BOSS_R, CTR - 10), c, BOSS_R, True),
     "boss_kill": lambda: fx.boss_kill(c, BOSS_R),
     "xp_pickup": lambda: fx.xp_pickup(c),
     "level_up": lambda: fx.level_up(player, PLAYER_R),
     "evolution": lambda: fx.evolution(player, PLAYER_R),
     "skill_up": lambda: fx.skill_up(player, PLAYER_R)}[name]()


def draw_frame(fx, surf):
    hx.draw_system(fx.ps, surf, CAM, NOSHAKE, fx.cache, CANVAS, CANVAS)
    fx.draw(surf, CAM, NOSHAKE)


def frames(name, times, ground=GRAY, fade=None, reduced=False, seed=1):
    fx = make_fx(reduced, seed, fade or ground)
    fx.prewarm()
    trigger(fx, name)
    out = []
    want = {int(round(x / DT)) for x in times}
    for f in range(int(round(max(times) / DT)) + 1):
        if f in want:
            s = pygame.Surface((CANVAS, CANVAS))
            s.fill(ground)
            draw_frame(fx, s)
            out.append(s)
        fx.update(DT)
    return out


def fg_mask(surf, bg, tol=12):
    m = pygame.mask.from_threshold(surf, bg, (tol, tol, tol, 255))
    m.invert()
    return m


def _gray_of(ground):
    g = pygame.Surface((1, 1))
    g.fill(ground)
    return tuple(pygame.transform.grayscale(g).get_at((0, 0)))[:3]


def accumulate_mask(name, gray=False):
    fx = make_fx()
    fx.prewarm()
    trigger(fx, name)
    acc = pygame.mask.Mask((CANVAS, CANVAS))
    bgc = _gray_of(GRAY)
    for _f in range(int(round(DURATION[name] / DT))):
        s = pygame.Surface((CANVAS, CANVAS))
        s.fill(GRAY)
        draw_frame(fx, s)
        acc.draw(fg_mask(pygame.transform.grayscale(s), bgc) if gray else fg_mask(s, GRAY), (0, 0))
        fx.update(DT)
    return acc


# ---- 1. flash Hz ------------------------------------------------------------------------------------------------------

def _flash_timeline(make, interval, secs=10.0):
    e = make()
    timeline, nxt, t = [], 0.0, 0.0
    for _f in range(int(secs * 60)):
        if t >= nxt - 1e-9:
            e.take_damage(0.001)
            nxt += interval
        timeline.append(e.hit_flash > 0)
        if e.hit_flash > 0:                       # the two timers Creature / Boss.update tick (no AI, no movement)
            e.hit_flash -= DT
        hx.tick_flash(e, DT)
        t += DT
    return timeline


def _window_counts(tl):
    starts = [i for i in range(1, len(tl)) if tl[i] and not tl[i - 1]] + ([0] if tl[0] else [])
    win = max(sum(1 for s in starts if w <= s < w + 60) for w in range(0, len(tl) - 59))
    flips = max(sum(1 for i in range(w + 1, w + 60) if tl[i] != tl[i - 1]) for w in range(0, len(tl) - 60))
    return win, flips


def _creature():
    c = Creature(Vector2(0, 0), CreatureType.BASIC, 20)
    c.hp = c.max_hp = 1e9
    return c


def _boss():
    b = Boss(Vector2(0, 0), 0, None)
    b.hp = b.max_hp = 1e12
    return b


@pytest.mark.parametrize("make", [_creature, _boss], ids=["creature", "boss"])
@pytest.mark.parametrize("interval", [0.06, 0.25, 0.5])
def test_1_flash_starts_at_most_3_per_second_and_2_reduced(make, interval, monkeypatch):
    starts, flips = _window_counts(_flash_timeline(make, interval))
    assert starts <= 3 and flips <= 6, (starts, flips)
    monkeypatch.setattr(config, "REDUCED_MOTION", True)
    assert _window_counts(_flash_timeline(make, interval))[0] <= 2


def test_1_flash_gap_keeps_0_34_s_and_off_restores_the_re_arming_flash(monkeypatch):
    c = _creature()
    c.take_damage(1.0)
    assert c.flash_started and c.hit_flash == pytest.approx(0.15) and c.flash_gap == pytest.approx(0.34)
    c.take_damage(1.0)
    assert not c.flash_started                                 # inside the gap: no new flash
    monkeypatch.setattr(config, "GFX_HITFX", False)
    c2 = _creature()
    for _ in range(3):
        c2.hit_flash = 0.0
        c2.take_damage(1.0)
        assert c2.hit_flash == pytest.approx(0.15)              # today: every hit re-arms


def test_1_shield_block_starts_at_most_one_flash_per_call():
    c = Creature(Vector2(0, 0), CreatureType.SHIELDER, 20)
    c.hp = c.max_hp = 1e9
    c.face_dir = Vector2(1, 0)
    c.take_damage(500.0, hit_from=Vector2(50, 0))           # front hit: block then damage in one call
    assert c.last_hit_blocked and c.flash_started and c.hit_flash == pytest.approx(0.10)


# ---- 2. zero allocations ----------------------------------------------------------------------------------------------

def _heavy(fx, shake, screen, nframes=300):
    rng = random.Random(5)
    player = Ent(600, 400)
    flash = [hx.FlashState() for _ in range(20)]
    boss_flash = hx.FlashState(0.2)
    cam = Vector2(600, 400)
    for f in range(nframes):
        for _k in range(3):
            i = rng.randrange(20)
            blocked = i % 5 == 0
            st = flash[i].hit(0.1 if blocked else 0.15)
            fx.creature_hit(Vector2(200 + (i % 5) * 180 + 20, 150 + (i // 5) * 160), 20, 0.0, blocked=blocked, ring=st)
        if f % 6 == 0:
            fx.creature_kill(Vector2(rng.uniform(100, 1100), rng.uniform(100, 700)), rng.uniform(10, 30))
        if f % 10 == 0:
            fx.absorb(Vector2(630, 400), 14, player.pos)
        if f % 30 == 0:
            fx.bomber_blast(Vector2(rng.uniform(200, 1000), rng.uniform(200, 600)), 70)
        if f % 3 == 0:
            fx.boss_hit(Vector2(900, 300), Vector2(850, 300), 90, boss_flash.hit())
        if f % 20 == 0:
            fx.player_hit(player)
            shake.add(5, "hit_proj")
        fx.xp_pickup(Vector2(rng.uniform(500, 700), rng.uniform(300, 500)))
        if f == 100:
            fx.boss_kill(Vector2(850, 300), 90)
        if f == 60:
            fx.level_up(player)
        if f == 120:
            fx.evolution(player)
        if f == 180:
            fx.skill_up(player)
        if f % 6 == 0:
            shake.add(2, "kill")
        for fl in flash:
            fl.update(DT)
        boss_flash.update(DT)
        fx.update(DT)
        shake.update(DT)
        sh = Vector2(*shake.int_offset())
        hx.draw_system(fx.ps, screen, cam, sh, fx.cache)
        fx.draw(screen, cam, sh)


class _Count:
    def __init__(self, monkeypatch):
        self.n = 0
        orig = pygame.Surface
        count = self

        class Counting(orig):
            def __init__(s, *a, **k):
                count.n += 1
                super().__init__(*a, **k)
        monkeypatch.setattr(pygame, "Surface", Counting)


@pytest.mark.parametrize("reduced", [False, True])
def test_2_zero_allocations_in_300_heavy_frames_after_prewarm(reduced, monkeypatch):
    fx = hx.HitFx(reduced=reduced, seed=3)
    fx.set_ground(8)
    fx.prewarm_all()
    misses, clears = fx.cache.misses, fx.cache.clears
    shake = hx.Shake(reduced=reduced, seed=1)
    screen = pygame.Surface((1200, 800))
    count = _Count(monkeypatch)
    _heavy(fx, shake, screen)
    assert (count.n, fx.cache.misses - misses, fx.cache.clears - clears) == (0, 0, 0)


def _particle_and_fx_surfaces(flag, monkeypatch):
    """Surfaces constructed from particle.py / hitfx.py during frames 1-239 of the integrated scene (the encounter's
    prewarm at load is before frame 0). Other systems' own per-frame surfaces (HUD panels, blob glows) are not ours."""
    import traceback
    monkeypatch.setattr(config, "GFX_HITFX", flag)
    on, n = [False], [0]
    orig = pygame.Surface

    class Counter(orig):
        def __init__(s, *a, **k):
            if on[0] and any(f.filename.endswith(("entities/particle.py", "systems/hitfx.py")) for f in traceback.extract_stack()[:-1]):
                n[0] += 1
            super().__init__(*a, **k)

    def rec(g, f):
        on[0] = True
    monkeypatch.setattr(pygame, "Surface", Counter)
    hitfx_scene.run_scene(0, record=rec)
    return n[0]


def test_2_the_real_game_draws_particles_and_cues_without_a_surface(monkeypatch):
    """The integrated scene (hits, kills, a bomber blast, player hits, XP, level-up): 0 surfaces from the particle draw
    or the hit cues with GFX_HITFX on; today's particle draw makes one per live particle per frame."""
    assert _particle_and_fx_surfaces(False, monkeypatch) > 100
    assert _particle_and_fx_surfaces(True, monkeypatch) == 0
    assert hx.CACHE.clears == 0


# ---- 3. grayscale distinctness ----------------------------------------------------------------------------------------

def test_3_every_cue_keeps_its_pixels_in_grayscale_and_is_a_distinct_shape():
    keep = {e: accumulate_mask(e, gray=True).count() / max(1, accumulate_mask(e).count()) for e in EVENTS}
    assert min(keep.values()) >= 0.90, keep
    k7 = pygame.mask.Mask((7, 7), fill=True)
    bgc = _gray_of(GRAY)
    fm = {e: [fg_mask(pygame.transform.grayscale(s), bgc).convolve(k7, None, (-3, -3))
              for s in frames(e, (0.08, 0.16, 0.28))] for e in EVENTS}
    worst = (9.0, "")
    for i, a in enumerate(EVENTS):
        for b in EVENTS[i + 1:]:
            sym = na = nb = 0
            for A, B in zip(fm[a], fm[b]):
                inter = A.overlap_area(B, (0, 0))
                sym += A.count() + B.count() - 2 * inter
                na += A.count()
                nb += B.count()
            worst = min(worst, (sym / max(1, min(na, nb)), f"{a}|{b}"))
    assert worst[0] >= 0.5, worst


# ---- 4. contrast ------------------------------------------------------------------------------------------------------

def test_4_every_light_colour_is_3_to_1_on_all_10_light_grounds():
    worst = min((hx.contrast(c, g), n) for n, c in hx.PAL.items() for g in hx.GROUND_LIGHT)
    assert worst[0] >= 3.0, worst


@pytest.mark.parametrize("act", range(10))
def test_4b_player_hit_ring_pixel_is_3_to_1_on_every_ground(act):
    g = hx.GROUND_LIGHT[act]
    s = frames("player_hit", [0.15], ground=g, fade=hx.GROUND_FADE[act])[0]
    fx = make_fx()
    trigger(fx, "player_hit")
    for _ in range(9):
        fx.update(DT)
    e = [e for e in fx.fx if e.active and e.kind == hx.K_RING][0]
    r = int(e.p0 + (e.p1 - e.p0) * hx.ease_out(e.t / e.p2))
    assert hx.contrast(tuple(s.get_at((CTR, CTR - r)))[:3], g) >= 3.0


# ---- 5. shake spectrum and decay --------------------------------------------------------------------------------------

def _spectrum(xs, fmax=8.0, fs=60.0, pad=480):
    xs = list(xs) + [0.0] * (pad - len(xs))
    N = len(xs)
    tot = hi = 0.0
    peak = (0.0, 0.0)
    for k in range(1, N // 2):
        re = sum(x * math.cos(2 * math.pi * k * i / N) for i, x in enumerate(xs) if x)
        im = sum(x * math.sin(2 * math.pi * k * i / N) for i, x in enumerate(xs) if x)
        p = re * re + im * im
        f = k * fs / N
        tot += p
        if f > fmax:
            hi += p
        if p > peak[1]:
            peak = (f, p)
    return (hi / tot if tot else 0.0), peak[0]


@pytest.mark.parametrize("A", [2, 3, 5, 6, 8, 12])
def test_5_shake_is_95_percent_below_8_hz_and_settles_by_T(A):
    T = max(hx.SHAKE_MIN_T, hx.SHAKE_DECAY_TAU * math.log(A / 0.1))
    for seed in (1, 2, 3):
        sh = hx.Shake(seed=seed)
        sh.add(A)
        xs, ys, mags = [], [], []
        for _f in range(60):
            sh.update(DT)
            xs.append(sh.offset_x)
            ys.append(sh.offset_y)
            mags.append(math.hypot(sh.offset_x, sh.offset_y))
        for axis in (xs, ys):
            hi, peak = _spectrum(axis)
            assert hi <= 0.05 and peak <= 8.0, (A, seed, hi, peak)
        settle = (max([i for i, m in enumerate(mags) if m >= 0.5] or [0]) + 1) / 60
        assert settle <= T + 0.02 and max(max(map(abs, xs)), max(map(abs, ys))) <= A


def test_5b_shake_storm_stays_under_the_cap():
    sh = hx.Shake(seed=2)
    mx = 0.0
    for _f in range(120):
        sh.add(8, "charger")
        sh.add(3, "boss_hit")
        sh.update(DT)
        mx = max(mx, abs(sh.offset_x), abs(sh.offset_y))
    assert mx <= hx.SHAKE_CAP


# ---- 6. reduced motion ------------------------------------------------------------------------------------------------

def test_6_reduced_shake_small_is_off_big_is_one_monotonic_nudge():
    assert not hx.Shake(reduced=True, seed=1).add(2, "kill")
    sh = hx.Shake(reduced=True, seed=1)
    assert sh.add(12, "boss_kill")
    xs = []
    for _f in range(30):
        sh.update(DT)
        xs.append(math.hypot(sh.offset_x, sh.offset_y))
    assert max(xs) <= 4.0 and all(xs[i + 1] <= xs[i] + 1e-9 for i in range(len(xs) - 1))


def _counts(reduced):
    out = {}
    for e in EVENTS:
        fx = make_fx(reduced)
        trigger(fx, e)
        if e == "boss_kill":
            for _ in range(8):
                fx.update(DT)
        out[e] = fx.ps.live
    return out


def test_6_reduced_particles_halved_hits_ring_only_no_pulse():
    cn, cr = _counts(False), _counts(True)
    assert all(cr[e] <= (cn[e] + 1) // 2 for e in EVENTS), (cn, cr)
    assert cr["creature_hit"] == 0 and cr["creature_block"] == 0
    assert hx.hurt_pulse(0.3, True) == 0
    assert len({hx.hurt_outline_set(t / 60, True) for t in range(60)}) == 1
    sg = [hx.hurt_outline_set(t / 600) for t in range(600)]
    assert sum(1 for i in range(1, 600) if sg[i] != sg[i - 1]) / 2 <= 3 and hx.HURT_PULSE_K / math.tau <= 3.0


# ---- 7. cache memory --------------------------------------------------------------------------------------------------

def test_7_prewarm_fits_the_cache_cap_without_clears():
    fx = hx.HitFx()
    n = fx.prewarm_all()
    assert hx.CACHE.bytes <= hx.CACHE_MAX_BYTES and hx.CACHE.clears == 0 and n >= 1952


# ---- 8. microbenchmarks (timing; deferred) ----------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("HITFX_TIMING") != "1", reason="timing run: HITFX_TIMING=1 when the machine is free")
def test_8_draw_300_live_costs_at_most_half_of_today():
    import time
    screen = pygame.display.get_surface()
    cam, sh0 = Vector2(600, 400), Vector2(0, 0)
    random.seed(300)
    ps = ParticleSystem()
    for i in range(300):
        p = ps.particles[i]
        p.spawn(Vector2(600 + random.uniform(-300, 300), 400 + random.uniform(-250, 250)),
                Vector2(random.uniform(-100, 100), random.uniform(-100, 100)), (255, 150, 50), random.uniform(2, 6), 10.0,
                ParticleType.EXPLOSION)
        p.lifetime = random.uniform(2, 10)

    def med(f, n=300):
        ts = []
        for _ in range(n):
            t = time.process_time()
            f()
            ts.append(time.process_time() - t)
        ts.sort()
        return ts[len(ts) // 2]
    for _ in range(3):
        hx.draw_particles(ps, screen, cam, sh0)
    config.GFX_HITFX = False
    old = med(lambda: ps.draw(screen, cam, sh0))
    config.GFX_HITFX = True
    new = med(lambda: ps.draw(screen, cam, sh0))
    assert new <= 0.5 * old, (old, new)


# ---- 9. hit honesty and geometry --------------------------------------------------------------------------------------

def test_9_blast_ring_ends_at_the_explosion_radius_chevrons_point_in_streaks_converge():
    fx = make_fx()
    fx.bomber_blast(Vector2(CTR, CTR), 70)
    for _ in range(20):
        fx.update(DT)
    e = [e for e in fx.fx if e.active and e.kind == hx.K_BLAST][0]
    r_end = e.p0 + (e.p1 - e.p0) * hx.ease_out(e.t / e.p2)
    s = pygame.Surface((CANVAS, CANVAS))
    s.fill(GRAY)
    fx.draw(s, CAM, NOSHAKE)
    m = fg_mask(s, GRAY)
    out = max(math.hypot(x - CTR, y - CTR) for x, y in m.outline())
    assert abs(r_end - 70) < 0.5 and out <= 70 + 2.5, (r_end, out)
    for i in range(4):
        ang = math.pi / 4 + i * math.pi / 2
        pts = hx.chev_points(math.cos(ang) * 40, math.sin(ang) * 40, ang, -1, 7)
        assert math.hypot(*pts[1]) < min(math.hypot(*pts[0]), math.hypot(*pts[2]))
    fx = make_fx()
    fx.absorb(Vector2(300, 260), 20, Vector2(260, 260))
    for _ in range(15):
        fx.update(DT)
    d = [math.hypot(p.pos.x - 260, p.pos.y - 260) for p in fx.ps.particles if p.active]
    assert d and max(d) <= 6


def test_9b_the_creature_hit_point_is_on_the_edge_toward_the_shot():
    fx = make_fx()
    c = _creature()
    c.pos = Vector2(1000, 1000)
    c.take_damage(1.0)
    fx.on_creature_hit(c, Vector2(1013, 1009))
    ring = [e for e in fx.fx if e.active and e.kind == hx.K_RING][0]
    assert math.hypot(ring.x - 1000, ring.y - 1000) == pytest.approx(c.radius)


# ---- 10. guards (integrated) ------------------------------------------------------------------------------------------

@pytest.fixture
def fight(make_game, monkeypatch):
    g = hitfx_scene.make_scene_game(0)
    g.creatures, g.bosses, g.projectiles, g.xp_orbs = [], [], [], []
    g.player.max_hp = g.player.hp = 1e9
    cues = []
    real = g.hitfx.player_hit
    monkeypatch.setattr(g.hitfx, "player_hit", lambda p, R=None: (cues.append(1), real(p, R)))
    g.cues = cues
    return g


def test_10_a_charger_overlapping_for_1_s_gives_one_cue_one_shake_one_hurt_sound(fight):
    g = fight
    c = Creature(Vector2(g.player.pos.x + 5, g.player.pos.y), CreatureType.CHARGER, g.player.size)   # neither eats
    c.speed = 0.0
    g.creatures = [c]
    g.player.invulnerable = 0.0
    shakes0 = g.shake_fx.triggers
    for _f in range(28):                                     # < 0.5 s: one hit, then invulnerable while overlapping
        c.charging = True
        c.pos.set(g.player.pos.x + 5, g.player.pos.y)
        g.player.invulnerable = max(g.player.invulnerable, 0.0)
        g._update_collisions()
        if g.player.hit_event:
            g.player.hit_event = False
            g.hitfx.player_hit(g.player)
        g.player.update(DT)
    assert len(g.cues) == 1 and g.shake_fx.triggers - shakes0 == 1
    assert sum(1 for n, _v in g.sounds if n == "hurt") == 1


def test_10_shots_absorbed_while_invulnerable_give_nothing_extra(fight):
    g = fight
    g.player.take_damage(1.0)
    g.player.hit_event = False
    shakes0, sounds0 = g.shake_fx.triggers, len(g.sounds)
    for _ in range(5):
        g.projectiles = [Projectile(g.player.pos.copy(), Vector2(1, 0), 0, 3, from_player=False)]
        g._update_projectiles(DT)
    assert not g.player.hit_event and g.shake_fx.triggers == shakes0
    assert not [s for s in g.sounds[sounds0:] if s[0] == "hurt"]


def test_10_the_scene_plays_the_hurt_sound_only_in_frames_where_a_hit_landed():
    """Today the scene's charger overlap replays "hurt" every frame while the player is invulnerable (180 plays); now a
    frame plays it at most once, and only when a hit landed in that frame (big-creature contact stays silent, as today)."""
    seen = []

    def rec(g, f):
        seen.append((g.player.hurt_timer, sum(1 for n, _v in g.sounds if n == "hurt")))
    hitfx_scene.run_scene(0, record=rec)
    prev_t, prev_n = 0.0, 0
    plays = 0
    for t, n in seen:
        if n > prev_n:
            assert n - prev_n == 1 and t > prev_t, (t, prev_t)
            plays += 1
        prev_t, prev_n = t, n
    assert plays >= 1


# ---- 11. toggle (integrated) ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("act", sorted(PRE_059_SCENE))
def test_11_hitfx_off_is_pixel_identical_to_the_pre_059_build(act, monkeypatch):
    monkeypatch.setattr(config, "GFX_HITFX", False)
    assert hitfx_scene.run_scene(act)[0] == PRE_059_SCENE[act]


def test_11_hitfx_on_draws_something_else():
    assert hitfx_scene.run_scene(0)[0] != PRE_059_SCENE[0]


def test_11_off_keeps_the_old_shake(monkeypatch):
    monkeypatch.setattr(config, "GFX_HITFX", False)
    g = hitfx_scene.make_scene_game(0)
    g._add_screen_shake(8)
    assert g.shake_intensity == 8 and g.shake_fx.triggers == 0


def test_11_gameplay_is_the_same_with_hitfx_on_and_off(monkeypatch):
    """Flash gap and cues are visual only: a scripted boss and creature fight (incl. shield blocks) keep every gameplay
    field and the global RNG equal; only hit_flash / flash fields differ."""
    def run(flag):
        monkeypatch.setattr(config, "GFX_HITFX", flag)
        random.seed(11)
        b = Boss(Vector2(1200, 1100), 7, None)
        c = Creature(Vector2(900, 900), CreatureType.SHIELDER, 22)
        out = []
        for f in range(400):
            if f % 2 == 0:
                b.take_damage(b.max_hp * 0.004, hit_from=Vector2(1300, 1100))
                c.take_damage(3.0, hit_from=Vector2(950 if f % 4 else 850, 900))
            b.update(DT, Vector2(1000, 1000), [])
            c.update(DT, Vector2(1000, 1000), 20, [])
            out.append((b.hp, b.phase, b.pos.x, b.pos.y, c.hp, c.shield_hp, c.pos.x, c.pos.y, random.random()))
        return out
    assert run(True) == run(False)


# ---- 12. counts never above today -------------------------------------------------------------------------------------

def test_12_particle_counts_never_exceed_today():
    cn = _counts(False)
    assert all(cn[e] <= hx.CURRENT_COUNTS[e] for e in EVENTS), cn


# ---- 13. options and save ---------------------------------------------------------------------------------------------

def _key(g, key):
    g._handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


def test_13_reduced_motion_row_toggles_and_back_is_row_6(make_game, monkeypatch):
    g = make_game()
    monkeypatch.setattr(g.audio, "play", lambda *a, **k: None)
    g.state = GameState.OPTIONS
    g.options_selected = 5
    _key(g, pygame.K_d)
    assert config.REDUCED_MOTION and g.shake_fx.reduced and g.hitfx.reduced
    _key(g, pygame.K_a)
    assert not config.REDUCED_MOTION
    g.options_selected = 6
    _key(g, pygame.K_RETURN)
    assert g.state == GameState.MAIN_MENU


def test_13_the_options_screen_shows_the_row(make_game, monkeypatch):
    from blob_evolution.ui import menus
    g = make_game()
    texts = []
    real = menus.style.draw_menu_row
    monkeypatch.setattr(menus.style, "draw_menu_row", lambda surface, font, text, *a, **k: (texts.append(text),
                                                                                             real(surface, font, text, *a, **k))[1])
    monkeypatch.setattr(config, "REDUCED_MOTION", True)
    g.state = GameState.OPTIONS
    g._draw()
    assert "Reduced Motion: ON" in texts and texts.index("Reduced Motion: ON") < texts.index("Back")


def test_13_reduced_motion_survives_save_and_load(make_game, isolated_save):
    g = make_game()
    g._set_reduced_motion(True)
    g._save_game()
    assert json.loads(isolated_save.read_text())["reduced_motion"] is True
    config.REDUCED_MOTION = False
    g2 = make_game()
    assert config.REDUCED_MOTION is True and g2.shake_fx.reduced and g2.hitfx.reduced
    g2._set_reduced_motion(False)
    g2._save_game()
    assert json.loads(isolated_save.read_text())["reduced_motion"] is False   # once saved it stays in the file


def test_13_an_old_save_without_the_key_loads_the_default_and_is_not_flagged(make_game, isolated_save, fixture_bytes):
    data = json.loads(fixture_bytes)
    assert "reduced_motion" not in data                      # the pre-059 fixture
    isolated_save.write_bytes(fixture_bytes)
    config.REDUCED_MOTION = True                             # stale value from elsewhere: the load resets it
    g = make_game()
    assert config.REDUCED_MOTION is False and g.save_notice is None
    g._save_game()
    assert "reduced_motion" not in json.loads(isolated_save.read_text())     # untouched default: the format is unchanged


def test_13_a_wrong_type_falls_back_to_the_default(make_game, isolated_save, fixture_bytes):
    data = json.loads(fixture_bytes)
    data["reduced_motion"] = "yes"
    isolated_save.write_text(json.dumps(data))
    make_game()
    assert config.REDUCED_MOTION is False


# ---- Visual Designer defaults and the rest ----------------------------------------------------------------------------

def test_vd_defaults_damage_numbers_built_but_off_and_the_gap_is_0_34():
    import importlib
    import blob_evolution.config as cfg_mod
    src = open(cfg_mod.__file__).read()
    assert "GFX_DAMAGE_NUMBERS = False" in src and "GFX_HITFX = True" in src and "REDUCED_MOTION = False" in src
    assert hx.FLASH_GAP == 0.34 and hx.FLASH_GAP_REDUCED == 0.50
    fx = hx.HitFx()
    fx.prewarm_all()
    assert fx.numbers is None                                # off: not even built
    del importlib


@pytest.fixture
def _font():
    """BUG-189: the damage-number glyphs need pygame.font, which another test may not have initialised yet."""
    pygame.font.init()
    yield


def test_damage_numbers_when_turned_on_are_prebaked_and_allocation_free(_font, monkeypatch):
    monkeypatch.setattr(config, "GFX_DAMAGE_NUMBERS", True)
    fx = hx.HitFx()
    fx.prewarm_all()
    assert fx.numbers is not None
    c = _creature()
    c.pos = Vector2(600, 400)
    screen = pygame.Surface((1200, 800))
    count = _Count(monkeypatch)
    for f in range(60):
        c.take_damage(7.0)
        fx.on_creature_hit(c, Vector2(650, 400), 7.0)
        fx.update_all(DT)
        fx.draw_all(screen, Vector2(600, 400), NOSHAKE)
    assert count.n == 0 and any(it[0] for it in fx.numbers.items)


def test_player_hit_event_and_hurt_timer_are_visual_only():
    from blob_evolution.entities.player import Player
    p = Player(Vector2(0, 0))
    assert p.take_damage(1.0) is False and p.hit_event and p.last_hit and p.hurt_timer == 0.5
    assert p.take_damage(1.0) is False and not p.last_hit       # invulnerable: no new hit
    p2 = Player(Vector2(0, 0))
    p2.dash_duration = 0.2
    p2.invulnerable = 0.2                                    # dash i-frames don't set the hurt outline
    assert p2.hurt_timer == 0.0


def test_reduced_motion_player_hit_chevrons_are_static(monkeypatch):
    fx = make_fx(reduced=True)
    trigger(fx, "player_hit")
    chev = [e for e in fx.fx if e.active and e.kind == hx.K_CHEV]
    assert len(chev) == 4 and all(e.p0 == e.p1 == PLAYER_R + 22 for e in chev)

