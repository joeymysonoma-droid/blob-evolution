"""Shared pytest setup for Blob Evolution.

Headless: SDL dummy drivers are set here, before any test module imports pygame.
Isolation: every test runs with cwd = tmp_path and config.SAVE_FILE pointing into
tmp_path, so the suite never reads or writes a save in the repo root or real cwd.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
FIXTURE_SAVE = TESTS_DIR / "fixtures" / "save_sample.json"


@pytest.fixture(scope="session", autouse=True)
def _session_audio():
    """The shared AudioManager is built once, before any test patches the sound library or folders (it takes ~0.4 s)."""
    from blob_evolution.systems import audio

    audio.get_audio()
    yield


@pytest.fixture(autouse=True)
def shared_audio_state(_session_audio):
    """TASK-062: every Game shares one AudioManager (systems/audio.get_audio). Give each test the manager as the previous
    test found it: its fields (volumes, enabled, the never-retried failed-key sets, loaded clips, the current narration)
    are put back after the test, and a manager first created inside a test (possibly under a patched library or
    NARRATION_DIR) is dropped. Sounds still playing are stopped. Defined first so it tears down last, after monkeypatch.
    """
    import pygame
    from blob_evolution.systems import audio

    before = audio._audio
    saved = None
    if before is not None:
        saved = {k: (v.copy() if isinstance(v, (dict, list, set)) else v) for k, v in vars(before).items()}
    yield
    if pygame.mixer.get_init():
        pygame.mixer.stop()
    if before is None:
        audio._audio = None
    else:
        audio._audio = before
        vars(before).clear()
        vars(before).update(saved)


@pytest.fixture(autouse=True)
def shared_shot_sprites():
    """Restore the module-level shot-sprite cache after every test.

    It is capped (projectile.SPRITE_CACHE_MAX) and refuses inserts once full, so a test that floods it with colours
    (the cap test) made later "no allocation after warm-up" tests allocate on every draw (shuf3 order). The sprites
    themselves are kept, so this is a dict copy, not a rebuild.
    """
    from blob_evolution.entities import projectile
    saved = dict(projectile._SPRITES)
    yield
    projectile._SPRITES.clear()
    projectile._SPRITES.update(saved)


@pytest.fixture(autouse=True)
def isolated_save(tmp_path, monkeypatch):
    """Run each test in tmp_path with the save file redirected there.

    Returns the absolute Path the game will use as its save file.
    """
    from blob_evolution import config

    monkeypatch.chdir(tmp_path)
    save_path = tmp_path / "blob_evolution_save.json"
    monkeypatch.setattr(config, "SAVE_FILE", str(save_path))
    return save_path


@pytest.fixture
def fixture_bytes() -> bytes:
    """Raw bytes of tests/fixtures/save_sample.json (read-only)."""
    return FIXTURE_SAVE.read_bytes()


@pytest.fixture
def fixture_data(fixture_bytes) -> dict:
    """Parsed contents of tests/fixtures/save_sample.json."""
    return json.loads(fixture_bytes)


@pytest.fixture
def make_game():
    """Factory that builds a real Game() (which calls Game._load_save at startup)."""
    from blob_evolution.game import Game

    def _make():
        return Game()

    return _make
