"""Global configuration constants for Blob Evolution."""

from __future__ import annotations

# Display
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
FPS = 60
TITLE = "Blob Evolution"

# World
WORLD_WIDTH = 2000
WORLD_HEIGHT = 2000

# Physics
GRAVITY = 600.0
PLAYER_BASE_SPEED = 280.0
PLAYER_BASE_HP = 100
PLAYER_BASE_DAMAGE = 10
PLAYER_BASE_SIZE = 20

# Entity limits
MAX_PARTICLES = 1200
MAX_CREATURES = 50
MAX_BOSSES = 5
MAX_PROJECTILES = 200

# Progression
XP_BASE = 50
XP_MULTIPLIER = 1.4
SKILL_POINTS_PER_LEVEL = 2
MAX_SKILL_LEVEL = 10

# Camera
CAMERA_SMOOTH = 0.12
SCREEN_SHAKE_DECAY = 0.85
HUD_NOTICE_QUEUE = 6                   # BUG-145: notices waiting behind the one on screen (the oldest waiting one drops beyond this)

# Colors
VOID_COLOR_SCALE = 0.5          # ground edge fill (outside the world) = the act's DARK ground tone x this
COLOR_BG = (15, 23, 42)          # slate-900
COLOR_PLAYER = (34, 197, 94)   # green-500
COLOR_PLAYER_CORE = (74, 222, 128)
COLOR_XP = (250, 204, 21)      # yellow
COLOR_PROJECTILE_PLAYER = (120, 255, 170)   # TASK-043: lighter than the player body so shots read against it
COLOR_PROJECTILE_ENEMY = (255, 150, 50)
COLOR_PROJECTILE_PLAYER_LEGACY = (34, 197, 94)   # pre-043 colours, used when GFX_READABILITY is False
COLOR_PROJECTILE_ENEMY_LEGACY = (249, 115, 22)
COLOR_UI_BG = (30, 41, 59)
COLOR_UI_BORDER = (71, 85, 105)
COLOR_TEXT = (226, 232, 240)
COLOR_HEALTH = (239, 68, 68)
COLOR_HEALTH_BG = (51, 65, 85)
COLOR_XP_BAR = (59, 130, 246)
COLOR_ESSENCE = (168, 85, 247)

# Minimap
MINIMAP_SIZE = 200
MINIMAP_PADDING = 10

# Overworld map layout
OVERWORLD_HEADER_RECT = (60, 8, SCREEN_WIDTH - 120, 88)  # x, y, w, h; bottom edge at y=96
OVERWORLD_NODE_TOP_REACH = 33  # boss radius 22 + selected ring max (5 + 3 pulse + 3)
OVERWORLD_MAP_TOP = OVERWORLD_HEADER_RECT[1] + OVERWORLD_HEADER_RECT[3] + OVERWORLD_NODE_TOP_REACH + 8  # = 137
OVERWORLD_MAP_BOTTOM = SCREEN_HEIGHT - 70  # 730

# Difficulty multipliers
DIFFICULTY_SETTINGS = {
    "easy": {"hp": 0.7, "damage": 0.7, "speed": 0.8, "xp": 1.2, "elite_chance": 0.0},
    "normal": {"hp": 1.0, "damage": 1.0, "speed": 1.0, "xp": 1.0, "elite_chance": 0.0},
    "hard": {"hp": 1.4, "damage": 1.3, "speed": 1.2, "xp": 0.9, "elite_chance": 0.05},
    "extreme": {"hp": 2.0, "damage": 1.6, "speed": 1.4, "xp": 0.8, "elite_chance": 0.15},
}

