"""TASK-059 (spec TASK-044): hit effects and juice, visual only. Ported from /workspace/handoffs/TASK-044-hitfx.py
(the Visual Designer's tested reference module; its numbers win over the spec text).

Parts
  SpriteCache + draw_system   cached particle sprites keyed (shape, size bucket, colour, alpha step, angle step), one fblits
  HitPool                     the hit-fx particles (repo Particle objects, live count for the soft / hard caps)
  HitFx                       rings / chevrons / hexagon / diamond / star / blast drawn with pygame.draw (no Surface)
  Shake                       time based, <= 8 Hz, intensity table, cap, per-source gaps, reduced-motion nudge
  flash / tick_flash          per entity hit flash with `flash_gap` (0.34 s) and `flash_started` (Creature / Boss)
  hurt_pulse / draw_hurt_outline   player invulnerability pulse (2.71 Hz) and the non-colour dashed outline
  DamageNumbers               PROPOSAL only (config.GFX_DAMAGE_NUMBERS, default off), cached glyph atlas
Everything is drawn only when config.GFX_HITFX is True; False keeps today's code paths exactly.
"""
from __future__ import annotations

import math
import random

import pygame

from blob_evolution import config
from blob_evolution.entities.particle import Particle
from blob_evolution.utils.enums import ParticleType

TAU = math.tau
SCREEN_W, SCREEN_H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
PType = ParticleType

# ground tones: (DARK, MID, LIGHT) per act 0..9
GROUND_RAMPS = config.GROUND_RAMPS
GROUND_LIGHT = [r[2] for r in GROUND_RAMPS]
GROUND_MID = [r[1] for r in GROUND_RAMPS]
PLAYER_BODY = (34, 197, 94)
DARK = (8, 6, 14)                      # outline / underlay colour of every effect element


