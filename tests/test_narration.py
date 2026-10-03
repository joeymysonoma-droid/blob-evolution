"""TASK-028: recorded narration on its own channel, the card triggers, skip/mute/volume and the saved volume.

No narration file is needed: every test generates its own fake clips in tmp_path and points audio.NARRATION_DIR
there (the root conftest points it at a missing folder for every other test).
"""
from __future__ import annotations

import importlib.util
import json
import wave
from pathlib import Path
from typing import List, Optional, Tuple

import pygame
import pytest

from blob_evolution import config
from blob_evolution.data import lore
from blob_evolution.systems import audio
from blob_evolution.systems.audio import AudioManager
from blob_evolution.ui.menus import MenuRenderer
from blob_evolution.utils.enums import GameState, NodeType


@pytest.fixture(autouse=True)
def _reset_shared_audio():
    """get_audio() is a process-wide singleton: put back what these tests change on it."""
    yield
    a = audio.get_audio()
    a.set_enabled(True)
    a.set_narration_volume(audio.NARRATION_VOLUME_DEFAULT)
    a.stop_narration()


def _write_wav(path: Path, seconds: float = 2.0, rate: int = 22050) -> None:
    """A loud-enough square-ish wave; `seconds` long so a clip is still busy while a test looks at it."""
    frames = (b"\x00\x20\x00\x20\x00\xe0\x00\xe0") * int(seconds * rate / 4)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)


@pytest.fixture
def cheap_library(monkeypatch):
    """Generated library with trivial sounds (the real one takes ~0.5 s to render)."""
    monkeypatch.setattr(audio, "_build_sfx", lambda: {n: pygame.mixer.Sound(buffer=bytes(2 * 4410)) for n in audio.SFX_BUILDERS})
    monkeypatch.setattr(audio, "_build_menu_theme", lambda: pygame.mixer.Sound(buffer=bytes(2 * 2205)))
    yield
    pygame.mixer.stop()


@pytest.fixture
def narr_dir(tmp_path, monkeypatch) -> Path:
    """An empty narration folder that audio.NARRATION_DIR points at."""
    folder = tmp_path / "narration"
    folder.mkdir()
    monkeypatch.setattr(audio, "NARRATION_DIR", folder)
    return folder


@pytest.fixture
def manager(cheap_library, narr_dir) -> AudioManager:
    mgr = AudioManager()
    assert mgr._ready
    yield mgr
    mgr.stop_narration()
    pygame.mixer.stop()


def _clips(folder: Path, *keys: str, seconds: float = 2.0) -> None:
    for k in keys:
        _write_wav(folder / f"{k}.wav", seconds)


def _settle(mgr: AudioManager, limit_s: float = 1.0) -> None:
    """Tick until the waiting clip (if any) has started, as the game's per-frame tick does."""
    waited = 0.0
    while mgr._narr_pending and waited < limit_s:
        pygame.time.wait(10)
        mgr.tick(0.01)
        waited += 0.01


def _idle(mgr: AudioManager, limit_ms: int = 600) -> bool:
    for _ in range(limit_ms // 10):
        if not mgr._narr_chan.get_busy():
            return True
        pygame.time.wait(10)
    return False


# --- keys and the trigger table ----------------------------------------------------------------------------

def test_narration_dir_is_module_relative_and_patchable() -> None:
    spec = importlib.util.spec_from_file_location("audio_fresh_copy", audio.__file__)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)          # the real value, before the conftest patch
    assert fresh.NARRATION_DIR.is_absolute()
    assert fresh.NARRATION_DIR == Path(audio.__file__).resolve().parent.parent / "assets" / "narration"
    assert audio.NARRATION_EXTS == (".wav", ".ogg")


def test_default_tests_see_no_narration_files() -> None:
    assert not audio.NARRATION_DIR.exists()


def test_opening_clip_keys() -> None:
    assert audio.OPENING_CLIPS == ("intro_card1", "intro_card2", "layer01_descent")


@pytest.mark.parametrize("act", range(10))
def test_descent_and_miniboss_keys_cover_every_layer(act) -> None:
    n = act + 1
    assert audio.descent_clip(act) == f"layer{n:02d}_descent"
    assert audio.miniboss_clip(act) == f"layer{n:02d}_miniboss"