# Map themes: name, base_color (= the MID tone of GROUND_RAMPS), accent, creatures, bosses, hazards
# Names align with data.lore.ACT_LORE lore_name fields.
MAP_THEMES = [
    {"name": "The Verdant Rim", "color": (28, 72, 42), "accent": (58, 150, 75), "creatures": 25, "bosses": 1, "hazards": []},
    {"name": "The Sinking Garden", "color": (42, 50, 28), "accent": (90, 140, 45), "creatures": 30, "bosses": 1, "hazards": ["toxic"]},
    {"name": "The Memory Vaults", "color": (26, 34, 74), "accent": (90, 160, 220), "creatures": 25, "bosses": 2, "hazards": []},
    {"name": "The Forge Veins", "color": (48, 24, 20), "accent": (220, 90, 35), "creatures": 35, "bosses": 2, "hazards": ["lava"]},
    {"name": "The Still Expanse", "color": (32, 56, 76), "accent": (130, 190, 235), "creatures": 20, "bosses": 1, "hazards": ["ice"]},
    {"name": "The Mirage Basin", "color": (80, 60, 36), "accent": (230, 190, 100), "creatures": 30, "bosses": 2, "hazards": []},
    {"name": "The Dreaming Thicket", "color": (52, 24, 82), "accent": (150, 90, 210), "creatures": 40, "bosses": 3, "hazards": ["toxic"]},
    {"name": "The Hollow Undermembrane", "color": (16, 14, 26), "accent": (70, 55, 95), "creatures": 45, "bosses": 3, "hazards": []},
    {"name": "The Ascending Strata", "color": (16, 22, 48), "accent": (190, 210, 255), "creatures": 50, "bosses": 4, "hazards": []},
    {"name": "The First Divide", "color": (42, 16, 48), "accent": (220, 55, 160), "creatures": 60, "bosses": 5, "hazards": ["lava", "toxic", "ice"]},
]

# Ground tone ramps per act (DARK, MID, LIGHT). The baked ground only ever uses tones between DARK and LIGHT,
# so its luminance stays low enough for the green player body to keep >= 3:1 (see tests/test_ground_terrain.py).
GROUND_RAMPS = [
    ((20, 52, 32), (28, 72, 42), (40, 98, 54)),     # 0 Verdant Rim
    ((30, 36, 20), (42, 50, 28), (62, 70, 32)),     # 1 Sinking Garden
    ((18, 24, 56), (26, 34, 74), (40, 56, 104)),    # 2 Memory Vaults (indigo)
    ((34, 16, 14), (48, 24, 20), (80, 36, 22)),     # 3 Forge Veins
    ((22, 40, 56), (32, 56, 76), (48, 80, 104)),    # 4 Still Expanse (teal-steel)
    ((58, 43, 26), (80, 60, 36), (104, 80, 48)),    # 5 Mirage Basin (dusk sand)
    ((36, 16, 58), (52, 24, 82), (72, 38, 108)),    # 6 Dreaming Thicket
    ((10, 9, 18), (16, 14, 26), (28, 23, 42)),      # 7 Hollow Undermembrane
    ((10, 15, 36), (16, 22, 48), (26, 36, 76)),     # 8 Ascending Strata (navy-black)
    ((30, 11, 34), (42, 16, 48), (76, 24, 68)),     # 9 First Divide
]
# Macro noise octaves: (cells per side, lowest ramp position, highest ramp position, blit alpha; None = opaque base)
GROUND_NOISE_OCTAVES = ((9, 0.0, 1.0, None), (22, 0.05, 0.95, 90), (60, 0.25, 0.75, 50))
GROUND_GRIT_COUNT = (1000, 1600)    # single-pixel grit specks per bake (min, max)
GROUND_GRIT_SPREAD = 14             # grit = MID +/- this per channel (never darker than 0.6 x DARK)
GROUND_CLUSTER_COUNT = (7, 10)      # decal cluster centres per act (plus one at the world centre)
GROUND_CLUSTER_MARGIN = 250         # cluster centres stay this far from the world edge
GROUND_CLUSTER_SIGMA = (110, 170)   # gaussian spread of a cluster (min, max)
GROUND_CLUSTER_SHARE = 0.7          # share of scattered decals that sit in clusters (rest uniform)
MAX_STAMPS_PER_ACT = 500            # decal budget per bake (checked via scatter.total)

