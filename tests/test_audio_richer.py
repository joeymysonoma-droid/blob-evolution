"""Headless audio checks for TASK-024/025 (richer generated sound).

Run:  SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=dummy python -m pytest tests/test_audio_richer.py -q
The module under test is blob_evolution.systems.audio; game.py is scanned for the sound names it plays.
"""
import array
import importlib
import os
import re

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

AUDIO_MODULE = "blob_evolution.systems.audio"
A = importlib.import_module(AUDIO_MODULE)
GAME_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blob_evolution", "game.py")
SR = A.SAMPLE_RATE
FREQUENT = {"shoot", "hit", "pickup", "ui_select"}   # <= 0.1 s, peak <= 0.2
THEME_KEYS = ["menu"] + ["act_%d" % i for i in range(10)]


def _samples(snd):
    a = array.array("h")
    a.frombytes(snd.get_raw())
    return a


@pytest.fixture(scope="module", autouse=True)
def mixer():
    if not pygame.mixer.get_init():
        pygame.mixer.pre_init(SR, -16, 1, 512)
        pygame.mixer.init()
    yield


@pytest.fixture(scope="module")
def sfx(mixer):
    return A._build_sfx()


@pytest.fixture(scope="module")
def tracks(mixer):
    out = {"menu": A._build_menu_theme()}
    for i in range(10):
        out["act_%d" % i] = A._build_act_theme(i)
    return out


def _game_sfx_names():
    if not os.path.exists(GAME_PY):
        pytest.skip("game.py not found")
    return set(re.findall(r'audio\.play\(\s*"(\w+)"', open(GAME_PY, encoding="utf-8").read()))


def test_every_game_call_has_a_sound(sfx):
    names = _game_sfx_names()
    assert names, "no audio.play calls found"
    assert names <= set(sfx), "missing sounds: %s" % sorted(names - set(sfx))


def test_new_sounds_present(sfx):
    for name in A.NEW_SFX:
        assert name in sfx


def test_sfx_duration_peak_clipping(sfx):
    for name, snd in sfx.items():
        a = _samples(snd)
        dur = len(a) / SR
        peak = max(abs(v) for v in a) / 32767.0
        assert 0 < dur < 0.7, (name, dur)
        assert 0.15 <= peak <= 0.40, (name, peak)
        assert sum(1 for v in a if abs(v) >= 32767) == 0, name
        assert abs(a[0]) <= 0.01 * 32767 and abs(a[-1]) <= 0.01 * 32767, (name, "edge click")


def test_frequent_sfx_short_and_soft(sfx):
    for name in FREQUENT:
        a = _samples(sfx[name])
        assert len(a) / SR <= 0.1, name
        assert max(abs(v) for v in a) / 32767.0 <= 0.20, name


def test_music_buffers_loop_cleanly(tracks):
    assert set(tracks) == set(THEME_KEYS)
    builders = [A._theme_menu] + list(A.ACT_THEME_BUILDERS)
    for key, tb in zip(THEME_KEYS, builders):
        a = _samples(tracks[key])
        assert len(a) > 6 * SR, key
        g, bars, _peak, _layers = tb()
        assert len(a) == g.samples(bars), (key, "not exactly bars * bar_length")
        peak = max(abs(v) for v in a) / 32767.0
        assert peak <= 0.5, (key, peak)
        assert sum(1 for v in a if abs(v) >= 32767) == 0, key
        assert abs(a[0]) <= 0.002 * 32767 and abs(a[-1]) <= 0.002 * 32767, (key, "seam")
        assert abs(a[0] - a[-1]) <= 0.004 * 32767, key
        assert sum(abs(v) for v in a) > 0, key        # not silent


def test_seam_step_is_not_an_outlier(tracks):
    for key, snd in tracks.items():
        a = _samples(snd)
        wrap = list(a[-8:]) + list(a[:8])
        seam = max(abs(wrap[i + 1] - wrap[i]) for i in range(len(wrap) - 1))
        body = max(abs(a[i + 1] - a[i]) for i in range(len(a) - 1))
        assert seam <= 0.25 * body, key


def test_tails_wrap_to_start():
    # an echo tail that runs off the end must be folded back, not dropped
    buf = [1.0] * 10 + [2.0] * 5
    assert len(A._loop_fit(buf, 10)) == 10
    assert abs(sum(A._loop_fit(buf, 10)) - sum(buf)) < 1e-9
    assert len(A._loop_fit([1.0] * 4, 10)) == 10


def test_helpers():
    assert len(A._echo([1.0] * 100, 0.01, 0.5, 0.5, 3)) == 100 + 3 * int(0.01 * SR)
    snd = A._finish([0.0, 0.9, -0.9, 0.5] * 500, 0.25)
    a = _samples(snd)
    assert abs(max(abs(v) for v in a) / 32767.0 - 0.25) < 0.01
    drums = A._drums("K...S...H...O...", 0.1)
    assert len(drums) == int(round(16 * 0.1 * SR))
    for wave in ("sine", "square", "triangle", "saw", "noise"):
        seq = A._sequence([(440, 0.1), (0, 0.05), (330, 0.1)], 0.2, wave)
        assert isinstance(seq, list) and isinstance(seq[0], int) and max(abs(v) for v in seq) > 0, wave
    assert max(abs(v) for v in A._sequence([(440, 0.1)], 0.2, "saw")) != \
        max(abs(v) for v in A._sequence([(440, 0.1)], 0.2, "sine"))   # saw no longer falls back to sine


def test_legacy_signatures():
    assert isinstance(A._tone(660, 0.05, 0.25, "sine", 0.005, 0.03), pygame.mixer.Sound)
    assert isinstance(A._tone(220, 0.1, 0.3, "noise", 0.001, 0.05, f_end=80, decay=0.05), pygame.mixer.Sound)
    assert isinstance(A._chord([523, 784], 0.12, 0.22), pygame.mixer.Sound)
    t1, t2 = A._sequence([(A.C4, 0.1)]), A._sequence([(A.E4, 0.1)])
    mix = A._mix_tracks([t1, t2], volume=0.9)
    assert len(mix.get_raw()) == len(t1) * 2
    peaked = A._mix_tracks([t1, t2], gains=[1.0, 0.5], peak=0.3)
    assert max(abs(v) for v in _samples(peaked)) / 32767.0 == pytest.approx(0.3, abs=0.01)
    assert A.B == 0.18 and A.Q == pytest.approx(0.36) and A.H == pytest.approx(0.72) and A.W == pytest.approx(1.44)


def test_audio_manager_lazy_and_playable(mixer, monkeypatch, tmp_path):
    monkeypatch.setattr(A, "MUSIC_DIR", tmp_path)     # no mp3s: this test is about the generated themes
    mgr = A.AudioManager()
    assert mgr._ready
    assert "menu" in mgr._tracks
    assert "act_9" not in mgr._tracks                 # act themes are lazy
    for name in list(mgr._sfx):
        mgr.play(name, 0.5)
    mgr.play("does_not_exist")
    mgr.play_menu_music()
    mgr.play_act_music(3)
    assert "act_3" in mgr._tracks
    mgr.play_act_music(99)                            # clamped to act 9
    assert "act_9" in mgr._tracks
    mgr.stop_music()
    mgr.set_enabled(False)
    mgr.play("hit")
    mgr.set_enabled(True)
    assert A.get_audio() is A.get_audio()
