"""TASK-027: eleven recorded sound effects (WAV files) over the generated library, with a retrigger gate.

Almost everything here uses synthetic wavs in a tmp folder and a cheap generated library, so it passes whether
or not blob_evolution/assets/sfx is present (the root conftest points audio.SFX_DIR at a missing folder for
every test). The tests that need the shipped files use the `real_files` fixture and are skipped without them.
"""
from __future__ import annotations

import array
import hashlib
import inspect
import math
import time
import wave
from pathlib import Path
from typing import Dict

import pygame
import pytest

from blob_evolution.systems import audio
from blob_evolution.systems.audio import AudioManager

REAL_DIR = Path(audio.__file__).resolve().parent.parent / "assets" / "sfx"
FILE_NAMES = ["ui_select", "ui_confirm", "shoot", "dash", "hit", "kill", "explode", "pickup", "absorb", "boss_hit", "story"]
GENERATED_NAMES = ["hurt", "ui_back", "shield_block", "heal", "artifact", "merge", "boss_warning",
                   "levelup", "boss_phase", "boss_spawn", "victory", "defeat"]
GATES = {"hit": (50, 4), "pickup": (40, 4), "kill": (70, 3), "absorb": (80, 3),
         "boss_hit": (80, 3), "hurt": (100, 3), "ui_select": (30, 2)}
# shipped file -> (sha256, keep ms, peak cap as a fraction of full scale)
REAL = {
    "ui_select": ("bbe3b54e91c09c92679c8acbff3d05236dfdaecb214378dce1f3a239b8022dc0", 125, 0.2),
    "ui_confirm": ("eb8943595ace8657668e8ece041adaff3ebf37d9106dce40fac4706103c6adc9", 175, 0.4),
    "shoot": ("c63833338ea8e2b479e1f71142744677a7e503785245807bbb31deee238d9616", 195, 0.2),
    "dash": ("26c8f5fffa7748f3d6c187ef75e155ffbf874c4f69c2241f2c5a8b7766c70b04", 200, 0.4),
    "hit": ("35c9167870ef30de8cfba9ab36f416e9012c04a8af4951dc2512940e0c3c9dac", 230, 0.2),
    "kill": ("0ded52d2eac06cbbea93cf8f318e70981d99cd6d9cfd3d58431da99032305e16", 365, 0.4),
    "explode": ("f4bf14592bb9f559be60d40f7a9160a2e6f6975d742e4962cbaf7643b9be9061", 430, 0.4),
    "pickup": ("563205bbc6b9c46f97d460de6e8de39628c27255ff6c0300dd7d26680fe0f9d8", 190, 0.2),
    "absorb": ("f61d948ad980ced15ad7de29ef6eef3f8f64794f49f0fea38a9d55bd36941a0b", 370, 0.2),
    "boss_hit": ("448193e24ea3b74b117f73185bcdbe98edac5ccfda18596a5fc2ada53056f2be", 310, 0.4),
    "story": ("f8934861abbc08114c5ca1936c13f76fb37aeb24c3901af7a8d7bc14d8b1ea6b", 300, 0.4),
}


# --- helpers / fixtures ---------------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def mixer():
    """The game's mixer format: 22050 Hz, 16-bit, mono, 20 channels."""
    if not pygame.mixer.get_init():
        pygame.mixer.pre_init(audio.SAMPLE_RATE, -16, 1, 512)
        pygame.mixer.init()
    pygame.mixer.set_num_channels(audio.SFX_CHANNELS + audio.MUSIC_CHANNELS)
    yield


def _long_silence() -> pygame.mixer.Sound:
    """A generated stand-in that stays busy for 5 s, so instance counts are stable during a test."""
    return pygame.mixer.Sound(buffer=bytes(2 * audio.SAMPLE_RATE * 5))