def _lin(c: int) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lum(rgb) -> float:
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def contrast(a, b) -> float:
    la, lb = lum(a), lum(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def mix(c0, c1, t: float):
    """c0 + (c1-c0)*t, int channels."""
    return (int(c0[0] + (c1[0] - c0[0]) * t + 0.5), int(c0[1] + (c1[1] - c0[1]) * t + 0.5),
            int(c0[2] + (c1[2] - c0[2]) * t + 0.5))


# effects fade toward this tone (half way between MID and LIGHT, the typical ground under an effect)
GROUND_FADE = [mix(r[1], r[2], 0.5) for r in GROUND_RAMPS]


# --------------------------------------------------------------------------------------------------------------------
# palette: light element colours (all drawn over / with the DARK underlay).  Every colour is >= 3.3:1 against every act
# LIGHT tone at full alpha; vector elements stay at full alpha for >= 30-60 % of their life (the "readable window", test 4).
# --------------------------------------------------------------------------------------------------------------------
PAL = {
    "player_ring": (255, 150, 140), "player_chev": (255, 236, 226),
    "hit_ring": (255, 240, 200), "hit_shard": (255, 200, 100),
    "block_hex": (190, 225, 255), "block_spark": (235, 245, 255),
    "kill_ring": (255, 190, 110), "kill_shard_a": (255, 150, 50), "kill_shard_b": (255, 220, 160), "kill_ember": (255, 150, 50),
    "absorb": (170, 255, 200),
    "blast_ring": (255, 160, 80), "blast_dust": (214, 186, 150), "blast_shard": (255, 150, 50),
    "boss_chev": (255, 225, 140),
    "bosskill_ring_a": (255, 235, 200), "bosskill_ring_b": (255, 160, 150),
    "bosskill_shard_a": (255, 150, 130), "bosskill_shard_b": (255, 220, 160), "bosskill_dust": (255, 150, 130),
    "xp_diamond": (255, 236, 140), "xp_spark": (250, 204, 21),
    "level_a": (255, 226, 120), "level_b": (255, 255, 255),
    "evo_a": (200, 170, 255), "evo_b": (255, 255, 255), "evo_diamond": (225, 205, 255),
    "skill_a": (150, 255, 210), "skill_b": (255, 255, 255),
}

# --------------------------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------
# constants (spec section 3 / 4); the tunables live in config
# --------------------------------------------------------------------------------------------------------------------
FLASH_GAP = config.HITFX_FLASH_GAP                 # s between flash STARTS per entity (2.94 Hz max)
FLASH_GAP_REDUCED = config.HITFX_FLASH_GAP_REDUCED  # 2 Hz when REDUCED_MOTION
CREATURE_FLASH, BLOCK_FLASH, BOSS_FLASH = 0.15, 0.10, 0.20
HURT_PULSE_K = 17.0              # sin(inv * 17) = 2.71 Hz  (was 20 = 3.18 Hz)
HURT_PULSE_AMP = 0.06
HURT_BLINK_PERIOD = 0.40         # dashed outline: set A 0.2 s, set B 0.2 s
ALPHA_LEVELS = (32, 64, 96, 128, 160, 192, 224, 255)   # 8 alpha steps for cached particle sprites
SIZE_MAX = 10                    # size bucket 1..10 px
ANGLES = 16                      # angle steps for streak sprites
SHARD_ANGLES = 8                 # angle steps for shard sprites (45 deg; halves the cache)
CACHE_MAX_BYTES = config.HITFX_CACHE_MAX_BYTES     # 6 MB cap for the particle sprite cache
FX_POOL = 64                     # effect slots
LIVE_SOFT_CAP = config.HITFX_SOFT_CAP              # hitfx particles: low priority spawns stop at this many live
LIVE_HARD_CAP = config.HITFX_HARD_CAP              # nothing spawns above this many live
SHAKE_CAP = float(config.SHAKE_CAP)
SHAKE_FREQS = ((2.8, 4.2), (3.4, 4.8))     # Hz per axis (x, y), weights 0.65 / 0.35
SHAKE_DECAY_TAU = 0.103          # seconds; = old 0.85 per frame at 60 fps
SHAKE_ATTACK = 0.06
SHAKE_MIN_T = 0.40               # shortest shake (small intensities would otherwise spread energy above 8 Hz)
SHAKE_SOURCE_GAP = {"kill": 0.10, "boss_hit": 0.34, "creature_hit": 0.20}   # min seconds between triggers of one source
# --------------------------------------------------------------------------------------------------------------------
# colour helpers
# --------------------------------------------------------------------------------------------------------------------
def alpha_at(u: float, hold: float) -> float:
    """Alpha curve: 1.0 until `hold` of the life, then linear to 0 (monotonic, one shot)."""
    if u <= hold:
        return 1.0
    if u >= 1.0:
        return 0.0
    return 1.0 - (u - hold) / (1.0 - hold)


def ease_out(u: float) -> float:
    if u >= 1.0:
        return 1.0
    return 1.0 - (1.0 - u) * (1.0 - u)


# --------------------------------------------------------------------------------------------------------------------
# cached particle sprites
# --------------------------------------------------------------------------------------------------------------------
SHAPES = ("disc", "star4", "streak", "shard")
_BY_NAME = {"EXPLOSION": "disc", "AMBIENT": "disc", "SPARKLE": "star4", "TRAIL": "streak", "SHARD": "shard"}
_SHAPE_OF: dict = {}
_ANGLED = ("streak", "shard")


def _poly(b: float, pts, ang: float, c: float):
    ca, sa = math.cos(ang), math.sin(ang)
    return [(c + (x * ca - y * sa) * b, c + (x * sa + y * ca) * b) for x, y in pts]


_STREAK = ((-3.2, 0), (-0.2, -0.75), (1.0, -0.5), (1.3, 0), (1.0, 0.5), (-0.2, 0.75))
_SHARD = ((2.0, 0), (0.2, -0.85), (-1.3, 0), (0.2, 0.85))
_STAR = ((2.0, 0), (0.35, -0.35), (0, -2.0), (-0.35, -0.35), (-2.0, 0), (-0.35, 0.35), (0, 2.0), (0.35, 0.35))
_EXT = {"disc": 1.0, "star4": 2.0, "streak": 3.3, "shard": 2.1}


class SpriteCache:
    """(shape, size bucket, colour, alpha step, angle step) -> (surface, offset_x, offset_y).  Cleared if the byte cap is hit."""

    def __init__(self, max_bytes: int = CACHE_MAX_BYTES) -> None:
        self.d: dict = {}
        self.bytes = 0
        self.max_bytes = max_bytes
        self.misses = 0
        self.clears = 0
        self.bake_seconds = 0.0

    def get(self, key):
        v = self.d.get(key)
        if v is None:
            v = self._bake(key)
        return v

    def _bake(self, key):
        shape, b, color, k, ai = key
        import time
        t0 = time.perf_counter()
        a = ALPHA_LEVELS[k]
        ext = int(math.ceil(_EXT[shape] * b)) + 1
        n = 2 * ext + 1
        surf = pygame.Surface((n, n), pygame.SRCALPHA)
        col = (color[0], color[1], color[2], a)
        edge = (DARK[0], DARK[1], DARK[2], int(a * 0.75))
        c = ext
        if shape == "disc":
            pygame.draw.circle(surf, col, (c, c), b)
            if b >= 3:
                pygame.draw.circle(surf, edge, (c, c), b, 1)
        else:
            ang = ai * TAU / (ANGLES if shape == "streak" else SHARD_ANGLES) - math.pi if shape in _ANGLED else 0.0
            pts = {"star4": _STAR, "streak": _STREAK, "shard": _SHARD}[shape]
            poly = _poly(b, pts, ang, c)
            pygame.draw.polygon(surf, col, poly)
            if b >= 3:
                pygame.draw.polygon(surf, edge, poly, 1)
        size = n * n * 4
        if self.bytes + size > self.max_bytes:
            self.d.clear()
            self.bytes = 0
            self.clears += 1
        if pygame.display.get_surface() is not None:
            surf = surf.convert_alpha()   # display pixel format: faster blits (bake time only)
        v = (surf, ext, ext)
        self.d[key] = v
        self.bytes += size
        self.misses += 1
        self.bake_seconds += time.perf_counter() - t0
        return v

    def __len__(self) -> int:
        return len(self.d)


def particle_key(shape: str, size: float, frac: float, color, vx: float = 0.0, vy: float = 0.0):
    b = int(size * frac)
    b = 1 if b < 1 else (SIZE_MAX if b > SIZE_MAX else b)
    k = int(frac * 8)
    k = 7 if k > 7 else (0 if k < 0 else k)
    ai = 0
    if shape in _ANGLED:
        na = ANGLES if shape == "streak" else SHARD_ANGLES
        ai = int((math.atan2(vy, vx) + math.pi) * (na / TAU) + 0.5) % na
    return (shape, b, color, k, ai)


def draw_system(ps, surface, camera, shake, cache: SpriteCache, W: int = SCREEN_W, H: int = SCREEN_H) -> int:
    """Drop-in replacement for ParticleSystem.draw (works on the repo Particle fields: pos, vel, color, size, lifetime,
    max_lifetime, ptype, active).  Returns the number drawn.  No Surface is created once the sprites are cached."""
    ox = W // 2 - camera.x + shake.x
    oy = H // 2 - camera.y + shake.y
    batch = []
    add = batch.append
    cget = cache.d.get
    shape_of = _SHAPE_OF
    atan2 = math.atan2
    n = 0
    for p in ps.particles:
        if not p.active:
            continue
        sx = int(p.pos.x + ox)
        sy = int(p.pos.y + oy)
        if not (-10 < sx < W + 10 and -10 < sy < H + 10):
            continue
        frac = p.lifetime / p.max_lifetime
        shape = shape_of.get(p.ptype)
        if shape is None:
            shape = shape_of[p.ptype] = _BY_NAME.get(getattr(p.ptype, "name", "EXPLOSION"), "disc")
        b = int(p.size * frac)
        b = 1 if b < 1 else (SIZE_MAX if b > SIZE_MAX else b)
        k = int(frac * 8)
        k = 7 if k > 7 else (0 if k < 0 else k)
        if shape == "streak":
            ai = int((atan2(p.vel.y, p.vel.x) + 3.141592653589793) * (ANGLES / TAU) + 0.5) % ANGLES
        elif shape == "shard":
            ai = int((atan2(p.vel.y, p.vel.x) + 3.141592653589793) * (SHARD_ANGLES / TAU) + 0.5) % SHARD_ANGLES
        else:
            ai = 0
        key = (shape, b, p.color, k, ai)
        v = cget(key)
        if v is None:
            v = cache.get(key)
        add((v[0], (sx - v[1], sy - v[2])))
        n += 1
    if batch:
        surface.fblits(batch)          # one C call for all particles (pygame-ce >= 2.4)
    return n



# --------------------------------------------------------------------------------------------------------------------
# the hit-fx particle pool (repo Particle objects; module semantics: no gravity unless asked, drag ** (dt*60))
# --------------------------------------------------------------------------------------------------------------------
class HitPool:
    """Pool of hit-fx particles with a live count (for the soft / hard caps). Recycles the next slot when full."""

    def __init__(self, size: int = 400):
        self.particles = [Particle() for _ in range(size)]
        self._i = 0
        self.live = 0

    def _get(self):
        n = len(self.particles)
        for _ in range(n):
            p = self.particles[self._i]
            self._i = (self._i + 1) % n
            if not p.active:
                self.live += 1
                return p
        p = self.particles[self._i]
        self._i = (self._i + 1) % n
        return p

    def spawn(self, x, y, vx, vy, color, size, life, ptype, gravity=False, drag=0.98):
        p = self._get()
        p.pos.set(x, y)
        p.vel.set(vx, vy)
        p.color = color; p.size = size; p.lifetime = life; p.max_lifetime = life
        p.ptype = ptype; p.active = True; p.gravity = gravity; p.bounce = False; p.drag = drag

    def update(self, dt: float, gravity: float = config.GRAVITY):
        for p in self.particles:
            if not p.active:
                continue
            p.lifetime -= dt
            if p.lifetime <= 0:
                p.active = False
                self.live -= 1
                continue
            v = p.vel
            if p.gravity:
                v.y += gravity * dt
            p.pos.x += v.x * dt
            p.pos.y += v.y * dt
            if p.drag != 1.0:
                d = p.drag ** (dt * 60.0)
                v.x *= d
                v.y *= d

    def clear(self):
        for p in self.particles:
            p.active = False
        self.live = 0

    @property
    def active_count(self) -> int:
        return self.live

# --------------------------------------------------------------------------------------------------------------------
# cue table (single source of truth for the spec).  Sizes in px, times in s.
# --------------------------------------------------------------------------------------------------------------------
CUES = {
    "player_hit": dict(dur=0.45, ring=dict(r0="R+2", r1="min(R+46,120)", grow=0.40, w=3, hold=0.5, col="player_ring"),
                       chev=dict(n=4, rho0="R+40", rho1="R+12", grow=0.30, arm=8, w=3, hold=0.6, col="player_chev"), particles=0),
    "creature_hit": dict(dur=0.30, ring=dict(r0=3, r1="min(8+0.2R,14)", grow=0.22, w=2, hold=0.5, col="hit_ring"),
                         shards=dict(n=4, col="hit_shard", speed=(90, 190), size=(2, 3), life=0.28, spread=1.7)),
    "creature_block": dict(dur=0.30, hexa=dict(r0=6, r1="min(16+0.25R,24)", grow=0.22, w=3, hold=0.5, col="block_hex"),
                           sparks=dict(n=3, col="block_spark", speed=(40, 90), size=(1, 2), life=0.25)),
    "creature_kill": dict(dur=0.45, ring=dict(r0="R", r1="min(1.6R+14,70)", grow=0.30, w=3, hold=0.5, col="kill_ring"),
                          shards=dict(n=10, cols=("kill_shard_a", "kill_shard_b"), speed=(110, 190), size="2+R/10", life=0.38),
                          embers=dict(n=6, col="kill_ember", speed=(40, 100), size=(2, 3), life=0.35)),
    "absorb": dict(dur=0.30, streaks=dict(n=10, col="absorb", start="R+30", life=0.26, size=(4, 5))),
    "bomber_blast": dict(dur=0.55, blast=dict(r0="0.3*B", r1="B", grow=0.28, w=3, hold=0.55, tick=9, ticks=8, col="blast_ring"),
                         dust=dict(n=12, col="blast_dust", speed=(20, 60), size=(4, 7), life=0.55, within="0.5*B"),
                         shards=dict(n=8, col="blast_shard", speed=(120, 220), size=(3, 4), life=0.30)),
    "boss_hit": dict(dur=0.35, chev=dict(n=5, fan_deg=36, d0=8, d1=36, grow=0.30, arm=9, w=3, hold=0.5, col="boss_chev"), particles=0,
                     tick=dict(d0=4, d1=14, dur=0.18, arm=5, gap=0.08)),
    "boss_kill": dict(dur=1.80, ring_a=dict(t=0.0, r0="R", r1="2.0R", grow=0.40, dur=0.60, w=4, hold=0.5, col="bosskill_ring_a"),
                      shards=dict(t=0.10, n=24, cols=("bosskill_shard_a", "bosskill_shard_b"), speed=(160, 320), size="3+R/70", life=0.9),
                      dust=dict(t=0.10, n=14, col="bosskill_dust", speed=(50, 140), size=(4, 6), life=0.7),
                      ring_b=dict(t=0.40, r0="R", r1="3.0R", grow=1.40, dur=1.40, w=3, hold=0.3, col="bosskill_ring_b")),
    "xp_pickup": dict(dur=0.35, diamond=dict(s0=5, s1=3, rise=20, hold=0.5, col="xp_diamond"),
                      sparks=dict(n=2, col="xp_spark", speed=(20, 60), size=(1, 2), life=0.40), gap=0.05, cap=12),
    "level_up": dict(dur=0.95, ring_a=dict(r0="R+4", r1="R+34", grow=0.80, w=3, rise=26, hold=0.55, col="level_a"),
                     ring_b=dict(delay=0.16, r0="R+4", r1="R+22", grow=0.70, w=2, rise=26, hold=0.55, col="level_b"),
                     chev=dict(n=2, up=True, y="-(R+40), -(R+49)", rise=26, arm=7, w=3, col="level_a")),
    "evolution": dict(dur=1.40, ring_a=dict(r0="R+6", r1="R+54", grow=1.10, w=3, rise=34, hold=0.6, col="evo_a"),
                      ring_b=dict(delay=0.22, r0="R+6", r1="R+34", grow=1.00, w=2, rise=34, hold=0.6, col="evo_b"),
                      diamonds=dict(n=6, rho="R+20", drift=22, rise=30, s0=5, s1=3, col="evo_diamond")),
    "skill_up": dict(dur=0.80, ring_a=dict(r0="R+2", r1="R+16", grow=0.60, w=2, rise=16, hold=0.55, col="skill_a"),
                     ring_b=dict(delay=0.12, r0="R+2", r1="R+9", grow=0.55, w=2, rise=16, hold=0.55, col="skill_b"),
                     star=dict(size="9->7", y="-(R+16)", rise=22, col="skill_a")),
}
# worst-case particle counts per event (spec 4); the repo's current counts are in CURRENT_COUNTS
EVENT_PARTICLES = {"player_hit": 0, "creature_hit": 4, "creature_block": 3, "creature_kill": 16, "absorb": 10, "bomber_blast": 20,
                   "boss_hit": 0, "boss_kill": 38, "xp_pickup": 2, "level_up": 0, "evolution": 0, "skill_up": 0}
CURRENT_COUNTS = {"player_hit": 0, "creature_hit": 5, "creature_block": 5, "creature_kill": 20, "absorb": 20, "bomber_blast": 28,
                  "boss_hit": 0, "boss_kill": 40, "xp_pickup": 5, "level_up": 0, "evolution": 0, "skill_up": 0}

# prewarm list: (shape, colour name, largest size bucket).  Every particle the events can emit is here.
WARM = (("shard", "hit_shard", 3), ("star4", "block_spark", 2), ("shard", "kill_shard_a", 5),
        ("shard", "kill_shard_b", 5), ("disc", "kill_ember", 3), ("streak", "absorb", 5), ("disc", "blast_dust", 7),
        ("shard", "blast_shard", 4), ("shard", "bosskill_shard_a", 5), ("shard", "bosskill_shard_b", 5),
        ("disc", "bosskill_dust", 6), ("star4", "xp_spark", 2))


class Shake:
    """Screen shake: time-based, smooth, <= 8 Hz.  offset(x,y) = A*env(t)*(0.65 sin(2 pi f1 t + p1) + 0.35 sin(2 pi f2 t + p2)).

    env = smoothstep attack (60 ms) * half-Hann decay over T = max(0.40, tau*ln(A/0.1)) (the time the old 0.85/frame decay took to reach 0.1 px).
    Reduced motion: only intensities >= 5 move, as ONE nudge of min(4, 0.35 A) px that eases back in 0.15 s.
    """

    def __init__(self, reduced: bool = False, seed=None):
        self.rng = random.Random(seed)
        self.reduced = reduced
        self.clk = 0.0
        self.t = 1e9
        self.A = 0.0
        self.T = 0.0
        self.ph = [0.0, 0.0, 0.0, 0.0]
        self.nudge = (0.0, 0.0)
        self.last = {}
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.triggers = 0
        self._reroll()

    def _reroll(self):
        self.ph = [self.rng.uniform(0, TAU) for _ in range(4)]

    def envelope(self) -> float:
        if self.A <= 0 or self.t >= self.T:
            return 0.0
        a = self.t / SHAKE_ATTACK
        att = 1.0 if a >= 1.0 else a * a * (3 - 2 * a)
        return self.A * att * 0.5 * (1.0 + math.cos(math.pi * self.t / self.T))

    def remaining(self) -> float:
        """Envelope without the attack ramp: what is left of the current shake (used for the re-trigger rule)."""
        if self.A <= 0 or self.t >= self.T:
            return 0.0
        return self.A * 0.5 * (1.0 + math.cos(math.pi * self.t / self.T))

    def add(self, intensity: float, source: str = "") -> bool:
        """Trigger; returns True if it started/refreshed a shake.  Same rule as today (max of intensity and what is left)."""
        a = min(intensity, SHAKE_CAP)
        gap = SHAKE_SOURCE_GAP.get(source, 0.0)
        if gap and self.clk - self.last.get(source, -1e9) < gap:
            return False
        if self.reduced:
            if a < 5.0:
                return False
            if self.t < 0.15 and self.A > 0:       # a nudge is already running
                return False
            self.A = min(4.0, 0.35 * a)
            self.T = 0.15
            self.t = 0.0
            d = self.rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)))
            self.nudge = d
            self.last[source] = self.clk
            self.triggers += 1
            return True
        if a <= self.remaining() * 1.15:
            return False
        self.A = a
        self.T = max(SHAKE_MIN_T, SHAKE_DECAY_TAU * math.log(a / 0.1))
        self.t = 0.0
        self.last[source] = self.clk
        self.triggers += 1
        return True

    def update(self, dt: float):
        self.clk += dt
        self.t += dt
        if self.reduced:
            if self.t >= self.T:
                self.offset_x = self.offset_y = 0.0
                return
            u = self.t / self.T
            e = self.A * (1.0 - u * u * (3 - 2 * u))
            self.offset_x, self.offset_y = self.nudge[0] * e, self.nudge[1] * e
            return
        e = self.envelope()
        if e <= 0.0:
            self.offset_x = self.offset_y = 0.0
            return
        (fx1, fx2), (fy1, fy2) = SHAKE_FREQS
        p = self.ph
        c = self.clk
        self.offset_x = e * (0.65 * math.sin(TAU * fx1 * c + p[0]) + 0.35 * math.sin(TAU * fx2 * c + p[1]))
        self.offset_y = e * (0.65 * math.sin(TAU * fy1 * c + p[2]) + 0.35 * math.sin(TAU * fy2 * c + p[3]))

    @property
    def active(self) -> bool:
        return self.t < self.T and self.A > 0

    def int_offset(self):
        return int(round(self.offset_x)), int(round(self.offset_y))


