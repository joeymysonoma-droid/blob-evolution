"""TASK-045 boss / mini-boss art + shared telegraph kit (visual only); TASK-058 (A1) adoption of the reference module.

Taken from /workspace/handoffs/TASK-045-boss_shapes.py (Visual Designer's tested bake of the spec recipes; spec section 9
says its values win). Repo changes, all marked "A1:": repo-only imports (no handoff paths, no sys.path edits), layer
alpha is restored after a faded blit, ring_out gains a 3 px "phase" style and caches rings up to 224 px.  Everything is baked lazily into
SRCALPHA sprites (bounded cache, cleared with clear() when the map ends); per frame a
boss costs 1-3 blits + draw_blob + one circle.  No hitbox / stat / AI is touched.

    bake(key, phase, R, step=0, var=0) -> (back, front)     # SRCALPHA, canvas half = ceil(1.8R)+6 (None = empty layer)
    draw_boss(dst, key, phase, sx, sy, R, t, aim, ...)        # composes the whole boss
    zone / lane / fan / ring_out / mark / safe_brackets       # telegraph kit (section 2.4)
    shot_sprite(shape, colour)  view_mask(name)  name_plate(...)  phase_pips(...)

Angles: radians, screen coordinates (y down, +x = 0, +pi/2 = down).
`step` = aim step (minis, 16), anim step (8) or spin step (24, bosses); `var` = per-entity variant
(Ash: 0 dim / 1 lit anvil; Masks: worn mask 0..2; First Sprout: 0 shielded / 1 free; Dry Maw: 0 surfaced /
1 hidden mound; Last Whole: bitmask of lit arcs; Borrowed Face / Forgotten Shape: 046 enemy type index).
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Tuple

import pygame

Color = Tuple[int, int, int]
TAU = math.tau
WHITE = (255, 255, 255)

# =====================================================================  DATA (exact RGB from spec / data.py)
GROUND = [(40, 98, 54), (62, 70, 32), (40, 56, 104), (80, 36, 22), (48, 80, 104),
          (104, 80, 48), (72, 38, 108), (28, 23, 42), (26, 36, 76), (76, 24, 68)]
ELEM = {  # layer index -> telegraph / element outline colours
    0: {"seed": (200, 245, 130), "thorn": (255, 150, 190)},
    1: {"toxic": (205, 255, 70), "droplet": (235, 255, 150)},
    2: {"echo": (190, 240, 255), "ghost": (255, 235, 170)},
    3: {"fire": (255, 205, 90), "ember": (255, 150, 60)},
    4: {"frost": (235, 248, 255), "chill": (150, 210, 255)},
    5: {"mirage": (255, 240, 190), "wind": (210, 250, 240)},
    6: {"mask": (255, 200, 235), "pollen": (255, 235, 130)},
    7: {"void": (215, 200, 255), "hush": (235, 225, 255)},
    8: {"lightning": (255, 250, 170), "wind": (170, 240, 235)},
    9: {"fire": (255, 160, 70), "ice": (175, 225, 255), "toxic": (200, 255, 80), "anchor": (255, 130, 205)},
}
# element id -> (shot shape, outline colour, dark fill, default layer)
ELEMENTS: Dict[str, Tuple[str, Color, Color, int]] = {
    "growth": ("trefoil", (200, 245, 130), (20, 60, 20), 0),
    "toxic": ("bubble", (205, 255, 70), (30, 45, 10), 1),
    "echo": ("double_ring", (190, 240, 255), (10, 20, 60), 2),
    "fire": ("triangle", (255, 205, 90), (70, 16, 6), 3),
    "frost": ("hexagon", (235, 248, 255), (10, 24, 56), 4),
    "mirage": ("diamond", (255, 240, 190), (60, 40, 10), 5),
    "dream": ("crescent", (255, 200, 235), (40, 10, 70), 6),
    "void": ("void_disc", (215, 200, 255), (8, 6, 16), 7),
    "lightning": ("bolt", (255, 250, 170), (6, 12, 40), 8),
    "anchor": ("anchor_disc", (255, 130, 205), (40, 6, 34), 9),
}
_ENT: Dict[str, dict] = {}


def _reg(key, name, layer, R, B, C, K, mini=False, **kw):
    d = dict(key=key, name=name, layer=layer, R=R, B=B, C=C, K=K, mini=mini, blob=True, eyes=True,
             rim="solid", edge=None, phases=1, dyn=None, kind=None, n=1, period=1.0, spin=None)
    d.update(kw)
    _ENT[key] = d


# ----- bosses (name, layer, R, B, C, K)
_reg("sprouting", "Warden of Sprouting", 0, 50, (60, 140, 70), (140, 230, 120), (190, 235, 170), phases=2)
_reg("rot", "Warden of Rot", 1, 60, (80, 110, 40), (160, 200, 60), (215, 235, 140), phases=2)
_reg("echoes", "Warden of Echoes", 2, 70, (70, 110, 180), (160, 210, 255), (200, 225, 255), phases=2,
     spin=("front", 24, 20.0 / 24))        # 12 s per turn -> 0.5 s per step
_reg("ash", "Warden of Ash", 3, 80, (180, 70, 30), (255, 140, 60), (255, 200, 130), phases=3, dyn="both",
     spin=("front", 24, 1 / (0.17 * 24)))
_reg("frost", "Warden of Frost", 4, 90, (140, 180, 210), (230, 245, 255), (240, 250, 255), phases=3,
     edge=(20, 40, 70))
_reg("thirst", "Warden of Thirst", 5, 100, (190, 150, 70), (255, 220, 120), (255, 240, 190), phases=3,
     spin=("front", 24, 10.0 / 0.2 / 24))   # 0.2 turn / 10 s
_reg("masks", "Warden of Masks", 6, 110, (120, 60, 160), (200, 130, 255), (235, 200, 255), phases=3, dyn="front")
_reg("silence", "Warden of Silence", 7, 120, (30, 24, 44), (96, 84, 140), (210, 195, 255), phases=3, eyes=False,
     spin=("back", 24, 1 / (0.08 * 24)))
_reg("ascent", "Warden of Ascent", 8, 130, (100, 120, 200), (200, 220, 255), (230, 240, 255), phases=3)
_reg("anchor", "Warden of the Divide", 9, 140, (160, 40, 120), (255, 100, 200), (255, 190, 230), phases=3)
# ----- minis
_AIM = dict(kind="aim", n=16, dyn="front")
_reg("cradle_husk", "Cradle Husk", 0, 35, (120, 100, 60), (190, 170, 100), (235, 215, 150), True, blob=False, rim="none", **_AIM)
_reg("first_sprout", "First Sprout", 0, 37, (70, 170, 90), (255, 150, 190), (215, 255, 200), True, dyn="front")
_reg("sinking_bloat", "Sinking Bloat", 1, 37, (150, 170, 60), (220, 235, 110), (240, 250, 170), True)
_reg("green_mourner", "Green Mourner", 1, 37, (60, 150, 120), (150, 230, 200), (190, 250, 225), True,
     kind="anim", n=8, period=1 / 0.7, dyn="back")
_reg("glass_clerk", "Glass Clerk", 2, 39, (120, 170, 220), (220, 240, 255), (225, 242, 255), True, blob=False, rim="none")
_reg("unfinished_entry", "Unfinished Entry", 2, 39, (150, 170, 210), (230, 240, 255), (235, 242, 255), True, blob=False, rim="none")
_reg("cinder_anvil", "Cinder Anvil", 3, 39, (70, 60, 64), (255, 120, 40), (255, 190, 120), True, blob=False, rim="none")
_reg("ember_runner", "Ember Runner", 3, 41, (230, 100, 30), (255, 220, 100), (255, 225, 150), True, blob=False, rim="none",
     kind="aim", n=16, dyn="front")
_reg("rime_sentinel", "Rime Sentinel", 4, 43, (170, 205, 230), (245, 252, 255), (245, 252, 255), True, blob=False, rim="none",
     edge=(20, 40, 70), **_AIM)
_reg("drift_sleeper", "Drift Sleeper", 4, 43, (110, 130, 200), (200, 215, 255), (215, 225, 255), True, blob=False, rim="none",
     kind="anim", n=8, period=2.0, dyn="front")
_reg("oasis_lure", "Oasis Lure", 5, 45, (60, 190, 200), (200, 255, 245), (215, 255, 250), True, blob=False, rim="none")
_reg("dry_maw", "Dry Maw", 5, 45, (150, 100, 60), (255, 200, 130), (255, 225, 175), True, eyes=False, dyn="both")
_reg("borrowed_face", "Borrowed Face", 6, 49, (200, 190, 220), (255, 250, 255), (250, 245, 255), True, rim="dashed", dyn="both")
_reg("pollen_sleeper", "Pollen Sleeper", 6, 49, (230, 200, 90), (255, 245, 170), (255, 245, 190), True, eyes=False,
     kind="anim", n=8, period=2.0, dyn="front")
_reg("quiet_hollow", "Quiet Hollow", 7, 51, (16, 12, 26), (120, 100, 170), (205, 190, 255), True, blob=False, rim="solid")
_reg("forgotten_shape", "Forgotten Shape", 7, 51, (110, 110, 125), (170, 170, 185), (220, 220, 235), True, eyes=False,
     rim="dashed", dyn="both")
_reg("updraft_herald", "Updraft Herald", 8, 47, (150, 200, 230), (240, 250, 255), (240, 250, 255), True, blob=False, rim="none", **_AIM)
_reg("verdict_pillar", "Verdict Pillar", 8, 47, (210, 205, 185), (255, 250, 215), (255, 252, 225), True, blob=False, rim="none")
_reg("first_split", "First Split", 9, 53, (100, 200, 230), (230, 250, 255), (235, 250, 255), True, blob=False, rim="none", **_AIM)
_reg("last_whole", "Last Whole", 9, 53, (225, 225, 240), (255, 255, 255), (255, 255, 255), True, eyes=False,
     edge=(30, 30, 50), dyn="front")

BOSSES = ["sprouting", "rot", "echoes", "ash", "frost", "thirst", "masks", "silence", "ascent", "anchor"]
MINIS = [k for k, d in _ENT.items() if d["mini"]]
ALL_KEYS = BOSSES + MINIS
# per-phase palettes where the spec changes them (B, C, K); missing -> base palette
_PAL = {
    ("sprouting", 2): ((60, 140, 70), (255, 175, 205), (190, 235, 170)),
    ("rot", 2): ((80, 110, 40), (210, 235, 90), (215, 235, 140)),
    ("thirst", 3): ((190, 150, 70), (255, 245, 190), (255, 240, 190)),
    ("ascent", 1): ((100, 120, 200), (200, 220, 255), (230, 240, 255)),
    ("ascent", 2): ((140, 110, 200), (220, 200, 255), (238, 225, 255)),
    ("ascent", 3): ((170, 200, 230), (245, 250, 255), (250, 252, 255)),
}
ASCENT_NAMES = ("Warden of Ascent", "Warden of Echoes", "Warden of Stillness")
CREATURES = ["BASIC", "SHOOTER", "SPLITTER", "CHARGER", "SHIELDER", "ORBITER", "BOMBER", "PHANTOM", "LEECH"]

# tunables that the tests moved (see report)  ------------------------------------------------
SIL_PIECE = dict(apex=0.95, r=0.55, deg=70.0)       # spec: radius .35R, 40 deg, outer arc at 1.4R (fails test 2)
RAY_TIP = {1: (1.6, 1.35), 2: (1.6, 1.35), 3: (1.66, 1.42)}      # spec P3 1.8 R > 1.7 R limit
FROST_TIP = {1: 1.66, 2: 1.66, 3: 1.66}                             # spec 1.7 / 1.9 / 1.9 > 1.7 R limit


def entity(key: str) -> dict:
    return _ENT[key]


def pal(key: str, phase: int) -> Tuple[Color, Color, Color]:
    d = _ENT[key]
    return _PAL.get((key, min(phase, d["phases"])), (d["B"], d["C"], d["K"]))


def display_name(key: str, phase: int = 1) -> str:
    return ASCENT_NAMES[min(max(phase, 1), 3) - 1] if key == "ascent" else _ENT[key]["name"]


def n_steps(key: str) -> int:
    d = _ENT[key]
    return d["n"] if d["kind"] else (d["spin"][1] if d["spin"] else 1)


# =====================================================================  canvas helpers
def _shade(c, a):
    return tuple(max(0, min(255, v + a)) for v in c)


class Cv:
    """Square SRCALPHA canvas; all geometry in fractions of R relative to the centre."""

    def __init__(self, R: int, mini: bool = False):
        self.R = R
        self.h = int(math.ceil(1.8 * R)) + 6
        self.surf = pygame.Surface((self.h * 2, self.h * 2), pygame.SRCALPHA)

    def pts(self, lst, rot=0.0, ox=0.0, oy=0.0, sc=1.0):
        c, s, h, R = math.cos(rot), math.sin(rot), self.h, self.R
        return [(h + ((x * c - y * s) * sc + ox) * R, h + ((x * s + y * c) * sc + oy) * R) for x, y in lst]

    def poly(self, fill, edge, lst, rot=0.0, ox=0.0, oy=0.0, sc=1.0, w=1):
        p = self.pts(lst, rot, ox, oy, sc)
        if fill is not None:
            pygame.draw.polygon(self.surf, fill, p)
        if edge is not None:
            if w <= 1:
                pygame.draw.polygon(self.surf, edge, p, 1)
            else:
                pygame.draw.lines(self.surf, edge, True, p, w)

    def line(self, col, a, b, w=1, rot=0.0, ox=0.0, oy=0.0, sc=1.0):
        p = self.pts([a, b], rot, ox, oy, sc)
        pygame.draw.line(self.surf, col, p[0], p[1], w)

    def lines(self, col, lst, w=1, closed=False, rot=0.0, ox=0.0, oy=0.0, sc=1.0):
        pygame.draw.lines(self.surf, col, closed, self.pts(lst, rot, ox, oy, sc), w)

    def circ(self, col, x, y, r, w=0):
        pygame.draw.circle(self.surf, col, (self.h + x * self.R, self.h + y * self.R), max(1, int(round(r * self.R))), w)

    def circ_px(self, col, x, y, rpx, w=0):
        pygame.draw.circle(self.surf, col, (self.h + x * self.R, self.h + y * self.R), rpx, w)

    def ell(self, fill, edge, a, b, rot=0.0, ox=0.0, oy=0.0, w=1, n=36):
        self.poly(fill, edge, ell_pts(a, b, n), rot, ox, oy, 1.0, w)

    def arc(self, col, r, a0, a1, w=1, ox=0.0, oy=0.0, rot=0.0):
        self.lines(col, arc_pts(r, a0, a1, max(6, int(abs(a1 - a0) * r * self.R / 6))), w, False, rot, ox, oy)

    def dashes(self, col, r, n, duty, w=1, a0=0.0, ox=0.0, oy=0.0):
        seg = 360.0 / n
        for i in range(n):
            s = a0 + i * seg
            self.arc(col, r, s, s + seg * duty, w, ox, oy)

    def sector(self, fill, edge, r, a0, a1, ox=0.0, oy=0.0, w=1):
        pts = [(0.0, 0.0)] + arc_pts(r, a0, a1, 10)
        self.poly(fill, edge, pts, 0.0, ox, oy, 1.0, w)


def arc_pts(r, a0, a1, n=12):
    return [(r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def ell_pts(a, b, n=36):
    return [(a * math.cos(TAU * i / n), b * math.sin(TAU * i / n)) for i in range(n)]


def _pol(ang_deg, d):
    a = math.radians(ang_deg)
    return (math.cos(a) * d, math.sin(a) * d)


def _teardrop(base, ang_deg, length, br):
    a = math.radians(ang_deg)
    dx, dy = math.cos(a), math.sin(a)
    px, py = -dy, dx
    ce = (base[0] + dx * (length - br), base[1] + dy * (length - br))
    pts = [base]
    for k in range(7):
        th = a + math.pi / 2 - k * math.pi / 6
        pts.append((ce[0] + br * math.cos(th), ce[1] + br * math.sin(th)))
    return pts


def _eye_geom(R):
    r = max(4, int(R))
    return max(3, int(r * 0.32)), max(2, int(r * 0.18)), -int(r * 0.12)     # sep, eye radius, eye y (px)


def _lids(cv: Cv, mode: str, col, line):
    sep, er, ey = _eye_geom(cv.R)
    s, h = cv.surf, cv.h
    for sx in (-1, 1):
        ex, y = h + sx * sep, h + ey
        if mode == "half":
            pts = [(ex + er * math.cos(math.radians(a)), y + er * math.sin(math.radians(a))) for a in range(180, 361, 20)]
            pygame.draw.polygon(s, col, pts)
            pygame.draw.line(s, line, (ex - er, y), (ex + er, y), 1)
        elif mode == "closed":
            pygame.draw.circle(s, col, (ex, y), er + 1)
            pygame.draw.line(s, line, (ex - er - 1, y + 1), (ex + er + 1, y + 1), 2)
        elif mode == "slit":                       # narrow slit: angled upper lid + lower lid in `col`
            up = [(ex - er - 1, y - er - 2), (ex + er + 1, y - er - 2), (ex + sx * (er + 1) * -1, y - 1), (ex + sx * (er + 1), y - er // 2 - 1)]
            up = [(ex - er - 1, y - er - 2), (ex + er + 1, y - er - 2), (ex + er + 1, y - er // 2 + (-sx) * 2),
                  (ex - er - 1, y - er // 2 + sx * 2)]
            pygame.draw.polygon(s, col, up)
            pygame.draw.polygon(s, col, [(ex - er - 1, y + er // 2), (ex + er + 1, y + er // 2), (ex + er + 1, y + er + 2), (ex - er - 1, y + er + 2)])


def _masked(cv: Cv, poly_px, drawfn):
    """Draw with drawfn(surface) then keep only what lies inside poly_px (bake-time only)."""
    tmp = pygame.Surface(cv.surf.get_size(), pygame.SRCALPHA)
    drawfn(tmp)
    m = pygame.Surface(cv.surf.get_size(), pygame.SRCALPHA)
    pygame.draw.polygon(m, (255, 255, 255, 255), poly_px)
    tmp.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    cv.surf.blit(tmp, (0, 0))


def _outline_from_alpha(cv: Cv, col, w=2):
    m = pygame.mask.from_surface(cv.surf, 40)
    o = m.outline()
    if len(o) > 2:
        pygame.draw.lines(cv.surf, col, True, o, w)


def _hatch_in(cv: Cv, poly_px, col, spacing_px, slope=1, w=1):
    """Diagonal hatch ('/' slope=1, '\\' slope=-1) clipped to poly_px."""
    S = cv.surf.get_width()

    def f(t):
        k = -S
        while k < 2 * S:
            if slope > 0:
                pygame.draw.line(t, col, (k, S), (k + S, 0), w)
            else:
                pygame.draw.line(t, col, (k, 0), (k + S, S), w)
            k += spacing_px
    _masked(cv, poly_px, f)


# =====================================================================  recipes
# signature: fn(bk, fr, phase, var, step, R, pal) ; bk / fr are Cv (back / front). Fractions of R.
def _r_sprouting(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    n = 8 if ph == 1 else 12
    for i in range(n):
        a = -90 + i * 360.0 / n
        even = i % 2 == 0
        tip = (1.55 if even else 1.35) if ph == 1 else (1.66 if even else 1.4)
        hw = 0.26 if ph == 1 else 0.2
        ar = math.radians(a)
        d, p = (math.cos(ar), math.sin(ar)), (-math.sin(ar), math.cos(ar))
        bs = 0.8
        pts = [(d[0] * bs - p[0] * hw, d[1] * bs - p[1] * hw), (d[0] * tip, d[1] * tip),
               (d[0] * bs + p[0] * hw, d[1] * bs + p[1] * hw)]
        bk.poly((36, 92, 46), K, pts)
        if ph == 2:
            bk.circ((255, 150, 190), d[0] * (tip - 0.07), d[1] * (tip - 0.07), 0.07)
    if ph == 2:
        for i, x0 in enumerate((-0.45, -0.15, 0.15, 0.45)):
            th = 90 + (x0 / 0.45) * 28
            sgn = 1 if i % 2 == 0 else -1
            ptsv = [_pol(th, 0.9), _pol(th + sgn * 9, 1.15), _pol(th - sgn * 9, 1.35), _pol(th + sgn * 7, 1.5)]
            bk.lines((20, 60, 24), ptsv, 6)
            bk.lines((110, 200, 100), ptsv, 4)
            bk.circ((255, 150, 190), *ptsv[-1], 0.05)
    for sx in (-1, 1):
        fr.ell((110, 200, 100), K, 0.22, 0.10, math.radians(35 * sx), sx * 0.18, -1.12)


def _r_cradle_husk(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    aim = step * TAU / 16
    RI, RO = 1.12, 1.47                                  # ring thickness 0.35 R (Husk Slam ZONE radius = RI)
    bk.circ((30, 24, 12), 0, 0, RI)
    bk.circ(K, 0, 0, RI, 2)
    for i in range(3):
        x, y = _pol(90 + i * 120, 0.55)
        bk.circ((110, 200, 100), x, y, 0.13)
        bk.circ((60, 130, 60), x, y, 0.13, 1)
    a0, a1 = math.degrees(aim) + 30, math.degrees(aim) + 330
    fr.poly(B, K, arc_pts(RO, a0, a1, 40) + arc_pts(RI, a0, a1, 40)[::-1], w=2)
    fr.lines(C, arc_pts((RI + RO) / 2, a0 + 3, a1 - 3, 40), 2)
    for k in range(7):
        ang = a0 + 30 + k * 45
        fr.line(_shade(B, -40), _pol(ang, RI + 0.04), _pol(ang, RO - 0.04), 2)


def _r_first_sprout(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    bk.poly(_shade(B, -30), K, [(-0.09, 0.5), (0.09, 0.5), (0.09, 1.5), (-0.09, 1.5)])
    for a in (70, 90, 110):
        bk.line(K, (0, 1.3), _pol(a, 1.55), 2)
    for a in (-90, 30, 150):
        x, y = _pol(a, 1.4)
        bk.line((215, 255, 200), (0, 0), (x, y), 2)
        bk.circ((255, 150, 190), x, y, 0.2)
        bk.circ(WHITE, x, y, 0.2, 2)
    pts = ell_pts(0.8, 1.1, 60)
    if var:                                                            # knots cut: solid bud outline
        fr.lines(K, pts, 2, True)
    else:                                                              # shielded: dashed bud outline
        for i in range(0, 60, 3):
            fr.lines(K, [pts[i], pts[(i + 1) % 60], pts[(i + 2) % 60]], 2)


def _r_rot(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    if ph == 2:                                                        # puddle ring under the boss, toxic alpha 60
        bk.ell((205, 255, 70, 60), None, 1.4, 0.5, 0, 0, 0.85)
        bk.ell((0, 0, 0, 0), None, 1.0, 0.33, 0, 0, 0.85)
    if ph == 1:
        for a, ln in zip((60, 75, 90, 105, 120), (0.3, 0.45, 0.6, 0.45, 0.3)):
            bk.poly((50, 70, 26), K, _teardrop(_pol(a, 0.92), a, ln + 0.12, 0.11))
    else:
        for i in range(10):
            a = 50 + i * 80.0 / 9
            bk.poly((50, 70, 26), K, _teardrop(_pol(a, 0.8), a, (0.9, 0.55, 0.75, 0.5, 0.85)[i % 5], 0.07))
    fr.lines(K, arc_pts(1.12, -150, -30, 24), 6 if ph == 1 else 4)


def _r_sinking_bloat(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    a = 220
    fr.circ((*B, a), 0, -0.8, 0.6)
    fr.circ((*K, a), 0, -0.8, 0.6, 2)
    for x, y, r in ((-0.2, -0.92, 0.13), (0.2, -0.7, 0.1), (-0.3, -0.05, 0.1), (0.3, 0.2, 0.13)):
        fr.circ((*C, a), x, y, r, 1)
    for i, (y, r) in enumerate(((1.12, 0.12), (1.32, 0.09), (1.5, 0.06))):
        fr.circ((*K, a), 0.03 * (i % 2), y, r)


def _r_green_mourner(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    sw = step / 8.0 * TAU
    for sx in (-1, 1):
        arm = []
        for j in range(7):
            s = j / 6.0
            arm.append((sx * (0.88 + 0.1 * math.sin(sw + s * 2.2 + (0 if sx > 0 else 1.2)) * (0.4 + s)), 0.25 + 0.85 * s))
        bk.lines(_shade(K, -60), arm, 9)
        bk.lines(B, arm, 6)
        bk.circ(_shade(K, -60), *arm[-1], 0.13)
        bk.circ(C, *arm[-1], 0.1)


def _r_echoes(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    for a in (45, 135, 225, 315):
        bk.poly((170, 220, 255), (20, 40, 90), [(0.55, 0), (1.075, 0.15), (1.6, 0), (1.075, -0.15)], math.radians(a))
    off = 0.18 if ph == 1 else 0.35
    for sx in (-1, 1):
        fr.circ((*K, 90), sx * off, 0, 1.0, 2)


def _r_glass_clerk(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    hexp = [(0.8 * p[0], 1.32 * p[1]) for p in (_pol(-90 + 60 * i, 1.0) for i in range(6))]
    fr.poly(B, None, hexp)
    for i in range(3):
        fr.line((20, 40, 90), hexp[i], hexp[i + 3], 1)
    fr.lines(_shade(B, 40), [(0.4 * math.cos(math.radians(-90 + 60 * i)), 0.66 * math.sin(math.radians(-90 + 60 * i))) for i in range(6)], 1, True)
    fr.poly(None, K, hexp, w=2)
    fr.circ(C, 0, 0, 0.3)
    fr.circ(K, 0, 0, 0.3, 2)


def _r_unfinished(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    left = arc_pts(1.0, 90, 270, 24)
    fr.poly(B, None, left)
    fr.poly(C, None, arc_pts(0.55, 90, 270, 14))
    fr.lines(K, left, 2)
    fr.line(K, (0, -1.0), (0, 1.0), 2)
    for i in range(8):                                 # right half: dashed outline only (8 dashes)
        s = -90 + i * 22.5
        fr.arc(K, 1.0, s, s + 14, 2)
    sep, er, ey = _eye_geom(R)
    pygame.draw.circle(fr.surf, (250, 250, 255), (fr.h - sep, fr.h + ey), er)
    pygame.draw.circle(fr.surf, (20, 24, 36), (fr.h - sep, fr.h + ey), max(1, int(er * .45)))
    fr.poly((110, 200, 100), K, [(0, -1.0), (-0.2, -1.25), (-0.02, -1.4)])      # seedling leaves
    fr.poly((110, 200, 100), K, [(0, -1.0), (0.2, -1.25), (0.02, -1.4)])


def _r_ash(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    FIRE, EMB = (255, 205, 90), (255, 150, 60)
    wid = 1.0 if ph == 1 else 1.1
    bk.ell(None, (*EMB, 120), 0.9 * wid, 0.2, 0, 0, 1.22, 2)
    bk.poly((60, 50, 54), K, [(-0.75, 0.65), (0.75, 0.65), (0.55, 1.15), (-0.55, 1.15)])
    bk.poly((60, 50, 54), K, [(0.7, 0.65), (1.45, 0.8), (0.7, 0.96)])
    if var:
        bk.line(FIRE, (-0.75, 0.65), (0.75, 0.65), 3)
        bk.line(FIRE, (0.75, 0.65), (1.4, 0.79), 3)
    for a in (-150, -126, -102, -78, -54, -30):
        fr.poly(FIRE, K, [(0.9, -0.09), (1.09, 0), (0.9, 0.09)], math.radians(a))
    if var:
        fr.circ((255, 140, 60, 70), 0, 0, 0.55)
    if ph >= 2:
        seams = [[(-.9, -.2), (-.4, -.3), (-.1, .1), (.4, 0), (.9, .3)], [(-.6, -.75), (-.3, -.4), (-.35, .2), (-.1, .6)],
                 [(.1, -.9), (.2, -.4), (.55, -.2), (.7, .3)], [(-.8, .4), (-.4, .5), (-.2, .9)], [(.3, .4), (.55, .7), (.8, .6)]]
        col, w = ((255, 200, 80), 3) if ph == 2 else ((255, 230, 130), 5)
        for s in seams:
            pp = []
            for x, y in s:
                d = math.hypot(x, y)
                k = min(1.0, 0.94 / d) if d else 1
                pp.append((x * k, y * k))
            fr.lines(col, pp, w)


def _r_cinder_anvil(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    poly = [(-.85, -.5), (.85, -.5), (1.5, -.2), (.85, 0), (.3, .22), (.3, .55), (.6, .8), (-.6, .8), (-.3, .55), (-.3, .22), (-.85, -.1)]
    fr.poly(B, None, poly)
    fr.line(_shade(B, 40), (-.8, -.45), (.8, -.45), 2)
    fr.line((*C, 90), (-.6, -.28), (1.0, -.28), 7)
    fr.line(C, (-.6, -.28), (1.0, -.28), 3)
    fr.poly(None, K, poly, w=2)


def _r_ember_runner(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    aim = step * TAU / 16
    for off, ln, col in ((-0.4, 0.7, (255, 150, 60)), (0, 0.8, (255, 205, 90)), (0.4, 0.7, (255, 150, 60))):
        fr.poly(col, (120, 40, 10), [(-0.8, off - 0.2), (-0.8 - ln * 0.9, off), (-0.8, off + 0.2)], aim)
    body = [(1.3, 0)] + [(1.0 * math.cos(math.radians(a)), 0.66 * math.sin(math.radians(a))) for a in range(40, 321, 20)]
    fr.poly(B, K, body, aim, w=2)                       # teardrop: ellipse 1.35:1 with a pointed nose
    fr.poly(C, None, ell_pts(0.5, 0.36, 24), aim, 0.1 * math.cos(aim), 0.1 * math.sin(aim))
    c, s = math.cos(aim), math.sin(aim)
    for sy in (-1, 1):
        x, y = 0.5, sy * 0.26
        fr.circ((250, 250, 255), x * c - y * s, x * s + y * c, 0.12)
        fr.circ((20, 24, 36), x * c - y * s + 0.03 * c, x * s + y * c + 0.03 * s, 0.06)


def _r_frost(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    if ph == 3:
        bk.circ((235, 248, 255, 40), 0, 0, 1.5)
    L = FROST_TIP[ph]
    for i in range(6):
        a = math.radians(-90 + 60 * i)
        bk.poly((200, 230, 250), (20, 40, 70), [(0.75, -0.19), (L, 0), (0.75, 0.19)], a)
        fr.line((*K, 120), (0.1 * math.cos(a), 0.1 * math.sin(a)), (0.75 * math.cos(a), 0.75 * math.sin(a)), 1)
    if ph == 2:
        for i in range(24):
            x, y = _pol(i * 15, 1.25)
            bk.circ_px((235, 248, 255, 160), x, y, 2)
    _lids(fr, "half" if ph < 3 else "closed", B, (20, 40, 70))


def _r_rime_sentinel(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    aim = step * TAU / 16
    a, ch = 0.85, 0.3
    oct_ = [(-a + ch, -a), (a - ch, -a), (a, -a + ch), (a, a - ch), (a - ch, a), (-a + ch, a), (-a, a - ch), (-a, -a + ch)]
    fr.poly(_shade(B, -80), K, [(0.5, -0.24), (1.4, -0.24), (1.5, -0.34), (1.5, 0.34), (1.4, 0.24), (0.5, 0.24)], aim, w=2)
    fr.poly(B, None, oct_)
    for (p, q) in (((-0.5, -0.6), (0.0, -0.1)), ((0.0, -0.1), (0.35, 0.3)), ((0.2, 0.6), (-0.2, 0.2))):
        fr.line((20, 40, 70), p, q, 2)
    fr.poly(None, K, oct_, w=2)
    fr.poly(None, (20, 40, 70), [(x * 0.82, y * 0.82) for x, y in oct_], w=1)


def _r_drift_sleeper(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    fr.circ(B, 0, 0, 1.0)
    fr.circ(C, 0, 0, 0.5)
    fr.circ_px((0, 0, 0, 0), 0.6, 0.5, int(0.55 * R))                  # the bite (lower right)
    _outline_from_alpha(fr, K, 2)
    sep, er, ey = _eye_geom(R)
    for sx in (-1, 1):
        pygame.draw.line(fr.surf, (20, 24, 50), (fr.h + sx * sep - er, fr.h + ey), (fr.h + sx * sep + er, fr.h + ey), 2)
    for off in (0.0, 0.5):                                             # two "z" glyphs floating up at 0.5 Hz
        s = (step / 8.0 + off) % 1.0
        al = int(255 * min(1.0, 2.2 * (1 - s)))
        x, y, z = 0.5 + 0.1 * s, -0.9 - 0.3 * s, 0.13
        fr.lines((*K, al), [(x - z, y - z), (x + z, y - z), (x - z, y + z), (x + z, y + z)], 2)


def _r_thirst(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    t1, t2 = RAY_TIP[ph]
    tilt = 8.0 if ph >= 2 else 0.0
    if ph >= 2:
        for y in (-0.3, 0.0, 0.3):
            bk.line((*K, 100), (-0.85, y), (-1.6, y), 2)
    for i in range(12):
        a = -90 + i * 30
        tip = t1 if i % 2 == 0 else t2
        ar = math.radians(a)
        d, p = (math.cos(ar), math.sin(ar)), (-math.sin(ar), math.cos(ar))
        bs = 0.85
        tp = math.radians(a + tilt)
        bk.poly((230, 190, 90), K, [(d[0] * bs - p[0] * 0.1, d[1] * bs - p[1] * 0.1),
                                    (math.cos(tp) * tip, math.sin(tp) * tip),
                                    (d[0] * bs + p[0] * 0.1, d[1] * bs + p[1] * 0.1)])


def _r_oasis_lure(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    fr.ell(B, None, 1.3, 0.72)
    for s_, col in ((0.72, C), (0.42, K)):
        fr.ell(None, col, 1.3 * s_, 0.72 * s_, 0, 0, 0, 1)
    fr.ell(None, K, 1.3, 0.72, 0, 0, 0, 2)
    for (x, y, ang) in ((-0.75, -0.55, -125), (0.0, -0.72, -90), (0.75, -0.55, -55)):
        a = math.radians(ang)
        fr.poly((40, 150, 90), K, [(x - 0.1 * math.sin(a), y + 0.1 * math.cos(a)),
                                    (x + 0.55 * math.cos(a), y + 0.55 * math.sin(a)),
                                    (x + 0.1 * math.sin(a), y - 0.1 * math.cos(a))])


def _r_dry_maw(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    if var:                                              # hidden: dust mound dome + 6 dots
        bk.poly(_shade(B, 10), K, arc_pts(1.0, 180, 360, 24), 0, 0, 0.45, w=2)
        for i in range(6):
            x, y = _pol(200 + i * 28, 0.62)
            bk.circ(_shade(C, -40), x, y + 0.45, 0.07)
        return
    ring = arc_pts(1.22, 0, 360, 48)
    fr.poly(_shade(B, -10), K, ring + arc_pts(1.0, 360, 0, 48), w=2)       # lips
    fr.circ((40, 16, 10), 0, 0, 0.62)
    fr.circ(K, 0, 0, 0.62, 2)
    for i in range(8):                                   # 8 radial teeth (0.3 R) around the throat
        ar = math.radians(i * 45 + 22.5)
        d, p = (math.cos(ar), math.sin(ar)), (-math.sin(ar), math.cos(ar))
        fr.poly((255, 240, 215), (90, 50, 30), [(d[0] * 1.0 - p[0] * 0.1, d[1] * 1.0 - p[1] * 0.1), (d[0] * 0.7, d[1] * 0.7),
                                                 (d[0] * 1.0 + p[0] * 0.1, d[1] * 1.0 + p[1] * 0.1)])


# --- Masks ------------------------------------------------------------------------------
def _mask_overlay(fr, bk, kind, sc, ox, oy, K):
    if kind == 0:     # hunter
        for sx in (-1, 1):
            fr.poly((110, 30, 60), K, [(sx * 0.2, -0.95), (sx * 0.5, -1.5), (sx * 0.8, -0.75)], 0, ox, oy, sc)
        fr.poly((110, 30, 60), K, [(-0.5, 0.02), (0.5, 0.02), (0.45, 0.4), (0.0, 0.85), (-0.45, 0.4)], 0, ox, oy, sc, w=2)
        fr.line(K, (0, 0.1), (0, 0.7), 1, 0, ox, oy, sc)
    elif kind == 1:   # gardener
        for i, d in enumerate((-50, -25, 0, 25, 50)):
            tip = 1.5 if d == 0 else (1.4 if abs(d) == 25 else 1.25)
            a = math.radians(-90 + d)
            dd, pp = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
            fr.poly((60, 150, 90), K, [(dd[0] * .85 - pp[0] * .13, dd[1] * .85 - pp[1] * .13), (dd[0] * tip, dd[1] * tip),
                                       (dd[0] * .85 + pp[0] * .13, dd[1] * .85 + pp[1] * .13)], 0, ox, oy, sc)
        fr.ell((50, 120, 80), K, 0.5, 0.4, 0, 0, 0.42, 2) if sc == 1.0 else fr.poly((50, 120, 80), K, ell_pts(0.5, 0.4), 0, ox, oy + 0.42 * sc, sc, w=2)
        fr.poly((140, 220, 140), None, ell_pts(0.2, 0.08), math.radians(-40), ox, oy + 0.4 * sc, sc)
    else:             # mourner (vulnerable mask: bright white 3px edge)
        fr.poly((60, 50, 100), WHITE, ell_pts(0.52, 0.42), 0, ox, oy + 0.42 * sc, sc, w=3)
        for sx in (-1, 1):
            fr.poly((150, 200, 255), K, _teardrop((sx * 0.32, 0.12), 90, 0.22, 0.06), 0, ox, oy, sc)
        fr.lines(K, arc_pts(0.24, 200, 340, 10), 2, False, 0, ox, oy + 0.78 * sc, sc)
        for sx in (-1, 1):
            for a in (15, 30, 45):
                x0, y0 = _pol(a, 1.0)
                y1 = math.sqrt(1.55 ** 2 - x0 ** 2)
                bk.line((*K, 160), (sx * x0, y0), (sx * x0, y1), 1)


def _r_masks(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    for sx in (-1, 1):                                    # ribbon tassels (back, static)
        for a in (-15, 10, 35):
            x, y = _pol(a, 0.97)
            x *= sx
            bk.poly((170, 60, 170), K, [(x - .05, y), (x + .05, y), (x + .05, y + .45), (x, y + .37), (x - .05, y + .45)])
    aura = (255, 200, 235, 120) if ph == 1 else (255, 235, 130, 170)
    bk.circ(aura, 0, 0, 1.18, 2)
    if ph == 1:
        _mask_overlay(fr, bk, var % 3, 1.0, 0, 0, K)
        _lids(fr, "slit", (50, 15, 60), (20, 24, 36)) if var % 3 == 0 else None
    elif ph == 2:
        _mask_overlay(fr, bk, var % 3, 1.0, 0, 0, K)
        fr.circ((230, 240, 255, 120), 0.62, 0.62, 0.3)
        for sx in (-1, 1):
            fr.circ((20, 24, 36, 150), 0.62 + sx * 0.1, 0.58, 0.04)
        _lids(fr, "slit", (50, 15, 60), (20, 24, 36)) if var % 3 == 0 else None
    else:
        _mask_overlay(fr, bk, var % 3, 0.7, -0.42, 0.1, K)
        _mask_overlay(fr, bk, (var + 1) % 3, 0.7, 0.42, 0.1, K)


def _r_borrowed_face(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    for sx in (-1, 1):                                  # ribbon ties of the theatrical mask
        bk.poly((250, 245, 255), K, [(sx * 0.9, 0.05), (sx * 1.1, 0.05), (sx * 1.12, 0.65), (sx * 1.0, 0.55), (sx * 0.88, 0.65)])
    _creature_layers(bk, fr, CREATURES[(var if var else 1) % 9], R, B, grey=False)
    plate = [(-1.0, -0.1), (1.0, -0.1)] + [(math.cos(math.radians(a)), math.sin(math.radians(a))) for a in range(0, 181, 15)]
    plate = [(0.97 * x, 0.97 * y) for x, y in plate]
    fr.poly((250, 245, 255, 235), None, [(-0.97, 0.0), (0.97, 0.0)] + [(0.97 * math.cos(math.radians(a)), 0.97 * math.sin(math.radians(a))) for a in range(0, 181, 15)][::-1])
    sep, er, ey = _eye_geom(R)
    fr.line(K, (-0.97, 0.0), (0.97, 0.0), 2)
    for sx in (-1, 1):
        pygame.draw.circle(fr.surf, (0, 0, 0, 0), (fr.h + sx * sep, fr.h + ey), er + 2)
        pygame.draw.circle(fr.surf, (60, 50, 80), (fr.h + sx * sep, fr.h + ey), er + 2, 2)


def _r_pollen_sleeper(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    for i in range(10):
        a = i * 36 + 18
        bk.line(_shade(B, -40), (0, 0), _pol(a, 1.38), 1)
        x, y = _pol(a, 1.4)
        bk.circ((255, 235, 130), x, y, 0.1)
    sep, er, ey = _eye_geom(R)
    for sx in (-1, 1):
        pygame.draw.line(fr.surf, (60, 40, 10), (fr.h + sx * sep - er, fr.h + ey), (fr.h + sx * sep + er, fr.h + ey), 2)
    for off in (0.0, 0.5):
        s = (step / 8.0 + off) % 1.0
        al = int(255 * min(1.0, 2.2 * (1 - s)))
        x, y, z = 0.35 + 0.1 * s, -1.0 - 0.3 * s, 0.13
        fr.lines((255, 235, 130, al), [(x - z, y - z), (x + z, y - z), (x - z, y + z), (x + z, y + z)], 2)


def _r_silence(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    fr.circ((4, 3, 10), 0, 0, 0.5)
    fr.circ(K, 0, 0, 0.5, 3)
    fr.dashes((*K, 140), 1.12, 24, 0.55, 2)
    for sx in (-1, 1):
        fr.line((170, 155, 230), (sx * 0.035, -0.32), (sx * 0.035, -0.02), 2)


def _r_quiet_hollow(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    fr.circ(K, 0, 0, 1.0, 3)
    for i, r_ in enumerate((0.72, 0.5, 0.3)):
        fr.dashes((*K, 140), r_, 10, 0.5, 2, a0=i * 40)


def _r_forgotten_shape(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    _creature_layers(bk, fr, CREATURES[(var if var else 2) % 9], R, B, grey=True)
    sep, er, ey = _eye_geom(R)
    for sx in (-1, 1):
        pygame.draw.circle(fr.surf, (230, 230, 245), (fr.h + sx * sep, fr.h + ey), er + 1, 2)


def _r_updraft_herald(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    aim = step * TAU / 16
    body = [(0.85, 0), (-0.7, -0.95), (-0.3, 0), (-0.7, 0.95)]
    for i, x in enumerate((-0.95, -1.15, -1.35)):
        fr.lines(C, [(x + 0.18, -0.4 + 0.0), (x, 0), (x + 0.18, 0.4)], 2, False, aim)
    fr.poly(B, None, body, aim)
    fr.poly((*C, 255), None, [(0.6, 0), (-0.4, -0.5), (-0.15, 0), (-0.4, 0.5)], aim)
    fr.poly(None, K, body, aim, w=2)
    sep = 0.28
    for sy in (-1, 1):
        c, s = math.cos(aim), math.sin(aim)
        x, y = 0.2, sy * 0.15
        fr.circ((250, 250, 255), x * c - y * s, x * s + y * c, 0.08)
        fr.circ((20, 24, 36), x * c - y * s + 0.025 * c, x * s + y * c + 0.025 * s, 0.04)


def _r_verdict_pillar(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    shaft = [(-0.4, -1.0), (0.4, -1.0), (0.4, 1.0), (-0.4, 1.0)]
    fr.poly(B, None, shaft)
    fr.poly(_shade(B, -30), K, [(-0.55, -1.3), (0.55, -1.3), (0.55, -1.0), (-0.55, -1.0)], w=2)
    fr.poly(_shade(B, -30), K, [(-0.55, 1.0), (0.55, 1.0), (0.55, 1.3), (-0.55, 1.3)], w=2)
    fr.poly(None, K, shaft, w=2)
    for x in (-0.2, 0.2):
        fr.line(_shade(B, -40), (x, -0.9), (x, 0.9), 1)
    fr.line((255, 250, 215, 90), (0, -0.55), (0, 0.15), 9)
    fr.line(C, (0, -0.55), (0, 0.15), 3)


def _r_first_split(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    aim = step * TAU / 16
    cut = 0.12                                         # flat edge (towards the arena centre) a hair past the centre
    a0 = int(math.degrees(math.acos(cut)))
    pts = [(math.cos(math.radians(a)), math.sin(math.radians(a))) for a in range(a0, 361 - a0, 8)]
    fr.poly(B, None, pts, aim)
    fr.poly(C, None, [(x * 0.55, y * 0.55) for x, y in pts], aim)
    fr.line((*C, 90), (cut, -0.95), (cut, 0.95), 9, aim)
    fr.line(C, (cut, -0.95), (cut, 0.95), 3, aim)
    fr.poly(None, K, pts, aim, w=2)
    c, s = math.cos(aim), math.sin(aim)
    x, y = -0.35, -0.08
    fr.circ((250, 250, 255), x * c - y * s, x * s + y * c, 0.14)
    fr.circ((20, 24, 36), x * c - y * s - 0.04 * c, x * s + y * c - 0.04 * s, 0.07)


def _r_last_whole(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    EDGE = (30, 30, 50)
    for i, ctr in enumerate((90, 210, 330)):
        a0, a1 = ctr - 50, ctr + 50
        outer, inner = arc_pts(1.16, a0, a1, 16), arc_pts(0.9, a0, a1, 16)[::-1]
        fr.poly((255, 255, 255) if (var >> i) & 1 else (*B, 40), None, outer + inner)      # lit = white fill
        fr.lines(EDGE, arc_pts(1.2, a0, a1, 16), 1)
        fr.lines(K, arc_pts(1.15, a0, a1, 16), 3)
        fr.lines(EDGE, arc_pts(1.08, a0, a1, 16), 1)


def _r_anchor(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    FIRE, ICE, TOX = (255, 160, 70), (175, 225, 255), (200, 255, 80)
    af = (70, 18, 56)

    def anchor(cracked):
        outer, inner = arc_pts(1.45, 20, 160, 30), arc_pts(1.2, 20, 160, 30)[::-1]
        bk.poly(af, K, outer + inner, w=2)
        for a, sgn in ((20, 1), (160, -1)):                       # triangle fluke tips at both crescent ends
            ar = math.radians(a)
            tip_dir = (math.sin(ar) * sgn, -math.cos(ar) * sgn)  # tangent pointing away from the arc
            e1, e2 = (1.2 * math.cos(ar), 1.2 * math.sin(ar)), (1.45 * math.cos(ar), 1.45 * math.sin(ar))
            tip = (1.325 * math.cos(ar) + tip_dir[0] * 0.28, 1.325 * math.sin(ar) + tip_dir[1] * 0.28)
            bk.poly(af, K, [e1, e2, tip], w=2)
        bk.poly(af, K, [(-0.11, -1.25), (0.11, -1.25), (0.11, 1.2), (-0.11, 1.2)], w=2)
        bk.poly(af, K, [(-0.45, -1.04), (0.45, -1.04), (0.45, -0.86), (-0.45, -0.86)], w=2)
        bk.circ(K, 0, -1.45, 0.2, 4)
        if cracked:
            for pts in ([(-0.11, -0.3), (0.0, -0.15), (-0.05, 0.1), (0.11, 0.3)], [(-0.4, -0.95), (-0.1, -0.9), (0.1, -1.0), (0.4, -0.93)]):
                bk.lines((10, 0, 10), pts, 3)
                bk.lines(TOX, pts, 1)

    if ph == 2:                                                    # two linked half-discs, 0.25 R gap
        for sx, edge in ((-1, FIRE), (1, ICE)):
            sx_ = 0.125 * sx
            pts = [(sx_, -0.9), (sx_, 0.9)] + [(sx_ + sx * 0.9 * math.cos(math.radians(a)), 0.9 * math.sin(math.radians(a)))
                                                 for a in range(80, -81, -10)]
            fr.poly(B, None, pts)
            fr.poly((*C, 200), None, [(sx_ + (x - sx_) * 0.6, y * 0.6) for x, y in pts])
            P_px = fr.pts(pts)
            if sx < 0:
                _hatch_in(fr, P_px, (*edge, 190), 16, 1, 1)
            else:
                def snow(t, edge=edge):
                    for (x, y) in ((0.45, -0.45), (0.75, 0.0), (0.45, 0.45), (0.25, 0.0), (0.7, -0.6), (0.7, 0.6)):
                        cx, cy = fr.h + x * R, fr.h + y * R
                        for a in range(3):
                            ar = a * math.pi / 3
                            pygame.draw.line(t, (*edge, 200), (cx - 6 * math.cos(ar), cy - 6 * math.sin(ar)),
                                             (cx + 6 * math.cos(ar), cy + 6 * math.sin(ar)), 1)
                _masked(fr, P_px, snow)
            fr.poly(None, edge, pts, w=3)
            fr.line(edge, (sx_, -0.88), (sx_, 0.88), 2)
            ex = sx * 0.5
            pygame.draw.circle(fr.surf, (250, 250, 255), (fr.h + ex * R, fr.h - int(0.12 * R)), max(2, int(R * 0.1)))
            pygame.draw.circle(fr.surf, (20, 24, 36), (fr.h + ex * R, fr.h - int(0.12 * R)), max(1, int(R * 0.05)))
        for i in range(4):                                         # tether: 3 px dots, spacing 10 px
            pygame.draw.circle(fr.surf, K, (fr.h - 15 + i * 10, fr.h), 2)
        return
    anchor(ph == 3)
    if ph == 3:                                                    # three wound cracks (fire / ice / toxic)
        for (pts, col) in (([(-.95, -.5), (-.5, -.38), (-.4, -.1), (0, -.04), (.3, .2)], FIRE),
                           ([(.92, -.42), (.55, -.25), (.5, .12), (.15, .3), (-.12, .72)], ICE),
                           ([(-.7, .68), (-.3, .45), (0, .56), (.4, .82)], TOX)):
            fr.lines((10, 0, 12), pts, 6)
            fr.lines(col, pts, 3)


RECIPES = {
    "sprouting": _r_sprouting, "cradle_husk": _r_cradle_husk, "first_sprout": _r_first_sprout, "rot": _r_rot,
    "sinking_bloat": _r_sinking_bloat, "green_mourner": _r_green_mourner, "echoes": _r_echoes,
    "glass_clerk": _r_glass_clerk, "unfinished_entry": _r_unfinished, "ash": _r_ash, "cinder_anvil": _r_cinder_anvil,
    "ember_runner": _r_ember_runner, "frost": _r_frost, "rime_sentinel": _r_rime_sentinel, "drift_sleeper": _r_drift_sleeper,
    "thirst": _r_thirst, "oasis_lure": _r_oasis_lure, "dry_maw": _r_dry_maw, "masks": _r_masks,
    "borrowed_face": _r_borrowed_face, "pollen_sleeper": _r_pollen_sleeper, "silence": _r_silence,
    "quiet_hollow": _r_quiet_hollow, "forgotten_shape": _r_forgotten_shape, "ascent": None, "updraft_herald": _r_updraft_herald,
    "verdict_pillar": _r_verdict_pillar, "anchor": _r_anchor, "first_split": _r_first_split, "last_whole": _r_last_whole,
}


# ---- Layer 9 body (separate so the recipe table above stays readable)
def _r_ascent(bk, fr, ph, var, step, R, pl):
    B, C, K = pl
    WF = (70, 90, 160)
    if ph == 3:
        bk.circ((235, 248, 255, 36), 0, 0, 1.4)
    for sx in (-1, 1):
        if ph == 3:                                                    # folded wings, tips 1.15 R pointing down
            pts = [(sx * 0.8, -0.2), (sx * 0.45, 1.06), (sx * 0.95, 0.3)]
            bk.poly(WF, K, pts)
            continue
        if ph == 2:                                                    # doubled pair, alpha 100, 0.12 R lower
            bk.poly((*WF, 100), (*K, 100), [(sx * 0.85, 0.12), (sx * 1.45, -0.7), (sx * 1.18, 0.37)])
        bk.poly(WF, K, [(sx * 0.85, 0), (sx * 1.45, -0.82), (sx * 1.18, 0.25)])
        for f in (0.35, 0.65):
            bk.line((*K, 160), (sx * 0.85, 0), (sx * (1.45 - 0.27 * f), -0.82 + 1.07 * f), 1)
    bk.poly(WF, K, [(0, -0.95), (0.14, -1.25), (0, -1.55), (-0.14, -1.25)])
    if ph == 3:                                                        # snowflake of 6 spokes above the crest
        for i in range(3):
            a = math.radians(i * 60)
            bk.line(K, (-0.075 * math.cos(a), -1.6 - 0.075 * math.sin(a)), (0.075 * math.cos(a), -1.6 + 0.075 * math.sin(a)), 1)
    for y in (1.05, 1.2, 1.35):
        fr.lines(K, [(-0.3, y + 0.15), (0, y), (0.3, y + 0.15)], 3)
    if ph == 2:
        fr.line((*K, 160), (0, -1.2), (0, 1.2), 1)


RECIPES["ascent"] = _r_ascent


# ---- 046 creature silhouettes (Borrowed Face, Forgotten Shape)
_cs = None


def _creature_module():
    global _cs
    if _cs is None:
        from blob_evolution.utils import creature_shapes as m          # A1: the repo's 046 module only
        _cs = m
    return _cs


class _V:
    def __init__(self, x, y):
        self.x, self.y = x, y


def _tint(surf, col, lift=45):
    g = pygame.transform.grayscale(surf)
    g.fill((*col, 255), special_flags=pygame.BLEND_RGBA_MULT)
    g.fill((lift, lift, lift, 0), special_flags=pygame.BLEND_RGB_ADD)
    return g


def _creature_layers(bk, fr, kind, R, body, grey):
    cs = _creature_module()
    if cs is None:
        return
    for layer, fn in ((bk, "under"), (fr, "over")):
        t = pygame.Surface(layer.surf.get_size(), pygame.SRCALPHA)
        face = _V(1.0, 0.0)
        if fn == "under":
            cs.draw_under(t, kind, layer.h, layer.h, R * 0.96, face, _V(0, 0), 4.0, R * 3.5, False, 0)
        else:
            cs.draw_over(t, kind, layer.h, layer.h, R * 0.96, face, 0.0, 1.0, 4.0, False, 0)
        # keep only what sticks out of the body disc (the body itself is draw_blob)
        pygame.draw.circle(t, (0, 0, 0, 0), (layer.h, layer.h), int(R * 0.9))
        layer.surf.blit(_tint(t, body, 45), (0, 0))


# =====================================================================  spin parts (rotating bits, tight-cropped)
def _spin_tags(key, ph, k):
    N = 24
    if key == "echoes":
        return [(("ring", k % 2), 0.0, 0.0)] if ph >= 2 else []
    if key == "ash":
        if ph < 3:
            return []
        return [(("mote",), math.cos(math.radians(-90 + 15 * k + 90 * i)) * 1.3, math.sin(math.radians(-90 + 15 * k + 90 * i)) * 1.3)
                for i in range(4)]
    if key == "thirst":
        return [(("arc", i, k), 0.0, 0.0) for i in range(3)]
    if key == "silence":
        n = {1: 3, 2: 2, 3: 1}[ph]
        out = []
        for i in range(n):
            idx = (i * 8 + k) % N
            a = math.radians(idx * 15)
            out.append((("wedge", idx), math.cos(a) * SIL_PIECE["apex"], math.sin(a) * SIL_PIECE["apex"]))
        return out
    return []


def _build_piece(key, ph, R, tag, pl):
    B, C, K = pl
    cv = Cv(R)
    if tag[0] == "ring":
        for i in range(12):
            a = i * 30 + tag[1] * 15
            cv.line(K, _pol(a, 1.2), _pol(a, 1.3), 2)
    elif tag[0] == "mote":
        cv.circ_px((255, 150, 60, 140), 0, 0, 5)
        cv.circ_px((255, 205, 90), 0, 0, 3)
    elif tag[0] == "arc":
        _, i, k = tag
        r = (1.15, 1.3, 1.45)[i]
        a0 = i * 120 + k * 15
        cv.arc((*K, 120), r, a0, a0 + 70, 1)
    elif tag[0] == "wedge":
        a = tag[1] * 15
        h = SIL_PIECE["deg"] / 2
        cv.sector((8, 6, 16), K, SIL_PIECE["r"], a - h, a + h, 0, 0, 2)
    bb = cv.surf.get_bounding_rect()
    spr = cv.surf.subsurface(bb).copy()
    return spr, bb.x - cv.h, bb.y - cv.h


# =====================================================================  caches
_layers: Dict[tuple, Optional[pygame.Surface]] = {}
_pieces: Dict[tuple, tuple] = {}
_comp: Dict[tuple, tuple] = {}
_rims: Dict[tuple, pygame.Surface] = {}
_kit: Dict[tuple, pygame.Surface] = {}


def _half(R):
    return int(math.ceil(1.8 * R)) + 6


def _flags(key, phase):
    d = _ENT[key]
    blob, eyes, rim = d["blob"], d["eyes"], d["rim"]
    if key == "anchor" and phase == 2:
        blob, rim = False, "none"
    return blob, eyes, rim


def _is_dyn(key, layer):
    dd = _ENT[key]["dyn"]
    return dd == "both" or dd == layer


def _crop(cv):
    bb = cv.surf.get_bounding_rect()
    if bb.w == 0:
        return None
    return (cv.surf.subsurface(bb).copy(), bb.x - cv.h, bb.y - cv.h)


# BUG-163 (Visual Designer): these five anchors' shapes do not cover their round hitbox, so a "hit body" disc at exactly
# the hit radius (R) is baked into the back layer under the shape: body colour at alpha 70, a 2 px edge in the rim colour
# at alpha 170 (>= 3:1 on the layer's light ground; raise in steps of 20 if a palette ever drops below). The shape draws
# on top unchanged; the disc is part of the back sprite, so the BUG-162 flash copy and the warm-up include it. Their
# recipes draw nothing else in the back layer; a decoy (12-dash rim) skips it.
HIT_BODY = ("first_split", "drift_sleeper", "verdict_pillar", "updraft_herald", "cinder_anvil")
HIT_BODY_FILL_ALPHA = 70
HIT_BODY_EDGE_ALPHA = 170
HIT_BODY_EDGE_W = 2


def _hit_body(bk, R, pl):
    B, _C, K = pl
    bk.circ_px((*B, HIT_BODY_FILL_ALPHA), 0, 0, R)
    bk.circ_px((*K, HIT_BODY_EDGE_ALPHA), 0, 0, R, HIT_BODY_EDGE_W)


def _get_layers(key, phase, R, var=0, step=0):
    """-> (back, front), each None or (cropped sprite, ox, oy) with the offset of its top-left from the boss centre."""
    d = _ENT[key]
    phase = min(max(1, phase), d["phases"])
    if d["kind"] is None:
        step = 0
    kb = (key, phase, R, "b") + ((var, step) if _is_dyn(key, "back") else ())
    kf = (key, phase, R, "f") + ((var, step) if _is_dyn(key, "front") else ())
    if kb not in _layers or kf not in _layers:
        bk, fr = Cv(R, d["mini"]), Cv(R, d["mini"])
        if key in HIT_BODY:
            _hit_body(bk, R, pal(key, phase))
        RECIPES[key](bk, fr, phase, var, step, R, pal(key, phase))
        for k_, cv in ((kb, bk), (kf, fr)):
            if k_ not in _layers:
                _layers[k_] = _crop(cv)
    return _layers[kb], _layers[kf]


def _spin_parts(key, phase, R, step):
    d = _ENT[key]
    if not d["spin"]:
        return ()
    phase = min(max(1, phase), d["phases"])
    out = []
    pl = pal(key, phase)
    for tag, ax, ay in _spin_tags(key, phase, step % d["spin"][1]):
        pk = (key, R, tag)                               # pieces do not depend on the phase
        pc = _pieces.get(pk)
        if pc is None:
            pc = _pieces[pk] = _build_piece(key, phase, R, tag, pl)
        out.append((pc[0], int(round(ax * R)) + pc[1], int(round(ay * R)) + pc[2]))
    return out


def bake(key: str, phase: int, R: int, step: int = 0, var: int = 0):
    """-> (back, front): full-canvas SRCALPHA sprites (half-size ceil(1.8R)+6, centre = boss centre), None for an
    empty layer; spin parts for `step` are composed in.  Tool / test entry point: draw_boss() uses the cropped
    layers directly and never calls this."""
    d = _ENT[key]
    ck = (key, phase, R, var, step % (d["n"] if d["kind"] else (d["spin"][1] if d["spin"] else 1)))
    if ck in _comp:
        return _comp[ck]
    h = _half(R)
    back, front = _get_layers(key, phase, R, var, step)
    parts = _spin_parts(key, phase, R, step) if d["spin"] else ()
    out = []
    for lay, crop in (("back", back), ("front", front)):
        extra = parts if (d["spin"] and d["spin"][0] == lay) else ()
        if crop is None and not extra:
            out.append(None)
            continue
        s = pygame.Surface((2 * h, 2 * h), pygame.SRCALPHA)
        if crop is not None:
            s.blit(crop[0], (h + crop[1], h + crop[2]))
        for spr, ox, oy in extra:
            s.blit(spr, (h + ox, h + oy))
        out.append(s)
    _comp[ck] = tuple(out)
    return _comp[ck]


# =====================================================================  blob (draw_blob + allocation-free twin)
_gfx = None


def _graphics():
    global _gfx
    if _gfx is None:
        from blob_evolution.utils import graphics as g                 # A1: no sys.path fallback
        _gfx = g
    return _gfx


def draw_blob_cached(surface, pos, radius, color, core_color, velocity=None, pulse=0.0, glow=False, rotation=0.0,
                     eyes=True, look=None, variant="default", outline=None):
    """Pixel-identical to graphics.draw_blob(variant='default', velocity=None) but with zero per-call
    allocations (the original builds one Surface for the membrane ripple and 4 scaled copies per call)."""
    g = _graphics()
    cache = g.get_graphics_cache()
    x, y = int(pos[0]), int(pos[1])
    r = max(4, int(radius * (1.0 + pulse)))
    dx, dy = 0.0, 0.0
    if look is not None:
        ln = math.hypot(look[0], look[1])
        if ln > 0.01:
            dx, dy = look[0] / ln, look[1] / ln
    if glow:
        gs = cache.get_circle(int(r * 1.55), color, 40)
        surface.blit(gs, gs.get_rect(center=(x, y)))
        ou = cache.get_circle(int(r * 1.85), color, 18)
        surface.blit(ou, ou.get_rect(center=(x, y)))
    rim = cache.get_circle(r + 2, outline or g._shade(color, -40), 70)
    surface.blit(rim, rim.get_rect(center=(x, y)))
    for lr, lc, a in ((r, color, 190), (int(r * 0.78), g._shade(color, 18), 230), (int(r * 0.48), core_color, 255),
                      (int(r * 0.22), g._shade(core_color, 40), 220)):
        if lr >= 1:
            c = cache.get_circle(lr, lc, a)
            surface.blit(c, c.get_rect(center=(x, y)))
    if r >= 10:
        rk = ("ripple", r, color)
        ring = _kit.get(rk)
        if ring is None:
            ring = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
            pygame.draw.circle(ring, (*g._shade(color, 50), 55), (r + 3, r + 3), r - 1, 2)
            _kit[rk] = ring
        surface.blit(ring, ring.get_rect(center=(x, y)))
    hr = max(2, int(r * 0.24))
    h1 = cache.get_circle(hr, (255, 255, 255), 145)
    surface.blit(h1, (x + int(-r * 0.30) - hr, y + int(-r * 0.32) - hr))
    h2 = cache.get_circle(max(1, hr // 2), (255, 255, 255), 80)
    surface.blit(h2, (x + int(r * 0.18) - h2.get_width() // 2, y + int(r * 0.12) - h2.get_height() // 2))
    if eyes and r >= 7:
        g._draw_eyes(surface, x, y, r, dx, dy, angry=False)


# =====================================================================  draw_boss
def _dashed_rim(R, col, n, duty, w):
    k = ("rim", R, col, n, duty, w)
    s = _kit.get(k)
    if s is None:
        s = pygame.Surface((2 * R + 8, 2 * R + 8), pygame.SRCALPHA)
        c = R + 4
        seg = TAU / n
        for i in range(n):
            a0 = i * seg
            pts = [(c + math.cos(a0 + seg * duty * j / 6) * (R - w / 2.0), c + math.sin(a0 + seg * duty * j / 6) * (R - w / 2.0)) for j in range(7)]
            pygame.draw.lines(s, col, False, pts, w)
        _kit[k] = s
    return s


def pulse_for(t: float) -> float:
    """Body pulse 0.48 Hz, kept inside the rim (-0.06 .. 0) and quantised to 0.02 (4 radii)."""
    return round((-0.03 * (1.0 + math.sin(3.0 * t))) / 0.02) * 0.02


FLASH_TO_WHITE = 0.55                                  # BUG-176 (VD): a non-blob flash copy is its art lerped 55 % to white ...
FLASH_OUTLINE = 3                                      # ... inside a 3 px white outline (alpha 255) dilated from its alpha mask
FLASH_PAD = FLASH_OUTLINE                              # the copy is this much bigger on every side (draw offsets - FLASH_PAD)
_DILATE = None                                         # the 7 x 7 disc the alpha mask is dilated with (built on first use)
_tints: Dict[int, pygame.Surface] = {}                 # id(sprite) -> its flash copy (built at warm-up, never per frame)
_tint_src: Dict[int, pygame.Surface] = {}              # keeps the source alive so its id is never reused


_lerp_of: Dict[str, float] = {}                       # art key -> its flash lerp share (config.FLASH_LERP_OVERRIDE or default)


def flash_lerp(key: str) -> float:
    """BUG-176: the share of the way to white `key`'s flash copy goes (config.FLASH_LERP_OVERRIDE, else FLASH_TO_WHITE)."""
    w = _lerp_of.get(key)
    if w is None:
        from blob_evolution import config               # lazy, like _graphics(): this module imports no game config
        w = _lerp_of[key] = float(getattr(config, "FLASH_LERP_OVERRIDE", {}).get(key, FLASH_TO_WHITE))
    return w


