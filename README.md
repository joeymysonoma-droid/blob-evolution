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
- **Sound** — 22 recorded sound effects (combat, UI, bosses, artifacts; only the hurt sound is generated), eleven recorded music tracks (one for the menu and one per layer) and narration for the opening cards (3 clips so far; mute in Options → Sound)
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

- **SFX are recorded; only `hurt` is generated at runtime** (pure Python, which is also the fallback for every other sound). 22 are recorded: the WAV files in `blob_evolution/assets/sfx/` (about 1 MB; the combat, UI and story sounds plus the boss, level-up, heal, artifact, merge, victory and defeat cues; a few of them run 2–4 s) replace the generated sound of the same name. **Music is recorded**: the 11 mp3 files in `blob_evolution/assets/music/` (about 13 MB). Together with the narration clips (3 so far) these are the only audio files in the game. They are loaded from the folder next to the package, so the working directory does not matter.
- If a music or SFX file is missing or will not load, the generated theme or sound is used instead, so the game always has sound. Rapid repeats of hit, pickup, kill, absorb, boss hit, hurt and the options-menu select sound are rate-limited so they cannot use up all the mixer channels. If no audio device is available the game runs silent.
- **Narration (3 of 53 clips included: `intro_card1`, `intro_card2`, `layer01_descent`, as `.ogg`; the rest stay silent until added):** if narration clips are present, they play on their own channel while a story card is up: the three opening cards, each layer's descent card, the Warden Encounter card (with the NG+ line variants) and the Lattice Anchor (mini-boss) card. Put `.wav` (or `.ogg`) files named by clip key in `blob_evolution/assets/narration/`, e.g. `intro_card1.wav`, `layer02_descent.wav`, `layer02_warden.wav`, `layer02_warden_ng2.wav`, `layer02_miniboss.wav` (the full list is `audio.all_narration_keys()`). Any clip that is missing or will not load is simply silent. Advancing a card fades its clip out in 80 ms and starts the next card's clip; the music already sits back under story cards. Sound OFF mutes narration too. Options → **Narration** (Left/Right or A/D) sets its level in 10% steps (OFF at 0; default 80%) and is saved as `narration_volume` (only written once it differs from the default).
- **Volume:** there is no music or SFX volume slider. Open Options from the main menu, select **Sound** and press Left/Right (or A/D) to switch all sound, music and SFX, ON or OFF. The choice is saved.
- **Credits:** the music, sound effects and narration (first three clips) were made with Wondercraft (wondercraft.ai) on a paid plan, for commercial use.
