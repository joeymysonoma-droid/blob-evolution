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

# Colors
VOID_COLOR_SCALE = 0.5          # ground edge fill (outside the world) = the act's DARK ground tone x this
COLOR_BG = (15, 23, 42)          # slate-900
COLOR_PLAYER = (34, 197, 94)   # green-500
COLOR_PLAYER_CORE = (74, 222, 128)
COLOR_XP = (250, 204, 21)      # yellow
COLOR_PROJECTILE_PLAYER = (34, 197, 94)
COLOR_PROJECTILE_ENEMY = (249, 115, 22)
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
GROUND_NOISE_OCTAVES = ((9, 0.0, 1.0, None), (22, 0.15, 0.85, 110), (60, 0.30, 0.70, 70))
GROUND_GRIT_COUNT = (1000, 1600)    # single-pixel grit specks per bake (min, max)
GROUND_GRIT_SPREAD = 14             # grit = MID +/- this per channel (never darker than 0.6 x DARK)
GROUND_CLUSTER_COUNT = (7, 10)      # decal cluster centres per act (plus one at the world centre)
GROUND_CLUSTER_MARGIN = 250         # cluster centres stay this far from the world edge
GROUND_CLUSTER_SIGMA = (110, 170)   # gaussian spread of a cluster (min, max)
GROUND_CLUSTER_SHARE = 0.7          # share of scattered decals that sit in clusters (rest uniform)
MAX_STAMPS_PER_ACT = 500            # decal budget per bake (checked via scatter.total)

SAVE_FILE = "blob_evolution_save.json"
SAVE_BACKUP_SUFFIX = ".bak"  # unreadable saves are copied to SAVE_FILE + suffix before overwrite
SAVE_BACKUP_LIMIT = 10  # backup slots: .bak, .bak.1 ... .bak.9; existing backups are never overwritten
SAVE_TEMP_SUFFIX = ".tmp"  # saves are written to SAVE_FILE + suffix, then atomically renamed
