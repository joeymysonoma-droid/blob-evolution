# Blob Evolution

A top-down roguelike where you control a blob that grows by absorbing smaller creatures, gains XP, levels up, unlocks skills, and defeats bosses across 10 themed maps.

## Requirements

- Python 3.10+
- pygame-ce 2.5+ (installed by `requirements.txt`)

## Install & Run

Create and activate a virtual environment first. Some systems manage their Python installation externally and refuse a bare `pip install`.

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m blob_evolution.main
```

## Development

With the virtual environment from Install & Run activated, install the runtime and test dependencies (pytest), then run the tests from the repo root:

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

To run the game or tests without a display or sound device (CI, servers), set SDL's dummy drivers:

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy pytest
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy timeout 10 python -m blob_evolution.main
```

The game runs until it is closed or killed, so a headless run needs a time limit such as `timeout 10`. Exit code 124 means it was still running when the timeout stopped it, which counts as a clean boot.

## Controls

| Key | Action |
|-----|--------|
| WASD / Arrows | Move |
| Left Click | Shoot at cursor |
| Right Click | Dash |
| TAB | Skills menu |
| 1-9 | Quick skill upgrade |
| P / ESC | Pause |
| M | Toggle minimap |
| F3 | Toggle FPS |

## Features

- **Story cinematics** — Pilgrimage opening, layer descents, and Warden confrontations
- **Procedural audio** — SFX for combat/UI plus soft per-layer ambient pads (toggle in Options)
- **9 enemy archetypes** — Driftlings, shooters, splitters, chargers, shielders, orbiters, bombers, phantoms, leeches
- **A Warden for every layer** — Each has distinct movement and attack patterns with multi-phase fights
- **Branching overworld map** — Choose your path after each encounter: fights, elites, rest, shops, events, blacksmith, mini-bosses
- **Shards** — Permanent currency for meta upgrades and blob skins (main menu → Upgrades)
- **9 upgradeable skills** (Speed, Size, Damage, Health, Regen, Projectile, Armor, Magnetism, Lifesteal)
- **20+ artifacts** with rarity tiers and blacksmith upgrades
- **Random events** with boons and curses
- **10 themed layers of the Lattice** with procedural backgrounds and dream journals at rest sites
- **Environmental hazards**: Lava, ice, toxic
- **New Game Plus** with permanent bonuses
- **Save system** for shards, skins, and NG+ progress
- **4 difficulty levels**: Easy, Normal, Hard, Extreme
- **Archive** — Cosmology, Warden memories, artifact lineages, and endings