# Hazard art (TASK-042): redraw only, collision (distance < radius) and effects are untouched. Colours per hazard type;
# every shape stays inside its radius (a 1 px outline may touch it). Zones bake their sprite once; frames animate with
# a few cached blits / 1 px circles. Pulses stay inside 0.5-1.0 and nothing blinks faster than 0.4 Hz (R5).
HAZARD_SPRITE_PAD = 6               # transparent border around the baked zone sprite
HAZARD_CORE_FRAMES = 6              # cached lava core sizes (50% -> 60% of the radius)
HAZARD_SPARKLE = (0.7, 2.0)         # ice sparkle seconds on / off
HAZARD_BUBBLE_RISE = 24             # px a toxic bubble rises at most (cut so it never leaves the green body)
HAZARD_STYLE = {     # dark, mostly opaque fills (the plan's (150,44,12) / (60,170,50) / (100,180,255) are far too bright to read a shot on);
    # r2: fills and outlines are dimmed (same hue) so enemy shots stay >= 3.3:1 everywhere inside and >= 2.7:1 on the outline band
    # BUG-134 (Visual Designer): toxic edge (146,196,69) -> (176,226,86), ice edge (180,215,240) -> (200,228,248); edge_inner kept
    "lava": {"fill": (60, 16, 5, 185), "crust": (40, 14, 8), "edge": (255, 170, 60), "core": (180, 80, 20, 30),
             "crack": (255, 200, 80), "bubble": (255, 200, 80)},
    "toxic": {"fill": (12, 42, 16, 185), "rim": (14, 40, 16), "edge": (176, 226, 86), "edge_inner": (50, 66, 24),
              "ring": (120, 210, 70, 50), "bubble": (147, 178, 105), "bubble_fade": (60, 150, 55)},
    "ice": {"fill": (10, 24, 56, 190), "edge": (200, 228, 248), "edge_inner": (90, 108, 120), "facet": (225, 245, 255),
            "facet_alpha": (4, 8), "shine": (255, 255, 255, 50), "spark": (200, 200, 200)},
}
HAZARD_MINIMAP = {"lava": (255, 80, 30), "ice": (100, 200, 255), "toxic": (80, 255, 80)}