def _flash_copy(spr: pygame.Surface, lerp: float = FLASH_TO_WHITE) -> pygame.Surface:
    """BUG-176: spr's art lerped FLASH_TO_WHITE toward white (alpha kept), on a white FLASH_OUTLINE px outline made by
    dilating its alpha mask; FLASH_PAD px bigger on every side."""
    global _DILATE
    if _DILATE is None:
        o = FLASH_OUTLINE
        _DILATE = pygame.mask.Mask((2 * o + 1, 2 * o + 1))
        for y in range(2 * o + 1):                     # a symmetric disc: every bit within o px of the centre
            for x in range(2 * o + 1):
                if (x - o) ** 2 + (y - o) ** 2 <= o * o + o * 0.5:
                    _DILATE.set_at((x, y), 1)
    art = spr.copy()
    keep = round(255 * (1 - lerp))
    art.fill((keep, keep, keep), special_flags=pygame.BLEND_RGB_MULT)          # rgb * 0.45 ...
    lift = 255 - keep
    art.fill((lift, lift, lift), special_flags=pygame.BLEND_RGB_ADD)           # ... + 255 * 0.55
    grown = pygame.mask.from_surface(spr, 1).convolve(_DILATE)                 # (w + 6) x (h + 6), the art at (3, 3)
    out = grown.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
    out.blit(art, (FLASH_PAD, FLASH_PAD))
    return out