@pytest.mark.parametrize("act", range(10))
@pytest.mark.parametrize("level", [0, 1, 2, 3, 4, 5, 6, 9, 10, 11, 25])
def test_warden_key_picks_the_same_tier_as_the_quote(act, level) -> None:
    tiers = [m for m, _ in lore.NG_WARDEN_QUOTES.get(act, []) if level >= m]
    key = audio.warden_clip(act, level)
    if not tiers:
        assert key == f"layer{act + 1:02d}_warden"
    else:
        assert key == f"layer{act + 1:02d}_warden_ng{max(tiers)}"
        assert lore.get_warden_quote(act, level) == dict(lore.NG_WARDEN_QUOTES[act])[max(tiers)]


def test_warden_tier_table_matches_the_scripts() -> None:
    """ng_plus_scripts.md: NG2 and NG5 for layers 1-9, plus NG10 for layer 10; NG+ 0 and 1 use the base clip."""
    assert audio.warden_clip(0, 0) == audio.warden_clip(0, 1) == "layer01_warden"
    assert audio.warden_clip(0, 2) == audio.warden_clip(0, 4) == "layer01_warden_ng2"
    assert audio.warden_clip(0, 5) == audio.warden_clip(0, 99) == "layer01_warden_ng5"
    assert audio.warden_clip(9, 9) == "layer10_warden_ng5"
    assert audio.warden_clip(9, 10) == "layer10_warden_ng10"


def test_all_narration_keys_is_the_full_unique_table() -> None:
    keys = audio.all_narration_keys()
    assert len(keys) == len(set(keys)) == 53    # 2 intro + 10 descent + 10 warden + 10 mini-boss + 21 NG+
    assert sum("_ng" in k for k in keys) == 21
    assert sum(k.endswith("_descent") for k in keys) == 10 and sum(k.endswith("_miniboss") for k in keys) == 10


# --- the reserved channel ----------------------------------------------------------------------------------

def test_mixer_opens_a_third_reserved_channel_for_narration(manager) -> None:
    assert (audio.SFX_CHANNELS, audio.MUSIC_CHANNELS, audio.NARRATION_CHANNELS) == (18, 2, 1)
    assert pygame.mixer.get_num_channels() == audio.TOTAL_CHANNELS == 21
    assert manager._narr_chan is not None and len(manager._chan) == audio.MUSIC_CHANNELS
    assert pygame.mixer.find_channel() is not None and pygame.mixer.find_channel(True) is not None


