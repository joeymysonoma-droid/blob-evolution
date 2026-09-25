# Blob Evolution

A top-down roguelike where you control a blob that grows by absorbing smaller creatures, gains XP, levels up, unlocks skills, and defeats bosses across 10 themed maps.

## Requirements

- Python 3.10+
- pygame 2.5+

## Install & Run

```bash
pip install -r requirements.txt
python -m blob_evolution.main
```

## Controls

| Key | Action |
|-----|--------|
| WASD / Arrows | Move |
| Left Click | Shoot at cursor |
| Right Click | Dash |
| TAB | Skills menu |
| 1-6 | Quick skill upgrade |
| P / ESC | Pause |
| M | Toggle minimap |
| F3 | Toggle FPS |

## Features

- **Story cinematics** — Pilgrimage opening, layer descents, and Warden confrontations
- **Procedural audio** — SFX for combat/UI plus soft per-act ambient pads (toggle in Options)
- **9 enemy archetypes** — Driftlings, shooters, splitters, chargers, shielders, orbiters, bombers, phantoms, leeches
- **Act-unique bosses** — Each Warden has distinct movement and attack patterns with multi-phase fights
- **Branching overworld map** — Choose your path after each encounter: fights, elites, rest, shops, events, blacksmith, mini-bosses
- **Shards** — Permanent currency for meta upgrades and blob skins (main menu → Upgrades)
- **6 upgradeable skills** (Speed, Size, Damage, Health, Regen, Projectile)
- **20+ artifacts** with rarity tiers and blacksmith upgrades
- **Random events** with boons and curses
- **10 themed acts** with procedural backgrounds and dream journals at rest sites
- **Environmental hazards**: Lava, ice, toxic
- **New Game Plus** with permanent bonuses
- **Save system** for shards, skins, and NG+ progress
- **4 difficulty levels**: Easy, Normal, Hard, Extreme
- **Archive** — Cosmology, Warden memories, artifact lineages, and endings