# Ambient mote field (TASK-040): purely visual world-space motes per act, drawn as prebuilt sprites.
# Layer keys: name, cap, colors, [end_color: colour lerp over life], shape (disc | streak_h | streak_v),
#   size (disc radius range in px, or streak (w, h)), vx / vy / life ranges, blend (add | alpha), peak alpha,
#   motion (drift | orbit | walk) with sway=(amp px, Hz), gust=(amp, rad/s), orbit=(speed lo, hi, rad/s),
#   walk=(max px/s, jitter), mod=(lowest brightness factor, Hz) for blink / twinkle / flicker / pulse (all <= 1 Hz),
#   spawn_band=share of the padded rect (from the bottom) a mote is (re)born in, instead of anywhere (embers).
AMBIENT_MAX_MOTES = 200                 # caps of one act add up to at most this many
AMBIENT_MARGIN = 150                    # motes live in the camera rect +/- this many px, and wrap inside it
AMBIENT_POP_PAD = 8                     # a wrapping mote must land at least its own size + this far outside the screen
AMBIENT_FRONT_EVERY = 4                 # every 4th mote (25%) is drawn in front of the entities
AMBIENT_FRONT_MAX_ALPHA = 90            # front motes never get brighter than this (they must not hide enemies)
AMBIENT_NEAR_REACH = 1.6                # BUG-119 (VD): a mote whose centre is within this x player R + its own radius ...
AMBIENT_NEAR_ALPHA = 0.5                # ... draws its pre-baked copy at this share of its alpha (two states, no lerp)
AMBIENT_FADE = 0.5                      # seconds to fade a mote in and out
AMBIENT_ALPHA_LADDER = (40, 80, 120, 160, 200, 255)
AMBIENT_COLOR_STEPS = 4                 # colour-lerp steps for motes with an end_color
AMBIENT_LAYERS = [
    [  # 0 Verdant Rim: pollen
        {"name": "pollen", "cap": 70, "colors": ((200, 230, 120), (240, 240, 170)), "shape": "disc", "size": (2, 3),
         "vx": (8, 16), "vy": (-12, -6), "life": (6, 9), "blend": "add", "peak": 150, "motion": "drift",
         "sway": (10, 0.7)},
    ],
    [  # 1 Sinking Garden: spores and fireflies
        {"name": "spores", "cap": 60, "colors": ((150, 190, 80),), "shape": "disc", "size": (2, 3),
         "vx": (0, 0), "vy": (-10, -10), "life": (5, 8), "blend": "add", "peak": 150, "motion": "drift"},
        {"name": "fireflies", "cap": 6, "colors": ((230, 240, 120),), "shape": "disc", "size": (2, 3),
         "vx": (-3, 3), "vy": (-5, 5), "life": (5, 8), "blend": "add", "peak": 255, "motion": "drift",
         "mod": (0.0, 0.4)},
    ],
    [  # 2 Memory Vaults: motes and glints
        {"name": "motes", "cap": 48, "colors": ((140, 200, 255), (210, 235, 255)), "shape": "disc", "size": (1, 3),
         "vx": (0, 0), "vy": (-14, -14), "life": (4, 7), "blend": "add", "peak": 160, "motion": "drift",
         "mod": (0.4, 0.5)},
        {"name": "glints", "cap": 12, "colors": ((210, 235, 255),), "shape": "disc", "size": (1, 1),
         "vx": (0, 0), "vy": (-14, -14), "life": (4, 7), "blend": "add", "peak": 255, "motion": "drift",
         "mod": (0.0, 0.5)},
    ],
    [  # 3 Forge Veins: embers
        {"name": "embers", "cap": 90, "colors": ((255, 150, 40), (255, 90, 20), (255, 200, 90)),
         "end_color": (120, 40, 20), "shape": "disc", "size": (2, 3),
         "vx": (-10, 10), "vy": (-110, -50), "life": (3.0, 5.0), "blend": "add", "peak": 230, "motion": "drift",
         "mod": (0.8, 0.8), "spawn_band": 0.4},
    ],
    [  # 4 Still Expanse: snow
        {"name": "snow", "cap": 120, "colors": ((235, 245, 255),), "shape": "disc", "size": (1, 3),
         "vx": (-22, -10), "vy": (18, 34), "life": (6, 8), "blend": "alpha", "peak": 200, "motion": "drift",
         "gust": (0.6, 0.3)},
    ],
    [  # 5 Mirage Basin: dust streaks and wisps
        {"name": "dust", "cap": 64, "colors": ((230, 200, 140),), "shape": "streak_h", "size": (10, 2),
         "vx": (60, 120), "vy": (-5, 5), "life": (4, 6), "blend": "alpha", "peak": 60, "motion": "drift"},
        {"name": "wisps", "cap": 6, "colors": ((230, 200, 140),), "shape": "streak_h", "size": (16, 3),
         "vx": (30, 60), "vy": (0, 0), "life": (4, 6), "blend": "alpha", "peak": 50, "motion": "orbit",
         "orbit": (25, 40, 1.2)},
    ],
    [  # 6 Dreaming Thicket: orbiting spores
        {"name": "spores", "cap": 80, "colors": ((190, 140, 255), (120, 255, 200)), "shape": "disc", "size": (2, 4),
         "vx": (0, 0), "vy": (0, 0), "life": (5, 8), "blend": "add", "peak": 170, "motion": "orbit",
         "orbit": (8, 14, 0.6), "mod": (0.5, 0.6)},
    ],
    [  # 7 Hollow Undermembrane: violet motes (rings: AMBIENT_RINGS)
        {"name": "motes", "cap": 40, "colors": ((150, 120, 210),), "shape": "disc", "size": (1, 3),
         "vx": (0, 0), "vy": (0, 0), "life": (6, 10), "blend": "add", "peak": 150, "motion": "walk",
         "walk": (8, 12)},
    ],
    [  # 8 Ascending Strata: rising light motes and streaks
        {"name": "motes", "cap": 50, "colors": ((210, 225, 255),), "shape": "disc", "size": (1, 3),
         "vx": (0, 0), "vy": (-90, -40), "life": (2, 4), "blend": "add", "peak": 180, "motion": "drift",
         "mod": (0.4, 0.8)},
        {"name": "streaks", "cap": 40, "colors": ((210, 225, 255),), "shape": "streak_v", "size": (3, 8),
         "vx": (0, 0), "vy": (-90, -40), "life": (2, 4), "blend": "add", "peak": 150, "motion": "drift",
         "mod": (0.4, 0.8)},
    ],
    [  # 9 First Divide: sparks and ash
        {"name": "sparks", "cap": 40, "colors": ((255, 90, 200),), "shape": "disc", "size": (2, 3),
         "vx": (-20, 20), "vy": (-50, -20), "life": (2, 4), "blend": "add", "peak": 220, "motion": "drift"},
        {"name": "ash", "cap": 40, "colors": ((90, 50, 80),), "shape": "disc", "size": (2, 3),
         "vx": (-6, 6), "vy": (6, 14), "life": (5, 8), "blend": "alpha", "peak": 120, "motion": "drift"},
    ],
]
# Expanding rings (act 7): colour, seconds between rings (lo, hi), end radius, life s, start alpha, max alive
AMBIENT_RINGS = {7: {"color": (90, 70, 140), "every": (3.0, 5.0), "radius": 90, "life": 2.0, "alpha": 60, "max": 2}}
AMBIENT_RING_STEPS = 12                 # prebuilt ring sprites per act (radius and alpha steps together)