class FlashState:
    """The creature / boss side of the flash limit.  Mirrors the 3-line patch in Creature.take_damage / Boss.take_damage / update."""

    def __init__(self, length: float = CREATURE_FLASH, reduced: bool = False):
        self.hit_flash = 0.0
        self.flash_gap = 0.0
        self.flash_started = False
        self.length = length
        self.reduced = reduced

    def hit(self, length: float = 0.0) -> bool:
        """Call from take_damage after damage is applied.  Returns True if this hit started a flash."""
        self.flash_started = False
        if self.flash_gap <= 0.0:
            self.hit_flash = length or self.length
            self.flash_gap = FLASH_GAP_REDUCED if self.reduced else FLASH_GAP
            self.flash_started = True
        return self.flash_started

    def update(self, dt: float):
        if self.hit_flash > 0:
            self.hit_flash -= dt
        if self.flash_gap > 0:
            self.flash_gap -= dt


def hurt_pulse(inv: float, reduced: bool = False) -> float:
    """Replacement for `math.sin(self.invulnerable * 20) * 0.06` in Player.draw: 2.71 Hz, none when reduced."""
    return 0.0 if reduced else math.sin(inv * HURT_PULSE_K) * HURT_PULSE_AMP


def hurt_outline_set(hurt_t: float, reduced: bool = False) -> int:
    """Which dash set (0/1) is visible; fixed 0 in reduced motion."""
    return 0 if reduced else int(hurt_t / (HURT_BLINK_PERIOD / 2)) & 1


