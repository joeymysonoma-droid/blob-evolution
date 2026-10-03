"""Repo-wide pytest setup (TASK-026).

The suite must not depend on the recorded music files, and decoding 11 mp3s would only slow it down. So
every test starts with MUSIC_DIR pointing at a folder that does not exist: the game then uses the generated
themes, exactly as it does when the mp3s are missing. Tests that want the real files (tests/test_music_files.py)
or a folder of their own point audio.MUSIC_DIR somewhere else with monkeypatch.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_music_files(monkeypatch, tmp_path_factory):
    from blob_evolution.systems import audio

    monkeypatch.setattr(audio, "MUSIC_DIR", tmp_path_factory.getbasetemp() / "no-music-files-here")