def _tinted(spr: pygame.Surface, lerp: float = FLASH_TO_WHITE) -> pygame.Surface:
    """BUG-162 / 176: the cached flash copy of a layer / spin sprite, for art with no blob body (built at warm-up)."""
    t_ = _tints.get(id(spr))
    if t_ is None:
        t_ = _flash_copy(spr, lerp)                    # one lerp per sprite: sprites belong to one art key
        _tints[id(spr)], _tint_src[id(spr)] = t_, spr
    return t_


def flashes_by_tint(key: str, phase: int) -> bool:
    """True where the hit flash lifts the sprites (no blob body to turn white)."""
    return not _flags(key, phase)[0]


def draw_boss(dst, key, phase, sx, sy, R, t, aim, *, var=0, pulse=None, flash=False, decoy=False, shadow=False,
              glow=True, alpha=255, blob_fn=None, fade_from=None, fade=1.0):
    """Compose one boss / mini at screen position (sx, sy).  Draw order = spec 2.1 (4..7).
    shadow=True draws the 043 contact shadow first (never for decoys).  blob_fn: None -> repo draw_blob,
    'cached' -> draw_blob_cached (no allocations), or any callable with the draw_blob signature.
    A1: fade_from / fade cross-fade the back and front sprites of phase `fade_from` (alpha 1 - fade) into `phase`'s
    (alpha fade) for the spec 2.2 phase change; body, rim and palette are the new phase's at once."""
    d = _ENT[key]
    sx, sy, R = int(sx), int(sy), int(R)
    w_, h_ = dst.get_size()
    m = 1.9 * R + 60
    if sx < -m or sx > w_ + m or sy < -m or sy > h_ + m:
        return
    kind = d["kind"]
    if kind == "aim":
        step = int(round((aim % TAU) / (TAU / d["n"]))) % d["n"]
    elif kind == "anim":
        step = int(t / d["period"] * d["n"]) % d["n"]
    elif d["spin"]:
        step = int(t / d["spin"][2]) % d["spin"][1]
    else:
        step = 0
    back, front = _get_layers(key, phase, R, var, step)
    parts = _spin_parts(key, phase, R, step) if d["spin"] else ()
    old = None
    if fade_from is not None and fade < 1.0 and min(max(1, fade_from), d["phases"]) != min(max(1, phase), d["phases"]):
        old = _get_layers(key, fade_from, R, var, step)
        a_new = max(0, min(255, int(alpha * fade)))
        a_old = max(0, min(255, int(alpha * (1.0 - fade))))
        alpha = a_new
    blob, eyes, rim = _flags(key, phase)
    B, C, K = pal(key, phase)
    ox = oy = 0
    if flash and not blob:                             # BUG-162: non-blob art flashes through its cached lifted copies
        lw = flash_lerp(key)
        back = back and (_tinted(back[0], lw), back[1] - FLASH_PAD, back[2] - FLASH_PAD)
        front = front and (_tinted(front[0], lw), front[1] - FLASH_PAD, front[2] - FLASH_PAD)
        parts = tuple((_tinted(spr, lw), px - FLASH_PAD, py - FLASH_PAD) for spr, px, py in parts)
    if decoy:
        ox = int(round(math.sin(TAU * 0.7 * t)))
        rim = "decoy"
        if key in HIT_BODY:                            # BUG-163: decoys keep their 12-dash rim only (their back is the disc)
            back = None
    elif shadow:
        _graphics().draw_contact_shadow(dst, sx, sy, R)
    if old is not None and old[0] is not None:
        old[0][0].set_alpha(a_old)
        dst.blit(old[0][0], (sx + old[0][1] + ox, sy + old[0][2] + oy))
        old[0][0].set_alpha(255)
    if back is not None:
        if alpha != 255:
            back[0].set_alpha(alpha)
        dst.blit(back[0], (sx + back[1] + ox, sy + back[2] + oy))
        if alpha != 255:
            back[0].set_alpha(255)                     # A1: shared cached sprite; the next full-alpha draw must not stay faded
    if d["spin"] and d["spin"][0] == "back":
        for spr, px, py in parts:
            dst.blit(spr, (sx + px + ox, sy + py + oy))
    if blob:
        if pulse is None:
            pulse = pulse_for(t)
        col, core = ((255, 255, 255), (255, 200, 200)) if flash else (B, C)
        fn = blob_fn
        if fn is None:
            fn = _graphics().draw_blob
        elif fn == "cached":
            fn = draw_blob_cached
        fn(dst, (sx + ox, sy + oy), R, col, core, None, pulse=pulse, glow=glow, eyes=eyes, look=(math.cos(aim), math.sin(aim)))
    wd = 2 if d["mini"] else 3
    if rim == "solid":
        pygame.draw.circle(dst, K, (sx + ox, sy + oy), R, wd)
        if d["edge"]:
            pygame.draw.circle(dst, d["edge"], (sx + ox, sy + oy), R + 1, 1)
            pygame.draw.circle(dst, d["edge"], (sx + ox, sy + oy), R - wd, 1)
    elif rim == "dashed":
        s = _dashed_rim(R, K, 16, 0.6, wd)
        dst.blit(s, (sx - R - 4 + ox, sy - R - 4 + oy))
    elif rim == "decoy":
        s = _dashed_rim(R, K, 12, 0.67, wd)
        dst.blit(s, (sx - R - 4 + ox, sy - R - 4 + oy))
    if old is not None and old[1] is not None:
        old[1][0].set_alpha(a_old)
        dst.blit(old[1][0], (sx + old[1][1] + ox, sy + old[1][2] + oy))
        old[1][0].set_alpha(255)
    if front is not None:
        if alpha != 255:
            front[0].set_alpha(alpha)
        dst.blit(front[0], (sx + front[1] + ox, sy + front[2] + oy))
        if alpha != 255:
            front[0].set_alpha(255)                    # A1: as above
    if d["spin"] and d["spin"][0] == "front":
        for spr, px, py in parts:
            dst.blit(spr, (sx + px + ox, sy + py + oy))


