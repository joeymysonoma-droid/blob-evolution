"""TASK-026: recorded music (11 mp3s) with the generated themes as fallback.

Most tests here use a synthetic wav in a tmp folder, so they pass whether or not the mp3s are present
(the root conftest points MUSIC_DIR at a missing folder for every test). The tests that need the real files
are marked by the `real_files` fixture and are skipped when the files are absent.
"""
from __future__ import annotations

import array
import hashlib
import math
import time
import wave
from pathlib import Path
from typing import Callable, Dict, List

import pygame
import pytest

from blob_evolution.systems import audio
from blob_evolution.systems.audio import AudioManager, FileTrack, TRACK_FILES, _loop_from_sound

REAL_DIR = Path(audio.__file__).resolve().parent.parent / "assets" / "music"
KEYS = ["menu"] + [f"act_{i}" for i in range(10)]
EXPECTED_FILES = {
    "menu": ("01-Menu.mp3", "2ab37eb1fb77578fac45416d6cb38d8d8aca418eb14df8a12cf1d21a60c62f79"),
    "act_0": ("02-MossyGlade.mp3", "2da30231defca81faa42f4e51a3addcfbcd2d3b485f241685db78014761e8e66"),
    "act_1": ("03-BogBloom.mp3", "032c46174a3c55f6f51971f5d5ad32bbba0b2fe70a6ec3ed36c7e4004d21cfd6"),
    "act_2": ("04-EchoesintheGlass.mp3", "3ea0987ca535ac75f7cfb247267090922118b2be3a7c9f81d4f5b7f3f9681e5d"),
    "act_3": ("05-IronBloom.mp3", "c84368880a912edb408189aba3cd3be3b84953b2039c7c8d58b9b441ee0c84fd"),
    "act_4": ("06-ArcticStillness.mp3", "0f3f1b3a5a4c911cc417664ba537409262876242e83f86bc3bd4e850662e0c8a"),
    "act_5": ("07-MirageSerenade.mp3", "9a3a6137f3bec620f08a242d6decf23ce9f827dc7fc2d361e316c58f684c5b6f"),
    "act_6": ("08-CreakingLullaby.mp3", "abd7774c1eb2467f592a8a263eb02f82029e21bf31706101804922a132bc885c"),
    "act_7": ("09-Hollow.mp3", "45d2256e170ff4006c4b55522d71f80657e75fe70a533b70bbb355f9aeeb6484"),
    "act_8": ("10-AscensionPulse.mp3", "d7685817c38df39bd783c2df453c03d8c9ea544db1776c1f1f40ecc538dcb8ee"),
    "act_9": ("11-AscensionsEnd.mp3", "3192ea4f4f941e22a8acfa787c8d079300a5e2a10a63598b293a38d7800d4782"),
}


# --- fixtures -------------------------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def mixer():
    """The game's mixer format: 22050 Hz, 16-bit, mono."""
    if not pygame.mixer.get_init():
        pygame.mixer.pre_init(audio.SAMPLE_RATE, -16, 1, 512)
        pygame.mixer.init()
    yield


def _tiny_sound() -> pygame.mixer.Sound:
    return pygame.mixer.Sound(buffer=bytes(2 * 2205))


@pytest.fixture
def manager(monkeypatch) -> AudioManager:
    """A real AudioManager with a cheap generated library (the real one takes ~0.5 s to render)."""
    monkeypatch.setattr(audio, "_build_sfx", lambda: {"ping": _tiny_sound()})
    monkeypatch.setattr(audio, "_build_menu_theme", _tiny_sound)
    monkeypatch.setattr(audio, "_build_act_theme", lambda idx: _tiny_sound())
    mgr = AudioManager()
    assert mgr._ready
    yield mgr
    pygame.mixer.stop()