def draw_hurt_outline(surface, sx: float, sy: float, R: float, hurt_t: float, reduced: bool = False,
                      light=PAL["player_chev"]) -> None:
    """Non-colour invulnerability cue: dark ring + 8 light dashes (22.5 deg each); dash set A and B swap every 0.2 s (2.5 Hz,
    every point toggles at 1.25 Hz).  9 draw calls, no Surface."""
    r = int(R) + 5
    ctr = (int(sx), int(sy))
    rect = pygame.Rect(ctr[0] - r, ctr[1] - r, 2 * r, 2 * r)
    pygame.draw.circle(surface, DARK, ctr, r, 4)
    off = hurt_outline_set(hurt_t, reduced) * (TAU / 16)
    for i in range(8):
        a0 = i * (TAU / 8) + off
        pygame.draw.arc(surface, light, rect, a0, a0 + TAU / 16, 2)


def chev_points(px: float, py: float, ang: float, pt: int, arm: float):
    """Chevron (3 points): apex at (px,py); apex points along `ang` when pt=+1 (outward) or against it when pt=-1 (inward)."""
    fa = ang if pt > 0 else ang + math.pi
    a1, a2 = fa + math.pi - 0.6, fa + math.pi + 0.6     # 34 deg half-angle
    return [(px + arm * math.cos(a1), py + arm * math.sin(a1)), (px, py), (px + arm * math.cos(a2), py + arm * math.sin(a2))]