def warm(key: str, R: Optional[int] = None, all_steps: bool = True):
    """Boss-spawn warm-up: bake every phase / step so nothing allocates in the fight."""
    d = _ENT[key]
    R = R or d["R"]
    varies = {"masks": 3, "ash": 2, "first_sprout": 2, "dry_maw": 2, "last_whole": 8}.get(key, 1)
    if key in ("borrowed_face", "forgotten_shape"):
        varies = 1
    for ph in range(1, d["phases"] + 1):
        for var in range(varies):
            for st in range(d["n"] if (d["kind"] and all_steps) else 1):
                bake(key, ph, R, st, var)
        if d["spin"] and all_steps:
            for st in range(d["spin"][1]):
                _spin_parts(key, ph, R, st)
    if d["blob"] or key == "anchor":
        for q in (0.0, -0.02, -0.04, -0.06):
            pass


def clear():
    for c in (_layers, _pieces, _comp, _rims, _kit, _tints, _tint_src):
        c.clear()
    global _scratch
    _scratch = None
    _masks.clear()
    _plates.clear()
    _lerp_of.clear()                                   # BUG-176 (own line: 058b extends the tuple above)


def _bytes(c):
    n = 0
    for v in c.values():
        if isinstance(v, pygame.Surface):
            n += v.get_width() * v.get_height() * 4
        elif isinstance(v, tuple):
            for e in v:
                if isinstance(e, pygame.Surface):
                    n += e.get_width() * e.get_height() * 4
    return n