def _write_wav(path: Path, seconds: float = 8.0, freq: float = 440.0, amp: int = 8000) -> None:
    n = int(seconds * audio.SAMPLE_RATE)
    data = array.array("h", (int(amp * math.sin(2 * math.pi * freq * i / audio.SAMPLE_RATE)) for i in range(n)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio.SAMPLE_RATE)
        w.writeframes(data.tobytes())


@pytest.fixture
def wav_music(tmp_path, monkeypatch) -> Path:
    """A music folder with one 8 s wav that every track key points at (gain 0.5, window 1..7 s => 4 s loop)."""
    _write_wav(tmp_path / "t.wav")
    monkeypatch.setattr(audio, "MUSIC_DIR", tmp_path)
    monkeypatch.setattr(audio, "TRACK_FILES", {k: FileTrack("t.wav", 0.5, 1.0, 7.0) for k in KEYS})
    return tmp_path


@pytest.fixture
def real_files(monkeypatch) -> Path:
    """Point MUSIC_DIR at the shipped mp3s; skip the test if they are not there."""
    if not all((REAL_DIR / f).is_file() for f, _ in EXPECTED_FILES.values()):
        pytest.skip("the mp3 files are not present")
    monkeypatch.setattr(audio, "MUSIC_DIR", REAL_DIR)
    return REAL_DIR


# --- the track table ------------------------------------------------------------------------------------

def test_table_covers_menu_and_ten_acts() -> None:
    assert list(TRACK_FILES) == KEYS
    assert {k: v.filename for k, v in TRACK_FILES.items()} == {k: f for k, (f, _h) in EXPECTED_FILES.items()}


def test_gains_are_attenuation_only_and_windows_fit_the_file() -> None:
    for key, spec in TRACK_FILES.items():
        assert 0.3 <= spec.gain <= 1.0, key
        assert 0 <= spec.loop_in < spec.loop_out <= 75.0, key
        assert spec.loop_out - spec.loop_in > 2 * audio.CROSSFADE_S + 20, key


def test_act_8_slot_uses_the_hollow_replacement_not_the_original_dreadfall() -> None:
    assert TRACK_FILES["act_7"].filename == "09-Hollow.mp3"
    assert not any("Dreadfall" in spec.filename for spec in TRACK_FILES.values())


def test_music_dir_is_relative_to_the_module_not_the_cwd(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert REAL_DIR.is_absolute()
    assert REAL_DIR == Path(audio.__file__).resolve().parent.parent / "assets" / "music"


def test_channels_are_reserved_for_music_and_sfx_get_eighteen(manager) -> None:
    assert audio.MUSIC_CHANNELS == 2 and audio.SFX_CHANNELS == 18
    assert pygame.mixer.get_num_channels() == 20
    assert len(manager._chan) == 2


# --- the loop builder -----------------------------------------------------------------------------------

def test_loop_has_the_expected_length_and_a_continuous_seam(wav_music) -> None:
    src = pygame.mixer.Sound(str(wav_music / "t.wav"))
    loop = _loop_from_sound(src, 1.0, 7.0, 2.0)
    assert loop is not src
    assert loop.get_length() == pytest.approx(4.0, abs=0.01)
    pcm = array.array("h")
    pcm.frombytes(loop.get_raw())
    biggest_step = max(abs(a - b) for a, b in zip(pcm, pcm[1:]))
    assert abs(pcm[-1] - pcm[0]) <= biggest_step + 2, "no jump where the loop wraps around"


@pytest.mark.parametrize("t_in,t_out,xfade", [(0.0, 3.0, 2.0), (5.0, 20.0, 2.0), (-1.0, 7.0, 2.0), (1.0, 7.0, 0.0)])
def test_loop_window_that_does_not_fit_returns_the_original(wav_music, t_in, t_out, xfade) -> None:
    src = pygame.mixer.Sound(str(wav_music / "t.wav"))
    assert _loop_from_sound(src, t_in, t_out, xfade) is src


# --- file vs generated fallback -----------------------------------------------------------------------------

def test_file_track_is_used_with_its_gain_on_a_music_channel(manager, wav_music) -> None:
    manager.play_menu_music()
    assert manager._current_track == "menu" and manager._current_source == "file"
    sound = manager._files["menu"]
    assert sound.get_volume() == pytest.approx(0.5, abs=0.01)
    assert sound.get_length() == pytest.approx(4.0, abs=0.01)
    channel = manager._chan[manager._cur]
    assert channel.get_sound() is sound and channel.get_busy()
    assert channel.get_volume() == pytest.approx(manager.music_volume, abs=0.01)


@pytest.mark.parametrize("make", ["missing_dir", "empty_dir", "garbage_file", "empty_file"])
def test_unusable_file_falls_back_to_the_generated_theme_quietly(manager, tmp_path, monkeypatch, capsys, make) -> None:
    folder = tmp_path / "music"
    if make != "missing_dir":
        folder.mkdir()
    if make == "garbage_file":
        (folder / "01-Menu.mp3").write_bytes(b"this is not an mp3 " * 50)
    if make == "empty_file":
        (folder / "01-Menu.mp3").write_bytes(b"")
    monkeypatch.setattr(audio, "MUSIC_DIR", folder)
    monkeypatch.setattr(audio, "TRACK_FILES", {"menu": FileTrack("01-Menu.mp3", 0.5, 1.0, 7.0)})
    capsys.readouterr()
    manager.play_menu_music()
    assert manager._current_track == "menu" and manager._current_source == "generated"
    assert manager._chan[manager._cur].get_busy()
    assert manager._chan[manager._cur].get_volume() == pytest.approx(1.0, abs=0.01)
    assert manager._tracks["menu"].get_volume() == pytest.approx(manager.music_volume, abs=0.01)
    assert "menu" in manager._file_failed
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_a_failed_file_is_not_retried_every_call(manager, tmp_path, monkeypatch) -> None:
    (tmp_path / "bad.mp3").write_bytes(b"junk" * 100)
    monkeypatch.setattr(audio, "MUSIC_DIR", tmp_path)
    monkeypatch.setattr(audio, "TRACK_FILES", {"act_2": FileTrack("bad.mp3", 0.5, 1.0, 7.0)})
    real_sound, loads = pygame.mixer.Sound, []

    def counting(*args, **kwargs):
        if args and isinstance(args[0], str):
            loads.append(args[0])
        return real_sound(*args, **kwargs)

    monkeypatch.setattr(audio.pygame.mixer, "Sound", counting)
    for _ in range(3):
        manager.stop_music()
        manager.play_act_music(2)
    assert len(loads) == 1 and manager._current_source == "generated"


def test_a_good_file_does_not_hide_the_generated_themes_from_other_keys(manager, wav_music, monkeypatch) -> None:
    monkeypatch.setattr(audio, "TRACK_FILES", {"menu": FileTrack("t.wav", 0.5, 1.0, 7.0)})
    manager.play_menu_music()
    assert manager._current_source == "file"
    manager.play_act_music(4)
    assert manager._current_track == "act_4" and manager._current_source == "generated"


def test_mixer_unavailable_means_silence_without_errors(monkeypatch, capsys) -> None:
    def refuse(*args, **kwargs):
        raise pygame.error("no audio device")

    monkeypatch.setattr(audio.pygame.mixer, "get_init", lambda: None)
    monkeypatch.setattr(audio.pygame.mixer, "init", refuse)
    monkeypatch.setattr(audio.pygame.mixer, "pre_init", lambda *a, **k: None)
    capsys.readouterr()
    mgr = AudioManager()
    assert mgr._ready is False
    mgr.play("hit")
    mgr.play_menu_music()
    mgr.play_act_music(3)
    mgr.prewarm(2)
    mgr.duck_music(0.5)
    mgr.tick(0.1)
    mgr.stop_music()
    mgr.set_enabled(False)
    mgr.set_enabled(True)
    assert mgr.toggle() is False
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# --- playback behaviour (start / stop / change / mute) -------------------------------------------------------

def test_same_track_twice_does_not_restart_and_a_new_one_uses_the_other_channel(manager, wav_music) -> None:
    manager.play_act_music(1)
    first_channel, first_sound = manager._cur, manager._files["act_1"]
    manager.play_act_music(1)
    assert manager._cur == first_channel and manager._chan[first_channel].get_sound() is first_sound
    manager.play_act_music(2)
    assert manager._cur != first_channel and manager._current_track == "act_2"
    assert manager._chan[manager._cur].get_busy()
    assert manager._chan[first_channel].get_busy(), "the old track is still fading out (crossfade, not a hard cut)"


def test_act_index_is_clamped_like_before(manager, wav_music) -> None:
    manager.play_act_music(-5)
    assert manager._current_track == "act_0"
    manager.play_act_music(99)
    assert manager._current_track == "act_9"


def test_stop_music_then_play_works_again(manager, wav_music) -> None:
    manager.play_menu_music()
    manager.stop_music()
    assert manager._current_track is None
    manager.play_act_music(3)
    assert manager._current_track == "act_3" and manager._chan[manager._cur].get_busy()


def test_mute_stops_music_and_blocks_new_music_until_re_enabled(manager, wav_music) -> None:
    manager.play_menu_music()
    manager.set_enabled(False)
    assert not any(c.get_busy() for c in manager._chan) and manager._current_track is None
    manager.play_act_music(5)
    manager.play_menu_music()
    manager.play("ping")
    assert manager._current_track is None and not any(c.get_busy() for c in manager._chan)
    assert manager.toggle() is True
    manager.play_menu_music()
    assert manager._current_track == "menu" and manager._chan[manager._cur].get_busy()


def test_sound_effects_never_land_on_the_music_channels(manager, wav_music) -> None:
    manager.play_menu_music()
    music = manager._chan[manager._cur].get_sound()
    for _ in range(60):
        manager.play("ping")
    assert manager._chan[manager._cur].get_sound() is music
    other = manager._chan[1 - manager._cur]
    assert other.get_sound() is None or other.get_sound() is not manager._sfx["ping"]


@pytest.mark.parametrize("music_volume", [0.0, 0.32, 1.0])
def test_music_volume_setting_scales_file_music_and_never_exceeds_one(manager, wav_music, music_volume) -> None:
    manager.music_volume = music_volume
    manager.play_menu_music()
    channel = manager._chan[manager._cur]
    assert channel.get_volume() == pytest.approx(music_volume, abs=0.01)
    manager.duck_music(0.5, immediate=True)
    assert channel.get_volume() == pytest.approx(music_volume * 0.5, abs=0.01)
    assert all(0.0 <= c.get_volume() <= 1.0 for c in manager._chan)


def test_ducking_ramps_down_and_back_up(manager, wav_music) -> None:
    manager.play_menu_music()
    channel = manager._chan[manager._cur]
    full = channel.get_volume()
    manager.duck_music(0.5)
    manager.tick(0.07)
    mid = channel.get_volume()
    assert full * 0.5 < mid < full
    manager.tick(0.5)
    assert channel.get_volume() == pytest.approx(full * 0.5, abs=0.01)
    manager.duck_music(1.0)
    manager.tick(0.5)
    assert channel.get_volume() == pytest.approx(full, abs=0.01)


def test_generated_fallback_also_ducks_and_keeps_its_old_level(manager) -> None:
    manager.play_menu_music()
    assert manager._current_source == "generated"
    channel = manager._chan[manager._cur]
    assert channel.get_volume() == pytest.approx(1.0, abs=0.01)
    manager.duck_music(0.5, immediate=True)
    assert channel.get_volume() == pytest.approx(0.5, abs=0.01)
    assert manager._tracks["menu"].get_volume() == pytest.approx(manager.music_volume, abs=0.01)


def test_at_most_two_decoded_files_stay_in_memory(manager, wav_music) -> None:
    for act in range(6):
        manager.play_act_music(act)
        assert len(manager._files) <= 2
    assert set(manager._files) == {"act_4", "act_5"}


def test_prewarm_loads_the_file_without_starting_playback(manager, wav_music) -> None:
    manager.prewarm(3)
    assert "act_3" in manager._files and manager._current_track is None
    assert not any(c.get_busy() for c in manager._chan)


# --- the shipped mp3s (skipped when absent) --------------------------------------------------------------------------

def test_shipped_folder_has_exactly_the_eleven_expected_files_with_the_right_hashes(real_files) -> None:
    on_disk = sorted(p.name for p in real_files.iterdir())
    assert on_disk == sorted(f for f, _h in EXPECTED_FILES.values()), "no stray files; the original Dreadfall is not shipped"
    for key, (name, digest) in EXPECTED_FILES.items():
        data = (real_files / name).read_bytes()
        assert len(data) > 1_000_000, name
        assert hashlib.sha256(data).hexdigest() == digest, name


def test_every_shipped_file_loads_as_a_loop_of_the_documented_length(manager, real_files) -> None:
    started, loaded = time.time(), {}
    for key, spec in TRACK_FILES.items():
        t0 = time.time()
        sound = manager._file_sound(key)
        assert sound is not None, key
        assert time.time() - t0 < 1.5, f"{key} took too long to decode"
        loaded[key] = sound.get_length()
        assert loaded[key] == pytest.approx(spec.loop_out - spec.loop_in - audio.CROSSFADE_S, abs=0.05), key
        assert len(manager._files) <= 2
    assert time.time() - started < 8.0 and not manager._file_failed


def test_menu_and_each_act_pick_their_own_file(manager, real_files) -> None:
    picked: Dict[str, str] = {}
    for key in KEYS:
        manager.stop_music()
        manager.play_menu_music() if key == "menu" else manager.play_act_music(int(key[4:]))
        assert manager._current_track == key and manager._current_source == "file", key
        picked[key] = manager._current_source
    assert len(picked) == 11
