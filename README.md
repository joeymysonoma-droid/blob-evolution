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
- **Sound** — Generated SFX (combat, UI, bosses, artifacts) with eleven recorded sound effects, eleven recorded music tracks (one for the menu and one per layer) and optional narration (mute in Options → Sound)
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

## Audio

- **Most SFX are generated at runtime** (pure Python). Eleven are recorded: the WAV files in `blob_evolution/assets/sfx/` (about 128 KB; shoot, hit, kill, explode, pickup, absorb, boss hit, dash, story and two UI sounds) replace the generated sound of the same name. **Music is recorded**: the 11 mp3 files in `blob_evolution/assets/music/` (about 13 MB). Together with the narration clips (once added) these are the only audio files in the game. They are loaded from the folder next to the package, so the working directory does not matter.
- If a music or SFX file is missing or will not load, the generated theme or sound is used instead, so the game always has sound. Rapid repeats of hit, pickup, kill, absorb, boss hit, hurt and the options-menu select sound are rate-limited so they cannot use up all the mixer channels. If no audio device is available the game runs silent.
- **Narration (optional, no files included):** if narration clips are present, they play on their own channel while a story card is up: the three opening cards, each layer's descent card, the Warden Encounter card (with the NG+ line variants) and the Lattice Anchor (mini-boss) card. Put `.wav` (or `.ogg`) files named by clip key in `blob_evolution/assets/narration/`, e.g. `intro_card1.wav`, `layer02_descent.wav`, `layer02_warden.wav`, `layer02_warden_ng2.wav`, `layer02_miniboss.wav` (the full list is `audio.all_narration_keys()`). Any clip that is missing or will not load is simply silent. Advancing a card fades its clip out in 80 ms and starts the next card's clip; the music already sits back under story cards. Sound OFF mutes narration too. Options → **Narration** (Left/Right or A/D) sets its level in 10% steps (OFF at 0; default 80%) and is saved as `narration_volume` (see **Volume** below).
- **Volume:** there is no music or SFX volume slider, and music and SFX levels are not saved (they are fixed in code: music 0.32, SFX 0.55). Only two audio keys are stored, at the top level of the save file (`blob_evolution_save.json`):
  - `audio_enabled` (true/false): the Options → **Sound** switch (Left/Right or A/D), which turns all sound, music, SFX and narration, ON or OFF. It is written on every save and read back on load if present.
  - `narration_volume` (number): the Options → **Narration** level. It is clamped to 0.0–1.0 and rounded to two decimals (10% steps in Options, 0 = OFF, default 0.8). It is written only if the save already contained the key or the level differs from the 0.8 default; a missing key loads as 0.8, and a non-numeric value falls back to 0.8 and flags the save as partly invalid.
- **Narration clip files:** each clip ID maps to `<ID>.wav`, else `<ID>.ogg` (checked in that order), inside `blob_evolution/assets/narration/`. A file is used only if it is between 0.05 s and 120 s long. There are 53 clip IDs (`NN` = layer `01`–`10`; the third opening card is `layer01_descent`):

  | Clip ID | Expected filename (`.wav` or `.ogg`) | Count |
  |---------|--------------------------------------|-------|
  | `intro_card1`, `intro_card2` | `intro_card1.wav`, `intro_card2.wav` | 2 |
  | `layerNN_descent` | `layer01_descent.wav` … `layer10_descent.wav` | 10 |
  | `layerNN_warden` | `layer01_warden.wav` … `layer10_warden.wav` | 10 |
  | `layerNN_warden_ng2` | `layer01_warden_ng2.wav` … `layer10_warden_ng2.wav` | 10 |
  | `layerNN_warden_ng5` | `layer01_warden_ng5.wav` … `layer10_warden_ng5.wav` | 10 |
  | `layer10_warden_ng10` | `layer10_warden_ng10.wav` | 1 |
  | `layerNN_miniboss` | `layer01_miniboss.wav` … `layer10_miniboss.wav` | 10 |

- **Credits:** the music, sound effects and narration (once added) were made with Wondercraft (wondercraft.ai) on a paid plan, for commercial use.