def test_narration_plays_on_the_reserved_channel_not_music_or_sfx(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1")
    manager.play_narration("intro_card1")
    assert manager.narration_playing() == "intro_card1"
    assert pygame.mixer.Channel(audio.MUSIC_CHANNELS).get_busy()
    assert not any(pygame.mixer.Channel(i).get_busy() for i in range(audio.MUSIC_CHANNELS))


def test_sfx_spam_never_takes_or_cuts_the_narration_channel(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1")
    manager.play_narration("intro_card1")
    for _ in range(40):
        for n in manager._sfx:
            manager._sfx[n].play()
    assert manager._narr_chan.get_busy() and manager.narration_playing() == "intro_card1"
    assert not any(pygame.mixer.Channel(i).get_busy() for i in range(audio.MUSIC_CHANNELS))


def test_sfx_may_still_use_eighteen_channels(manager) -> None:
    sound = pygame.mixer.Sound(buffer=bytes(2 * audio.SAMPLE_RATE * 5))
    started = [sound.play() for _ in range(25)]
    assert sum(c is not None for c in started) == audio.SFX_CHANNELS


# --- lookup and the silent fallback ------------------------------------------------------------------------

def test_clip_is_looked_up_by_key_in_narration_dir(manager, narr_dir) -> None:
    _clips(narr_dir, "layer03_descent")
    manager.play_narration("layer03_descent")
    assert manager.narration_playing() == "layer03_descent"
    assert manager._narr_chan.get_sound() is manager._narr_sound


def test_ogg_extension_is_accepted_and_wav_wins_when_both_exist(manager, narr_dir) -> None:
    _write_wav(narr_dir / "layer02_descent.ogg", 1.0)      # SDL_mixer sniffs the content, so this loads
    manager.play_narration("layer02_descent")
    assert manager.narration_playing() == "layer02_descent"
    manager.stop_narration()
    _idle(manager)
    _write_wav(narr_dir / "layer04_descent.wav", 1.5)
    _write_wav(narr_dir / "layer04_descent.ogg", 4.0)
    manager.play_narration("layer04_descent")
    assert manager._narr_sound.get_length() == pytest.approx(1.5, abs=0.05)


def test_missing_file_is_silent_and_not_an_error(manager, capsys) -> None:
    manager.play_narration("layer05_miniboss")
    assert manager.narration_playing() is None and not manager._narr_chan.get_busy()
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_missing_file_leaves_the_previous_clip_cut_not_stuck(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1")
    manager.play_narration("intro_card1")
    manager.play_narration("intro_card2")                  # no file: the old clip must still be cut
    assert manager.narration_playing() is None
    assert _idle(manager)


@pytest.mark.parametrize("payload", [b"", b"not audio at all", b"RIFF\x00\x00\x00\x00WAVEjunk"])
def test_corrupt_file_is_silent(manager, narr_dir, capsys, payload) -> None:
    (narr_dir / "layer06_descent.wav").write_bytes(payload)
    manager.play_narration("layer06_descent")
    assert manager.narration_playing() is None and not manager._narr_chan.get_busy()
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_absurdly_short_file_counts_as_broken(manager, narr_dir) -> None:
    _write_wav(narr_dir / "layer07_descent.wav", 0.005)
    manager.play_narration("layer07_descent")
    assert manager.narration_playing() is None


def test_a_failed_key_is_never_retried(manager, narr_dir, monkeypatch) -> None:
    calls: List[str] = []
    real = audio._load_narration
    monkeypatch.setattr(audio, "_load_narration", lambda k, d: calls.append(k) or real(k, d))
    manager.play_narration("layer08_warden")
    _clips(narr_dir, "layer08_warden")                     # the file shows up later: still no retry
    manager.play_narration("layer08_warden")
    manager.play_narration("layer08_warden")
    assert calls == ["layer08_warden"] and manager.narration_playing() is None
    assert "layer08_warden" in manager._narr_failed


def test_a_good_key_is_not_marked_failed_and_can_replay(manager, narr_dir) -> None:
    _clips(narr_dir, "layer09_descent")
    manager.play_narration("layer09_descent")
    manager.stop_narration()
    assert _idle(manager)
    manager.play_narration("layer09_descent")
    assert manager.narration_playing() == "layer09_descent" and not manager._narr_failed


def test_none_or_empty_key_just_stops(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1")
    manager.play_narration("intro_card1")
    manager.play_narration(None)
    assert manager.narration_playing() is None and _idle(manager)
    manager.play_narration("")
    assert manager.narration_playing() is None


# --- skip / replace: a short fade, never a hard cut ----------------------------------------------------------

def test_stop_fades_out_instead_of_cutting_hard(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1")
    manager.play_narration("intro_card1")
    manager.stop_narration()
    assert manager._narr_chan.get_busy(), "still fading for a few ms, no hard stop (that would click)"
    assert manager.narration_playing() is None
    assert _idle(manager, 400), "gone within the cut time"


def test_cut_time_is_short(manager) -> None:
    assert 20 <= audio.NARRATION_CUT_MS <= 200


def test_new_clip_replaces_the_old_one_after_its_fade(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1", "intro_card2")
    manager.play_narration("intro_card1")
    first = manager._narr_sound
    manager.play_narration("intro_card2")
    assert manager.narration_playing() == "intro_card2" and manager._narr_pending
    _settle(manager)
    assert not manager._narr_pending and manager._narr_chan.get_busy()
    assert manager._narr_chan.get_sound() is manager._narr_sound is not first


def test_rapid_skipping_keeps_only_the_last_clip(manager, narr_dir) -> None:
    keys = ["intro_card1", "intro_card2", "layer01_descent", "layer02_descent"]
    _clips(narr_dir, *keys)
    for k in keys:
        manager.play_narration(k)
    _settle(manager)
    assert manager.narration_playing() == "layer02_descent"
    assert manager._narr_chan.get_sound() is manager._narr_sound


def test_stop_clears_a_waiting_clip(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1", "intro_card2")
    manager.play_narration("intro_card1")
    manager.play_narration("intro_card2")
    manager.stop_narration()
    _settle(manager)
    assert _idle(manager) and manager.narration_playing() is None


def test_clip_ends_by_itself(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1", seconds=0.1)
    manager.play_narration("intro_card1")
    pygame.time.wait(300)
    assert manager.narration_playing() is None


# --- volume --------------------------------------------------------------------------------------------------

def test_default_volume_and_clamping(manager) -> None:
    assert manager.narration_volume == audio.NARRATION_VOLUME_DEFAULT == 0.8
    assert manager.set_narration_volume(1.7) == 1.0 and manager.narration_volume == 1.0
    assert manager.set_narration_volume(-0.3) == 0.0
    assert manager.set_narration_volume(0.30000000000000004) == 0.3


def test_volume_is_applied_to_the_clip(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1", "intro_card2")
    manager.set_narration_volume(0.4)
    manager.play_narration("intro_card1")
    assert manager._narr_sound.get_volume() == pytest.approx(0.4, abs=0.01)
    manager.set_narration_volume(0.7)                      # changed while it plays
    assert manager._narr_sound.get_volume() == pytest.approx(0.7, abs=0.01)
    manager.play_narration("intro_card2")
    _settle(manager)
    assert manager._narr_sound.get_volume() == pytest.approx(0.7, abs=0.01)


def test_volume_zero_is_off_and_cuts_a_playing_clip(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1")
    manager.play_narration("intro_card1")
    manager.set_narration_volume(0.0)
    assert manager.narration_playing() is None and _idle(manager)
    manager.play_narration("intro_card1")
    assert manager.narration_playing() is None and not manager._narr_chan.get_busy()


def test_narration_volume_does_not_touch_sfx_or_music_levels(manager) -> None:
    sfx, music = manager.sfx_volume, manager.music_volume
    manager.set_narration_volume(0.1)
    assert (manager.sfx_volume, manager.music_volume) == (sfx, music)


# --- Sound off mutes narration -----------------------------------------------------------------------------

def test_sound_off_cuts_the_clip_and_blocks_new_ones(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1")
    manager.play_narration("intro_card1")
    manager.set_enabled(False)
    assert manager.narration_playing() is None and not manager._narr_chan.get_busy()
    manager.play_narration("intro_card1")
    assert manager.narration_playing() is None and not manager._narr_chan.get_busy()
    manager.set_enabled(True)
    manager.play_narration("intro_card1")
    assert manager.narration_playing() == "intro_card1"


def test_sound_off_drops_a_waiting_clip(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1", "intro_card2")
    manager.play_narration("intro_card1")
    manager.play_narration("intro_card2")
    manager.set_enabled(False)
    pygame.time.wait(150)
    manager.tick(0.2)
    assert not manager._narr_chan.get_busy()


def test_toggle_mutes_narration_too(manager, narr_dir) -> None:
    _clips(narr_dir, "intro_card1")
    manager.play_narration("intro_card1")
    assert manager.toggle() is False
    assert not manager._narr_chan.get_busy()


# --- the game: triggers -------------------------------------------------------------------------------------

@pytest.fixture
def game(make_game, isolated_save, narr_dir):
    """A real Game past the opening cards, with the narration calls recorded (real audio is not driven)."""
    g = make_game()
    calls: List[Tuple[str, Optional[str]]] = []
    a = g.audio
    a.stop_narration()
    pygame.mixer.stop()
    real_play, real_stop = a.play_narration, a.stop_narration
    a.play_narration = lambda key: (calls.append(("play", key)), real_play(key))[0]
    a.stop_narration = lambda *args, **kw: (calls.append(("stop", None)), real_stop(*args, **kw))[0]
    g.calls = calls
    g._start_new_run()
    g.story = None
    g.state = GameState.OVERWORLD
    calls.clear()
    a._narr_failed.clear()      # the setup run above had no clips; forget that so tests can add some
    yield g
    a.play_narration, a.stop_narration = real_play, real_stop
    real_stop()
    a.set_enabled(True)
    a.set_narration_volume(audio.NARRATION_VOLUME_DEFAULT)
    pygame.mixer.stop()


def _played(game) -> List[Optional[str]]:
    return [k for what, k in game.calls if what == "play"]


def _enter(game, node_type: NodeType) -> None:
    node = game.overworld.get_available_nodes()[0]
    node.node_type = node_type
    game._enter_node(node.id)


def test_new_run_narrates_the_three_opening_cards_in_order(game) -> None:
    game._start_new_run()
    assert _played(game) == ["intro_card1"]
    game._advance_story()
    game._advance_story()
    assert _played(game) == ["intro_card1", "intro_card2", "layer01_descent"]
    assert [p.title for p in game.story.pages] == ["You Wake Hungry", "Choose Your Path", "The Verdant Rim"]


def test_finishing_the_opening_stops_the_clip_and_restores_the_music(game) -> None:
    game._start_new_run()
    for _ in range(3):
        game._advance_story()
    assert game.state == GameState.OVERWORLD and game.story is None
    assert game.calls[-1] == ("stop", None)
    assert _played(game) == ["intro_card1", "intro_card2", "layer01_descent"], "nothing plays after the last card"


def test_descent_card_plays_that_layers_clip(game) -> None:
    game.overworld.current_node_id = game.overworld.get_available_nodes()[0].id
    game.overworld.nodes[game.overworld.current_node_id].node_type = NodeType.BOSS
    game._finish_non_combat_node()
    assert game.overworld.act_index == 1
    assert _played(game) == ["layer02_descent"]


@pytest.mark.parametrize("act", [0, 4, 9])
def test_warden_encounter_plays_the_warden_clip(game, act) -> None:
    from blob_evolution.systems.overworld import OverworldMap

    game.overworld = OverworldMap(act_index=act)
    _enter(game, NodeType.BOSS)
    assert game.state == GameState.STORY
    assert _played(game) == [f"layer{act + 1:02d}_warden"]


@pytest.mark.parametrize("level,suffix", [(0, ""), (1, ""), (2, "_ng2"), (4, "_ng2"), (5, "_ng5"), (12, "_ng5")])
def test_warden_clip_follows_the_ng_plus_level(game, level, suffix) -> None:
    game.ng_plus.ng_plus_level = level
    _enter(game, NodeType.BOSS)
    assert _played(game) == [f"layer01_warden{suffix}"]


def test_prime_anchor_has_a_third_tier_at_ng_plus_ten(game) -> None:
    from blob_evolution.systems.overworld import OverworldMap

    game.overworld = OverworldMap(act_index=9)
    game.ng_plus.ng_plus_level = 10
    _enter(game, NodeType.BOSS)
    assert _played(game) == ["layer10_warden_ng10"]


@pytest.mark.parametrize("act", [0, 3, 9])
def test_miniboss_intro_plays_the_lattice_anchor_clip(game, act) -> None:
    from blob_evolution.systems.overworld import OverworldMap

    game.overworld = OverworldMap(act_index=act)
    _enter(game, NodeType.MINIBOSS)
    assert _played(game) == [f"layer{act + 1:02d}_miniboss"]


@pytest.mark.parametrize("node_type", [NodeType.FIGHT, NodeType.ELITE])
def test_ordinary_fights_play_no_narration(game, node_type) -> None:
    _enter(game, node_type)
    assert game.state == GameState.PLAYING and game.calls == []


def test_already_seen_layer_descent_has_no_card_and_no_clip(game) -> None:
    game._seen_acts.add(1)
    game.overworld.current_node_id = game.overworld.get_available_nodes()[0].id
    game.overworld.nodes[game.overworld.current_node_id].node_type = NodeType.BOSS
    game._finish_non_combat_node()
    assert game.calls == []


def test_skipping_a_boss_card_cuts_its_clip_and_the_fight_starts(game, narr_dir) -> None:
    _clips(narr_dir, "layer01_warden")
    _enter(game, NodeType.BOSS)
    assert game.audio.narration_playing() == "layer01_warden"
    game._advance_story()
    assert game.state == GameState.PLAYING and game.audio.narration_playing() is None
    assert _idle(game.audio)


def test_skipping_through_opening_cards_with_real_clips(game, narr_dir) -> None:
    _clips(narr_dir, *audio.OPENING_CLIPS)
    game._start_new_run()
    seen = [game.audio.narration_playing()]
    for _ in range(2):
        game._advance_story()
        _settle(game.audio)
        seen.append(game.audio.narration_playing())
    assert seen == ["intro_card1", "intro_card2", "layer01_descent"]
    game._advance_story()
    assert game.audio.narration_playing() is None and _idle(game.audio)


def test_missing_clips_leave_the_cards_working_exactly_as_before(game, capsys) -> None:
    game._start_new_run()
    while game.state == GameState.STORY:
        game._advance_story()
    assert game.state == GameState.OVERWORLD
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_music_stays_ducked_while_a_clip_plays_and_is_restored(game, narr_dir, monkeypatch) -> None:
    _clips(narr_dir, "layer01_miniboss")
    ducks: List[float] = []
    real = game.audio.duck_music
    monkeypatch.setattr(game.audio, "duck_music", lambda f, immediate=False: (ducks.append(f), real(f, immediate))[0])
    _enter(game, NodeType.MINIBOSS)
    assert game.audio.narration_playing() == "layer01_miniboss" and ducks == [0.5]
    game._advance_story()
    assert ducks == [0.5, 1.0]


def test_sound_off_means_no_clip_on_the_next_card(game, narr_dir) -> None:
    _clips(narr_dir, "layer01_miniboss")
    game.audio.set_enabled(False)
    _enter(game, NodeType.MINIBOSS)
    assert game.audio.narration_playing() is None


# --- Options -------------------------------------------------------------------------------------------------

def _key(game, key: int) -> None:
    game._handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


@pytest.fixture
def options(game):
    game.state = GameState.OPTIONS
    game.options_selected = 4
    return game


def test_options_has_a_narration_row_before_back(options) -> None:
    g = options
    _key(g, pygame.K_s)
    assert g.options_selected == 5
    _key(g, pygame.K_s)
    assert g.options_selected == 0, "six rows now"
    _key(g, pygame.K_w)
    assert g.options_selected == 5


def test_back_still_returns_to_the_main_menu(options) -> None:
    options.options_selected = 5
    _key(options, pygame.K_RETURN)
    assert options.state == GameState.MAIN_MENU


def test_row_four_confirm_does_not_leave_the_menu(options) -> None:
    _key(options, pygame.K_RETURN)
    assert options.state == GameState.OPTIONS


def test_left_right_change_narration_by_ten_percent_and_clamp(options) -> None:
    g = options
    assert g.audio.narration_volume == 0.8
    _key(g, pygame.K_d)
    assert g.audio.narration_volume == 0.9
    _key(g, pygame.K_RIGHT)
    _key(g, pygame.K_d)
    assert g.audio.narration_volume == 1.0
    for _ in range(12):
        _key(g, pygame.K_a)
    assert g.audio.narration_volume == 0.0
    _key(g, pygame.K_LEFT)
    assert g.audio.narration_volume == 0.0
    for _ in range(3):
        _key(g, pygame.K_d)
    assert g.audio.narration_volume == 0.3


def test_the_other_option_rows_are_unchanged(options) -> None:
    g = options
    before = g.audio.narration_volume
    for row in (0, 1, 2, 3):
        g.options_selected = row
        _key(g, pygame.K_d)
    assert g.audio.narration_volume == before
    assert g.audio.enabled is False, "row 3 is still the Sound toggle"


def _option_texts(volume: float) -> List[str]:
    pygame.init()
    renderer = MenuRenderer()
    seen: List[str] = []
    real = renderer.menu_font.render

    class Rec:
        def __getattr__(self, n):
            return getattr(renderer_font, n)

        def render(self, text, *a, **k):
            seen.append(text)
            return real(text, *a, **k)

    renderer_font = renderer.menu_font
    renderer.menu_font = Rec()
    from blob_evolution.utils.enums import Difficulty

    renderer.draw_options(pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT)), 4, Difficulty.NORMAL, False, True, True, volume)
    return seen


@pytest.mark.parametrize("volume,text", [(0.8, "Narration: 80%"), (1.0, "Narration: 100%"), (0.3, "Narration: 30%"), (0.0, "Narration: OFF")])
def test_options_row_text(volume, text) -> None:
    texts = _option_texts(volume)
    assert text in texts and texts[-1] == "Back" and len([t for t in texts if t.startswith("Narration")]) == 1


def test_options_panel_holds_all_six_rows() -> None:
    from blob_evolution.ui import menus
    import inspect

    assert "392" in inspect.getsource(menus.MenuRenderer.draw_options)
    assert 140 + 392 < config.SCREEN_HEIGHT


# --- the saved volume ---------------------------------------------------------------------------------------

def _saved(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_old_save_without_the_field_loads_quietly(make_game, isolated_save, fixture_bytes, capsys) -> None:
    isolated_save.write_bytes(fixture_bytes)
    g = make_game()
    assert g.audio.narration_volume == audio.NARRATION_VOLUME_DEFAULT
    assert g.save_notice is None
    assert capsys.readouterr().err == ""
    assert not list(isolated_save.parent.glob("*.bak*"))
    assert isolated_save.read_bytes() == fixture_bytes, "loading never rewrites the file"


def test_old_save_resaved_has_no_new_key_and_is_otherwise_identical(make_game, isolated_save, fixture_bytes, fixture_data) -> None:
    isolated_save.write_bytes(fixture_bytes)
    g = make_game()
    g._save_game()
    saved = _saved(isolated_save)
    assert "narration_volume" not in saved
    fixture_data["ng_plus"]["best_map_reached"] = 9     # TASK-013c migration, unrelated to narration
    assert saved == fixture_data


def test_changed_volume_is_saved_as_a_plain_number_and_reloaded(make_game, isolated_save, fixture_bytes, capsys) -> None:
    isolated_save.write_bytes(fixture_bytes)
    g = make_game()
    g.audio.set_narration_volume(0.5)
    g._save_game()
    saved = _saved(isolated_save)
    assert saved["narration_volume"] == 0.5 and type(saved["narration_volume"]) is float
    g2 = make_game()
    assert g2.audio.narration_volume == 0.5 and g2.save_notice is None
    assert capsys.readouterr().err == ""
    assert not list(isolated_save.parent.glob("*.bak*"))


def test_saved_zero_means_off_and_survives(make_game, isolated_save, fixture_bytes) -> None:
    isolated_save.write_bytes(fixture_bytes)
    g = make_game()
    g.audio.set_narration_volume(0.0)
    g._save_game()
    assert _saved(isolated_save)["narration_volume"] == 0
    assert make_game().audio.narration_volume == 0.0


def test_the_only_bool_in_the_save_is_still_audio_enabled(make_game, isolated_save, fixture_bytes) -> None:
    isolated_save.write_bytes(fixture_bytes)
    g = make_game()
    g.audio.set_narration_volume(0.3)
    g._save_game()
    assert isinstance(_saved(isolated_save)["audio_enabled"], bool)
    assert not isinstance(_saved(isolated_save)["narration_volume"], bool)


def test_a_saved_default_value_is_kept_on_resave(make_game, isolated_save, fixture_data) -> None:
    fixture_data["narration_volume"] = audio.NARRATION_VOLUME_DEFAULT
    isolated_save.write_text(json.dumps(fixture_data, indent=2), encoding="utf-8")
    g = make_game()
    assert g.save_notice is None
    g._save_game()
    fixture_data["ng_plus"]["best_map_reached"] = 9     # TASK-013c migration, unrelated to narration
    assert _saved(isolated_save) == fixture_data


@pytest.mark.parametrize("bad", ["loud", "0.5", True, False, None, [0.5], {"v": 1}])
def test_wrong_typed_value_takes_the_safe_default_path(make_game, isolated_save, fixture_data, capsys, bad) -> None:
    fixture_data["narration_volume"] = bad
    isolated_save.write_text(json.dumps(fixture_data), encoding="utf-8")
    g = make_game()
    assert g.audio.narration_volume == audio.NARRATION_VOLUME_DEFAULT
    assert g.save_notice == "partial"
    assert "invalid data" in capsys.readouterr().err
    assert list(isolated_save.parent.glob("*.bak*")), "backed up like any other rejected field"
    g._save_game()
    assert _saved(isolated_save)["narration_volume"] == audio.NARRATION_VOLUME_DEFAULT, "rewritten as a real number"


@pytest.mark.parametrize("raw,expected", [(7, 1.0), (1.5, 1.0), (-2, 0.0), (0.456, 0.46)])
def test_out_of_range_numbers_are_clamped_quietly(make_game, isolated_save, fixture_data, capsys, raw, expected) -> None:
    fixture_data["narration_volume"] = raw
    isolated_save.write_text(json.dumps(fixture_data), encoding="utf-8")
    g = make_game()
    assert g.audio.narration_volume == expected and g.save_notice is None
    assert capsys.readouterr().err == ""


def test_narration_save_key_is_the_only_new_top_level_key(make_game, isolated_save, fixture_bytes) -> None:
    isolated_save.write_bytes(fixture_bytes)
    g = make_game()
    g.audio.set_narration_volume(0.2)
    g._save_game()
    assert set(_saved(isolated_save)) == {"ng_plus", "permanent", "economy", "audio_enabled", "narration_volume"}


def test_loading_a_save_without_the_field_resets_to_the_default(make_game, isolated_save, fixture_bytes) -> None:
    audio.get_audio().set_narration_volume(0.2)
    isolated_save.write_bytes(fixture_bytes)
    assert make_game().audio.narration_volume == audio.NARRATION_VOLUME_DEFAULT
