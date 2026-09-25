"""Procedural audio: SFX and simple looping melodies via pygame.mixer."""

from __future__ import annotations

import array
import math
import random
from typing import Dict, List, Optional, Tuple, Union

import pygame


SAMPLE_RATE = 22050

# Named pitches (Hz)
C3, D3, E3, F3, G3, A3, B3 = 130.81, 146.83, 164.81, 174.61, 196.00, 220.00, 246.94
C4, D4, E4, F4, G4, A4, B4 = 261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88
C5, D5, E5, F5, G5, A5 = 523.25, 587.33, 659.25, 698.46, 783.99, 880.00


def _envelope(i: int, n: int, attack: float = 0.01, release: float = 0.08) -> float:
    """Simple ASR envelope."""
    a = int(SAMPLE_RATE * attack)
    r = int(SAMPLE_RATE * release)
    if a > 0 and i < a:
        return i / a
    if r > 0 and i > n - r:
        return max(0.0, (n - i) / r)
    return 1.0


def _tone(
    freq: float,
    duration: float,
    volume: float = 0.35,
    wave: str = "sine",
    attack: float = 0.01,
    release: float = 0.08,
) -> pygame.mixer.Sound:
    """Synthesize a mono 16-bit tone as a Sound."""
    n = max(1, int(SAMPLE_RATE * duration))
    buf = array.array("h")
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _envelope(i, n, attack, release) * volume
        phase = 2.0 * math.pi * freq * t
        if wave == "square":
            sample = 1.0 if math.sin(phase) >= 0 else -1.0
            sample *= 0.55
        elif wave == "triangle":
            sample = 2.0 * abs(2.0 * ((freq * t) % 1.0) - 1.0) - 1.0
        elif wave == "saw":
            sample = 2.0 * ((freq * t) % 1.0) - 1.0
            sample *= 0.45
        elif wave == "noise":
            sample = random.uniform(-1.0, 1.0)
        else:
            sample = math.sin(phase)
        val = int(max(-32767, min(32767, sample * env * 32767)))
        buf.append(val)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _chord(freqs: list, duration: float, volume: float = 0.2) -> pygame.mixer.Sound:
    """Layer several sines into one buffer (SFX stingers only)."""
    n = max(1, int(SAMPLE_RATE * duration))
    buf = array.array("h")
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _envelope(i, n, 0.05, 0.2) * volume
        sample = 0.0
        for f in freqs:
            sample += math.sin(2.0 * math.pi * f * t)
        sample /= max(1, len(freqs))
        val = int(max(-32767, min(32767, sample * env * 32767)))
        buf.append(val)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _note_sample(
    freq: float,
    duration: float,
    volume: float,
    wave: str = "triangle",
) -> List[int]:
    """Render one note (or silence if freq <= 0) as sample list."""
    n = max(1, int(SAMPLE_RATE * duration))
    # Leave a tiny gap so notes don't smear into a drone
    gap = min(int(SAMPLE_RATE * 0.03), n // 5)
    sounding = max(1, n - gap)
    out: List[int] = []
    if freq <= 0:
        return [0] * n
    for i in range(sounding):
        t = i / SAMPLE_RATE
        env = _envelope(i, sounding, 0.012, 0.06) * volume
        phase = 2.0 * math.pi * freq * t
        if wave == "square":
            sample = (1.0 if math.sin(phase) >= 0 else -1.0) * 0.5
        elif wave == "triangle":
            sample = 2.0 * abs(2.0 * ((freq * t) % 1.0) - 1.0) - 1.0
        else:
            sample = math.sin(phase)
        out.append(int(max(-32767, min(32767, sample * env * 32767))))
    out.extend([0] * (n - sounding))
    return out


def _mix_tracks(tracks: List[List[int]], volume: float = 1.0) -> pygame.mixer.Sound:
    """Mix equal-length (or pad shorter) mono tracks into one Sound."""
    length = max((len(t) for t in tracks), default=1)
    buf = array.array("h")
    for i in range(length):
        sample = 0.0
        for track in tracks:
            if i < len(track):
                sample += track[i]
        sample = sample * volume / max(1, len(tracks))
        buf.append(int(max(-32767, min(32767, sample))))
    return pygame.mixer.Sound(buffer=buf.tobytes())


Note = Union[float, int]  # Hz, or 0 = rest


def _sequence(
    notes: List[Tuple[Note, float]],
    volume: float = 0.22,
    wave: str = "triangle",
) -> List[int]:
    """Build a monophonic phrase from (freq, duration_seconds) pairs."""
    samples: List[int] = []
    for freq, dur in notes:
        samples.extend(_note_sample(float(freq), dur, volume, wave))
    return samples


# Beat length helpers
B = 0.18       # sixteenth-ish
Q = B * 2      # eighth
H = B * 4      # quarter
W = B * 8      # half


def _build_menu_theme() -> pygame.mixer.Sound:
    """Bright looping menu motif."""
    melody = _sequence([
        (E4, Q), (G4, Q), (A4, Q), (G4, Q),
        (E4, Q), (D4, Q), (C4, H),
        (E4, Q), (G4, Q), (A4, Q), (C5, Q),
        (B4, Q), (A4, Q), (G4, H),
    ], volume=0.20, wave="triangle")
    bass = _sequence([
        (C3, H), (G3, H), (A3, H), (E3, H),
        (C3, H), (G3, H), (F3, H), (G3, H),
    ], volume=0.14, wave="sine")
    return _mix_tracks([melody, bass], volume=0.95)


def _build_act_theme(act: int) -> pygame.mixer.Sound:
    """Simple act-flavored looping phrase."""
    # (melody notes, bass notes, melody wave, tempo scale)
    themes = [
        # 0 Rim — gentle green
        (
            [(G4, Q), (A4, Q), (B4, Q), (A4, Q), (G4, Q), (E4, Q), (D4, H),
             (E4, Q), (G4, Q), (A4, H), (G4, H)],
            [(C3, H), (E3, H), (G3, H), (E3, H), (C3, H), (G3, H)],
            "triangle",
        ),
        # 1 Rot — murky minor
        (
            [(D4, Q), (F4, Q), (G4, Q), (F4, Q), (D4, H), (C4, H),
             (D4, Q), (F4, Q), (A4, Q), (G4, Q), (F4, H)],
            [(D3, H), (A3, H), (F3, H), (A3, H), (D3, W)],
            "triangle",
        ),
        # 2 Echoes — crystalline
        (
            [(A4, Q), (0, Q), (C5, Q), (0, Q), (E5, Q), (0, Q), (C5, Q), (0, Q),
             (A4, Q), (C5, Q), (E5, H), (D5, H)],
            [(A3, H), (E3, H), (A3, H), (C4, H), (A3, W)],
            "sine",
        ),
        # 3 Ash — punchy
        (
            [(E4, B), (E4, B), (G4, Q), (A4, Q), (G4, Q), (E4, Q), (D4, H),
             (E4, B), (G4, B), (A4, Q), (B4, Q), (A4, H)],
            [(E3, Q), (E3, Q), (G3, H), (A3, H), (E3, H), (B3, H)],
            "square",
        ),
        # 4 Frost — sparse
        (
            [(C5, H), (0, Q), (A4, H), (0, Q), (G4, H), (0, Q),
             (A4, Q), (C5, Q), (E5, H)],
            [(C3, W), (A3, W), (G3, W)],
            "sine",
        ),
        # 5 Thirst — swaying
        (
            [(F4, Q), (A4, Q), (C5, Q), (A4, Q), (G4, Q), (F4, Q), (D4, H),
             (F4, Q), (A4, Q), (G4, H), (F4, H)],
            [(F3, H), (C4, H), (D3, H), (A3, H), (F3, W)],
            "triangle",
        ),
        # 6 Masks — odd intervals
        (
            [(E4, Q), (G4, Q), (A4, Q), (C5, Q), (B4, Q), (G4, Q), (A4, H),
             (E4, Q), (A4, Q), (G4, H), (E4, H)],
            [(E3, H), (A3, H), (G3, H), (B3, H), (E3, W)],
            "triangle",
        ),
        # 7 Silence — low & thin
        (
            [(G3, H), (0, Q), (A3, H), (0, Q), (B3, H), (0, Q),
             (A3, Q), (G3, Q), (E3, H)],
            [(E3, W), (0, H), (G3, W), (0, H)],
            "sine",
        ),
        # 8 Ascent — rising fanfare-ish
        (
            [(C4, Q), (E4, Q), (G4, Q), (A4, Q), (G4, Q), (E4, Q), (C5, H),
             (B4, Q), (A4, Q), (G4, H), (C5, H)],
            [(C3, H), (G3, H), (E3, H), (G3, H), (C3, W)],
            "triangle",
        ),
        # 9 Divide — tense
        (
            [(A3, Q), (C4, Q), (E4, Q), (C4, Q), (A3, Q), (G3, Q), (A3, H),
             (C4, Q), (E4, Q), (F4, Q), (E4, Q), (C4, H)],
            [(110.0, H), (E3, H), (A3, H), (E3, H), (110.0, W)],
            "square",
        ),
    ]
    idx = max(0, min(act, len(themes) - 1))
    mel_notes, bass_notes, wave = themes[idx]
    melody = _sequence(mel_notes, volume=0.18, wave=wave)
    bass = _sequence(bass_notes, volume=0.12, wave="sine")
    # Match lengths by padding the shorter track with silence
    if len(melody) < len(bass):
        melody = melody + [0] * (len(bass) - len(melody))
    elif len(bass) < len(melody):
        bass = bass + [0] * (len(melody) - len(bass))
    return _mix_tracks([melody, bass], volume=0.9)


class AudioManager:
    """Global procedural sound manager."""

    def __init__(self) -> None:
        self.enabled = True
        self.sfx_volume = 0.55
        self.music_volume = 0.32
        self._ready = False
        self._sfx: Dict[str, pygame.mixer.Sound] = {}
        self._tracks: Dict[str, pygame.mixer.Sound] = {}
        self._music_channel: Optional[pygame.mixer.Channel] = None
        self._current_track: Optional[str] = None
        self._init_mixer()

    def _init_mixer(self) -> None:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
                pygame.mixer.init()
            pygame.mixer.set_num_channels(16)
            self._build_library()
            self._music_channel = pygame.mixer.Channel(15)
            self._ready = True
        except pygame.error:
            self._ready = False

    def _build_library(self) -> None:
        self._sfx = {
            "ui_select": _tone(660, 0.05, 0.25, "sine", 0.005, 0.03),
            "ui_confirm": _chord([523, 784], 0.12, 0.22),
            "shoot": _tone(880, 0.04, 0.18, "square", 0.002, 0.03),
            "dash": _tone(180, 0.12, 0.3, "saw", 0.005, 0.08),
            "hit": _tone(220, 0.06, 0.28, "square", 0.002, 0.04),
            "hurt": _tone(140, 0.15, 0.35, "saw", 0.005, 0.1),
            "kill": _chord([392, 523, 659], 0.14, 0.25),
            "explode": _tone(90, 0.22, 0.4, "noise", 0.001, 0.15),
            "levelup": _chord([523, 659, 784, 1046], 0.35, 0.28),
            "pickup": _tone(740, 0.08, 0.22, "sine", 0.005, 0.05),
            "boss_hit": _tone(160, 0.08, 0.32, "square", 0.002, 0.06),
            "boss_phase": _chord([110, 165, 220], 0.45, 0.35),
            "boss_spawn": _chord([98, 147, 196], 0.5, 0.3),
            "victory": _chord([523, 659, 784, 1046], 0.7, 0.3),
            "defeat": _chord([196, 185, 147], 0.6, 0.28),
            "story": _tone(330, 0.1, 0.18, "sine", 0.02, 0.06),
            "absorb": _tone(300, 0.1, 0.25, "sine", 0.01, 0.06),
        }
        self._tracks["menu"] = _build_menu_theme()
        for i in range(10):
            self._tracks[f"act_{i}"] = _build_act_theme(i)
        for sound in self._tracks.values():
            sound.set_volume(self.music_volume)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.stop_music()
            if self._ready:
                pygame.mixer.stop()

    def toggle(self) -> bool:
        self.set_enabled(not self.enabled)
        return self.enabled

    def play(self, name: str, volume_scale: float = 1.0) -> None:
        if not self.enabled or not self._ready:
            return
        sound = self._sfx.get(name)
        if not sound:
            return
        sound.set_volume(max(0.0, min(1.0, self.sfx_volume * volume_scale)))
        sound.play()

    def _play_track(self, key: str) -> None:
        if not self.enabled or not self._ready or not self._music_channel:
            return
        track = self._tracks.get(key)
        if not track:
            return
        if self._current_track == key and self._music_channel.get_busy():
            return
        self._current_track = key
        track.set_volume(self.music_volume)
        self._music_channel.play(track, loops=-1, fade_ms=400)

    def play_act_music(self, act_index: int) -> None:
        """Start looping act theme."""
        idx = max(0, min(act_index, 9))
        self._play_track(f"act_{idx}")

    def play_menu_music(self) -> None:
        """Start looping menu theme (separate from act 0)."""
        self._play_track("menu")

    def stop_music(self) -> None:
        if self._music_channel:
            self._music_channel.fadeout(350)
        self._current_track = None


_audio: Optional[AudioManager] = None


def get_audio() -> AudioManager:
    """Return singleton audio manager."""
    global _audio
    if _audio is None:
        _audio = AudioManager()
    return _audio
