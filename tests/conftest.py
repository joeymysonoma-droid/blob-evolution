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
