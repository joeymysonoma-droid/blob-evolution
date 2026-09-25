# Blob Evolution — Bot Team Brief

Source of truth for every Grok Bot working on this project. Read this before starting any task.
If this file and your memory disagree, this file wins.

## Project

- **Game:** Blob Evolution, a top-down roguelike. Tagline: *"Eat. Adapt. Remember."*
- **Premise:** The player is a Seedling blob climbing 10 layers of the Lattice, fighting Wardens.
- **Stack:** Python 3.10+, `pygame-ce` (see `requirements.txt`). No other dependencies.
- **Run:** `pip install -r requirements.txt` then `python -m blob_evolution.main`
- **Headless checks:** set `SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy`.
- **Workspace path:** `/workspace/IAMBLOB`

## Everything is procedural

There are no image or audio asset files, and the game has no loader for them.

- **Graphics:** drawn with `pygame.draw` in `blob_evolution/utils/graphics.py`.
- **Palettes:** `blob_evolution/ui/style.py` (UI) and `blob_evolution/config.py` (`MAP_THEMES`, entity colors).
- **Audio:** synthesized in `blob_evolution/systems/audio.py` — sine/square/triangle/saw/noise, 22050 Hz mono.
  SFX use `_tone()` / `_chord()`; music uses `_sequence()` with note constants `C3`–`A5` and beat helpers `B`, `Q`, `H`, `W`.

## Layout

| Path | Contents |
|------|----------|
| `blob_evolution/game.py` | Main loop and most game logic (~1,700 lines — high risk, keep changes minimal) |
| `blob_evolution/config.py` | Constants, difficulty settings, map themes, entity limits |
| `blob_evolution/entities/` | player, creature, boss, projectile, pickups, particle |
| `blob_evolution/systems/` | audio, skills, artifacts, economy, events, hazards, overworld, evolution, permanent, newgameplus |
| `blob_evolution/ui/` | hud, menus, cinematic, overworld_map, style |
| `blob_evolution/maps/generator.py` | Procedural map generation |
| `blob_evolution/data/lore.py` | All story text and names — the lore source of truth |

## Hard limits

- Performance caps in `config.py`: 1,200 particles, 50 creatures, 5 bosses, 200 projectiles, 60 FPS.
- The save file (`blob_evolution_save.json`) format must stay backward compatible, or ship with a migration.
- Known lore drift: act names in `systems/audio.py` comments (Rot, Echoes, Ash...) don't match `config.py` / `lore.py`.

## Team

| Bot | Owns |
|-----|------|
| Producer | Task breakdown, assignment, status board. The only bot that assigns work. |
| Lead Dev | All code changes. |
| QA | Testing, bug reports, pytest tests, balance numbers. Never fixes bugs. |
| Visual Designer | Palettes, shapes, UI layout, particles — delivered as RGB values and draw specs. |
| Audio Designer | SFX and music — delivered as `_tone` / `_chord` / `_sequence` code. |
| Narrative | Names, lore text, tone, and consistency. |

The human is the **Director** and has final say.

## Group chat rules

1. Act only when @mentioned or assigned a task by the Producer.
2. Stay in your lane; @mention the owning bot instead of doing its work.
3. Start every reply with: `[ROLE] Task: <one line> | Status: proposal / done / blocked / question`
4. Keep replies under ~300 words unless delivering code or specs.
5. Read current files from the workspace before proposing changes. Never guess file contents.
6. One owner per stage. Code flows Dev → QA. Design flows Designer → Dev → QA.
7. Images can't be passed through the group; send them directly to the bot that needs them.
8. Disagree once, clearly, then follow the Director's decision.

## Formats

- **Task:** `TASK-### | owner | goal | files | done when`
- **Bug:** `BUG-### | severity (blocker/major/minor) | repro steps | expected | actual | suspected file`

## Git rules

- One feature branch per task, named `task-###-short-name`.
- Never push to `main`, force-push, delete files, or add dependencies without Director approval.
- Small commits with clear messages. Dev ends each delivery with a "What QA should test" list.