# --------------------------------------------------------------------------------------------------------------------
# effects: rings, chevrons, hexagon, diamond, star, blast.  Drawn with pygame.draw; "alpha" = colour mixed toward the act
# MID ground tone (no per-frame Surface, any radius).
# --------------------------------------------------------------------------------------------------------------------
K_RING, K_CHEV, K_HEX, K_DIAMOND, K_STAR, K_BLAST = range(1, 7)


class Fx:
    __slots__ = ("active", "kind", "x", "y", "follow", "t", "dur", "delay", "p0", "p1", "p2", "p3", "p4", "p5", "ang", "pt",
                 "light", "dark", "dx", "dy")

    def __init__(self):
        self.active = False


class HitFx:
    def __init__(self, reduced: bool = False, seed=None, W: int = SCREEN_W, H: int = SCREEN_H):
        self.W, self.H = W, H
        self.reduced = reduced
        self.rng = random.Random(seed)
        self.cache = CACHE
        self.ps = HitPool()
        self.fx = [Fx() for _ in range(FX_POOL)]
        self.fade_to = GROUND_FADE[0]
        self.dropped = 0
        self.sched = []                       # (delay, name, x, y, R) staged boss-kill pieces; list reused
        self.xp_clock = 0.0
        self.last_xp = -9.0
        self.tick_clock = {}
        self.clk = 0.0
        self.skipped_particles = 0
        self.live_fx = 0
        self._pt = pygame.Vector2()           # reused hit point
        self.numbers = None                   # DamageNumbers, built on first use when GFX_DAMAGE_NUMBERS is on

    # ---- set-up ----
    def set_ground(self, act: int):
        self.fade_to = GROUND_FADE[max(0, min(9, act))]

    def prewarm(self) -> int:
        """Bake every particle sprite the events can emit.  Call at map load; returns sprite count."""
        for shape, name, bmax in WARM:
            col = PAL[name]
            for b in range(1, max(bmax, 1) + 1):
                for k in range(8):
                    for ai in (range(ANGLES) if shape == "streak" else range(SHARD_ANGLES) if shape == "shard" else (0,)):
                        key = (shape, b, col, k, ai)
                        if key not in self.cache.d:
                            self.cache._bake(key)
        return len(self.cache)

    # ---- low level ----
    def _slot(self):
        for e in self.fx:
            if not e.active:
                return e
        self.dropped += 1
        return None

    def _add(self, kind, x, y, dur, light, dark=DARK, delay=0.0, follow=None, p=(0, 0, 0, 0, 0, 0), ang=0.0, pt=1, dx=0.0, dy=0.0):
        e = self._slot()
        if e is None:
            return None
        e.active = True; e.kind = kind; e.x = x; e.y = y; e.follow = follow; e.t = 0.0; e.dur = dur; e.delay = delay
        e.p0, e.p1, e.p2, e.p3, e.p4, e.p5 = p
        e.ang = ang; e.pt = pt; e.light = light; e.dark = dark; e.dx = dx; e.dy = dy
        self.live_fx += 1
        return e

    def _emit(self, x, y, n, color, speed, size, life, ptype, direction=None, spread=TAU, gravity=False, drag=0.98, priority=0):
        live = self.ps.live
        if live >= LIVE_HARD_CAP or (priority == 0 and live >= LIVE_SOFT_CAP):
            self.skipped_particles += n
            return 0
        rng = self.rng
        if self.reduced:
            n = max(1, (n + 1) // 2)
        for _ in range(n):
            a = rng.uniform(0, spread) if direction is None else direction + rng.uniform(-spread / 2, spread / 2)
            s = rng.uniform(*speed)
            sz = rng.uniform(*size) if isinstance(size, tuple) else size
            self.ps.spawn(x, y, math.cos(a) * s, math.sin(a) * s, color, sz, life + rng.uniform(-0.04, 0.04), ptype, gravity, drag)
        return n

    def update(self, dt: float):
        self.clk += dt
        self.ps.update(dt)
        for e in self.fx:
            if not e.active:
                continue
            if e.delay > 0:
                e.delay -= dt
                continue
            e.t += dt
            if e.t >= e.dur:
                e.active = False
                self.live_fx -= 1
        if self.sched:
            keep = []
            for item in self.sched:
                d, name, x, y, R = item
                d -= dt
                if d <= 0:
                    self._stage(name, x, y, R)
                else:
                    keep.append((d, name, x, y, R))
            self.sched = keep

    # ---- drawing of the vector effects ----
    def _c(self, c, a):
        return c if a >= 0.999 else mix(self.fade_to, c, a)

    def draw(self, surface, camera, shake) -> int:
        ox = self.W // 2 - camera.x + shake.x
        oy = self.H // 2 - camera.y + shake.y
        n = 0
        circle, lines, polygon, line, arc = pygame.draw.circle, pygame.draw.lines, pygame.draw.polygon, pygame.draw.line, pygame.draw.arc
        for e in self.fx:
            if not e.active or e.delay > 0:
                continue
            u = e.t / e.dur
            a = alpha_at(u, e.p5)
            if a <= 0.0:
                continue
            if e.follow is not None:
                bx = e.follow.pos.x + e.x
                by = e.follow.pos.y + e.y
            else:
                bx, by = e.x, e.y
            sx = bx + ox
            sy = by + oy
            k = e.kind
            lc = self._c(e.light, a)
            dc = self._c(e.dark, a * a)       # the dark underlay fades out first (no dark ghost ring)
            if k == K_RING or k == K_BLAST or k == K_HEX:
                g = e.t / e.p2 if e.p2 > 0 else 1.0
                r = e.p0 + (e.p1 - e.p0) * ease_out(g)
                if k != K_HEX:
                    sy -= e.p4 * ease_out(u)
                if sx < -r - 12 or sx > self.W + r + 12 or sy < -r - 12 or sy > self.H + r + 12:
                    continue
                w = int(e.p3)
                if k == K_HEX:
                    pts = [(sx + r * math.cos(i * TAU / 6), sy + r * math.sin(i * TAU / 6)) for i in range(6)]
                    polygon(surface, dc, pts, w + 2)
                    polygon(surface, lc, pts, w)
                else:
                    ri = int(r)
                    if ri > w:
                        circle(surface, dc, (int(sx), int(sy)), ri, w + 2)
                        circle(surface, lc, (int(sx), int(sy)), ri, w)
                    if k == K_BLAST:
                        for i in range(8):
                            ca, sa = math.cos(i * TAU / 8 + TAU / 16), math.sin(i * TAU / 8 + TAU / 16)
                            p0 = (sx + ca * (r - 9), sy + sa * (r - 9))
                            p1 = (sx + ca * r, sy + sa * r)
                            line(surface, dc, p0, p1, 4)
                            line(surface, lc, p0, p1, 2)
            elif k == K_CHEV:
                g = e.t / e.p2 if e.p2 > 0 else 1.0
                d = e.p0 + (e.p1 - e.p0) * ease_out(g)
                ca, sa = math.cos(e.ang), math.sin(e.ang)
                pts = chev_points(sx + ca * d, sy + sa * d, e.ang, e.pt, e.p3)
                lines(surface, dc, False, pts, int(e.p4) + 2)
                lines(surface, lc, False, pts, int(e.p4))
            elif k == K_DIAMOND or k == K_STAR:
                g = ease_out(u)
                size = e.p0 + (e.p1 - e.p0) * u
                px = sx + e.dx * g
                py = sy + e.dy * g - e.p4 * g
                if k == K_DIAMOND:
                    pts = [(px, py - size), (px + size * 0.75, py), (px, py + size), (px - size * 0.75, py)]
                    big = [(px, py - size - 1.5), (px + size * 0.75 + 1.5, py), (px, py + size + 1.5), (px - size * 0.75 - 1.5, py)]
                else:
                    s = size
                    pts = [(px + x * s * 0.5, py + y * s * 0.5) for x, y in _STAR]
                    big = [(px + x * (s + 1.5) * 0.5, py + y * (s + 1.5) * 0.5) for x, y in _STAR]
                polygon(surface, dc, big)
                polygon(surface, lc, pts)
            n += 1
        return n

    # ------------------------------------------------------------------------------------------------------------
    # events.  R = entity radius (px); positions are world px.
    # ------------------------------------------------------------------------------------------------------------
    def _ring(self, x, y, r0, r1, grow, w, hold, col, dur, rise=0.0, delay=0.0, follow=None, kind=K_RING):
        if self.reduced:
            r1 = r0 + (r1 - r0) * (1.0 if kind == K_BLAST else 0.5)
            rise = 0.0
        return self._add(kind, x, y, dur, PAL[col], DARK, delay, follow, (r0, r1, grow, w, rise, hold))

    def player_hit(self, player, R=None):
        R = R or player.size
        c = CUES["player_hit"]
        self._ring(0.0, 0.0, R + 2, min(R + 46, 120), 0.40, 3, 0.5, "player_ring", c["dur"], follow=player)
        rho0, rho1 = R + 40, R + 12
        for i in range(4):
            ang = math.pi / 4 + i * math.pi / 2
            if self.reduced:
                rho0 = rho1 = R + 22
            self._add(K_CHEV, 0.0, 0.0, c["dur"], PAL["player_chev"], DARK, 0.0, player, (rho0, rho1, 0.30, 8, 3, 0.6), ang, -1)

    def creature_hit(self, hit_pt, R, out_dir, blocked=False, ring=True):
        """hit_pt: Vector2-like; out_dir: angle (rad) pointing away from the attacker.  ring=False when flash_started was False."""
        x, y = hit_pt.x, hit_pt.y
        if blocked:
            if ring:
                self._ring(x, y, 6, min(16 + 0.25 * R, 24), 0.22, 3, 0.5, "block_hex", 0.30, kind=K_HEX)
            if not self.reduced:
                self._emit(x, y, 3, PAL["block_spark"], (40, 90), (1, 2), 0.25, PType.SPARKLE, out_dir, 2.0)
            return
        if ring:
            self._ring(x, y, 3, min(8 + 0.2 * R, 14), 0.22, 2, 0.5, "hit_ring", 0.30)
        if not self.reduced:
            self._emit(x, y, 4, PAL["hit_shard"], (90, 190), (2, 3), 0.28, PType.SHARD, out_dir, 1.7)

    def creature_kill(self, pos, R):
        x, y = pos.x, pos.y
        self._ring(x, y, R, min(1.6 * R + 14, 70), 0.30, 3, 0.5, "kill_ring", 0.45)
        size = max(2.0, min(5.0, 2 + R / 10))
        n = 10
        if self.reduced:
            n = 5
        a0 = self.rng.uniform(0, TAU)
        for i in range(n):
            a = a0 + i * TAU / n + self.rng.uniform(-0.14, 0.14)
            s = self.rng.uniform(110, 190)
            col = PAL["kill_shard_a"] if i % 2 == 0 else PAL["kill_shard_b"]
            if self.ps.live >= LIVE_HARD_CAP:
                self.skipped_particles += 1
                continue
            self.ps.spawn(x, y, math.cos(a) * s, math.sin(a) * s, col, size, 0.38 + self.rng.uniform(-0.04, 0.04), PType.SHARD, False, 0.96)
        self._emit(x, y, 6, PAL["kill_ember"], (40, 100), (2, 3), 0.35, PType.EXPLOSION, priority=1)

    def absorb(self, pos, R, player_pos):
        """Inward streaks: start on a ring of R+30 round the creature, arrive at the player centre after 0.26 s."""
        n = 5 if self.reduced else 10
        rr = R + 30
        life = 0.26
        a0 = self.rng.uniform(0, TAU)
        for i in range(n):
            a = a0 + i * TAU / n + self.rng.uniform(-0.2, 0.2)
            sx, sy = pos.x + math.cos(a) * rr, pos.y + math.sin(a) * rr
            dx, dy = player_pos.x - sx, player_pos.y - sy
            # drag 1.0: straight line at constant speed
            if self.ps.live >= LIVE_HARD_CAP:
                self.skipped_particles += 1
                continue
            self.ps.spawn(sx, sy, dx / life, dy / life, PAL["absorb"], self.rng.uniform(4, 5), life, PType.TRAIL, False, 1.0)

    def bomber_blast(self, pos, B):
        """B = creature.explosion_radius.  The ring's final radius is exactly B (hit honesty)."""
        x, y = pos.x, pos.y
        self._ring(x, y, 0.3 * B, B, 0.28, 3, 0.55, "blast_ring", 0.55, kind=K_BLAST)
        nd = 6 if self.reduced else 12
        for _ in range(nd):
            r = self.rng.uniform(0, 0.5 * B)
            a = self.rng.uniform(0, TAU)
            s = self.rng.uniform(20, 60)
            if self.ps.live >= LIVE_HARD_CAP:
                self.skipped_particles += 1
                continue
            self.ps.spawn(x + math.cos(a) * r, y + math.sin(a) * r, math.cos(a) * s, math.sin(a) * s, PAL["blast_dust"],
                          self.rng.uniform(4, 7), 0.55, PType.EXPLOSION, False, 0.96)
        self._emit(x, y, 8, PAL["blast_shard"], (120, 220), (3, 4), 0.30, PType.SHARD, priority=1)

    def boss_hit(self, hit_pt, boss_pos, R, burst=True):
        """burst=flash_started and the 0.34 s gap; otherwise one small tick chevron (at most every 0.08 s)."""
        out = math.atan2(hit_pt.y - boss_pos.y, hit_pt.x - boss_pos.x)
        if burst:
            n = 3 if self.reduced else 5
            fan = math.radians(36)
            for i in range(n):
                ang = out + (i - (n - 1) / 2) * fan
                d0, d1 = (8, 36) if not self.reduced else (22, 22)
                self._add(K_CHEV, hit_pt.x, hit_pt.y, 0.35, PAL["boss_chev"], DARK, 0.0, None, (d0, d1, 0.30, 9, 3, 0.5), ang, 1)
        else:
            if self.clk - self.tick_clock.get("boss", -9) < 0.08:
                return
            self.tick_clock["boss"] = self.clk
            d0, d1 = (4, 14) if not self.reduced else (9, 9)
            self._add(K_CHEV, hit_pt.x, hit_pt.y, 0.18, PAL["boss_chev"], DARK, 0.0, None, (d0, d1, 0.15, 5, 3, 0.5), out, 1)

    def boss_kill(self, pos, R):
        x, y = pos.x, pos.y
        self._ring(x, y, R, 2.0 * R, 0.40, 4, 0.5, "bosskill_ring_a", 0.60)
        self.sched.append((0.10, "bk_burst", x, y, R))
        self.sched.append((0.40, "bk_ring", x, y, R))

    def _stage(self, name, x, y, R):
        if name == "bk_burst":
            n = 12 if self.reduced else 24
            size = 3 + R / 70
            a0 = self.rng.uniform(0, TAU)
            for i in range(n):
                a = a0 + i * TAU / n + self.rng.uniform(-0.08, 0.08)
                s = self.rng.uniform(160, 320)
                col = PAL["bosskill_shard_a"] if i % 2 == 0 else PAL["bosskill_shard_b"]
                if self.ps.live >= LIVE_HARD_CAP:
                    self.skipped_particles += 1
                    continue
                self.ps.spawn(x, y, math.cos(a) * s, math.sin(a) * s, col, size, 0.9, PType.SHARD, False, 0.96)
            self._emit(x, y, 14, PAL["bosskill_dust"], (50, 140), (4, 6), 0.7, PType.EXPLOSION, priority=1)
        elif name == "bk_ring":
            self._ring(x, y, R, 3.0 * R, 1.40, 3, 0.3, "bosskill_ring_b", 1.40)

    def xp_pickup(self, pos):
        if self.clk - self.last_xp < CUES["xp_pickup"]["gap"] or self.live_fx >= FX_POOL - 20:
            return
        self.last_xp = self.clk
        rise = 0.0 if self.reduced else 20.0
        self._add(K_DIAMOND, pos.x, pos.y, 0.35, PAL["xp_diamond"], DARK, 0.0, None, (5, 3, 0, 0, rise, 0.5))
        self._emit(pos.x, pos.y, 2, PAL["xp_spark"], (20, 60), (1, 2), 0.40, PType.SPARKLE)

    def _chev_up(self, player, R, col):
        rise = 0 if self.reduced else 26
        for i in range(2):
            self._add(K_CHEV, 0.0, -(R + 40 + i * 9), 0.95, PAL[col], DARK, 0.0, player, (0, rise, 0.90, 7, 3, 0.55), -math.pi / 2, 1)

    def level_up(self, player, R=None):
        R = R or player.size
        self._ring(0.0, 0.0, R + 4, R + 34, 0.80, 3, 0.55, "level_a", 0.95, 26, follow=player)
        self._ring(0.0, 0.0, R + 4, R + 22, 0.70, 2, 0.55, "level_b", 0.95, 26, 0.16, follow=player)
        self._chev_up(player, R, "level_a")

    def evolution(self, player, R=None):
        R = R or player.size
        self._ring(0.0, 0.0, R + 6, R + 54, 1.10, 3, 0.6, "evo_a", 1.40, 34, follow=player)
        self._ring(0.0, 0.0, R + 6, R + 34, 1.00, 2, 0.6, "evo_b", 1.40, 34, 0.22, follow=player)
        n = 3 if self.reduced else 6
        for i in range(n):
            a = i * TAU / n - math.pi / 2
            rho = R + 20
            drift = 22 if not self.reduced else 0
            rise = 30 if not self.reduced else 0
            self._add(K_DIAMOND, math.cos(a) * rho, math.sin(a) * rho, 1.40, PAL["evo_diamond"], DARK, 0.0, player,
                      (5, 3, 0, 0, rise, 0.6), 0, 1, math.cos(a) * drift, math.sin(a) * drift)

    def skill_up(self, player, R=None):
        R = R or player.size
        self._ring(0.0, 0.0, R + 2, R + 16, 0.60, 2, 0.55, "skill_a", 0.80, 16, follow=player)
        self._ring(0.0, 0.0, R + 2, R + 9, 0.55, 2, 0.55, "skill_b", 0.80, 16, 0.12, follow=player)
        self._add(K_STAR, 0.0, -(R + 16), 0.80, PAL["skill_a"], DARK, 0.0, player, (9, 7, 0, 0, 0 if self.reduced else 22, 0.55))

    # ------------------------------------------------------------------------------------------------------------
    # repo glue (TASK-059): what Game calls, so game.py stays a one-liner per event
    # ------------------------------------------------------------------------------------------------------------
    def set_reduced(self, reduced: bool) -> None:
        self.reduced = reduced

    def prewarm_all(self) -> int:
        """Bake every sprite the hit-fx events AND the game's remaining emits (trail, artifact blast) can draw."""
        n = self.prewarm()
        for shape, col, bmax in GAME_WARM:
            for b in range(1, bmax + 1):
                for k in range(8):
                    for ai in (range(ANGLES) if shape == "streak" else range(SHARD_ANGLES) if shape == "shard" else (0,)):
                        key = (shape, b, col, k, ai)
                        if key not in self.cache.d:
                            self.cache._bake(key)
        if config.GFX_DAMAGE_NUMBERS and self.numbers is None:
            self.numbers = DamageNumbers()
        return len(self.cache) if n is not None else 0

    def clear(self) -> None:
        """Drop every live effect and particle (map change)."""
        for e in self.fx:
            e.active = False
        self.live_fx = 0
        self.sched = []
        self.ps.clear()

    def on_creature_hit(self, creature, from_pos, damage: float = 0.0) -> None:
        """2.2 / 2.3: the hit point is on the creature's edge toward the shot; out = away from the creature centre."""
        dx, dy = from_pos.x - creature.pos.x, from_pos.y - creature.pos.y
        d = math.hypot(dx, dy)
        R = creature.radius
        if d > 1:
            hx, hy = creature.pos.x + dx / d * R, creature.pos.y + dy / d * R
        else:
            hx, hy = creature.pos.x, creature.pos.y
        self._pt.x, self._pt.y = hx, hy
        self.creature_hit(self._pt, R, math.atan2(dy, dx), blocked=creature.last_hit_blocked,
                          ring=creature.flash_started)
        if self.numbers is not None and config.GFX_DAMAGE_NUMBERS and damage > 0:
            self.numbers.spawn(creature.pos.x, creature.pos.y - R, damage, creature)

    def on_boss_hit(self, boss, from_pos) -> None:
        """2.7: burst when the hit started a flash (<= 1 per 0.34 s), else a tick chevron."""
        dx, dy = from_pos.x - boss.pos.x, from_pos.y - boss.pos.y
        d = math.hypot(dx, dy)
        R = boss.radius
        if d > 1:
            self._pt.x, self._pt.y = boss.pos.x + dx / d * R, boss.pos.y + dy / d * R
        else:
            self._pt.x, self._pt.y = boss.pos.x + R, boss.pos.y
        self.boss_hit(self._pt, boss.pos, R, burst=boss.flash_started)

    def on_messages(self, player, messages) -> None:
        """2.10 / 2.11: add_xp / evolution messages -> level-up or evolution cue (one each)."""
        lv = evo = False
        for m in messages:
            if m.startswith("Evolution"):
                evo = True
            elif "level" in m.lower():
                lv = True
        if lv:
            self.level_up(player)
        if evo:
            self.evolution(player)

    def update_all(self, dt: float) -> None:
        self.update(dt)
        if self.numbers is not None:
            self.numbers.update(dt)

    def draw_all(self, surface, camera, shake) -> None:
        """Hit-fx particles (cached, one fblits) then the vector effects, then damage numbers if turned on."""
        draw_system(self.ps, surface, camera, shake, self.cache, self.W, self.H)
        self.draw(surface, camera, shake)
        if self.numbers is not None and config.GFX_DAMAGE_NUMBERS:
            self.numbers.draw(surface, camera, shake, self.reduced)


# the game's own emits that stay (drawn through draw_system when GFX_HITFX is on): player trail, artifact blast
GAME_WARM = (("streak", config.COLOR_PLAYER, 4), ("disc", (255, 100, 30), 6))
CACHE = SpriteCache()                 # shared by HitFx and ParticleSystem.draw


def draw_particles(ps, surface, camera, shake) -> int:
    """ParticleSystem.draw when GFX_HITFX is on: cached sprites, one fblits."""
    return draw_system(ps, surface, camera, shake, CACHE)


def flash(entity, length: float) -> None:
    """1.1: replaces `entity.hit_flash = length` in take_damage. Off: exactly that. On: a flash starts only when the
    entity's flash_gap has run out (0.34 s, 0.50 s reduced); entity.flash_started tells whether this call started one."""
    if not config.GFX_HITFX:
        entity.hit_flash = length
        return
    if entity.flash_gap <= 0.0:
        entity.flash_started = True
        entity.hit_flash = length
        entity.flash_gap = FLASH_GAP_REDUCED if config.REDUCED_MOTION else FLASH_GAP


def tick_flash(entity, dt: float) -> None:
    if entity.flash_gap > 0:
        entity.flash_gap -= dt


# --------------------------------------------------------------------------------------------------------------------
# PROPOSAL (default off): floating damage numbers.  Not part of the accepted scope; see spec section 2.12.
# --------------------------------------------------------------------------------------------------------------------
class DamageNumbers:
    SLOTS = 24
    LIFE = 0.60
    RISE = 28
    MERGE = 0.25          # hits on one entity within this window add into the same number (max 4 numbers/s per entity)

    def __init__(self):
        font = pygame.font.Font(None, 22)
        self.glyph = {}
        for ch in "0123456789":
            base = font.render(ch, True, (255, 255, 255))
            edge = font.render(ch, True, DARK)
            s = pygame.Surface((base.get_width() + 2, base.get_height() + 2), pygame.SRCALPHA)
            for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
                s.blit(edge, (dx, dy))
            s.blit(base, (1, 1))
            self.glyph[ch] = s
        self.items = [[False, 0.0, 0.0, 0, 0.0, None] for _ in range(self.SLOTS)]   # active, x, y, value, t, owner

    def spawn(self, x, y, value, owner=None):
        free = None
        for it in self.items:
            if it[0] and owner is not None and it[5] is owner and it[4] < self.MERGE:
                it[3] += int(value)
                return
            if not it[0] and free is None:
                free = it
        if free is not None:
            free[0] = True; free[1] = x; free[2] = y; free[3] = int(value); free[4] = 0.0; free[5] = owner

    def update(self, dt):
        for it in self.items:
            if it[0]:
                it[4] += dt
                if it[4] >= self.LIFE:
                    it[0] = False

    def draw(self, surface, camera, shake, reduced=False):
        ox = SCREEN_W // 2 - camera.x + shake.x
        oy = SCREEN_H // 2 - camera.y + shake.y
        for it in self.items:
            if not it[0]:
                continue
            u = it[4] / self.LIFE
            rise = 0 if reduced else self.RISE * ease_out(u)
            txt = str(it[3])
            w = sum(self.glyph[c].get_width() - 2 for c in txt)
            x = int(it[1] + ox - w / 2)
            y = int(it[2] + oy - rise - 10)
            for c in txt:
                g = self.glyph[c]
                surface.blit(g, (x, y))
                x += g.get_width() - 2