def cache_bytes():
    return {"layers": _bytes(_layers), "pieces": _bytes(_pieces), "composites": _bytes(_comp),
            "kit": _bytes(_kit), "masks": _bytes(_masks), "plates": _bytes(_plates),
            "flash_tints": _bytes(_tints)}


# =====================================================================  shared kit
_masks: Dict[tuple, pygame.Surface] = {}
_plates: Dict[tuple, pygame.Surface] = {}
_scratch: Optional[pygame.Surface] = None
SHOT_R = 8


def _ec(elem):
    return ELEMENTS[elem][1]


def shot_sprite(shape_or_elem: str, color: Optional[Color] = None, edge: Optional[Color] = None):
    """Cached 20x20 boss shot (draw radius 8).  Accepts an element id or a shape name."""
    shape = ELEMENTS[shape_or_elem][0] if shape_or_elem in ELEMENTS else shape_or_elem
    elem = next((e for e, v in ELEMENTS.items() if v[0] == shape), "anchor")
    col = color or ELEMENTS[elem][1]
    dark = ELEMENTS[elem][2]
    k = ("shot", shape, col, edge)
    s = _kit.get(k)
    if s is not None:
        return s
    s = pygame.Surface((20, 20), pygame.SRCALPHA)
    c = (10, 10)

    def P(x, y):
        return (c[0] + x, c[1] + y)
    halo = (8, 8, 12, 200)
    if shape == "trefoil":
        for a in (-90, 30, 150):
            pygame.draw.circle(s, halo, P(4.6 * math.cos(math.radians(a)), 4.6 * math.sin(math.radians(a))), 4)
        for a in (-90, 30, 150):
            pygame.draw.circle(s, col, P(4.6 * math.cos(math.radians(a)), 4.6 * math.sin(math.radians(a))), 3)
    elif shape == "bubble":
        pygame.draw.circle(s, (*dark, 170), c, 8)
        pygame.draw.circle(s, halo, c, 8, 3)
        pygame.draw.circle(s, col, c, 8, 2)
        pygame.draw.circle(s, col, P(-2, -2), 2)
    elif shape == "double_ring":
        pygame.draw.circle(s, (*dark, 170), c, 8)
        pygame.draw.circle(s, col, c, 8, 2)
        pygame.draw.circle(s, col, c, 4, 2)
    elif shape == "triangle":
        tri = [P(0, -8), P(8, 6), P(-8, 6)]
        pygame.draw.polygon(s, halo, [P(0, -9), P(9, 7), P(-9, 7)])
        pygame.draw.polygon(s, col, tri)
        pygame.draw.polygon(s, dark, [P(0, -2), P(3.5, 3.5), P(-3.5, 3.5)])
    elif shape == "hexagon":
        hexp = [P(8 * math.cos(math.radians(60 * i)), 8 * math.sin(math.radians(60 * i))) for i in range(6)]
        pygame.draw.polygon(s, dark, hexp)
        pygame.draw.polygon(s, col, hexp, 2)
        pygame.draw.polygon(s, col, [P(3.5 * math.cos(math.radians(60 * i)), 3.5 * math.sin(math.radians(60 * i))) for i in range(6)])
    elif shape == "diamond":
        dm = [P(0, -8), P(8, 0), P(0, 8), P(-8, 0)]
        pygame.draw.polygon(s, (*dark, 200), dm)
        pygame.draw.polygon(s, col, dm, 2)
    elif shape == "crescent":
        pygame.draw.circle(s, halo, c, 9)
        pygame.draw.circle(s, col, c, 8)
        pygame.draw.circle(s, (0, 0, 0, 0), P(-3.5, -3.5), 6)
    elif shape == "void_disc":
        for a in (0, 90, 180, 270):
            ar = math.radians(a)
            pygame.draw.line(s, col, P(6.5 * math.cos(ar), 6.5 * math.sin(ar)), P(9.5 * math.cos(ar), 9.5 * math.sin(ar)), 2)
        pygame.draw.circle(s, dark, c, 6)
        pygame.draw.circle(s, col, c, 6, 2)
    elif shape == "bolt":
        zz = [P(3, -6), P(-2, -1), P(2, 1), P(-3, 6)]
        pygame.draw.lines(s, halo, False, zz, 5)
        pygame.draw.lines(s, col, False, zz, 3)
    elif shape == "anchor_disc":
        pygame.draw.circle(s, WHITE, c, 8, 2)
        pygame.draw.circle(s, col, c, 6)
    if edge:
        pygame.draw.circle(s, edge, c, 9, 1)
    _kit[k] = s
    return s


