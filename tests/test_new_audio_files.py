"""TASK-035: the 11 new sound-effect WAVs, the longer limit for the long cues, and the first 3 narration clips.

The shipped-file tests read blob_evolution/assets directly (the root conftest points SFX_DIR / NARRATION_DIR at
missing folders for every test, so each test that wants the real folder patches the module path itself).
The loader and fallback tests use generated WAVs in tmp_path and need no shipped file.
"""
from __future__ import annotations

import array
import hashlib
import math
import wave
from pathlib import Path
from typing import Dict, Tuple

import pygame
import pytest

from blob_evolution.systems import audio
from blob_evolution.systems.audio import AudioManager

ASSETS = Path(audio.__file__).resolve().parent.parent / "assets"
SFX_REAL = ASSETS / "sfx"
NARR_REAL = ASSETS / "narration"

# name -> (sha256, length in s, peak cap in dBFS); lengths are the untrimmed lengths of the source cues
NEW_SFX: Dict[str, Tuple[str, float, float]] = {
    "artifact": ("0498cf92c8b0b7a626d21bccdb7cfedea1a72fd5caf64e83a8c4f18582642214", 1.2, -8.0),
    "boss_phase": ("7ea218ec81ad2a63639f7ebcb0f96863f7a122e886bc9d6b9c6788e9200433ac", 2.0, -1.0),
    "boss_spawn": ("d8f2ba9d05e86c43cced82ab684067932515c99524201ccf3f8e2768b8fcd4eb", 3.0, -4.0),
    "boss_warning": ("b35e119c12fccabfb578b39373dc4fccd014956c3f7598bcdca2f1268265d965", 1.5, -1.0),
    "defeat": ("dbc754ad68016eef5ccd05dfb871742dc98aa6df334c23f36f30ec38ed38bb3d", 4.0, -9.0),
    "heal": ("b77ef8036ec0c7c58fe06fd7c44d3c8debc992d53f8e9b7df248465230de0a47", 0.6, -18.5),   # +15 dB (TASK-035 r2)
    "levelup": ("68a43c53eecca0d00f34261fd8edff3d7e7377dcb001a9fc4448a64c377bc2d3", 1.2, -5.0),
    "merge": ("8e6f0e76838e7d45c55875541e125649e2e0aebe308687a826430583b56847b4", 3.0, -7.0),
    "shield_block": ("7de95c5c3979c21779208170242421d24eabb6565676603e7a90b19010420200", 0.3, -11.0),
    "ui_back": ("ad4bc38f667889216ccb69e204f92394a34779b08fe7378febb33e153950e84a", 0.2, -19.0),
    "victory": ("cb1abce45237281c004bcc2fdb1f25b226aca279f4295aff5eed8266782584f9", 4.0, -1.0),
}
LONG = {"boss_warning", "boss_phase", "boss_spawn", "merge", "victory", "defeat"}
NARRATION = {
    "intro_card1": ("f48c515df99d56839c72d0a129be8c805add89af24bcea225623c63fc53a21c4", 20.0),
    "intro_card2": ("bccc9e161176b9f32d1f7fbcc7c7950f6405d0d4e4b7c55a438438544571268b", 14.7),
    "layer01_descent": ("9b2ebe865cb71dacf8671b82d24a9036c913139988a5a1808503053bcf84fe8a", 14.0),
}


@pytest.fixture(scope="module", autouse=True)
def mixer():
    """The game's mixer format: 22050 Hz, 16-bit, mono."""
    if not pygame.mixer.get_init():
        pygame.mixer.pre_init(audio.SAMPLE_RATE, -16, 1, 512)
        pygame.mixer.init()
    pygame.mixer.set_num_channels(audio.TOTAL_CHANNELS)
    yield


@pytest.fixture
def cheap_library(monkeypatch):
    """Generated library with trivial sounds (the real one takes ~0.5 s to render)."""
    monkeypatch.setattr(audio, "_build_sfx", lambda: {n: pygame.mixer.Sound(buffer=bytes(2 * 4410)) for n in audio.SFX_BUILDERS})
    monkeypatch.setattr(audio, "_build_menu_theme", lambda: pygame.mixer.Sound(buffer=bytes(2 * 2205)))
    yield
    pygame.mixer.stop()


