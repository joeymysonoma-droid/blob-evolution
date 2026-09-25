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

# Map themes: name, base_color, accent, creatures, bosses, hazards
# Names align with data.lore.ACT_LORE lore_name fields.
MAP_THEMES = [
    {"name": "The Verdant Rim", "color": (28, 72, 42), "accent": (58, 150, 75), "creatures": 25, "bosses": 1, "hazards": []},
    {"name": "The Sinking Garden", "color": (38, 62, 30), "accent": (90, 140, 45), "creatures": 30, "bosses": 1, "hazards": ["toxic"]},
    {"name": "The Memory Vaults", "color": (24, 42, 78), "accent": (90, 160, 220), "creatures": 25, "bosses": 2, "hazards": []},
    {"name": "The Forge Veins", "color": (58, 22, 14), "accent": (220, 90, 35), "creatures": 35, "bosses": 2, "hazards": ["lava"]},
    {"name": "The Still Expanse", "color": (170, 195, 220), "accent": (130, 190, 235), "creatures": 20, "bosses": 1, "hazards": ["ice"]},
    {"name": "The Mirage Basin", "color": (170, 140, 70), "accent": (230, 190, 100), "creatures": 30, "bosses": 2, "hazards": []},
    {"name": "The Dreaming Thicket", "color": (52, 24, 82), "accent": (150, 90, 210), "creatures": 40, "bosses": 3, "hazards": ["toxic"]},
    {"name": "The Hollow Undermembrane", "color": (16, 14, 26), "accent": (70, 55, 95), "creatures": 45, "bosses": 3, "hazards": []},
    {"name": "The Ascending Strata", "color": (18, 28, 58), "accent": (190, 210, 255), "creatures": 50, "bosses": 4, "hazards": []},
    {"name": "The First Divide", "color": (42, 16, 48), "accent": (220, 55, 160), "creatures": 60, "bosses": 5, "hazards": ["lava", "toxic", "ice"]},
]

SAVE_FILE = "blob_evolution_save.json"
SAVE_BACKUP_SUFFIX = ".bak"  # unreadable saves are copied to SAVE_FILE + suffix before overwrite
SAVE_BACKUP_LIMIT = 10  # backup slots: .bak, .bak.1 ... .bak.9; existing backups are never overwritten
SAVE_TEMP_SUFFIX = ".tmp"  # saves are written to SAVE_FILE + suffix, then atomically renamed