# Depth layers (TASK-041): a half-speed fog / parallax layer above the ground and a cached screen-space light overlay.
GFX_LAYERS = True                       # Producer A/B switch: False builds and draws neither layer
FOG_TILE = 512                          # seamless fog tile size; pre-tiled to (screen + tile) so one blit covers the screen
FOG_PARALLAX = 0.5                      # the fog slides at this share of the camera speed
# Fog groups per act, drawn in order into the tile. kind: blob (soft disc), ellipse (soft horizontal ellipse),
# caustic (wavy 1 px lines, additive). color; alpha (lo, hi); radius (lo, hi) for blobs / size (w, h) for ellipses; n.
FOG_LAYERS = [
    [{"kind": "blob", "color": (4, 16, 8), "alpha": (40, 60), "radius": (40, 90), "n": 14}],            # 0 leaf-shadow dapple
    [{"kind": "blob", "color": (84, 100, 44), "alpha": (26, 40), "radius": (60, 120), "n": 10}],        # 1 marsh mist (darker: Visual Designer)
    [{"kind": "caustic", "color": (90, 150, 230), "alpha": (16, 24), "n": 30}],                         # 2 caustic light
    [{"kind": "blob", "color": (20, 8, 6), "alpha": (50, 70), "radius": (70, 130), "n": 10}],           # 3 smoke
    [{"kind": "blob", "color": (52, 88, 118), "alpha": (22, 34), "radius": (80, 140), "n": 5},         # 4 cold haze (dim) ...
     {"kind": "blob", "color": (6, 16, 28), "alpha": (44, 60), "radius": (90, 150), "n": 6}],           #   ... + shadow blobs
    [{"kind": "blob", "color": (96, 74, 44), "alpha": (24, 36), "radius": (80, 140), "n": 5},           # 5 dust haze (dim) ...
     {"kind": "blob", "color": (40, 28, 14), "alpha": (44, 60), "radius": (90, 150), "n": 5}],          #   ... + shadow blobs
    [{"kind": "blob", "color": (120, 70, 180), "alpha": (24, 38), "radius": (70, 120), "n": 10}],       # 6 spore fog (darker)
    [{"kind": "blob", "color": (0, 0, 0), "alpha": (60, 90), "radius": (90, 160), "n": 8},              # 7 dark fog ...
     {"kind": "blob", "color": (70, 50, 110), "alpha": (20, 20), "radius": (90, 160), "n": 4}],         #   ... + violet wisps
    [{"kind": "ellipse", "color": (150, 180, 255), "alpha": (16, 26), "size": (220, 40), "n": 12}],     # 8 cloud streaks
    [{"kind": "blob", "color": (180, 30, 120), "alpha": (24, 40), "radius": (80, 140), "n": 8},         # 9 blood haze ...
     {"kind": "blob", "color": (12, 2, 14), "alpha": (50, 50), "radius": (80, 140), "n": 4}],           #   ... + dark
]
FOG_HALO = 1.35                         # soft edge: a larger circle at a third of the alpha
# Screen-space light overlay: (tint, max alpha) per act; alpha = max * smoothstep(0.35, 1.0, d) from the screen centre
LIGHT_GRID = (16, 10)
LIGHT_START = 0.35
LIGHT_OVERLAYS = [
    ((2, 10, 6), 120), ((8, 12, 2), 130), ((2, 4, 18), 130), ((24, 4, 0), 120), ((6, 14, 26), 110),
    ((30, 18, 4), 110), ((14, 4, 26), 130), ((0, 0, 4), 170), ((2, 4, 16), 120), ((22, 0, 16), 140),
]
LOW_HP_RATIO = 0.30                     # below this share of max HP the overlay turns red
LOW_HP_OVERLAY = ((120, 10, 20), 150)   # tint, max alpha
LOW_HP_PULSE = (0.6, 1.0, 1.0)          # surface alpha factor low, high, Hz (<= 1 Hz: R5)
HEARTBEAT = (1.0, 1.15, 0.8)            # act 9: overlay max alpha scale low, high, Hz (baked at high, set_alpha 222..255)
# Pulses use Surface.set_alpha on the one cached overlay (R5: both <= 1 Hz); the red overlay is built once, on first use.