def _write_wav(path: Path, seconds: float = 0.2, freq: float = 600.0, amp: int = 6000, rate: int = 22050) -> None:
    n = int(seconds * rate)
    data = array.array("h", (int(amp * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


@pytest.fixture
def cheap_library(monkeypatch):
    """Generated library with all 23 real names but trivial sounds (the real one takes ~0.5 s to render)."""
    monkeypatch.setattr(audio, "_build_sfx", lambda: {n: _long_silence() for n in audio.SFX_BUILDERS})
    monkeypatch.setattr(audio, "_build_menu_theme", lambda: pygame.mixer.Sound(buffer=bytes(2 * 2205)))
    yield
    pygame.mixer.stop()


@pytest.fixture
def sfx_dir(tmp_path, monkeypatch) -> Path:
    """A folder with a valid synthetic wav for each of the 11 names."""
    for n in FILE_NAMES:
        _write_wav(tmp_path / f"{n}.wav")
    monkeypatch.setattr(audio, "SFX_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def manager(cheap_library, sfx_dir) -> AudioManager:
    mgr = AudioManager()
    assert mgr._ready
    return mgr


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock(manager) -> Clock:
    c = Clock()
    manager._clock = c
    return c


@pytest.fixture
def real_files(monkeypatch) -> Path:
    if not all((REAL_DIR / f"{n}.wav").is_file() for n in FILE_NAMES):
        pytest.skip("the sfx wav files are not present")
    monkeypatch.setattr(audio, "SFX_DIR", REAL_DIR)
    return REAL_DIR


def _samples(snd: pygame.mixer.Sound) -> array.array:
    a = array.array("h")
    a.frombytes(snd.get_raw())
    return a


# --- the mapping and the folder -------------------------------------------------------------------------

def test_mapping_covers_exactly_the_eleven_file_backed_names() -> None:
    assert sorted(audio.SFX_FILES) == sorted(FILE_NAMES) and len(audio.SFX_FILES) == 11
    assert set(audio.SFX_FILES) <= set(audio.SFX_BUILDERS), "every file-backed name has a generated fallback"
    assert sorted(set(audio.SFX_BUILDERS) - set(audio.SFX_FILES)) == sorted(GENERATED_NAMES)


def test_sfx_dir_is_next_to_the_package_and_not_cwd_relative(tmp_path, monkeypatch) -> None:
    real = Path(audio.__file__).resolve().parent.parent / "assets" / "sfx"
    assert REAL_DIR == real and REAL_DIR.is_absolute()
    monkeypatch.chdir(tmp_path)
    assert REAL_DIR.is_absolute() and REAL_DIR.parent.name == "assets"


def test_gate_table_is_the_producers_list_and_shoot_is_ungated() -> None:
    assert audio.SFX_GATES == GATES
    for ungated in ("shoot", "explode", "dash", "ui_confirm", "story", "levelup", "boss_phase", "victory"):
        assert ungated not in audio.SFX_GATES


def test_play_signature_is_unchanged() -> None:
    assert str(inspect.signature(AudioManager.play)) == "(self, name: 'str', volume_scale: 'float' = 1.0) -> 'None'"


# --- file lookup and fallback ---------------------------------------------------------------------------

def test_files_replace_exactly_the_eleven_names_and_the_rest_stay_generated(cheap_library, sfx_dir) -> None:
    generated = audio._build_sfx()
    mgr = AudioManager()
    assert mgr._sfx_failed == []
    for n in FILE_NAMES:
        assert mgr.sfx_source(n) == "file"
        assert mgr._sfx[n].get_length() == pytest.approx(0.2, abs=0.01)
    for n in GENERATED_NAMES:
        assert mgr.sfx_source(n) == "generated" and mgr._sfx[n].get_length() == pytest.approx(5.0, abs=0.01)
    assert set(mgr._sfx) == set(generated), "no name added or lost"
    assert mgr.sfx_source("nope") is None


def test_missing_folder_means_all_generated_and_silent(cheap_library, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(audio, "SFX_DIR", tmp_path / "nope")
    capsys.readouterr()
    mgr = AudioManager()
    assert sorted(mgr._sfx_failed) == sorted(FILE_NAMES)
    assert all(mgr.sfx_source(n) == "generated" for n in mgr._sfx)
    mgr.play("hit")
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def _garbage(p: Path) -> None:
    p.write_bytes(bytes(range(256)) * 16)


def _empty(p: Path) -> None:
    p.write_bytes(b"")


def _truncated(p: Path) -> None:
    p.write_bytes(p.read_bytes()[:30])


def _silent(p: Path) -> None:
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(bytes(2 * 4410))


def _too_long(p: Path) -> None:
    _write_wav(p, seconds=3.0)


def _too_short(p: Path) -> None:
    _write_wav(p, seconds=0.01)


@pytest.mark.parametrize("damage", [_garbage, _empty, _truncated, _silent, _too_long, _too_short],
                         ids=lambda f: f.__name__.strip("_"))
def test_a_broken_file_falls_back_for_that_name_only_without_noise(cheap_library, sfx_dir, capsys, damage) -> None:
    damage(sfx_dir / "kill.wav")
    (sfx_dir / "absorb.wav").unlink()                                   # and one missing for good measure
    capsys.readouterr()
    mgr = AudioManager()
    assert sorted(mgr._sfx_failed) == ["absorb", "kill"]
    assert mgr.sfx_source("kill") == "generated" and mgr.sfx_source("absorb") == "generated"
    assert all(mgr.sfx_source(n) == "file" for n in FILE_NAMES if n not in ("kill", "absorb"))
    mgr.play("kill")
    mgr.play("absorb")
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_load_raising_means_fallback_and_the_file_is_not_retried(cheap_library, sfx_dir, monkeypatch, capsys) -> None:
    real_sound = pygame.mixer.Sound
    opened = []

    def flaky(*args, **kwargs):
        if args and isinstance(args[0], str):
            opened.append(Path(args[0]).name)
            if Path(args[0]).name == "hit.wav":
                raise pygame.error("cannot decode")
            if Path(args[0]).name == "story.wav":
                raise MemoryError("no memory")
        return real_sound(*args, **kwargs)

    monkeypatch.setattr(audio.pygame.mixer, "Sound", flaky)
    capsys.readouterr()
    mgr = AudioManager()
    assert sorted(mgr._sfx_failed) == ["hit", "story"]
    assert mgr.sfx_source("hit") == "generated" and mgr.sfx_source("story") == "generated"
    n_opened = len(opened)
    assert sorted(opened) == sorted(f"{n}.wav" for n in FILE_NAMES), "each file is tried once"
    for _ in range(5):
        mgr.play("hit")
        mgr.play("story")
    assert len(opened) == n_opened, "a failed file is never retried"
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_mixer_unavailable_means_silence_without_errors(monkeypatch, capsys) -> None:
    def refuse(*args, **kwargs):
        raise pygame.error("no audio device")

    monkeypatch.setattr(audio.pygame.mixer, "get_init", lambda: None)
    monkeypatch.setattr(audio.pygame.mixer, "init", refuse)
    monkeypatch.setattr(audio.pygame.mixer, "pre_init", lambda *a, **k: None)
    capsys.readouterr()
    mgr = AudioManager()
    assert mgr._ready is False
    for n in FILE_NAMES + GENERATED_NAMES:
        mgr.play(n)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# --- play(): volume, mute, channels -----------------------------------------------------------------------

def test_play_sets_volume_from_sfx_volume_and_scale_and_uses_a_file_sound(manager) -> None:
    sound = manager._sfx["pickup"]
    manager.play("pickup", 0.5)
    assert sound.get_num_channels() == 1
    assert sound.get_volume() == pytest.approx(manager.sfx_volume * 0.5, abs=1 / 128)
    manager.play("pickup", 40.0)
    assert sound.get_volume() <= 1.0


def test_mute_blocks_file_backed_and_generated_sounds_and_does_not_consume_the_gate(manager, clock) -> None:
    manager.set_enabled(False)
    for n in FILE_NAMES + GENERATED_NAMES:
        manager.play(n)
    assert all(manager._sfx[n].get_num_channels() == 0 for n in manager._sfx)
    assert manager._sfx_last == {}, "a muted call must not start the retrigger gap"
    manager.set_enabled(True)
    manager.play("hit")
    manager.play("hurt")
    assert manager._sfx["hit"].get_num_channels() == 1 and manager._sfx["hurt"].get_num_channels() == 1


def test_sfx_never_land_on_the_music_channels_and_may_use_all_eighteen(manager, clock) -> None:
    for i in range(60):
        for n in manager._sfx:
            manager.play(n)
        clock.t += 1.0
    assert not any(pygame.mixer.Channel(i).get_busy() for i in range(audio.MUSIC_CHANNELS))
    assert pygame.mixer.get_num_channels() == audio.SFX_CHANNELS + audio.MUSIC_CHANNELS == 20


# --- the retrigger gate -------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(GATES))
def test_min_gap_blocks_a_start_that_is_too_soon(manager, clock, name) -> None:
    gap_ms, _ = GATES[name]
    sound = manager._sfx[name]
    manager.play(name)
    assert sound.get_num_channels() == 1
    clock.t += (gap_ms - 1) / 1000.0
    manager.play(name)
    assert sound.get_num_channels() == 1, "1 ms short of the gap: blocked"
    clock.t += 2 / 1000.0
    manager.play(name)
    assert sound.get_num_channels() == 2, "gap elapsed: allowed again"


@pytest.mark.parametrize("name", sorted(GATES))
def test_max_simultaneous_blocks_extra_copies(manager, clock, name) -> None:
    _, cap = GATES[name]
    sound = manager._sfx[name]
    for _ in range(cap + 3):
        manager.play(name)
        clock.t += 1.0                                  # gap always satisfied, only the cap can block
    assert sound.get_num_channels() == cap
    sound.stop()
    manager.play(name)
    assert sound.get_num_channels() == 1, "room again once copies finish"


def test_a_blocked_start_does_not_restart_the_gap(manager, clock) -> None:
    manager.play("hit")                                  # t0
    clock.t += 0.030
    manager.play("hit")                                  # blocked at +30 ms
    clock.t += 0.025                                     # +55 ms after the first start
    manager.play("hit")
    assert manager._sfx["hit"].get_num_channels() == 2


def test_gates_are_independent_per_name(manager, clock) -> None:
    manager.play("hit")
    manager.play("pickup")
    manager.play("kill")
    assert [manager._sfx[n].get_num_channels() for n in ("hit", "pickup", "kill")] == [1, 1, 1]


def test_hurt_is_gated_although_it_stays_generated(manager, clock) -> None:
    assert manager.sfx_source("hurt") == "generated"
    for _ in range(10):
        manager.play("hurt")                              # same instant: only the first gets through
    assert manager._sfx["hurt"].get_num_channels() == 1


@pytest.mark.parametrize("name", ["shoot", "explode", "dash", "ui_confirm", "story", "levelup", "boss_phase", "victory"])
def test_ungated_sounds_play_every_time(manager, clock, name) -> None:
    for _ in range(6):
        manager.play(name)                                # same instant, no clock movement
    assert manager._sfx[name].get_num_channels() == 6


def test_the_gate_uses_the_injectable_clock_and_defaults_to_monotonic(cheap_library, sfx_dir) -> None:
    mgr = AudioManager()
    assert mgr._clock is time.monotonic


# --- the shipped files -----------------------------------------------------------------------------------------

def test_shipped_folder_has_exactly_the_eleven_files_with_the_pinned_hashes(real_files) -> None:
    assert sorted(p.name for p in real_files.iterdir()) == sorted(f"{n}.wav" for n in FILE_NAMES)
    for n, (digest, _, _) in REAL.items():
        assert hashlib.sha256((real_files / f"{n}.wav").read_bytes()).hexdigest() == digest, n
    assert sum(p.stat().st_size for p in real_files.iterdir()) == 128316


def test_shipped_files_load_at_the_mixer_format_with_safe_levels_and_clean_edges(real_files, cheap_library) -> None:
    mgr = AudioManager()
    assert mgr._sfx_failed == []
    for n, (_, keep_ms, cap) in REAL.items():
        assert mgr.sfx_source(n) == "file"
        snd = mgr._sfx[n]
        with wave.open(str(real_files / f"{n}.wav")) as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (22050, 1, 2), n
        assert abs(snd.get_length() * 1000 - keep_ms) <= 5, (n, snd.get_length())
        a = _samples(snd)
        peak = max(abs(v) for v in a) / 32768.0
        assert 20 * math.log10(peak) <= -3.0 and peak <= cap + 0.005, (n, peak)
        assert max(abs(a[0]), abs(a[-1])) <= 0.01 * 32768, (n, "edge click")


def test_every_name_plays_twice_and_rapid_fire_never_raises_with_the_real_files(real_files) -> None:
    mgr = AudioManager()                                  # the real generated library plus the real files
    assert mgr._ready and mgr._sfx_failed == []
    for n in list(mgr._sfx) * 2:
        mgr.play(n, 0.7)
    for _ in range(120):
        mgr.play("hit", 0.45)
        mgr.play("pickup", 0.5)
        mgr.play("kill", 0.7)
        mgr.play("shoot", 0.55)
    assert not any(pygame.mixer.Channel(i).get_busy() for i in range(audio.MUSIC_CHANNELS))
    pygame.mixer.stop()


def test_loading_the_eleven_files_is_quick(real_files, cheap_library) -> None:
    t0 = time.perf_counter()
    loaded = audio._load_sfx_files(audio.SFX_FILES, real_files)
    ms = (time.perf_counter() - t0) * 1000.0
    assert len(loaded) == 11
    assert ms < 50.0, ms