def _write_wav(path: Path, seconds: float, amp: int = 6000) -> None:
    n = int(seconds * 22050)
    data = array.array("h", (int(amp * math.sin(2 * math.pi * 500 * i / 22050)) for i in range(n)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(data.tobytes())


def _samples(snd: pygame.mixer.Sound) -> array.array:
    a = array.array("h")
    a.frombytes(snd.get_raw())
    return a


def _need(path: Path) -> Path:
    if not path.is_file():
        pytest.skip(f"{path} is not present")
    return path


# --- the shipped sfx files ----------------------------------------------------------------------------

def test_all_22_file_backed_names_have_a_shipped_wav_and_only_hurt_is_generated_only() -> None:
    assert len(audio.SFX_FILES) == 22 and set(NEW_SFX) <= set(audio.SFX_FILES)
    assert set(audio.SFX_BUILDERS) - set(audio.SFX_FILES) == {"hurt"}
    for n in audio.SFX_FILES:
        assert (SFX_REAL / f"{n}.wav").is_file(), n


@pytest.mark.parametrize("name", sorted(NEW_SFX))
def test_new_wav_matches_its_pinned_hash_format_length_peak_and_edges(name, cheap_library) -> None:
    digest, seconds, cap_db = NEW_SFX[name]
    path = _need(SFX_REAL / f"{name}.wav")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    with wave.open(str(path)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (22050, 1, 2)
    loaded = audio._load_sfx_files([name], SFX_REAL)
    assert name in loaded, "the loader accepts it (length limit included)"
    snd = loaded[name]
    assert snd.get_length() == pytest.approx(seconds, abs=0.01)
    a = _samples(snd)
    peak_db = 20 * math.log10(max(abs(v) for v in a) / 32768.0)
    assert peak_db <= cap_db + 0.5, peak_db
    assert peak_db <= -1.0, "never above -1 dBFS"
    assert max(abs(a[0]), abs(a[-1])) <= 0.01 * 32768, "no edge click"


def test_every_new_file_that_is_longer_than_the_default_limit_is_a_named_long_cue() -> None:
    for name, (_, seconds, _) in NEW_SFX.items():
        assert (seconds >= audio.SFX_MAX_S) == (name in LONG), name


def test_total_added_size_is_reasonable() -> None:
    wav = sum(_need(SFX_REAL / f"{n}.wav").stat().st_size for n in NEW_SFX)
    ogg = sum(_need(NARR_REAL / f"{n}.ogg").stat().st_size for n in NARRATION)
    assert wav < 1_000_000 and ogg < 400_000


# --- the longer limit applies only to the named cues -----------------------------------------------------------

def test_long_limit_table_is_exactly_the_named_cues() -> None:
    assert set(audio.SFX_MAX_S_LONG) == LONG
    assert (audio.SFX_MIN_S, audio.SFX_MAX_S) == (0.04, 1.5), "default limit unchanged"
    assert all(v > audio.SFX_MAX_S for v in audio.SFX_MAX_S_LONG.values())


@pytest.mark.parametrize("name,seconds,ok", [
    ("victory", 4.0, True), ("defeat", 4.0, True), ("boss_spawn", 3.0, True), ("merge", 3.0, True),
    ("boss_phase", 2.0, True), ("boss_warning", 1.5, True),
    ("victory", 5.0, False), ("boss_spawn", 3.6, False), ("boss_warning", 2.2, False),     # still bounded
    ("hit", 2.0, False), ("levelup", 1.6, False), ("heal", 3.0, False), ("artifact", 1.6, False),
    ("shoot", 4.0, False), ("ui_back", 1.51, False),                                          # default limit stays
    ("hit", 1.4, True), ("levelup", 1.4, True),
])
def test_length_limit_depends_on_the_name(tmp_path, name, seconds, ok) -> None:
    _write_wav(tmp_path / f"{name}.wav", seconds)
    failed = []
    loaded = audio._load_sfx_files([name], tmp_path, failed)
    assert (name in loaded) is ok and (failed == []) is ok


def test_too_short_is_still_rejected_for_long_cues(tmp_path) -> None:
    _write_wav(tmp_path / "victory.wav", 0.02)
    failed = []
    assert audio._load_sfx_files(["victory"], tmp_path, failed) == {} and failed == ["victory"]


# --- fallback and playing --------------------------------------------------------------------------------

def test_missing_new_file_falls_back_to_the_generated_sound_for_that_name_only(cheap_library, tmp_path, monkeypatch, capsys) -> None:
    for n in audio.SFX_FILES:
        if n != "victory":
            _write_wav(tmp_path / f"{n}.wav", 0.3)
    monkeypatch.setattr(audio, "SFX_DIR", tmp_path)
    capsys.readouterr()
    mgr = AudioManager()
    assert mgr._sfx_failed == ["victory"]
    assert mgr.sfx_source("victory") == "generated" and mgr.sfx_source("defeat") == "file"
    assert mgr.sfx_source("hurt") == "generated"
    mgr.play("victory")
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_real_long_cues_play_on_sfx_channels_and_overlap_without_errors(cheap_library, monkeypatch) -> None:
    _need(SFX_REAL / "victory.wav")
    monkeypatch.setattr(audio, "SFX_DIR", SFX_REAL)
    mgr = AudioManager()
    assert mgr._sfx_failed == []
    for n in sorted(LONG):
        assert mgr.sfx_source(n) == "file"
        mgr.play(n)
    assert mgr._sfx["victory"].get_num_channels() == 1
    mgr.play("victory")                                  # ungated: a second copy may start
    assert mgr._sfx["victory"].get_num_channels() == 2
    assert not any(pygame.mixer.Channel(i).get_busy() for i in range(audio.MUSIC_CHANNELS))
    assert "victory" not in audio.SFX_GATES and "boss_spawn" not in audio.SFX_GATES
    pygame.mixer.stop()


# --- the game still calls every one of the 11 cues ------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(NEW_SFX))
def test_game_py_has_a_play_call_for_each_new_cue(name) -> None:
    src = (Path(audio.__file__).resolve().parent.parent / "game.py").read_text(encoding="utf-8")
    assert f'self.audio.play("{name}"' in src or (name == "victory" and '"victory"' in src), name


# --- narration clips --------------------------------------------------------------------------------------------

def test_narration_folder_has_exactly_the_three_clips() -> None:
    assert sorted(p.name for p in _need(NARR_REAL / "intro_card1.ogg").parent.iterdir()) == sorted(f"{k}.ogg" for k in NARRATION)
    assert set(NARRATION) == set(audio.OPENING_CLIPS)


@pytest.mark.parametrize("key", sorted(NARRATION))
def test_narration_clip_loads_with_the_game_loader(key, monkeypatch) -> None:
    digest, seconds = NARRATION[key]
    path = _need(NARR_REAL / f"{key}.ogg")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    snd = audio._load_narration(key, NARR_REAL)
    assert snd is not None and snd.get_length() == pytest.approx(seconds, abs=0.1)


def test_other_narration_keys_stay_silent_and_the_three_play(cheap_library, monkeypatch, capsys) -> None:
    _need(NARR_REAL / "intro_card1.ogg")
    monkeypatch.setattr(audio, "NARRATION_DIR", NARR_REAL)
    mgr = AudioManager()
    capsys.readouterr()
    for key in audio.all_narration_keys():
        mgr.play_narration(key)
        if key in NARRATION:
            assert mgr.narration_playing() == key, key
        else:
            assert mgr.narration_playing() is None, key
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
    mgr.stop_narration()
    pygame.mixer.stop()


def test_missing_narration_folder_is_silent(cheap_library, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(audio, "NARRATION_DIR", tmp_path / "nope")
    mgr = AudioManager()
    capsys.readouterr()
    mgr.play_narration("intro_card1")
    assert mgr.narration_playing() is None
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_opening_cards_trigger_the_three_clips_in_the_game(make_game, monkeypatch) -> None:
    """Game._start_new_run -> _start_story -> play_narration(OPENING_CLIPS[0]); each advance plays the next."""
    _need(NARR_REAL / "intro_card1.ogg")
    monkeypatch.setattr(audio, "NARRATION_DIR", NARR_REAL)
    g = make_game()
    played = []
    real = g.audio.play_narration
    monkeypatch.setattr(g.audio, "play_narration", lambda k: (played.append(k), real(k))[1])
    g._start_new_run()
    assert played == ["intro_card1"] and g.audio.narration_playing() == "intro_card1"
    g._advance_story()
    g._advance_story()
    assert played == ["intro_card1", "intro_card2", "layer01_descent"]
    g._advance_story()
    assert g.audio.narration_playing() is None, "the last card ends the sequence and cuts the clip"
    g.audio.stop_narration()
    pygame.mixer.stop()