SAVE_FILE = "blob_evolution_save.json"
SAVE_BACKUP_SUFFIX = ".bak"  # unreadable saves are copied to SAVE_FILE + suffix before overwrite
SAVE_BACKUP_LIMIT = 10  # backup slots: .bak, .bak.1 ... .bak.9; existing backups are never overwritten
SAVE_TEMP_SUFFIX = ".tmp"  # saves are written to SAVE_FILE + suffix, then atomically renamed

# Enemy shapes (TASK-046): a silhouette per enemy type, light rim rings, LEECH recoloured bone-pale. Visual only.
GFX_ENEMY_SHAPES = True                 # Producer A/B switch: False restores the pre-046 creature drawing exactly
ENEMY_AIM_STEPS = 32                    # shooter barrel / charger horns aim steps (11.25 deg)
ENEMY_SHIELD_STEPS = 24                 # shielder plate aim steps
ENEMY_ORBIT_STEPS = 12                  # orbiter satellite steps per 120 deg
ENEMY_TENDRIL_PHASES = 8                # leech tendril frames per 0.7 Hz loop
ENEMY_SPRITE_CACHE_MAX = 1500           # baked extras are cached lazily; the cache is cleared when it reaches this size
ENEMY_PHASED_ALPHA = 110                # phased phantoms are drawn see-through
ENEMY_RIM_WIDTH = 2                     # light ring round every enemy body
ENEMY_BLAST_ALPHA = (38, 120)           # bomber blast disc fill / ring alpha (shown while fuse < 1 s)
ENEMY_LEECH_COLORS = ((205, 196, 176), (245, 240, 220))      # bone-pale; pre-046 green was (60, 160, 100) / (120, 230, 160)
ENEMY_PHANTOM_COLORS = ((150, 130, 200), (232, 222, 255))    # BUG-137 (Visual Designer): body grey 144 vs BASIC 108, core ~2.6:1 vs body; was (120, 100, 160) / (180, 160, 220)
ENEMY_WISP_RIM = (201, 193, 217)          # BUG-137: opaque 1 px rim on each phantom wisp (4.19:1 on every ground), also while phased

# Readability pass (TASK-043): contact shadows, outlined shots, XP orbs by value. Visual only.
GFX_READABILITY = True                  # Producer A/B switch: False restores the pre-043 drawing exactly
# Median orb value per act (180 s headless sims, real spawn / kill flow, acts 0..9); tier cut-offs are factors of it:
# cut-offs = factors x m: tier 1 below the first, tier 2 below the second, tier 3 below the third, tier 4 from there on
XP_TIER_MEDIAN = (29, 42, 39, 64, 61, 66, 70, 54, 94, 93)
XP_TIER_FACTORS_DEFAULT = (0.75, 1.4, 2.5)
XP_TIER_FACTORS_OVERRIDE = {7: (0.85, 1.1, 1.5)}      # act 7 orbs sit in a narrow band (34..68), so its cut-offs are closer to the median
XP_TIER_FACTORS = tuple(XP_TIER_FACTORS_OVERRIDE.get(a, XP_TIER_FACTORS_DEFAULT) for a in range(10))   # per act
DARK_SHOT_LUMINANCE = 0.25             # shots darker than this (WCAG relative luminance) get a light outline ring
SHOT_LIGHT_OUTLINE = (225, 220, 245)   # ring colour for dark shots: alpha 230 at R + 2, plus a 1 px ring at R + 3 (alpha 120)
XP_BLINK_SECONDS = 3.0                  # an orb blinks during the last seconds of its life
XP_BLINK_HZ = 0.9                       # at most 0.9 Hz (R5)
# XP tier look: body colour, core colour. Shape cue: 1 disc, 2 disc + ring, 3 diamond, 4 four-point star.
XP_TIER_STYLE = (
    {"body": (250, 204, 21), "core": (255, 245, 180)},
    {"body": (255, 240, 140), "core": (255, 255, 255)},
    {"body": (120, 225, 255), "core": (230, 250, 255)},
    {"body": (255, 130, 225), "core": (255, 230, 250)},
)
XP_DIAMOND_REACH = 1.45                 # tier 3 diamond half-diagonal in radii (spec 1.25, widened so the 4 tier areas differ >= 12 %)
XP_STAR_REACH = (1.45, 0.55)            # tier 4 star outer / inner radius in radii
XP_OUTLINE = (10, 10, 16)               # dark outline shared by orbs and shots
SHOT_DRAW_RADIUS = {"player": 5, "enemy": 6, "boss": 8}   # sprite size only; the hitbox stays 5 / 6 / 6
SHOT_HALO_ALPHA = 55
SHADOW_ALPHAS = (38, 90)                # outer soft ellipse, inner ellipse
SHADOW_MIN_RADIUS = 4