# ---- ZONE -----------------------------------------------------------------------------------
def _zone_ring(q, elem, commit, colour=None):
    k = ("zring", q, elem, commit, colour)
    s = _kit.get(k)
    if s is not None:
        return s
    col = colour or _ec(elem)
    c = q + 4
    s = pygame.Surface((2 * c, 2 * c), pygame.SRCALPHA)
    pc = (*col, 150)
    rr = q
    if elem == "growth":                                   # 6 small leaves, radial
        for i in range(6):
            a_ = math.radians(i * 60 + 30)
            ce = (c + math.cos(a_) * rr * .52, c + math.sin(a_) * rr * .52)
            lf = [(ce[0] + math.cos(a_) * x * rr * .17 - math.sin(a_) * y * rr * .17,
                   ce[1] + math.sin(a_) * x * rr * .17 + math.cos(a_) * y * rr * .17)
                  for x, y in ell_pts(1.0, 0.5, 12)]
            pygame.draw.polygon(s, pc, lf, 2)
            pygame.draw.line(s, pc, (ce[0] - math.cos(a_) * rr * .17, ce[1] - math.sin(a_) * rr * .17),
                             (ce[0] + math.cos(a_) * rr * .17, ce[1] + math.sin(a_) * rr * .17), 1)
    elif elem == "toxic":                                  # 5 rising bubble dots
        for i in range(5):
            a_ = math.radians(i * 72 - 90)
            pygame.draw.circle(s, pc, (c + math.cos(a_) * rr * .5, c + math.sin(a_) * rr * .5), max(4, rr // 9), 2)
    elif elem == "echo":
        pygame.draw.circle(s, pc, (c, c), int(rr * .66), 2)
        pygame.draw.circle(s, pc, (c, c), int(rr * .33), 2)
    elif elem in ("fire", "anchor") and elem == "fire":
        _hatch_circle(s, pc, c, rr * .93, 14, 1)
    elif elem == "anchor":
        for f in (.75, .5, .25):
            pygame.draw.circle(s, pc, (c, c), int(rr * f), 2)
    elif elem == "frost":                                  # six-point snow ticks (snowflake spokes with side branches)
        for i in range(6):
            a_ = math.radians(i * 60)
            p0, p1 = (c + math.cos(a_) * rr * .12, c + math.sin(a_) * rr * .12), (c + math.cos(a_) * rr * .7, c + math.sin(a_) * rr * .7)
            pygame.draw.line(s, pc, p0, p1, 2)
            pm = (c + math.cos(a_) * rr * .45, c + math.sin(a_) * rr * .45)
            for sd in (-0.7, 0.7):
                pygame.draw.line(s, pc, pm, (pm[0] + 8 * math.cos(a_ + sd), pm[1] + 8 * math.sin(a_ + sd)), 2)
    elif elem == "mirage":
        for yy in (-.5, -.17, .17, .5):
            half = math.sqrt(max(0, (rr * .9) ** 2 - (yy * rr) ** 2))
            pts = [(c - half + 2 * half * j / 24, c + yy * rr + 4 * math.sin(j / 24 * TAU * 2)) for j in range(25)]
            pygame.draw.lines(s, pc, False, pts, 2)
    elif elem == "dream":
        for i in range(8):
            a = math.radians(i * 45)
            pygame.draw.circle(s, pc, (c + math.cos(a) * rr * .6, c + math.sin(a) * rr * .6), max(3, rr // 14))
    elif elem == "void":
        pass
    elif elem == "lightning":
        for sg in (-1, 1):
            zz = [(c + sg * rr * .35 * (1 - 2 * ((j % 2) * .6)) * 0 + sg * (-rr * .35 + rr * .7 * j / 5), c - rr * .35 + rr * .7 * j / 5 + (6 if j % 2 else -6)) for j in range(6)]
            pygame.draw.lines(s, pc, False, [(x if sg > 0 else 2 * c - x, y) for x, y in zz], 2)
    w = 4 if commit else 2
    oc = (*col, 230)
    if elem == "void":
        seg = TAU / 28
        for i in range(28):
            pts = [(c + math.cos(i * seg + seg * .6 * j / 4) * (rr - 1), c + math.sin(i * seg + seg * .6 * j / 4) * (rr - 1)) for j in range(5)]
            pygame.draw.lines(s, oc, False, pts, w)
    else:
        pygame.draw.circle(s, oc, (c, c), rr, w)
    _kit[k] = s
    return s


def _hatch_circle(s, col, c, rr, spacing, slope):
    k = -rr * 1.5
    while k < rr * 1.5:
        d = abs(k) / math.sqrt(2)
        if d < rr:
            hc = math.sqrt(rr * rr - d * d)
            mx, my = (k / 2, k / 2) if True else (0, 0)
            # line u + v = k  (slope=1 -> '/'): centre of chord at (k/2, k/2), direction (1,-1)/sqrt2
            if slope > 0:
                a = (c + k / 2 - hc / math.sqrt(2), c + k / 2 + hc / math.sqrt(2))
                b = (c + k / 2 + hc / math.sqrt(2), c + k / 2 - hc / math.sqrt(2))
            else:
                a = (c + k / 2 - hc / math.sqrt(2), c - k / 2 - hc / math.sqrt(2))
                b = (c + k / 2 + hc / math.sqrt(2), c - k / 2 + hc / math.sqrt(2))
            pygame.draw.line(s, col, a, b, 2)
        k += spacing


def _zone_fill(q, elem, alpha_px=80):
    k = ("zfill", q, elem, alpha_px)
    s = _kit.get(k)
    if s is None:
        s = pygame.Surface((2 * q + 2, 2 * q + 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*ELEMENTS[elem][2], alpha_px), (q + 1, q + 1), q)
        _kit[k] = s
    return s


def zone(dst, cx, cy, radius, elem, p=1.0, commit=False, colour=None, fill_alpha=80):
    """Ground ZONE.  p = warning progress 0..1 (fill alpha 40 -> 80 via set_alpha); commit -> 4 px outline."""
    q = max(8, int(round(radius / 4.0)) * 4)
    fill = _zone_fill(q, elem, fill_alpha)
    fill.set_alpha(int(127 + 128 * min(max(p, 0.0), 1.0)))
    dst.blit(fill, (int(cx) - q - 1, int(cy) - q - 1))
    ring = _zone_ring(q, elem, bool(commit), colour)
    dst.blit(ring, (int(cx) - q - 4, int(cy) - q - 4))


# ---- LANE -----------------------------------------------------------------------------------
def warm_kit(size=(1200, 800)):
    global _scratch
    if _scratch is None or _scratch.get_size() != tuple(size):
        _scratch = pygame.Surface(size, pygame.SRCALPHA)


def lane(dst, x0, y0, x1, y1, width, elem, p=1.0, commit=False, hatch="/", chevrons=False, colour=None,
         fill="alpha", ground=None):
    """Danger lane: filled+outlined rectangle (parallelogram) with diagonal hatch; <= 12 draw calls.
    fill: "alpha" = dark fill via the pre-allocated screen-size scratch (translucent, ~25 ns/px of the bbox),
          "solid" = opaque polygon in dark-fill blended into `ground` (cheap, hides ground detail), "none"."""
    col = colour or _ec(elem)
    dark = ELEMENTS[elem][2]
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    if L < 1:
        return
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    hw = width / 2.0
    P = [(x0 + nx * hw, y0 + ny * hw), (x1 + nx * hw, y1 + ny * hw), (x1 - nx * hw, y1 - ny * hw), (x0 - nx * hw, y0 - ny * hw)]
    a = (40 + 40 * min(max(p, 0), 1)) / 255.0
    if fill == "alpha" and _scratch is not None:
        xs, ys = [q[0] for q in P], [q[1] for q in P]
        bb = pygame.Rect(int(min(xs)) - 1, int(min(ys)) - 1, int(max(xs) - min(xs)) + 3, int(max(ys) - min(ys)) + 3)
        bb = bb.clip(_scratch.get_rect())
        if bb.w > 0 and bb.h > 0:
            pygame.draw.polygon(_scratch, (*dark, int(a * 255)), P)
            dst.blit(_scratch, bb.topleft, bb)
            _scratch.fill((0, 0, 0, 0), bb)
    elif fill == "solid":
        g = ground or GROUND[ELEMENTS[elem][3]]
        pygame.draw.polygon(dst, tuple(int(gc * (1 - a) + dc * a) for gc, dc in zip(g, dark)), P)
    n = int(min(8, max(3, L / 22)))
    sp = max(0.0, L - width) / max(1, n - 1)
    sgn = 1 if hatch == "/" else -1
    for i in range(n):
        u = i * sp
        if u + width <= L + 0.5:
            pygame.draw.line(dst, col, (x0 + ux * u - nx * hw * sgn, y0 + uy * u - ny * hw * sgn),
                             (x0 + ux * (u + width) + nx * hw * sgn, y0 + uy * (u + width) + ny * hw * sgn), 1)
    pygame.draw.polygon(dst, col, P, 4 if commit else 2)
    if chevrons:
        for u in (L * 0.25, L * 0.5, L * 0.75):
            c = (x0 + ux * u, y0 + uy * u)
            pygame.draw.lines(dst, col, False, [(c[0] - ux * 8 + nx * 9, c[1] - uy * 8 + ny * 9), (c[0] + ux * 6, c[1] + uy * 6),
                                                (c[0] - ux * 8 - nx * 9, c[1] - uy * 8 - ny * 9)], 3)


# ---- FAN ------------------------------------------------------------------------------------
def fan(dst, cx, cy, ang, spread, length, elem, colour=None):
    col = colour or _ec(elem)
    pts = [(cx + math.cos(ang - spread / 2 + spread * i / 6) * length, cy + math.sin(ang - spread / 2 + spread * i / 6) * length) for i in range(7)]
    pygame.draw.lines(dst, col, False, pts, 2)
    for a in (ang - spread / 2, ang, ang + spread / 2):
        pygame.draw.line(dst, col, (cx, cy), (cx + math.cos(a) * length, cy + math.sin(a) * length), 2 if a != ang else 1)


# ---- RING-OUT -------------------------------------------------------------------------------
RING_CACHE_MAX = 224        # A1: was 192; the Frost / Silence warning rings are 180 / 220 px and fade


def ring_out(dst, cx, cy, radius, colour, alpha=255, style="solid", quant=8):
    """Thin ring (2 px) sprite cached per (radius step 8, colour, style); set_alpha fades it.
    Radii above RING_CACHE_MAX are drawn directly (no cache, no fade). A1: quant=1 keeps an exact radius."""
    q = max(quant, int(round(radius / float(quant))) * quant)
    if q > RING_CACHE_MAX:
        pygame.draw.circle(dst, colour, (int(cx), int(cy)), int(radius), 3 if style == "phase" else 2)
        return
    k = ("ring", q, colour, style)
    s = _kit.get(k)
    if s is None:
        c = q + 3
        s = pygame.Surface((2 * c, 2 * c), pygame.SRCALPHA)
        if style in ("solid", "thick", "phase"):
            pygame.draw.circle(s, colour, (c, c), q, {"thick": 4, "phase": 3}.get(style, 2))   # A1: 3 px phase ring
        elif style == "dashed":
            n = max(12, q // 3)
            seg = TAU / n
            for i in range(n):
                pygame.draw.lines(s, colour, False, [(c + math.cos(i * seg + seg * .55 * j / 4) * q, c + math.sin(i * seg + seg * .55 * j / 4) * q) for j in range(5)], 2)
        else:                                               # dotted
            n = max(16, q // 2)
            for i in range(n):
                pygame.draw.circle(s, colour, (c + math.cos(i * TAU / n) * q, c + math.sin(i * TAU / n) * q), 2)
        _kit[k] = s
    s.set_alpha(int(alpha))
    dst.blit(s, (int(cx) - s.get_width() // 2, int(cy) - s.get_height() // 2))


# ---- MARK -----------------------------------------------------------------------------------
def _mark_sprite(q, elem):
    k = ("mark", q, elem)
    s = _kit.get(k)
    if s is None:
        col = _ec(elem)
        c = q + 12
        s = pygame.Surface((2 * c, 2 * c), pygame.SRCALPHA)
        pygame.draw.circle(s, (*ELEMENTS[elem][2], 60), (c, c), q)
        pygame.draw.circle(s, (*col, 230), (c, c), q, 2)
        for a in (0, 90, 180, 270):
            ar = math.radians(a)
            pygame.draw.line(s, (*col, 230), (c + math.cos(ar) * (q - 4), c + math.sin(ar) * (q - 4)), (c + math.cos(ar) * (q + 9), c + math.sin(ar) * (q + 9)), 2)
        ic = shot_sprite(elem)
        s.blit(ic, (c - ic.get_width() // 2, c - ic.get_height() // 2))
        _kit[k] = s
    return s


def mark(dst, x, y, radius, elem, p=0.0):
    """Reticle; p 0..1 = warning progress, the inner ring shrinks radius -> 0 (hits at p=1). 1 blit + 1 circle."""
    q = max(8, int(round(radius / 4.0)) * 4)
    s = _mark_sprite(q, elem)
    dst.blit(s, (int(x) - s.get_width() // 2, int(y) - s.get_height() // 2))
    r = int(q * (1.0 - min(max(p, 0.0), 1.0)))
    if r >= 3:
        pygame.draw.circle(dst, _ec(elem), (int(x), int(y)), r, 2)


def safe_brackets(dst, rect, colour=WHITE, arm=12, w=2):
    x0, y0, x1, y1 = rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]
    for (x, y, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        pygame.draw.line(dst, colour, (x, y), (x + sx * arm, y), w)
        pygame.draw.line(dst, colour, (x, y), (x, y + sy * arm), w)


# ---- view-dimming masks (2.7) --------------------------------------------------------------
MASKS = {  # name -> (edge colour, max alpha, clear radius px)
    "veil": ((20, 14, 12), 150, 200),
    "whiteout": ((112, 140, 165), 100, 260),     # spec (205,225,240): chill outlines only 2.3:1 -> darker edge tone
    "whiteout3": ((112, 140, 165), 100, 320),
    "erasure": ((4, 3, 10), 140, 220),
}
MASK_RAMP = 140.0     # px from the clear radius to full alpha


def view_mask(name: str, size=(1200, 800)) -> pygame.Surface:
    k = (name, tuple(size))
    s = _masks.get(k)
    if s is None:
        col, amax, clear_r = MASKS[name]
        cell = 4
        gw, gh = size[0] // cell, size[1] // cell
        small = pygame.Surface((gw, gh), pygame.SRCALPHA)
        for j in range(gh):
            for i in range(gw):
                d = math.hypot((i + .5) * cell - size[0] / 2, (j + .5) * cell - size[1] / 2)
                u = min(1.0, max(0.0, (d - clear_r) / MASK_RAMP))
                small.set_at((i, j), (*col, int(amax * u * u * (3 - 2 * u))))
        s = pygame.transform.smoothscale(small, size)
        _masks[k] = s
    return s


def draw_mask(dst, name, fade=1.0):
    m = view_mask(name, dst.get_size())
    m.set_alpha(int(255 * min(max(fade, 0.0), 1.0)))
    dst.blit(m, (0, 0))


def masked_ground(layer_ground: Color, name: str, at_corner=True) -> Color:
    col, amax, _ = MASKS[name]
    return tuple(int(round(g * (1 - amax / 255.0) + c * (amax / 255.0))) for g, c in zip(layer_ground, col))


# ---- text plates ----------------------------------------------------------------------------
_font_obj = None


def _font():
    global _font_obj
    if _font_obj is None:
        _font_obj = pygame.font.SysFont("segoeui", 13, bold=True)
    return _font_obj


def name_plate(text: str, colour: Color = (230, 210, 180)) -> pygame.Surface:
    k = ("name", text, colour)
    s = _plates.get(k)
    if s is None:
        f = _font()
        fg, bg = f.render(text, True, colour), f.render(text, True, (10, 8, 14))
        s = pygame.Surface((fg.get_width() + 2, fg.get_height() + 2), pygame.SRCALPHA)
        for ox, oy in ((0, 0), (1, 0), (2, 0), (0, 1), (2, 1), (0, 2), (1, 2), (2, 2)):
            s.blit(bg, (ox, oy))
        s.blit(fg, (1, 1))
        _plates[k] = s
    return s


def phase_pips(total: int, lit: int, colour: Color) -> pygame.Surface:
    k = ("pips", total, lit, colour)
    s = _plates.get(k)
    if s is None:
        s = pygame.Surface((total * 8 + (total - 1) * 5 + 2, 10), pygame.SRCALPHA)
        for i in range(total):
            cx = 5 + i * 13
            pts = [(cx, 1), (cx + 4, 5), (cx, 9), (cx - 4, 5)]
            pygame.draw.polygon(s, colour if i < lit else (20, 16, 28), pts)
            pygame.draw.polygon(s, WHITE, pts, 1)
        _plates[k] = s
    return s


def draw_plate(dst, sx, sy, R, key, phase, hp_frac=1.0):
    """Name plate + pips above the boss (cached blits only)."""
    d = _ENT[key]
    B, C, K = pal(key, phase)
    colour = (230, 210, 180) if phase == 1 else K
    np_ = name_plate(display_name(key, phase), colour)
    y = sy - R - 20
    dst.blit(np_, (sx - np_.get_width() // 2, y - 18))
    if d["phases"] > 1:
        pp = phase_pips(d["phases"], phase, ELEMENTS[_elem_of(key)][1])
        dst.blit(pp, (sx - pp.get_width() // 2, y - 32))


def _elem_of(key):
    return {"sprouting": "growth", "rot": "toxic", "echoes": "echo", "ash": "fire", "frost": "frost", "thirst": "mirage",
            "masks": "dream", "silence": "void", "ascent": "lightning", "anchor": "anchor"}.get(key, ["growth", "toxic", "echo", "fire", "frost", "mirage", "dream", "void", "lightning", "anchor"][_ENT[key]["layer"]])


# =====================================================================  A1: boss health bar and spawn warm-up
_BAR_BASE = (239, 68, 68)                 # graphics.draw_health_bar defaults (low HP < 30 % switches colour)


def _bar_sprite(w: int, h: int, low: bool) -> pygame.Surface:
    """The bar's gradient + sheen baked once at full width (draw_health_bar redraws it per pixel column each frame)."""
    k = ("bar", w, h, low)
    s = _plates.get(k)
    if s is None:
        col = (255, min(120, _BAR_BASE[1] + 40), 60) if low else _BAR_BASE
        s = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        for i in range(w):
            t = i / max(1, w)
            c = (int(col[0] * (1 - t * 0.25) + 20 * t), int(col[1] * (1 - t * 0.25)), int(col[2] * (1 - t * 0.2)))
            pygame.draw.line(s, c, (i, 1), (i, h - 2))
        sheen = pygame.Surface((max(1, w), max(1, h // 3)), pygame.SRCALPHA)
        sheen.fill((255, 255, 255, 35))
        s.blit(sheen, (0, 1))
        _plates[k] = s
    return s


def health_bar(dst, x: int, y: int, w: int, h: int, ratio: float, notches=(), notch_colour: Color = WHITE) -> None:
    """Boss health bar: frame and border as draw_health_bar, the gradient blitted from a cached sprite (clipped to
    the HP fraction), plus a 2 px tick at each phase threshold (spec 2.6). No allocations after the first call."""
    ratio = max(0.0, min(1.0, ratio))
    pygame.draw.rect(dst, (36, 48, 64), (x, y, w, h), border_radius=4)
    fw = int(w * ratio)
    if fw > 0:
        dst.blit(_bar_sprite(w, h, ratio < 0.3), (x, y), (0, 0, fw, h))
    pygame.draw.rect(dst, (90, 110, 130), (x, y, w, h), 1, border_radius=4)
    for f in notches:
        nx = x + int(w * f)
        pygame.draw.line(dst, notch_colour, (nx, y + 1), (nx, y + h - 2), 2)


def warm_entity(key: str, R: int, names=(), name_colours=(), bar_w: int = 0, bar_h: int = 8,
                ring_colour: Optional[Color] = None, flash_colours=((255, 255, 255), (255, 200, 200))) -> None:
    """Spawn-time bake of everything Boss.draw can touch for this entity at radius R (layers, spin parts, body
    circles at the 4 pulse radii incl. the flash palette, plates, pips, bar sprites, phase-ring sprites)."""
    d = _ENT[key]
    for ph in range(1, d["phases"] + 1):                # the cropped layers draw_boss uses (bake()'s composites
        tint = flashes_by_tint(key, ph)                 # are a tool / test path and are not built here)
        for st in range(d["n"] if d["kind"] else 1):
            for lay in _get_layers(key, ph, R, 0, st):
                if tint and lay is not None:
                    _tinted(lay[0], flash_lerp(key))    # BUG-162: the flash copies too
        if d["spin"]:
            for st in range(d["spin"][1]):
                for spr, _x, _y in _spin_parts(key, ph, R, st):
                    if tint:
                        _tinted(spr, flash_lerp(key))
    scratch = pygame.Surface((8, 8), pygame.SRCALPHA)
    for ph in range(1, d["phases"] + 1):
        B, C, K = pal(key, ph)
        for col, core in ((B, C), flash_colours):
            for q in (0.0, -0.02, -0.04, -0.06):
                draw_blob_cached(scratch, (4, 4), R, col, core, None, pulse=q, glow=True, eyes=d["eyes"], look=(1, 0))
        if d["phases"] > 1:
            phase_pips(d["phases"], ph, ELEMENTS[_elem_of(key)][1])
        if _flags(key, ph)[2] == "dashed":
            _dashed_rim(R, K, 16, 0.6, 2 if d["mini"] else 3)
    for text in names:
        for colour in name_colours:
            name_plate(text, colour)
    if bar_w:
        _bar_sprite(bar_w, bar_h, False)
        _bar_sprite(bar_w, bar_h, True)
    if ring_colour is not None:
        for r in range(max(8, (R // 8) * 8), 3 * R + 9, 8):              # every 8 px step a cached ring passes
            if 3 * R <= RING_CACHE_MAX:
                ring_out(scratch, -999, -999, r, ring_colour, 0, style="phase")


def phase_ring_direct(R: int) -> bool:
    """True when the phase ring outgrows the ring cache (3 R > RING_CACHE_MAX) and is drawn directly."""
    return 3 * R > RING_CACHE_MAX


def phase_ring(dst, sx: int, sy: int, R: int, p: float, colour: Color, ground: Color, alpha0: float = 170) -> None:
    """Spec 2.5 phase ring at progress p (0..1): radius R -> 3 R, 3 px. Up to RING_CACHE_MAX the cached sprite fades by
    alpha (alpha0 -> 0); larger rings (VD r2, spec 9.9) are pygame.draw.circle with the colour lerped toward the
    layer's LIGHT ground tone, matching the sprite's look at p = 0 and reaching the ground colour at p = 1."""
    radius = R + 2 * R * p
    if not phase_ring_direct(R):
        ring_out(dst, sx, sy, radius, colour, alpha0 * (1 - p), style="phase")
        return
    k = 1.0 - (alpha0 / 255.0) * (1.0 - p)                      # share of the ground in the ring colour
    col = tuple(int(round(c + (g - c) * k)) for c, g in zip(colour, ground))
    pygame.draw.circle(dst, col, (int(sx), int(sy)), int(radius), 3)


def entity_element_colour(key: str) -> Color:
    """Outline colour of the entity's element (phase ring, pips)."""
    return ELEMENTS[_elem_of(key)][1]