# Boss phases (TASK-055). The roster gives the thresholds (data/bosses.py); these are the numbers it leaves open.
BOSS_PHASE2_SPECIAL_COOLDOWN = 1.5      # special fires this soon after phase 2 starts (as on main)
BOSS_PHASE3_SPECIAL_COOLDOWN = 1.0      # same for phase 3 (main used it on layers 9-10 only; layers 4-8 get it too)
BOSS_VERDICT_ORDER = ("radial", "targeted", "cross")   # layer 9 verdicts cycle in this order

# Boss spawns and hit direction (TASK-056 framework; no boss uses them yet, so these change nothing today).
BOSS_SPAWN_QUEUE_MAX = 32               # pending spawn requests per game; more are dropped (push returns False)
BOSS_SPAWNS_DIE_WITH_OWNER = True       # pending and live boss spawns go when their boss dies
BOSS_SPAWN_EPS = 1e-9                   # BUG-152: a delay / lifetime within this of 0 counts as done (float dt sums)
BOSS_SPAWN_MAX_DT = 0.1                 # BUG-154: the director never steps more than this per frame (dt spikes)
BOSS_SPAWN_SEED = 5600                  # BUG-155: the director's own RNG (pool animation phase), reseeded per fight
BOSS_POOL_RADIUS = 70.0                 # timed pool default radius (px), when the request gives none
BOSS_POOL_LIFETIME = 6.0                # timed pool default lifetime (s)
BOSS_POOL_HAZARD = "toxic"              # timed pool default hazard type: "lava", "ice" or "toxic"

# Named mini-bosses (TASK-057). Which of a layer's two anchors a mini-boss node spawns.
BOSS_ANCHOR_PICK = "alternate"          # "alternate": a layer's mini nodes take turns (seeded start); or "random"

# Boss art (TASK-058 / A1, spec TASK-045): per-boss sprites, cached plate / pips / bar, no per-frame allocations.
GFX_BOSS_ART = True                     # Producer A/B switch: False restores the pre-058 Boss.draw exactly
BOSS_FLASH_MIN_GAP = 0.34               # s between hit-flash starts (spec rule 3: at most 3 Hz)
BOSS_FLASH_TIME = 0.2                   # s a hit flash shows (main's hit_flash length)
BOSS_PHASE_FADE = 0.6                   # s cross-fade of the old and new phase sprites (spec 2.2)
BOSS_PHASE_RING_TIME = 0.8              # s of the one-shot phase ring, R -> 3 R, alpha 170 -> 0 (spec 2.5)
BOSS_PHASE_RING_ALPHA = 170
BOSS_NAME_COLOUR = (230, 210, 180)      # phase 1 plate colour; later phases use the boss rim colour (module rule)
BOSS_BAR_NOTCH = (255, 255, 255)        # 2 px phase-threshold ticks on the boss health bar (spec 2.6)
BOSS_BAR_HEIGHT = 8
BOSS_PLATE_LIFT = 1.72                  # VD r2: bar top at sy - (1.72 R + 18), clear of the art (extents <= 1.7 R)
BOSS_PLATE_GAP = 4                      # px between bar and name, and name and pips
BOSS_PLATE_TOP_MIN = 6                  # the plate (pips or name) never starts above this screen y
BOSS_PLATE_TITLES = {9: "Warden of the Divide"}    # BOSS-ROSTER.md plate / card title where it differs from lore
