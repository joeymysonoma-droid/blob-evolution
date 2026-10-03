"""Audio: synthesized sounds plus Director-approved files, with generated fallback (pygame.mixer).

Layered SFX and looping act themes are generated at runtime in pure Python (no numpy). Director-approved
files override them where present: eleven SFX WAVs in blob_evolution/assets/sfx (TASK-027), the mp3 music in
blob_evolution/assets/music (TASK-026) and optional narration clips in blob_evolution/assets/narration
(TASK-028). When a file is missing or will not load, the generated sound or theme is used instead (narration
has no generated fallback and stays silent).
The mixer opens 21 channels: 18 SFX + 2 music + 1 narration.
Rendering works on float buffers (lists of floats, nominal range -1..1) and only
the last step (`_finish` / `_to_sound`) converts to 16-bit mono Sounds.

Layout:
  1. note constants + beat helpers
  2. DSP helpers  (_osc, _env, _voice, _noise_burst, _filter, _echo, _layer, _finish ...)
  3. legacy API   (_tone, _chord, _note_sample, _sequence, _mix_tracks)  -- same signatures,
                  only optional kwargs were added
  4. drum helper (_drums) and loop helper (_loop_fit, _Grid)
  5. SFX library  (_build_sfx)
  6. music        (menu + 10 act themes)
  7. recorded music (TRACK_FILES, _loop_from_sound)
  8. recorded narration (NARRATION_DIR, clip keys, one reserved channel; TASK-028)
  9. AudioManager / get_audio  (public API unchanged; act tracks are built lazily)
"""

from __future__ import annotations

import array
import math
import random
import time
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple, Union

import pygame

from blob_evolution.data.lore import NG_WARDEN_QUOTES


SAMPLE_RATE = 22050
_SR = float(SAMPLE_RATE)
_TWO_PI = 2.0 * math.pi
_CENT = math.log(2.0) / 1200.0

# Deterministic noise source (re-seeded per sound / track so builds are repeatable)
_rng = random.Random(24)

# Named pitches (Hz)
C2, D2, E2, F2, G2, A2, B2 = 65.41, 73.42, 82.41, 87.31, 98.00, 110.00, 123.47     # NEW: low octave
C3, D3, E3, F3, G3, A3, B3 = 130.81, 146.83, 164.81, 174.61, 196.00, 220.00, 246.94
C4, D4, E4, F4, G4, A4, B4 = 261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88
C5, D5, E5, F5, G5, A5 = 523.25, 587.33, 659.25, 698.46, 783.99, 880.00
B5, C6, D6, E6 = 987.77, 1046.50, 1174.66, 1318.51                                  # NEW: top octave
# NEW: accidentals (sharp names; flats are aliases)
Bb2, Bb3, Bb4 = 116.54, 233.08, 466.16
Cs4, Cs5 = 277.18, 554.37
Eb3, Eb4, Eb5 = 155.56, 311.13, 622.25
Fs3, Fs4, Fs5 = 185.00, 369.99, 739.99
Gs3, Gs4, Gs5 = 207.65, 415.30, 830.61
Ab3, Ab4 = Gs3, Gs4
Db4 = Cs4

# Beat helpers for SFX (0.18 s base). Music themes use _Grid(bpm) instead.
B = 0.18       # sixteenth-ish
Q = B * 2      # eighth
H = B * 4      # quarter
W = B * 8      # half

Note = Union[float, int]  # Hz, or 0 = rest
Buf = List[float]


# ---------------------------------------------------------------------------
# 2. DSP helpers (float buffers)
# ---------------------------------------------------------------------------

def _pair(v) -> Optional[Tuple[float, float]]:
    """Accept None, a number, or (start, end) and return (start, end) or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v), float(v)
    return float(v[0]), float(v[1])


def _envelope(i: int, n: int, attack: float = 0.01, release: float = 0.08) -> float:
    """Simple ASR envelope (legacy helper, kept for compatibility)."""
    a = int(SAMPLE_RATE * attack)
    r = int(SAMPLE_RATE * release)
    if a > 0 and i < a:
        return i / a
    if r > 0 and i > n - r:
        return max(0.0, (n - i) / r)
    return 1.0


def _env(
    n: int,
    attack: float = 0.01,
    decay: Optional[float] = None,
    sustain: float = 1.0,
    release: float = 0.08,
) -> Buf:
    """ADSR-style envelope of n samples.

    attack  : linear ramp 0 -> 1 (seconds)
    decay   : exponential fall from 1 toward `sustain`, reaching ~1% of the gap after
              `decay` seconds (None = no decay stage, plain ASR)
    sustain : level held after the decay (0 = pluck / percussive)
    release : linear fade to 0 over the last `release` seconds (overlaps the body)
    """
    a = min(n, int(attack * SAMPLE_RATE))
    env: Buf = [i / a for i in range(a)] if a > 0 else []
    rem = n - a
    if rem > 0:
        if decay is None or sustain >= 1.0:
            env.extend([1.0] * rem)
        else:
            dn = max(1, min(rem, int(decay * SAMPLE_RATE)))
            k = math.exp(-4.6 / dn)
            x = 1.0 - sustain
            seg: Buf = []
            for _ in range(dn):
                seg.append(sustain + x)
                x *= k
            env.extend(seg)
            env.extend([sustain] * (rem - dn))
    r = min(n, int(release * SAMPLE_RATE))
    if r > 0:
        base = n - r
        for j in range(r):
            env[base + j] *= (r - j) / r
    return env


def _osc(
    wave: str,
    freq: float,
    n: int,
    f_end: Optional[float] = None,
    sweep: str = "exp",
    vibrato: Optional[Tuple[float, float]] = None,
    detune: float = 0.0,
) -> Buf:
    """Unit oscillator (n samples). Phase-accumulating, so pitch sweeps are click-free.

    wave   : sine | square | triangle | saw | noise   (square scaled 0.55, saw 0.45)
    f_end  : if given, pitch glides freq -> f_end over the buffer ("exp" or "lin")
    vibrato: (rate_hz, depth_cents)
    detune : constant offset in cents
    """
    if n <= 0:
        return []
    if wave == "noise":
        rnd = _rng.random
        return [rnd() * 2.0 - 1.0 for _ in range(n)]
    det = 2.0 ** (detune / 1200.0) if detune else 1.0
    isr = 1.0 / _SR
    sin = math.sin
    if f_end is None and not vibrato:
        inc = freq * det * isr
        if wave not in ("square", "triangle", "saw"):
            w = _TWO_PI * inc
            return [sin(w * i) for i in range(n)]
        ph = [(inc * i) % 1.0 for i in range(n)]
    else:
        ph = []
        p = 0.0
        f0 = freq * det
        f1 = (f_end if f_end else freq) * det
        ratio = (f1 / f0) ** (1.0 / max(1, n - 1)) if f0 > 0 else 1.0
        step = (f1 - f0) / max(1, n - 1)
        f = f0
        use_exp = sweep != "lin"
        if vibrato:
            vw = _TWO_PI * vibrato[0] * isr
            vd = vibrato[1] * _CENT
            for i in range(n):
                p += f * (1.0 + vd * sin(vw * i)) * isr
                p -= int(p)
                ph.append(p)
                f = f * ratio if use_exp else f + step
        else:
            for i in range(n):
                p += f * isr
                p -= int(p)
                ph.append(p)
                f = f * ratio if use_exp else f + step
    if wave == "square":
        return [0.55 if p < 0.5 else -0.55 for p in ph]
    if wave == "saw":
        return [(2.0 * p - 1.0) * 0.45 for p in ph]
    if wave == "triangle":
        return [4.0 * abs(p - 0.5) - 1.0 for p in ph]
    return [sin(_TWO_PI * p) for p in ph]


def _norm(buf: Buf, peak: float = 1.0) -> Buf:
    """Scale a buffer so its absolute maximum equals `peak`."""
    m = max((abs(v) for v in buf), default=0.0)
    if m <= 1e-12:
        return buf
    g = peak / m
    return [v * g for v in buf]


def _voice(
    wave: str,
    freq: float,
    duration: float,
    vol: float = 1.0,
    a: float = 0.005,
    d: Optional[float] = None,
    s: float = 1.0,
    r: float = 0.02,
    f_end: Optional[float] = None,
    sweep: str = "exp",
    vib: Optional[Tuple[float, float]] = None,
    det: float = 0.0,
    lp: Union[None, float, Tuple[float, float]] = None,
) -> Buf:
    """One enveloped oscillator: osc * ADSR * vol (optionally low-passed, then re-leveled)."""
    n = max(1, int(SAMPLE_RATE * duration))
    o = _osc(wave, freq, n, f_end, sweep, vib, det)
    if lp is not None:
        o = _norm(_filter(o, "lp", *_pair(lp)), 1.0)
    e = _env(n, a, d, s, r)
    return [x * y * vol for x, y in zip(o, e)]


def _filter(buf: Buf, kind: str = "lp", f0: float = 1000.0, f1: Optional[float] = None, poles: int = 1,
            sr: Optional[float] = None) -> Buf:
    """One-pole (or cascaded) low/high-pass with a cutoff swept f0 -> f1 (exponentially).
    `sr` = sample rate of `buf` (default SAMPLE_RATE; used by _wash)."""
    n = len(buf)
    if n == 0:
        return buf
    if f1 is None:
        f1 = f0
    f0 = max(20.0, f0)
    f1 = max(20.0, f1)
    ratio = f1 / f0
    exp = math.exp
    rate = sr or _SR
    src = buf
    block = 64
    for _ in range(max(1, poles)):
        y = 0.0
        res = [0.0] * n
        for s in range(0, n, block):
            f = min(f0 * ratio ** (s / n), 0.45 * rate)
            a = 1.0 - exp(-_TWO_PI * f / rate)
            for i in range(s, min(n, s + block)):
                y += a * (src[i] - y)
                res[i] = y
        src = res
    if kind == "hp":
        return [x - y for x, y in zip(buf, src)]
    return src


def _noise_burst(
    duration: float,
    vol: float = 1.0,
    a: float = 0.002,
    d: Optional[float] = None,
    s: float = 1.0,
    r: float = 0.01,
    lp: Union[None, float, Tuple[float, float]] = None,
    hp: Union[None, float, Tuple[float, float]] = None,
    poles: int = 1,
) -> Buf:
    """Enveloped white noise with optional swept low-pass / high-pass (leveled to peak 1 first)."""
    n = max(1, int(SAMPLE_RATE * duration))
    x = _osc("noise", 0.0, n)
    if hp is not None:
        x = _filter(x, "hp", *_pair(hp), poles=poles)
    if lp is not None:
        x = _filter(x, "lp", *_pair(lp), poles=poles)
    x = _norm(x, 1.0)
    e = _env(n, a, d, s, r)
    return [u * v * vol for u, v in zip(x, e)]


def _echo(buf: Buf, delay: float, feedback: float = 0.45, mix: float = 0.35, taps: int = 3) -> Buf:
    """Feedback-style echo: dry + `taps` repeats, each `delay` later and `feedback` x quieter.

    First repeat has gain `mix`. The result is `taps * delay` seconds LONGER than the input.
    """
    d = int(delay * SAMPLE_RATE)
    n = len(buf)
    if d <= 0 or taps <= 0 or n == 0:
        return buf
    out = list(buf) + [0.0] * (d * taps)
    g = mix
    for k in range(1, taps + 1):
        off = d * k
        seg = out[off:off + n]
        out[off:off + n] = [u + v * g for u, v in zip(seg, buf)]
        g *= feedback
    return out


def _layer(parts: Sequence[Tuple[Buf, float, float]], length: Optional[int] = None) -> Buf:
    """Mix [(buffer, offset_seconds, gain), ...] into one float buffer (sum, no normalization)."""
    total = 0
    for buf, off, _g in parts:
        total = max(total, int(off * SAMPLE_RATE) + len(buf))
    if length is not None:
        total = max(total, length)
    out = [0.0] * total
    for buf, off, g in parts:
        o = int(off * SAMPLE_RATE)
        seg = out[o:o + len(buf)]
        out[o:o + len(buf)] = [u + v * g for u, v in zip(seg, buf)]
    return out


def _fade_edges(buf: Buf, ms: float = 2.0) -> Buf:
    """Linear fade-in / fade-out over `ms` milliseconds (kills edge clicks)."""
    f = min(len(buf) // 2, max(1, int(SAMPLE_RATE * ms / 1000.0)))
    for i in range(f):
        g = i / f
        buf[i] *= g
        buf[-1 - i] *= g
    return buf


def _to_int16(buf: Buf) -> array.array:
    out = array.array("h")
    out.extend([int(max(-32767.0, min(32767.0, v * 32767.0))) for v in buf])
    return out


def _to_sound(buf: Buf) -> pygame.mixer.Sound:
    return pygame.mixer.Sound(buffer=_to_int16(buf or [0.0]).tobytes())


def _finish(buf: Buf, peak: float = 0.3, fade_ms: float = 2.0) -> pygame.mixer.Sound:
    """Normalize to `peak` (fraction of full scale), fade edges ~2 ms, return a Sound.

    Volume is safe by construction: nothing leaves this function above `peak`.
    """
    buf = _norm(list(buf), peak)
    _fade_edges(buf, fade_ms)
    return _to_sound(buf)


def _loop_fit(buf: Buf, n: int) -> Buf:
    """Force `buf` to exactly n samples. Overflow (echo / release tails) is folded back
    onto the start so a looping buffer stays seamless; short buffers are zero-padded."""
    m = len(buf)
    if m == n:
        return buf
    if m < n:
        return buf + [0.0] * (n - m)
    out = buf[:n]
    for k in range(n, m, n):
        seg = buf[k:k + n]
        out[:len(seg)] = [u + v for u, v in zip(out[:len(seg)], seg)]
    return out


class _Grid:
    """Tempo grid. B/Q/H/W follow the global helpers (sixteenth, eighth, quarter, half)
    but scale with `bpm`. `bar` = `beats` quarter notes (4 = 4/4, 3.5 = 7/8)."""

    def __init__(self, bpm: float, beats: float = 4.0) -> None:
        self.beat = 60.0 / bpm
        self.B = self.beat / 4.0
        self.Q = self.beat / 2.0
        self.H = self.beat
        self.W = self.beat * 2.0
        self.T = self.beat / 3.0     # triplet eighth
        self.bar = self.beat * beats
        self.bpm = bpm

    def samples(self, bars: int) -> int:
        return int(round(self.bar * bars * SAMPLE_RATE))


def _wash(
    duration: float,
    vol: float = 1.0,
    a: float = 0.5,
    r: float = 0.5,
    lp: Tuple[float, float] = (400.0, 900.0),
    factor: int = 8,
) -> Buf:
    """Cheap low-frequency noise texture (wind / breath): noise is generated and filtered at
    SAMPLE_RATE/factor and linearly interpolated back up. Only valid for cutoffs < ~1.2 kHz."""
    n = max(1, int(SAMPLE_RATE * duration))
    m = n // factor + 2
    rnd = _rng.random
    x = [rnd() * 2.0 - 1.0 for _ in range(m)]
    x = _filter(x, "lp", lp[0], lp[1], sr=_SR / factor)
    out: Buf = []
    for k in range(m - 1):
        u = x[k]
        d = (x[k + 1] - u) / factor
        out.extend([u + d * j for j in range(factor)])
    x = _norm(out[:n], 1.0)
    e = _env(n, a, None, 1.0, r)
    return [u * v * vol for u, v in zip(x, e)]


# ---------------------------------------------------------------------------
# 3. Legacy API (backward compatible; new behaviour is opt-in via keyword args)
# ---------------------------------------------------------------------------

def _tone(
    freq: float,
    duration: float,
    volume: float = 0.35,
    wave: str = "sine",
    attack: float = 0.01,
    release: float = 0.08,
    *,
    decay: Optional[float] = None,
    sustain: float = 1.0,
    f_end: Optional[float] = None,
    sweep: str = "exp",
    vibrato: Optional[Tuple[float, float]] = None,
    detune: float = 0.0,
    echo: Optional[Tuple[float, float, float, int]] = None,
) -> pygame.mixer.Sound:
    """Synthesize a mono 16-bit tone as a Sound (amplitude = `volume`, not normalized).

    Old behaviour (ASR) is unchanged. New optional args: `decay`/`sustain` (exponential
    decay stage), `f_end`/`sweep` (pitch glide), `vibrato=(Hz, cents)`, `detune` (cents),
    `echo=(delay, feedback, mix, taps)`.
    """
    n = max(1, int(SAMPLE_RATE * duration))
    o = _osc(wave, freq, n, f_end, sweep, vibrato, detune)
    e = _env(n, attack, decay, sustain, release)
    buf = [x * y * volume for x, y in zip(o, e)]
    if echo:
        buf = _echo(buf, *echo)
    return _to_sound(buf)


def _chord(
    freqs: list,
    duration: float,
    volume: float = 0.2,
    *,
    wave: str = "sine",
    attack: float = 0.05,
    release: float = 0.2,
    decay: Optional[float] = None,
    sustain: float = 1.0,
    detune: float = 0.0,
    echo: Optional[Tuple[float, float, float, int]] = None,
) -> pygame.mixer.Sound:
    """Layer several oscillators into one Sound (average of voices, then envelope)."""
    n = max(1, int(SAMPLE_RATE * duration))
    voices = [_osc(wave, f, n, detune=detune * (1 if k % 2 == 0 else -1)) for k, f in enumerate(freqs)]
    e = _env(n, attack, decay, sustain, release)
    cnt = float(max(1, len(voices)))
    buf = [sum(vs) / cnt * ev * volume for vs, ev in zip(zip(*voices), e)] if voices else [0.0] * n
    if echo:
        buf = _echo(buf, *echo)
    return _to_sound(buf)


# Per-note render cache (cleared after each music track so memory stays flat)
_NOTE_CACHE: Dict[tuple, Buf] = {}


def _note_buf(
    freqs: tuple,
    sounding: int,
    wave: str,
    attack: float,
    decay: Optional[float],
    sustain: float,
    release: float,
    vibrato: Optional[Tuple[float, float]],
    detune: float,
) -> Buf:
    key = (freqs, sounding, wave, attack, decay, sustain, release, vibrato, detune)
    hit = _NOTE_CACHE.get(key)
    if hit is not None:
        return hit
    cnt = float(len(freqs))
    voices = []
    for k, f in enumerate(freqs):
        det = detune * (1 if k % 2 == 0 else -1) if len(freqs) > 1 else detune
        voices.append(_osc(wave, f, sounding, None, "exp", vibrato, det))
    if len(voices) == 1:
        o = voices[0]
    else:
        o = [sum(vs) / cnt for vs in zip(*voices)]
    e = _env(sounding, attack, decay, sustain, release)
    out = [x * y for x, y in zip(o, e)]
    _NOTE_CACHE[key] = out
    return out


def _sequence_f(
    notes: list,
    volume: float = 0.22,
    wave: str = "triangle",
    *,
    attack: Optional[float] = None,
    decay: Optional[float] = None,
    sustain: float = 1.0,
    release: Optional[float] = None,
    gap: Optional[float] = None,
    vibrato: Optional[Tuple[float, float]] = None,
    detune: float = 0.0,
) -> Buf:
    """Float version of `_sequence`.

    `notes` items are (freq, seconds) or (freq, seconds, velocity). `freq` may be a
    tuple/list of Hz (a chord, voices averaged) or 0 for a rest. Start times come from
    cumulative durations (rounded once), so long phrases never drift.
    Defaults reproduce the old note shape (12 ms attack, 60 ms release, 30 ms gap).
    """
    atk = 0.012 if attack is None else attack
    rel = 0.06 if release is None else release
    gp = 0.03 if gap is None else gap
    out: Buf = []
    t = 0.0
    pos = 0
    for item in notes:
        freq, dur = item[0], item[1]
        vel = item[2] if len(item) > 2 else 1.0
        t += dur
        n = max(1, int(round(t * SAMPLE_RATE)) - pos)
        pos += n
        freqs = tuple(float(f) for f in freq) if isinstance(freq, (tuple, list)) else (float(freq),)
        freqs = tuple(f for f in freqs if f > 0)
        if not freqs:
            out.extend([0.0] * n)
            continue
        gsamp = min(int(SAMPLE_RATE * gp), n // 5)
        sounding = max(1, n - gsamp)
        buf = _note_buf(freqs, sounding, wave, atk, decay, sustain, rel, vibrato, detune)
        g = volume * vel
        if g == 1.0:
            out.extend(buf)
        else:
            out.extend([v * g for v in buf])
        if n > sounding:
            out.extend([0.0] * (n - sounding))
    return out


def _note_sample(
    freq: float,
    duration: float,
    volume: float,
    wave: str = "triangle",
    *,
    attack: Optional[float] = None,
    decay: Optional[float] = None,
    sustain: float = 1.0,
    release: Optional[float] = None,
) -> List[int]:
    """Render one note (or silence if freq <= 0) as a 16-bit sample list.
    All five waves are supported now (saw / noise used to fall back to sine)."""
    buf = _sequence_f([(freq, duration)], volume, wave, attack=attack, decay=decay,
                      sustain=sustain, release=release)
    return [int(max(-32767.0, min(32767.0, v * 32767.0))) for v in buf]


def _sequence(
    notes: list,
    volume: float = 0.22,
    wave: str = "triangle",
    *,
    attack: Optional[float] = None,
    decay: Optional[float] = None,
    sustain: float = 1.0,
    release: Optional[float] = None,
    gap: Optional[float] = None,
    vibrato: Optional[Tuple[float, float]] = None,
    detune: float = 0.0,
) -> List[int]:
    """Build a phrase from (freq, seconds[, velocity]) pairs -> List[int] (16-bit)."""
    buf = _sequence_f(notes, volume, wave, attack=attack, decay=decay, sustain=sustain,
                      release=release, gap=gap, vibrato=vibrato, detune=detune)
    return [int(max(-32767.0, min(32767.0, v * 32767.0))) for v in buf]


def _mix_tracks(
    tracks: List[List[int]],
    volume: float = 1.0,
    gains: Optional[List[float]] = None,
    peak: Optional[float] = None,
) -> pygame.mixer.Sound:
    """Mix mono int tracks into one Sound.

    Default (gains=None, peak=None): old behaviour, sum / track_count * volume.
    gains : per-track weights, summed WITHOUT the 1/N division.
    peak  : if given, the mix is normalized so its maximum is `peak` of full scale.
    """
    length = max((len(t) for t in tracks), default=1)
    cnt = float(max(1, len(tracks)))
    out = [0.0] * length
    for k, track in enumerate(tracks):
        g = gains[k] if gains is not None else 1.0 / cnt
        seg = out[:len(track)]
        out[:len(track)] = [u + v * g for u, v in zip(seg, track)]
    if peak is not None:
        m = max((abs(v) for v in out), default=0.0)
        if m > 0:
            out = [v * (peak * 32767.0 / m) for v in out]
    else:
        out = [v * volume for v in out]
    buf = array.array("h", [int(max(-32767.0, min(32767.0, v))) for v in out] or [0])
    return pygame.mixer.Sound(buffer=buf.tobytes())


# ---------------------------------------------------------------------------
# 4. Drums
# ---------------------------------------------------------------------------

_DRUM_CACHE: Dict[str, Buf] = {}


def _drum_hit(kind: str) -> Buf:
    """One drum voice at unit peak (cached). K kick, S snare, H closed hat, O open hat,
    T tom, X rim click, M metal clank, C clap."""
    hit = _DRUM_CACHE.get(kind)
    if hit is not None:
        return hit
    if kind == "K":
        buf = _layer([
            (_voice("sine", 150, 0.20, 1.0, a=0.001, d=0.16, s=0.0, r=0.02, f_end=45), 0, 1.0),
            (_noise_burst(0.01, 1.0, a=0.0005, d=0.008, s=0.0, r=0.002, hp=1200), 0, 0.25),
        ])
    elif kind == "S":
        buf = _layer([
            (_noise_burst(0.16, 1.0, a=0.0005, d=0.12, s=0.0, r=0.02, hp=1500, lp=(7000, 3000)), 0, 1.0),
            (_voice("triangle", 200, 0.10, 1.0, a=0.0005, d=0.08, s=0.0, r=0.01, f_end=140), 0, 0.6),
        ])
    elif kind == "H":
        buf = _noise_burst(0.05, 1.0, a=0.0005, d=0.035, s=0.0, r=0.01, hp=6500)
    elif kind == "O":
        buf = _noise_burst(0.20, 1.0, a=0.0005, d=0.17, s=0.0, r=0.02, hp=5500)
    elif kind == "T":
        buf = _layer([
            (_voice("sine", 220, 0.24, 1.0, a=0.001, d=0.2, s=0.0, r=0.02, f_end=110), 0, 1.0),
            (_noise_burst(0.01, 1.0, a=0.0005, d=0.008, s=0.0, r=0.002, hp=1500), 0, 0.15),
        ])
    elif kind == "X":
        buf = _layer([
            (_voice("square", 1800, 0.03, 1.0, a=0.0005, d=0.02, s=0.0, r=0.005), 0, 0.6),
            (_noise_burst(0.025, 1.0, a=0.0005, d=0.02, s=0.0, r=0.005, hp=3000), 0, 0.5),
        ])
    elif kind == "M":
        buf = _layer([
            (_voice("square", 563, 0.16, 1.0, a=0.0005, d=0.12, s=0.0, r=0.01), 0, 0.5),
            (_voice("square", 841, 0.16, 1.0, a=0.0005, d=0.10, s=0.0, r=0.01), 0, 0.4),
            (_voice("square", 1297, 0.12, 1.0, a=0.0005, d=0.08, s=0.0, r=0.01), 0, 0.3),
            (_noise_burst(0.08, 1.0, a=0.0005, d=0.06, s=0.0, r=0.01, hp=4000), 0, 0.4),
        ])
    elif kind == "C":
        burst = _noise_burst(0.02, 1.0, a=0.0005, d=0.015, s=0.0, r=0.004, hp=1200, lp=5000)
        tail = _noise_burst(0.14, 1.0, a=0.0005, d=0.11, s=0.0, r=0.02, hp=1200, lp=4500)
        buf = _layer([(burst, 0, 0.8), (burst, 0.012, 0.8), (burst, 0.024, 0.8), (tail, 0.03, 0.7)])
    else:
        buf = [0.0]
    buf = _norm(buf, 1.0)
    _DRUM_CACHE[kind] = buf
    return buf


def _drums(pattern: str, step: float, gain: float = 1.0, steps: Optional[int] = None) -> Buf:
    """Render a drum pattern string, one character per `step` seconds.

    K kick  S snare  H hat  O open hat  T tom  X rim  M metal  C clap  . rest
    UPPERCASE = full hit, lowercase = soft (x0.45). Spaces and '|' are ignored. The pattern
    is tiled to `steps` steps (default: its own length). Hit tails that run past the end are
    folded back to the start, so the result loops seamlessly.
    """
    pat = [c for c in pattern if c not in " |"]
    total = steps if steps is not None else len(pat)
    n = int(round(total * step * SAMPLE_RATE))
    out = [0.0] * (n + 5000)   # headroom: hit tails are folded back by _loop_fit
    for i in range(total):
        c = pat[i % len(pat)]
        if c == ".":
            continue
        hit = _drum_hit(c.upper())
        g = gain * (0.45 if c.islower() else 1.0)
        o = int(round(i * step * SAMPLE_RATE))
        seg = out[o:o + len(hit)]
        out[o:o + len(hit)] = [u + v * g for u, v in zip(seg, hit)]
    return _loop_fit(out, n)


# ---------------------------------------------------------------------------
# 5. SFX library.  Each builder is a recipe: layers (buffer, offset_s, gain) -> _finish(peak)
#    Peaks: frequent sounds <= 0.20, others 0.24-0.40. Every sound < 0.7 s incl. echo tail.
# ---------------------------------------------------------------------------

def _sfx_ui_select() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_voice("triangle", 880, 0.07, a=0.002, d=0.05, s=0.0, r=0.015), 0.0, 1.0),
        (_voice("sine", 1760, 0.05, a=0.001, d=0.03, s=0.0, r=0.01), 0.0, 0.35),
    ]), 0.16)


def _sfx_ui_confirm() -> pygame.mixer.Sound:
    return _finish(_echo(_layer([
        (_voice("triangle", 523, 0.12, a=0.003, d=0.10, s=0.0, r=0.02), 0.00, 1.0),
        (_voice("triangle", 784, 0.16, a=0.003, d=0.13, s=0.0, r=0.03), 0.07, 1.0),
        (_voice("sine", 1568, 0.12, a=0.002, d=0.09, s=0.0, r=0.02), 0.07, 0.3),
    ]), 0.09, 0.4, 0.30, 2), 0.24)


def _sfx_ui_back() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_voice("triangle", 659, 0.07, a=0.002, d=0.05, s=0.0, r=0.015), 0.00, 1.0),
        (_voice("triangle", 440, 0.08, a=0.002, d=0.06, s=0.0, r=0.02), 0.04, 1.0),
    ]), 0.18)


def _sfx_shoot() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_voice("sine", 1400, 0.07, a=0.001, d=0.06, s=0.0, r=0.01, f_end=500), 0.0, 1.0),
        (_noise_burst(0.02, a=0.0005, d=0.015, s=0.0, r=0.004, hp=3500), 0.0, 0.45),
    ]), 0.17)


def _sfx_hit() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_noise_burst(0.06, a=0.0005, d=0.045, s=0.0, r=0.01, lp=(3500, 700)), 0.0, 1.0),
        (_voice("sine", 170, 0.09, a=0.001, d=0.07, s=0.0, r=0.015, f_end=65), 0.0, 0.65),
    ]), 0.19)


def _sfx_dash() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_noise_burst(0.22, a=0.06, s=1.0, r=0.12, lp=(500, 6000), hp=200, poles=2), 0.0, 1.0),
        (_voice("saw", 110, 0.20, a=0.04, s=1.0, r=0.10, f_end=330, lp=1200), 0.0, 0.25),
    ]), 0.28)


def _sfx_hurt() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_voice("saw", 220, 0.26, a=0.003, d=0.20, s=0.2, r=0.08, f_end=80, lp=(1800, 400)), 0.0, 0.8),
        (_noise_burst(0.12, a=0.001, d=0.09, s=0.0, r=0.02, lp=(2500, 300)), 0.0, 0.5),
        (_voice("sine", 90, 0.20, a=0.002, d=0.15, s=0.0, r=0.03, f_end=50), 0.0, 0.8),
    ]), 0.34)


def _sfx_kill() -> pygame.mixer.Sound:
    return _finish(_echo(_layer([
        (_voice("triangle", 392, 0.10, a=0.002, d=0.08, s=0.0, r=0.015), 0.00, 1.0),
        (_voice("triangle", 523, 0.10, a=0.002, d=0.08, s=0.0, r=0.015), 0.04, 1.0),
        (_voice("triangle", 659, 0.10, a=0.002, d=0.08, s=0.0, r=0.015), 0.08, 1.0),
        (_noise_burst(0.015, a=0.0005, d=0.01, s=0.0, r=0.003, hp=4000), 0.0, 0.3),
    ]), 0.07, 0.35, 0.25, 2), 0.24)


def _sfx_explode() -> pygame.mixer.Sound:
    return _finish(_echo(_layer([
        (_noise_burst(0.38, a=0.001, d=0.30, s=0.0, r=0.04, lp=(4500, 180), poles=2), 0.0, 1.0),
        (_voice("sine", 95, 0.36, a=0.002, d=0.30, s=0.0, r=0.04, f_end=32), 0.0, 0.65),
        (_noise_burst(0.12, a=0.0005, d=0.10, s=0.0, r=0.02, hp=2500), 0.0, 0.35),
    ]), 0.10, 0.40, 0.28, 2), 0.38)


def _sfx_levelup() -> pygame.mixer.Sound:
    return _finish(_echo(_layer([
        (_voice("triangle", C5, 0.16, a=0.003, d=0.13, s=0.0, r=0.03), 0.00, 1.0),
        (_voice("triangle", E5, 0.16, a=0.003, d=0.13, s=0.0, r=0.03), 0.07, 1.0),
        (_voice("triangle", G5, 0.16, a=0.003, d=0.13, s=0.0, r=0.03), 0.14, 1.0),
        (_voice("triangle", C6, 0.22, a=0.003, d=0.19, s=0.0, r=0.04), 0.21, 1.0),
        (_voice("sine", G5 * 2, 0.16, a=0.002, d=0.12, s=0.0, r=0.03), 0.14, 0.3),
        (_voice("sine", C6 * 2, 0.20, a=0.002, d=0.16, s=0.0, r=0.04), 0.21, 0.3),
    ]), 0.10, 0.45, 0.30, 2), 0.33)


def _sfx_pickup() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_voice("sine", 700, 0.08, a=0.002, d=0.06, s=0.0, r=0.015, f_end=1050), 0.0, 1.0),
        (_voice("triangle", 1400, 0.04, a=0.001, d=0.03, s=0.0, r=0.01), 0.03, 0.3),
    ]), 0.16)


def _sfx_boss_hit() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_noise_burst(0.08, a=0.0005, d=0.06, s=0.0, r=0.01, lp=(2500, 600)), 0.0, 1.0),
        (_voice("square", 180, 0.11, a=0.001, d=0.09, s=0.0, r=0.015, f_end=90, lp=1500), 0.0, 0.6),
        (_voice("sine", 80, 0.12, a=0.001, d=0.10, s=0.0, r=0.02), 0.0, 0.6),
    ]), 0.27)


def _sfx_boss_phase() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_voice("saw", A2, 0.62, a=0.25, s=1.0, r=0.20, lp=(300, 1200)), 0.0, 0.7),
        (_voice("saw", E3, 0.62, a=0.25, s=1.0, r=0.20, det=7, lp=(300, 1200)), 0.0, 0.5),
        (_voice("saw", A3, 0.62, a=0.25, s=1.0, r=0.20, det=-7, lp=(300, 1200)), 0.0, 0.4),
        (_noise_burst(0.50, a=0.30, s=1.0, r=0.15, lp=(300, 3000)), 0.1, 0.35),
        (_voice("sine", 70, 0.30, a=0.002, d=0.25, s=0.0, r=0.04, f_end=35), 0.0, 1.0),
    ]), 0.38)


def _sfx_boss_spawn() -> pygame.mixer.Sound:
    return _finish(_echo(_layer([
        (_voice("saw", G2, 0.50, a=0.12, s=1.0, r=0.18, lp=(300, 900)), 0.0, 0.7),
        (_voice("saw", D3, 0.50, a=0.12, s=1.0, r=0.18, det=6, lp=(300, 900)), 0.0, 0.5),
        (_voice("triangle", G3, 0.50, a=0.12, s=1.0, r=0.18, det=-6), 0.0, 0.4),
        (_noise_burst(0.45, a=0.10, s=1.0, r=0.2, lp=(400, 120), poles=2), 0.0, 0.6),
        (_voice("sine", 60, 0.35, a=0.002, d=0.30, s=0.0, r=0.05, f_end=30), 0.0, 1.0),
    ]), 0.08, 0.40, 0.25, 2), 0.36)


def _sfx_victory() -> pygame.mixer.Sound:
    return _finish(_echo(_layer([
        (_voice("triangle", C5, 0.20, a=0.004, d=0.17, s=0.2, r=0.04), 0.00, 1.0),
        (_voice("triangle", E5, 0.20, a=0.004, d=0.17, s=0.2, r=0.04), 0.08, 1.0),
        (_voice("triangle", G5, 0.20, a=0.004, d=0.17, s=0.2, r=0.04), 0.16, 1.0),
        (_voice("triangle", C6, 0.24, a=0.004, d=0.20, s=0.3, r=0.06), 0.24, 1.0),
        (_voice("sine", C5, 0.24, a=0.03, s=1.0, r=0.08), 0.24, 0.5),
        (_voice("sine", E5, 0.24, a=0.03, s=1.0, r=0.08), 0.24, 0.4),
        (_voice("sine", G5, 0.24, a=0.03, s=1.0, r=0.08), 0.24, 0.4),
    ]), 0.08, 0.40, 0.25, 2), 0.34)


def _sfx_defeat() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_voice("saw", 196, 0.55, a=0.01, d=0.45, s=0.15, r=0.15, f_end=98, lp=(1200, 200)), 0.00, 0.8),
        (_voice("sine", 98, 0.60, a=0.01, d=0.50, s=0.1, r=0.20, f_end=49), 0.00, 0.8),
        (_voice("triangle", Eb3, 0.30, a=0.01, d=0.25, s=0.0, r=0.08), 0.15, 0.5),
        (_voice("triangle", D3, 0.30, a=0.01, d=0.25, s=0.0, r=0.08), 0.30, 0.5),
        (_noise_burst(0.20, a=0.002, d=0.15, s=0.0, r=0.04, lp=(1500, 150)), 0.0, 0.4),
    ]), 0.32)


def _sfx_story() -> pygame.mixer.Sound:
    return _finish(_echo(_layer([
        (_voice("sine", 330, 0.10, a=0.01, d=0.08, s=0.0, r=0.03), 0.00, 1.0),
        (_voice("sine", 495, 0.08, a=0.01, d=0.06, s=0.0, r=0.03), 0.05, 0.5),
    ]), 0.11, 0.40, 0.30, 1), 0.17)


def _sfx_absorb() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_voice("sine", 220, 0.10, a=0.008, d=0.08, s=0.0, r=0.02, f_end=460), 0.0, 1.0),
        (_noise_burst(0.06, a=0.002, d=0.04, s=0.0, r=0.01, lp=(800, 300)), 0.0, 0.3),
    ]), 0.20)


# ---- NEW sounds (no game.py hook yet) ----

def _sfx_shield_block() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_voice("square", 740, 0.14, a=0.0005, d=0.10, s=0.0, r=0.02), 0.0, 0.5),
        (_voice("square", 1180, 0.12, a=0.0005, d=0.08, s=0.0, r=0.02), 0.0, 0.4),
        (_voice("sine", 2430, 0.10, a=0.0005, d=0.06, s=0.0, r=0.02), 0.0, 0.3),
        (_noise_burst(0.05, a=0.0005, d=0.035, s=0.0, r=0.01, hp=3000), 0.0, 0.5),
        (_voice("sine", 120, 0.10, a=0.001, d=0.08, s=0.0, r=0.02, f_end=70), 0.0, 0.7),
    ]), 0.30)


def _sfx_heal() -> pygame.mixer.Sound:
    return _finish(_echo(_layer([
        (_voice("sine", C5, 0.20, a=0.02, d=0.17, s=0.0, r=0.05, det=8), 0.00, 1.0),
        (_voice("sine", C5, 0.20, a=0.02, d=0.17, s=0.0, r=0.05, det=-8), 0.00, 1.0),
        (_voice("sine", G5, 0.24, a=0.02, d=0.20, s=0.0, r=0.06, det=8), 0.09, 0.9),
        (_voice("sine", G5, 0.24, a=0.02, d=0.20, s=0.0, r=0.06, det=-8), 0.09, 0.9),
    ]), 0.08, 0.40, 0.25, 2), 0.24)


def _sfx_artifact() -> pygame.mixer.Sound:
    return _finish(_echo(_layer([
        (_voice("sine", A5, 0.34, a=0.002, d=0.30, s=0.0, r=0.05), 0.00, 1.0),
        (_voice("sine", A5 * 2.76, 0.20, a=0.002, d=0.12, s=0.0, r=0.03), 0.00, 0.35),
        (_voice("sine", E6, 0.30, a=0.002, d=0.26, s=0.0, r=0.05), 0.08, 0.7),
        (_voice("sine", A5 * 2.76 * 0.75, 0.16, a=0.002, d=0.10, s=0.0, r=0.03), 0.08, 0.25),
        (_voice("triangle", A3, 0.30, a=0.10, d=0.25, s=0.0, r=0.08), 0.0, 0.5),
    ]), 0.11, 0.42, 0.28, 2), 0.32)


def _sfx_merge() -> pygame.mixer.Sound:
    return _finish(_echo(_layer([
        (_voice("triangle", E5, 0.26, a=0.01, s=1.0, r=0.04, f_end=G4), 0.00, 0.9),
        (_voice("triangle", G3, 0.26, a=0.01, s=1.0, r=0.04, f_end=G4), 0.00, 0.9),
        (_voice("sine", G4, 0.18, a=0.01, d=0.16, s=0.0, r=0.05), 0.26, 1.0),
        (_voice("sine", D5, 0.18, a=0.01, d=0.16, s=0.0, r=0.05), 0.26, 0.6),
        (_voice("sine", G5, 0.18, a=0.01, d=0.16, s=0.0, r=0.05), 0.26, 0.5),
        (_noise_burst(0.26, a=0.13, s=1.0, r=0.09, lp=(300, 1200)), 0.0, 0.25),
        (_voice("sine", 98, 0.18, a=0.01, d=0.16, s=0.0, r=0.05), 0.26, 0.8),
    ]), 0.10, 0.40, 0.25, 2), 0.32)


def _sfx_boss_warning() -> pygame.mixer.Sound:
    return _finish(_layer([
        (_voice("square", A3, 0.14, a=0.005, d=0.10, s=0.4, r=0.03, lp=900), 0.00, 0.8),
        (_voice("square", Eb4, 0.14, a=0.005, d=0.10, s=0.4, r=0.03, lp=900), 0.00, 0.6),
        (_voice("square", A3, 0.14, a=0.005, d=0.10, s=0.4, r=0.03, lp=900), 0.24, 0.8),
        (_voice("square", Eb4, 0.14, a=0.005, d=0.10, s=0.4, r=0.03, lp=900), 0.24, 0.6),
        (_voice("saw", 55, 0.56, a=0.28, s=1.0, r=0.18, lp=(200, 700)), 0.0, 0.6),
        (_noise_burst(0.36, a=0.22, s=1.0, r=0.10, lp=(200, 2500)), 0.20, 0.3),
        (_voice("sine", 65, 0.18, a=0.002, d=0.14, s=0.0, r=0.03, f_end=40), 0.44, 0.9),
    ]), 0.34)


# name -> builder. The first 17 names REPLACE existing sounds; the last 6 (NEW_SFX) need a game.py hook
SFX_BUILDERS: Dict[str, Callable[[], pygame.mixer.Sound]] = {
    "ui_select": _sfx_ui_select, "ui_confirm": _sfx_ui_confirm, "shoot": _sfx_shoot,
    "dash": _sfx_dash, "hit": _sfx_hit, "hurt": _sfx_hurt, "kill": _sfx_kill,
    "explode": _sfx_explode, "levelup": _sfx_levelup, "pickup": _sfx_pickup,
    "boss_hit": _sfx_boss_hit, "boss_phase": _sfx_boss_phase, "boss_spawn": _sfx_boss_spawn,
    "victory": _sfx_victory, "defeat": _sfx_defeat, "story": _sfx_story, "absorb": _sfx_absorb,
    # NEW (need a hook in game.py; harmless if never played)
    "ui_back": _sfx_ui_back, "shield_block": _sfx_shield_block, "heal": _sfx_heal,
    "artifact": _sfx_artifact, "merge": _sfx_merge, "boss_warning": _sfx_boss_warning,
}
NEW_SFX = ("ui_back", "shield_block", "heal", "artifact", "merge", "boss_warning")


def _build_sfx() -> Dict[str, pygame.mixer.Sound]:
    out: Dict[str, pygame.mixer.Sound] = {}
    for name, fn in SFX_BUILDERS.items():
        _rng.seed("sfx:" + name)
        out[name] = fn()
    return out


# ---------------------------------------------------------------------------
# 6. Music.  Each theme returns (grid, bars, peak, layers).  Layers are dicts:
#    {"kind": "seq",   "notes": [(Hz|chord tuple, seconds[, vel]), ...], "wave": ..., "opts": {...}}
#    {"kind": "drums", "pattern": "K...S...", "step": seconds}
#    {"kind": "buf",   "buf": float list, "offset": seconds}
#    common: "gain" (relative level, each layer is peak-normalized first), "lp" (cutoff or
#            (start, end) Hz), "echo": (delay, feedback, mix, taps)  -- the echo tail wraps.
#    Every layer is forced to exactly bars * bar_length samples (see _loop_fit), so the loop is
#    sample-exact and tails run over the seam instead of clicking.
# ---------------------------------------------------------------------------

Layer = Dict[str, object]
Theme = Tuple[_Grid, int, float, List[Layer]]


def _seq(notes: list, wave: str, gain: float, lp=None, echo=None, **opts) -> Layer:
    lay: Layer = {"kind": "seq", "notes": notes, "wave": wave, "gain": gain, "opts": opts}
    if lp is not None:
        lay["lp"] = lp
    if echo is not None:
        lay["echo"] = echo
    return lay


def _dr(pattern: str, step: float, gain: float) -> Layer:
    return {"kind": "drums", "pattern": pattern, "step": step, "gain": gain}


def _raw(buf: Buf, gain: float, offset: float = 0.0) -> Layer:
    return {"kind": "buf", "buf": buf, "offset": offset, "gain": gain}


def _cat(*parts: list) -> list:
    out: list = []
    for p in parts:
        out.extend(p)
    return out


def _render_theme(theme: Theme) -> pygame.mixer.Sound:
    g, bars, peak, layers = theme
    n = g.samples(bars)
    parts = []
    for lay in layers:
        kind = lay["kind"]
        if kind == "seq":
            buf = _sequence_f(lay["notes"], 1.0, lay["wave"], **lay["opts"])
            if abs(len(buf) - n) > 3:
                raise ValueError("music layer length %d != loop length %d" % (len(buf), n))
        elif kind == "drums":
            step = float(lay["step"])
            buf = _drums(lay["pattern"], step, 1.0, steps=int(round(g.bar * bars / step)))
        else:
            buf = [0.0] * int(float(lay["offset"]) * SAMPLE_RATE) + list(lay["buf"])
        if "lp" in lay:
            buf = _filter(buf, "lp", *_pair(lay["lp"]))
        buf = _norm(buf, 1.0)
        if "echo" in lay:
            buf = _echo(buf, *lay["echo"])
        parts.append((_loop_fit(buf, n), 0.0, float(lay["gain"])))
    snd = _finish(_layer(parts, n), peak)
    _NOTE_CACHE.clear()
    return snd


# ---- 0  The Verdant Rim: gentle cradle. C major, 76 bpm, 4 bars --------------------------
def _theme_rim() -> Theme:
    g = _Grid(76)
    b, q, h, w = g.B, g.Q, g.H, g.W
    melody = _cat(
        [(E4, h), (G4, q), (A4, q), (G4, h), (E4, h)],
        [(A4, h + q), (G4, q), (E4, h), (0, h)],
        [(F4, h), (A4, q), (C5, q), (A4, h), (F4, h)],
        [(D5, h), (B4, q), (G4, q), (G4, w)],
    )
    roots = [(C3, G3), (A2, E3), (F2, C3), (G2, D3)]
    bass = _cat(*[[(r, h + q), (0, q), (f, h), (0, h)] for r, f in roots])
    pad = [((C4, E4, G4), g.bar), ((A3, C4, E4), g.bar), ((F3, A3, C4), g.bar), ((G3, B3, D4), g.bar)]
    return g, 4, 0.36, [
        _seq(melody, "triangle", 0.55, echo=(q * 3, 0.4, 0.25, 2),
             attack=0.03, release=0.12, vibrato=(5.0, 8.0)),
        _seq(bass, "sine", 0.80, attack=0.02, release=0.15),
        _seq(pad, "sine", 0.45, attack=0.35, release=0.45, gap=0.0, detune=5.0),
        _dr("k...h...k...h...", b, 0.40),
    ]


# ---- 1  The Sinking Garden: murky mournful. D minor, 62 bpm, 4 bars ----------------------
def _theme_garden() -> Theme:
    g = _Grid(62)
    b, q, h, w = g.B, g.Q, g.H, g.W
    melody = _cat(
        [(A4, h + q), (F4, q), (D4, h), (E4, h)],
        [(D4, h + q), (F4, q), (Bb4, h), (A4, h)],
        [(G4, h + q), (Bb4, q), (A4, h), (G4, h)],
        [(E4, h), (Cs4, q), (D4, q), (E4, w)],
    )
    bass = [(D3, g.bar), (Bb2, g.bar), (G2, g.bar), (A2, g.bar)]
    pad = [((D3, F3, A3), g.bar), ((Bb3, D4, F4), g.bar), ((G3, Bb3, D4), g.bar), ((A3, Cs4, E4), g.bar)]
    return g, 4, 0.32, [
        _seq(melody, "sine", 0.60, echo=(h * 0.75, 0.5, 0.3, 3),
             attack=0.06, release=0.25, vibrato=(4.5, 22.0), detune=4.0),
        _seq(bass, "triangle", 0.80, attack=0.1, release=0.4, gap=0.0),
        _seq(pad, "saw", 0.35, lp=(650, 650), attack=0.5, release=0.6, gap=0.0, detune=12.0),
        _dr("K.......t.......", b, 0.55),
    ]


# ---- 2  The Memory Vaults: crystalline arpeggios. A minor, 96 bpm, 4 bars ----------------
def _theme_vaults() -> Theme:
    g = _Grid(96)
    b, q, h, w = g.B, g.Q, g.H, g.W
    arp = _cat(
        [(f, q) for f in (A4, C5, E5, A5, E5, C5, E5, C5)],
        [(f, q) for f in (F4, A4, C5, F5, C5, A4, C5, A4)],
        [(f, q) for f in (C5, E5, G5, C6, G5, E5, G5, E5)],
        [(f, q) for f in (G4, B4, D5, G5, D5, B4, D5, B4)],
    )
    melody = _cat(
        [(A5, h + q), (G5, q), (E5, w)],
        [(F5, h + q), (E5, q), (C5, w)],
        [(G5, h + q), (E5, q), (C6, w)],
        [(D5, h + q), (B4, q), (D5, h), (0, h)],
    )
    roots = [A2, F2, C3, G2]
    fifths = [E3, C3, G3, D3]
    bass = _cat(*[[(r, h + q), (0, q), (f, h), (0, h)] for r, f in zip(roots, fifths)])
    pad = [((A3, C4, E4), g.bar), ((F3, A3, C4), g.bar), ((C4, E4, G4), g.bar), ((G3, B3, D4), g.bar)]
    return g, 4, 0.40, [
        _seq(arp, "triangle", 0.50, echo=(b * 3, 0.5, 0.35, 3),
             attack=0.004, decay=0.22, sustain=0.0, release=0.02, gap=0.0),
        _seq(melody, "sine", 0.55, echo=(b * 3, 0.5, 0.40, 3),
             attack=0.003, decay=0.7, sustain=0.0, release=0.05, gap=0.0),
        _seq(bass, "sine", 0.70, attack=0.015, release=0.12),
        _seq(pad, "sine", 0.35, attack=0.5, release=0.5, gap=0.0, detune=6.0),
        _dr("k.x...x.k.x...x.", b, 0.35),
    ]


# ---- 3  The Forge Veins: driving heat / industrial. E phrygian, 120 bpm, 4 bars ---------
def _theme_forge() -> Theme:
    g = _Grid(120)
    b, q, h, w = g.B, g.Q, g.H, g.W
    bass = _cat(
        [(E2, q)] * 8,
        [(E2, q)] * 6 + [(F2, q), (F2, q)],
        [(E2, q)] * 6 + [(G2, q), (A2, q)],
        [(E2, q)] * 4 + [(B2, q), (B2, q), (C3, q), (B2, q)],
    )
    riff = [(E4, q), (0, b), (E4, b), (G4, q), (F4, q), (E4, q), (0, q), (B3, q), (E4, q)]
    lead = _cat(
        riff,
        [(E4, q), (0, b), (E4, b), (G4, q), (A4, q), (B4, q), (0, q), (C5, q), (B4, q)],
        riff,
        [(B4, q), (B4, q), (C5, q), (B4, q), (A4, q), (G4, q), (F4, q), (E4, q)],
    )
    pad = [((E3, B3), g.bar), ((E3, B3), g.bar), ((E3, B3, G4), g.bar), ((E3, B3, C4), g.bar)]
    return g, 4, 0.42, [
        _seq(bass, "saw", 0.85, lp=(500, 500), attack=0.003, decay=0.12, sustain=0.5, release=0.03, gap=0.01),
        _seq(lead, "square", 0.50, lp=(2500, 2500), attack=0.004, decay=0.10, sustain=0.5, release=0.04),
        _seq(pad, "saw", 0.25, lp=(900, 900), attack=0.1, release=0.2, gap=0.0, detune=9.0),
        _dr("K...K...K...K...", b, 0.75),
        _dr("....S.......S...", b, 0.60),
        _dr("..M...M...M...M.", b, 0.30),
        _dr("h.h.h.h.h.h.h.hO", b, 0.30),
    ]


# ---- 4  The Still Expanse: sparse icy, DRUMLESS. C lydian, 56 bpm, 4 bars ----------------
def _theme_frost() -> Theme:
    g = _Grid(56)
    b, q, h, w = g.B, g.Q, g.H, g.W
    bass = [(C2, g.bar), (C2, g.bar), (G2, g.bar), (C2, g.bar)]
    pad = [((C4, G4, D5), g.bar), ((C4, G4, E5), g.bar), ((D4, A4, E5), g.bar), ((C4, G4, D5), g.bar)]
    melody = _cat(
        [(G5, h), (0, h), (E5, h), (0, h)],
        [(0, h), (D5, h), (0, h), (A4, h)],
        [(Fs5, h), (0, h), (E5, h), (0, h)],
        [(D5, w), (0, w)],
    )
    wind = _wash(g.bar * 4, 1.0, a=g.bar * 1.5, r=g.bar * 1.5, lp=(500, 900))
    return g, 4, 0.26, [
        _seq(melody, "sine", 0.55, echo=(h, 0.55, 0.45, 3),
             attack=0.004, decay=0.9, sustain=0.0, release=0.1, gap=0.0),
        _seq(bass, "sine", 0.80, attack=0.6, release=0.9, gap=0.0),
        _seq(pad, "sine", 0.40, attack=1.0, release=1.2, gap=0.0, detune=4.0),
        _raw(wind, 0.30),
    ]


# ---- 5  The Mirage Basin: swaying mirage. D phrygian-dominant, 88 bpm, 4 bars (triplet feel)
def _theme_mirage() -> Theme:
    g = _Grid(88)
    t, h = g.T, g.H
    melody = _cat(
        [(D5, h), (Eb5, t), (D5, t), (C5, t), (A4, h), (Fs4, h)],
        [(Eb5, h), (D5, t), (C5, t), (Bb4, t), (G4, h), (A4, h)],
        [(D5, h), (Fs5, t), (Eb5, t), (D5, t), (A4, h), (D5, h)],
        [(C5, h), (Bb4, t), (A4, t), (G4, t), (A4, 2 * h)],
    )
    sway = lambda r, f: [(r, h), (f, 2 * t), (0, t), (r, h), (f, 2 * t), (0, t)]
    bass = _cat(sway(D3, A3), sway(Eb3, Bb3), sway(D3, A3), sway(C3, G3))
    pad = [((D4, Fs4, A4), g.bar), ((Eb4, G4, Bb4), g.bar), ((D4, Fs4, A4), g.bar), ((C4, Eb4, G4), g.bar)]
    return g, 4, 0.34, [
        _seq(melody, "triangle", 0.60, echo=(h * 0.75, 0.45, 0.30, 2),
             attack=0.02, release=0.08, vibrato=(5.5, 30.0)),
        _seq(bass, "sine", 0.80, attack=0.01, release=0.1),
        _seq(pad, "triangle", 0.40, attack=0.5, release=0.6, gap=0.0, detune=14.0, vibrato=(4.0, 10.0)),
        _dr("K..h..T..h.t", t, 0.55),
    ]


# ---- 6  The Dreaming Thicket: uncanny odd intervals. E / Bb tritone, 7/8, 100 bpm, 4 bars
def _theme_thicket() -> Theme:
    g = _Grid(100, beats=3.5)
    b, q, h = g.B, g.Q, g.H
    melody = _cat(
        [(E4, q), (Bb4, q), (A4, q), (Eb5, q), (D5, q), (Gs4, q), (0, q)],
        [(B4, q), (F5, q), (E5, q), (Bb4, q), (Cs5, q), (G4, q), (0, q)],
        [(E4, q), (Bb4, q), (A4, q), (Eb5, q), (D5, q), (Fs4, q), (Bb4, q)],
        [(Eb5, q), (A4, q), (Eb5, q), (A4, q), (Bb4, q), (E4, q), (0, q)],
    )
    bass = [(E2, h), (Bb2, h), (E2, h), (F2, q)] * 4
    pad = [((E3, Bb3, Fs4), g.bar), ((F3, B3, G4), g.bar), ((E3, Bb3, Fs4), g.bar), ((Eb3, A3, Gs4), g.bar)]
    slip = _voice("sine", 1400, g.bar * 0.9, a=g.bar * 0.45, s=1.0, r=g.bar * 0.45, f_end=500)
    return g, 4, 0.36, [
        _seq(melody, "triangle", 0.55, echo=(q * 3, 0.5, 0.35, 2),
             attack=0.01, release=0.08, vibrato=(6.5, 45.0), detune=10.0),
        _seq(bass, "saw", 0.65, lp=(420, 420), attack=0.01, release=0.1, detune=7.0),
        _seq(pad, "sine", 0.40, attack=0.4, release=0.5, gap=0.0, detune=25.0, vibrato=(7.0, 30.0)),
        _raw(slip, 0.22, offset=g.bar * 1.0),
        _raw(slip, 0.22, offset=g.bar * 3.0),
        _dr("K..h.S.h.K.h.h", b, 0.45),
    ]


# ---- 7  The Hollow Undermembrane: near-silent, thin. E phrygian, 48 bpm, 4 bars -----------
def _theme_hollow() -> Theme:
    g = _Grid(48)
    b, q, h, w = g.B, g.Q, g.H, g.W
    melody = _cat(
        [(G4, w), (0, w)],
        [(F4, w), (0, h), (E4, h)],
        [(B4, h), (0, h), (A4, w)],
        [(0, w), (G4, h), (0, h)],
    )
    bass = [(E2, g.bar), (E2, g.bar), (G2, g.bar), (E2, g.bar)]
    breath = _wash(g.bar * 4, 1.0, a=g.bar * 1.5, r=g.bar * 1.5, lp=(300, 200))
    return g, 4, 0.12, [
        _seq(melody, "sine", 0.45, echo=(h * 1.5, 0.5, 0.45, 2),
             attack=0.5, decay=1.5, sustain=0.3, release=1.0, gap=0.0, vibrato=(3.0, 12.0)),
        _seq(bass, "sine", 0.80, attack=1.0, release=1.5, gap=0.0),
        _raw(breath, 0.30),
        _dr("k.k.............", b, 0.40),
    ]


# ---- 8  The Ascending Strata: rising fanfare w/ tension. C major, 108 bpm, 8 bars ---------
def _theme_ascent() -> Theme:
    g = _Grid(108)
    b, q, h, w = g.B, g.Q, g.H, g.W
    melody = _cat(
        [(G4, q), (C5, q), (E5, h), (D5, q), (C5, q), (E5, h)],
        [(D5, q), (G5, q), (G5, h), (F5, q), (E5, q), (D5, h)],
        [(E5, q), (A5, q), (C6, h), (B5, q), (A5, q), (C6, h)],
        [(G5, h), (E5, q), (G5, q), (B5, h), (A5, h)],
        [(A5, h), (F5, q), (A5, q), (C6, h), (A5, h)],
        [(G5, q), (C6, q), (E6, h), (D6, q), (C6, q), (G5, h)],
        [(F5, h), (A5, h), (D6, h), (C6, q), (A5, q)],
        [(C6, w), (D6, h), (B5, h)],
    )
    chords = [(C4, E4, G4), (B3, D4, G4), (A3, C4, E4), (G3, B3, E4),
              (A3, C4, F4), (C4, E4, G4), (A3, D4, F4), (G3, C4, D4)]
    pad = [(c, g.bar) for c in chords]
    rf = [(C3, G3), (G2, D3), (A2, E3), (E2, B2), (F2, C3), (C3, G3), (D3, A3), (G2, D3)]
    bass = _cat(*[[(r, q), (r, q), (f, q), (r, q)] * 2 for r, f in rf])
    snare = "....S.......S..." * 7 + "....S...S.S.SSSS"
    return g, 8, 0.42, [
        _seq(melody, "saw", 0.50, lp=(3000, 3000), attack=0.01, decay=0.15, sustain=0.6,
             release=0.06, detune=6.0, vibrato=(5.5, 15.0)),
        _seq(pad, "saw", 0.30, lp=(1200, 1200), attack=0.08, release=0.15, detune=8.0),
        _seq(bass, "triangle", 0.80, attack=0.004, decay=0.12, sustain=0.5, release=0.03),
        _dr("K...K...K...K...", b, 0.65),
        _dr(snare, b, 0.55),
        _dr("h.h.h.h.h.h.h.h.", b, 0.25),
    ]


# ---- 9  The First Divide: tense final climax. A minor (harmonic), 132 bpm, 8 bars ---------
def _theme_divide() -> Theme:
    g = _Grid(132)
    b, q, h, w = g.B, g.Q, g.H, g.W
    roots = [A2, A2, F2, E2, A2, Bb2, F2, E2]
    bass = _cat(*[[(r, b, 1.0 if i % 4 == 0 else 0.55) for i in range(16)] for r in roots])
    mA = [(A4, q), (A4, b), (C5, b), (E5, q), (D5, q), (C5, q), (B4, q), (A4, q), (0, q)]
    mF = [(F4, q), (F4, b), (A4, b), (C5, q), (Bb4, q), (A4, q), (G4, q), (F4, q), (0, q)]
    mE = [(E4, q), (E4, b), (Gs4, b), (B4, q), (A4, q), (Gs4, q), (Fs4, q), (E4, q), (0, q)]
    mHi = [(A5, q), (A5, b), (C6, b), (E6, q), (D6, q), (C6, q), (B5, q), (A5, q), (0, q)]
    mTr = [(A4, q), (A4, b), (C5, b), (E5, q), (Eb5, q), (D5, q), (Bb4, q), (A4, q), (0, q)]
    mEe = [(E4, q), (E4, b), (Gs4, b), (B4, q), (D5, q), (B4, q), (Gs4, q), (B4, q), (0, q)]
    lead = _cat(mA, mA, mF, mE, mHi, mTr, mF, mEe)
    pad = [((A3, C4, E4), g.bar), ((A3, C4, E4), g.bar), ((F3, A3, C4), g.bar), ((E3, Gs3, B3, D4), g.bar),
           ((A3, C4, E4), g.bar), ((Bb3, D4, F4), g.bar), ((F3, A3, C4), g.bar), ((Gs3, B3, D4, F4), g.bar)]
    riser = _noise_burst(g.bar * 2, 1.0, a=g.bar * 1.9, s=1.0, r=0.02, lp=(500, 6000), hp=200)
    snare = "....S.......S..." * 3 + "....S...S.S.S.SS"
    snare = snare * 2
    return g, 8, 0.44, [
        _seq(bass, "saw", 0.85, lp=(600, 600), attack=0.002, decay=0.06, sustain=0.5, release=0.015, gap=0.005),
        _seq(lead, "square", 0.50, lp=(3000, 3000), echo=(q, 0.55, 0.50, 2),
             attack=0.004, decay=0.10, sustain=0.5, release=0.04, detune=7.0),
        _seq(pad, "saw", 0.28, lp=(1000, 1000), attack=0.1, release=0.2, gap=0.0, detune=10.0),
        _raw(riser, 0.28, offset=g.bar * 6),
        _dr("K.K.K.K.K.K.K.K.", b, 0.80),
        _dr(snare, b, 0.65),
        _dr("HhhhHhhhHhhhHhhh", b, 0.30),
        _dr("." * 16 * 3 + "............TTTT" + "." * 16 * 3 + "............TTTT", b, 0.55),
    ]


# ---- Menu: bright looping motif (old tune kept, now 4 bars with fifth-dyad variation) ------
def _theme_menu() -> Theme:
    g = _Grid(60.0 / 0.72)     # beat = 0.72 s, same tempo as the old menu theme
    b, q, h, w = g.B, g.Q, g.H, g.W
    m1 = [
        (E4, q), (G4, q), (A4, q), (G4, q), (E4, q), (D4, q), (C4, h),
        (E4, q), (G4, q), (A4, q), (C5, q), (B4, q), (A4, q), (G4, h),
    ]
    m2 = [((f, f * 1.5), d) if f else (0, d) for f, d in m1]
    bass1 = [(C3, h), (G3, h), (A3, h), (E3, h), (C3, h), (G3, h), (F3, h), (G3, h)]
    pad1 = [((C4, E4, G4), w), ((A3, C4, E4), w), ((C4, E4, G4), w), ((A3, C4, F4), w)]
    return g, 4, 0.34, [
        _seq(_cat(m1, m2), "triangle", 0.55, echo=(q * 3, 0.4, 0.25, 2), attack=0.012, release=0.08),
        _seq(_cat(bass1, bass1), "sine", 0.80, attack=0.01, release=0.1),
        _seq(_cat(pad1, pad1), "sine", 0.35, attack=0.25, release=0.3, gap=0.0, detune=5.0),
        _dr("K...h.h.S...h.h.", b, 0.40),
    ]


ACT_THEME_BUILDERS: List[Callable[[], Theme]] = [
    _theme_rim, _theme_garden, _theme_vaults, _theme_forge, _theme_frost,
    _theme_mirage, _theme_thicket, _theme_hollow, _theme_ascent, _theme_divide,
]


def _build_menu_theme() -> pygame.mixer.Sound:
    """Bright looping menu motif."""
    _rng.seed("music:menu")
    return _render_theme(_theme_menu())


def _build_act_theme(act: int) -> pygame.mixer.Sound:
    """Act-flavored looping theme (act index is clamped to 0..9)."""
    idx = max(0, min(act, len(ACT_THEME_BUILDERS) - 1))
    _rng.seed("music:act_%d" % idx)
    return _render_theme(ACT_THEME_BUILDERS[idx]())


# ---------------------------------------------------------------------------
# 7. AudioManager (public API unchanged)
# ---------------------------------------------------------------------------

# --- Recorded music (TASK-026) ------------------------------------------------------------------------
# Eleven mp3 files in blob_evolution/assets/music play instead of the generated themes. The generated
# themes above stay as the fallback when a file is missing or will not load.
MUSIC_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"
CROSSFADE_S = 2.0        # equal-power seam crossfade baked into the in-memory loop
TARGET_LUFS = -21.0      # every gain below is TARGET_LUFS minus the loop's measured loudness
MUSIC_CHANNELS = 2       # mixer channels 0 and 1 are reserved for music; SFX use the rest
SFX_CHANNELS = 18        # channels left for sound effects
NARRATION_CHANNELS = 1   # one reserved voice channel (index MUSIC_CHANNELS), never used by SFX or music
TOTAL_CHANNELS = SFX_CHANNELS + MUSIC_CHANNELS + NARRATION_CHANNELS   # the mixer opens 21
ACT_FADE_MS = 1200       # crossfade when the music changes
MENU_FADE_MS = 1500      # crossfade back to the menu theme (after game over / victory / quit to menu)
DUCK_RAMP_S = 0.3        # how fast ducking changes the music level


# --- Recorded sound effects (TASK-027, TASK-035) -----------------------------------------------------
# Twenty-two pre-processed 22050 Hz mono 16-bit WAVs replace the generated sound of the same name (the first
# eleven have gain, tail trim and edge fades baked in offline; the TASK-035 cues are untrimmed). Only "hurt" is
# still generated. A file that is missing or will not load leaves the generated sound.
SFX_DIR = Path(__file__).resolve().parent.parent / "assets" / "sfx"
SFX_FILES: Tuple[str, ...] = (
    "ui_select", "ui_confirm", "shoot", "dash", "hit", "kill", "explode", "pickup", "absorb", "boss_hit", "story",
    "artifact", "boss_phase", "boss_spawn", "boss_warning", "defeat", "heal", "levelup", "merge", "shield_block",
    "ui_back", "victory",
)                        # sfx name -> SFX_DIR / f"{name}.wav"
SFX_MIN_S, SFX_MAX_S = 0.04, 1.5   # a file outside this length is treated as broken
# The long fanfare/sting cues may be longer than SFX_MAX_S: name -> longest accepted length in seconds
# (files are 1.5-4.0 s; every other name keeps SFX_MAX_S).
SFX_MAX_S_LONG: Dict[str, float] = {
    "boss_warning": 2.0, "boss_phase": 2.5, "boss_spawn": 3.5, "merge": 3.5, "victory": 4.5, "defeat": 4.5,
}
# Retrigger gate per sound name: (minimum ms between two starts, maximum simultaneous instances). Names that
# are not listed (shoot, explode, dash, ...) are never gated. Applies whether the sound is a file or generated.
SFX_GATES: Dict[str, Tuple[int, int]] = {
    "hit": (50, 4), "pickup": (40, 4), "kill": (70, 3), "absorb": (80, 3),
    "boss_hit": (80, 3), "hurt": (100, 3), "ui_select": (30, 2),
}


def _load_sfx_files(names: Sequence[str], sfx_dir: Path, failed: Optional[List[str]] = None
                    ) -> Dict[str, pygame.mixer.Sound]:
    """Load SFX_DIR/<name>.wav for each name. Names whose file is missing, unreadable, empty/silent or an odd
    length (SFX_MIN_S..SFX_MAX_S, or up to SFX_MAX_S_LONG[name] for the long cues) are left out (and added to
    `failed`); nothing is raised or printed and nothing is retried."""
    out: Dict[str, pygame.mixer.Sound] = {}
    for name in names:
        try:
            path = Path(sfx_dir) / f"{name}.wav"
            if not path.is_file():
                raise FileNotFoundError(str(path))
            snd = pygame.mixer.Sound(str(path))
            if not (SFX_MIN_S <= snd.get_length() <= SFX_MAX_S_LONG.get(name, SFX_MAX_S)):
                raise ValueError("length out of range")
            if not any(snd.get_raw()):
                raise ValueError("silent")
        except (pygame.error, OSError, ValueError, MemoryError):
            if failed is not None:
                failed.append(name)
            continue
        out[name] = snd
    return out


# --- Recorded narration (TASK-028) -------------------------------------------------------------------
# Voice clips (.wav or .ogg) in blob_evolution/assets/narration play on their own reserved channel while a
# story card is up. Files are supplied separately and are not in the repo: a clip that is missing or will not
# load is silently skipped (and never retried), the card just shows without a voice.
NARRATION_DIR = Path(__file__).resolve().parent.parent / "assets" / "narration"
NARRATION_EXTS: Tuple[str, ...] = (".wav", ".ogg")    # tried in this order: NARRATION_DIR / f"{key}{ext}"
NARRATION_VOLUME_DEFAULT = 0.8
NARRATION_VOLUME_STEP = 0.1     # one left/right press in Options
NARRATION_CUT_MS = 80           # a skipped or replaced clip fades out this fast (no click) before the next starts
NARRATION_MIN_S, NARRATION_MAX_S = 0.05, 120.0   # a file outside this length is treated as broken
OPENING_CLIPS: Tuple[str, ...] = ("intro_card1", "intro_card2", "layer01_descent")   # the three opening cards


def descent_clip(act: int) -> str:
    """Key of the descent-card clip for a layer (act index 0-9); script clip 'NA'."""
    return f"layer{act + 1:02d}_descent"


def miniboss_clip(act: int) -> str:
    """Key of the Lattice Anchor (mini-boss) card clip for a layer."""
    return f"layer{act + 1:02d}_miniboss"


def warden_clip(act: int, ng_plus_level: int = 0) -> str:
    """Key of the Warden Encounter clip: the NG+ tier at or below the level (as get_warden_quote picks), else base."""
    tiers = [m for m, _ in NG_WARDEN_QUOTES.get(act, []) if ng_plus_level >= m]
    base = f"layer{act + 1:02d}_warden"
    return f"{base}_ng{max(tiers)}" if tiers else base


def all_narration_keys() -> List[str]:
    """Every key the game can ask for (opening, per-layer descent/warden/mini-boss, NG+ warden tiers)."""
    keys = list(OPENING_CLIPS)
    for act in range(10):
        keys += [descent_clip(act), f"layer{act + 1:02d}_warden"]
        keys += [f"layer{act + 1:02d}_warden_ng{m}" for m, _ in sorted(NG_WARDEN_QUOTES.get(act, []))]
        keys.append(miniboss_clip(act))
    return list(dict.fromkeys(keys))


def _load_narration(key: str, narration_dir: Path) -> Optional[pygame.mixer.Sound]:
    """Load NARRATION_DIR/<key>.wav (or .ogg). Returns None if no file exists, it will not load, or its length is
    out of range; nothing is raised or printed."""
    for ext in NARRATION_EXTS:
        try:
            path = Path(narration_dir) / f"{key}{ext}"
            if not path.is_file():
                continue
            snd = pygame.mixer.Sound(str(path))
            if NARRATION_MIN_S <= snd.get_length() <= NARRATION_MAX_S:
                return snd
        except (pygame.error, OSError, ValueError, MemoryError, RuntimeError):
            continue
    return None


class FileTrack(NamedTuple):
    """One recorded track: file name, linear gain (<= 1.0) and the loop window in seconds of the decoded file."""

    filename: str
    gain: float
    loop_in: float
    loop_out: float


TRACK_FILES: Dict[str, FileTrack] = {
    "menu": FileTrack("01-Menu.mp3", 0.369, 13.75, 63.53),
    "act_0": FileTrack("02-MossyGlade.mp3", 0.380, 30.50, 62.25),
    "act_1": FileTrack("03-BogBloom.mp3", 0.501, 18.00, 63.00),
    "act_2": FileTrack("04-EchoesintheGlass.mp3", 0.332, 14.50, 67.02),
    "act_3": FileTrack("05-IronBloom.mp3", 0.518, 0.50, 74.50),
    "act_4": FileTrack("06-ArcticStillness.mp3", 0.649, 18.75, 56.75),
    "act_5": FileTrack("07-MirageSerenade.mp3", 0.364, 12.00, 65.90),
    "act_6": FileTrack("08-CreakingLullaby.mp3", 0.597, 11.00, 61.25),
    "act_7": FileTrack("09-Hollow.mp3", 0.813, 17.50, 57.00),
    "act_8": FileTrack("10-AscensionPulse.mp3", 0.525, 19.75, 51.75),
    "act_9": FileTrack("11-AscensionsEnd.mp3", 0.634, 5.50, 59.79),
}


def _loop_from_sound(snd: pygame.mixer.Sound, t_in: float, t_out: float, xfade: float) -> pygame.mixer.Sound:
    """Cut [t_in, t_out] out of a decoded 16-bit Sound and blend its tail into its head (equal power).

    The result plays as a seamless loop of (t_out - t_in - xfade) seconds. If the window does not fit or the
    mixer format is not 16-bit, the original Sound is returned (it then loops as a whole file).
    """
    init = pygame.mixer.get_init()
    if not init or init[1] != -16:
        return snd
    freq, _fmt, ch = init
    samples = array.array("h")
    samples.frombytes(snd.get_raw())
    i0, i1 = int(t_in * freq) * ch, int(t_out * freq) * ch
    n = int(xfade * freq) * ch
    if not (0 <= i0 and n > 0 and i0 + 2 * n < i1 <= len(samples)):
        return snd
    head, tail = samples[i0:i0 + n], samples[i1 - n:i1]
    frames = n // ch
    blend = array.array("h", tail)
    for f in range(frames):
        th = 0.5 * math.pi * f / frames
        fade_in, fade_out = math.sin(th), math.cos(th)
        for c in range(ch):
            k = f * ch + c
            v = tail[k] * fade_out + head[k] * fade_in
            blend[k] = -32768 if v < -32768 else 32767 if v > 32767 else int(v)
    loop = samples[i0 + n:i1 - n] + blend
    try:
        return pygame.mixer.Sound(buffer=loop.tobytes())
    except pygame.error:
        return snd


class AudioManager:
    """Global sound manager: generated SFX, recorded music (generated themes as fallback)."""

    def __init__(self) -> None:
        self.enabled = True
        self.sfx_volume = 0.55
        self.music_volume = 0.32
        self._ready = False
        self._sfx: Dict[str, pygame.mixer.Sound] = {}
        self._sfx_source: Dict[str, str] = {}          # sfx name -> "file" or "generated"
        self._sfx_failed: List[str] = []               # file-backed names whose file did not load (never retried)
        self._sfx_last: Dict[str, float] = {}          # retrigger gate: when each gated name last started
        self._clock: Callable[[], float] = time.monotonic
        self._tracks: Dict[str, pygame.mixer.Sound] = {}      # generated themes (menu eager, acts lazy)
        self._files: Dict[str, pygame.mixer.Sound] = {}       # decoded file loops (current + previous only)
        self._file_failed: set = set()                        # keys whose file would not load: no retries
        self._chan: List[pygame.mixer.Channel] = []           # the two music channels, alternated per change
        self._cur = 0
        self._music_channel: Optional[pygame.mixer.Channel] = None  # channel of the current track
        self._current_track: Optional[str] = None
        self._current_source: Optional[str] = None            # "file" or "generated" for the current track
        self._duck = 1.0
        self._duck_target = 1.0
        self._fade_left = 0.0
        self.narration_volume = NARRATION_VOLUME_DEFAULT
        self._narr_chan: Optional[pygame.mixer.Channel] = None    # the reserved voice channel
        self._narr_failed: set = set()                            # keys with no usable file: never retried
        self._narr_sound: Optional[pygame.mixer.Sound] = None     # the clip on the channel (or about to be)
        self._narr_key: Optional[str] = None
        self._narr_pending = False                                # a clip waits for the old one's fade-out
        self._init_mixer()

    def _init_mixer(self) -> None:
        try:
            opened = pygame.mixer.get_init()
            if opened and tuple(opened[:3]) != (SAMPLE_RATE, -16, 1):
                # pygame.init() (called by Game before this) opens the mixer at 44100 Hz stereo, which would
                # play every 22050 Hz mono buffer here 4x too fast. Reopen it in the format the sounds use.
                pygame.mixer.quit()
                opened = None
            if not opened:
                pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
                pygame.mixer.init()
            pygame.mixer.set_num_channels(TOTAL_CHANNELS)
            pygame.mixer.set_reserved(MUSIC_CHANNELS + NARRATION_CHANNELS)
            self._build_library()
            self._chan = [pygame.mixer.Channel(i) for i in range(MUSIC_CHANNELS)]
            self._narr_chan = pygame.mixer.Channel(MUSIC_CHANNELS)
            self._music_channel = self._chan[0]
            self._ready = True
        except pygame.error:
            self._ready = False

    def _build_library(self) -> None:
        """SFX and the menu theme are built at startup; act themes are built lazily."""
        self._sfx = _build_sfx()
        self._sfx_source = {name: "generated" for name in self._sfx}
        files = _load_sfx_files([n for n in SFX_FILES if n in self._sfx], SFX_DIR, self._sfx_failed)
        self._sfx.update(files)
        self._sfx_source.update({name: "file" for name in files})
        self._tracks["menu"] = _build_menu_theme()
        for sound in self._tracks.values():
            sound.set_volume(self.music_volume)

    def _get_track(self, key: str) -> Optional[pygame.mixer.Sound]:
        """Return a generated music Sound, building (and caching) act themes on first use."""
        track = self._tracks.get(key)
        if track is None and key.startswith("act_"):
            try:
                idx = int(key[4:])
            except ValueError:
                return None
            if 0 <= idx < len(ACT_THEME_BUILDERS):
                track = _build_act_theme(idx)
                track.set_volume(self.music_volume)
                self._tracks[key] = track
        return track

    def _file_sound(self, key: str) -> Optional[pygame.mixer.Sound]:
        """Return the recorded loop for a track key, or None if it has no file or the file will not load."""
        spec = TRACK_FILES.get(key)
        if spec is None or key in self._file_failed:
            return None
        snd = self._files.get(key)
        if snd is None:
            try:
                snd = pygame.mixer.Sound(str(MUSIC_DIR / spec.filename))
                snd = _loop_from_sound(snd, spec.loop_in, spec.loop_out, CROSSFADE_S)
            except (pygame.error, OSError, ValueError, MemoryError):
                self._file_failed.add(key)
                return None
            snd.set_volume(max(0.0, min(1.0, spec.gain)))
            while len(self._files) >= 2:
                self._files.pop(next(iter(self._files)))
            self._files[key] = snd
        return snd

    def prewarm(self, act_index: int) -> None:
        """Optionally load an act's music ahead of time (e.g. during a story page)."""
        if self._ready:
            key = f"act_{max(0, min(act_index, 9))}"
            if self._file_sound(key) is None:
                self._get_track(key)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self._narr_pending = False
            self._narr_key = None
            self.stop_music()
            if self._ready:
                pygame.mixer.stop()

    def set_narration_volume(self, volume: float) -> float:
        """Set the narration level (0 = off, 1 = full), clamped to 0..1; applies to a clip that is playing."""
        self.narration_volume = round(max(0.0, min(1.0, float(volume))), 2)
        if self._narr_sound is not None:
            self._narr_sound.set_volume(self.narration_volume)
        if self.narration_volume == 0.0:
            self.stop_narration()
        return self.narration_volume

    def play_narration(self, key: Optional[str]) -> None:
        """Play the clip for a story card, replacing the previous clip (it fades out first); None just stops.

        Silent when Sound is off, the volume is 0, or the clip has no usable file (that is remembered, no retry)."""
        if not key:
            self.stop_narration()
            return
        if not self.enabled or not self._ready or self._narr_chan is None or self.narration_volume <= 0.0:
            self.stop_narration()
            return
        snd = None
        if key not in self._narr_failed:
            snd = _load_narration(key, NARRATION_DIR)
            if snd is None:
                self._narr_failed.add(key)
        self.stop_narration()
        if snd is None:
            return
        self._narr_sound, self._narr_key, self._narr_pending = snd, key, True
        if not self._narr_chan.get_busy():
            self._start_narration()

    def _start_narration(self) -> None:
        """Start the waiting clip on the (now idle) voice channel."""
        self._narr_pending = False
        if self._narr_sound is None or self._narr_chan is None:
            return
        self._narr_sound.set_volume(self.narration_volume)
        self._narr_chan.set_volume(1.0)
        self._narr_chan.play(self._narr_sound)

    def stop_narration(self, fade_ms: int = NARRATION_CUT_MS) -> None:
        """Cut the current (and any waiting) clip with a short fade so the cut does not click."""
        self._narr_pending = False
        if self._narr_chan is not None and self._narr_chan.get_busy():
            self._narr_chan.fadeout(fade_ms)
        self._narr_sound = None
        self._narr_key = None

    def narration_playing(self) -> Optional[str]:
        """Key of the clip that is playing or about to start, else None."""
        busy = self._narr_chan is not None and self._narr_chan.get_busy()
        return self._narr_key if (busy or self._narr_pending) and self._narr_key else None

    def toggle(self) -> bool:
        self.set_enabled(not self.enabled)
        return self.enabled

    def play(self, name: str, volume_scale: float = 1.0) -> None:
        if not self.enabled or not self._ready:
            return
        sound = self._sfx.get(name)
        if not sound or not self._gate_allows(name, sound):
            return
        sound.set_volume(max(0.0, min(1.0, self.sfx_volume * volume_scale)))
        sound.play()

    def sfx_source(self, name: str) -> Optional[str]:
        """"file" if the recorded WAV is in use for this sound, "generated" if not, None for an unknown name."""
        return self._sfx_source.get(name)

    def _gate_allows(self, name: str, sound: pygame.mixer.Sound) -> bool:
        """Retrigger gate (SFX_GATES): skip a start that is too soon after the last or has too many copies playing."""
        limit = SFX_GATES.get(name)
        if limit is None:
            return True
        min_gap_ms, max_instances = limit
        now = self._clock()
        if min_gap_ms and (now - self._sfx_last.get(name, -1e9)) * 1000.0 < min_gap_ms:
            return False
        if max_instances and sound.get_num_channels() >= max_instances:
            return False
        self._sfx_last[name] = now
        return True

    def _level(self) -> float:
        """Volume of the current music channel (recorded music carries its gain on the Sound)."""
        base = self.music_volume if self._current_source == "file" else 1.0
        return max(0.0, min(1.0, base * self._duck))

    def _apply_volume(self) -> None:
        if self._current_track and self._chan:
            self._chan[self._cur].set_volume(self._level())

    def duck_music(self, factor: float, immediate: bool = False) -> None:
        """Lower (or restore) the music level, e.g. 0.5 while a story card is up; ramps unless immediate."""
        self._duck_target = max(0.0, min(1.0, factor))
        if immediate:
            self._duck = self._duck_target
            self._apply_volume()

    def tick(self, dt: float) -> None:
        """Advance the duck ramp; call once per frame."""
        if self._duck != self._duck_target:
            step = dt / DUCK_RAMP_S
            self._duck += max(-step, min(step, self._duck_target - self._duck))
            self._apply_volume()
        if self._narr_pending and self._narr_chan is not None and not self._narr_chan.get_busy():
            self._start_narration()
        self._fade_left -= dt
        if self._fade_left <= 0 and self._ready and self._chan:
            # SDL_mixer drives the channel volume itself while a fade-in runs and restores the volume it had
            # when the fade started, which silently undoes any duck applied meanwhile. Re-assert it afterwards.
            channel = self._chan[self._cur]
            if channel.get_busy() and abs(channel.get_volume() - self._level()) > 0.02:
                self._apply_volume()

    def _play_track(self, key: str, fade_ms: int = ACT_FADE_MS) -> None:
        if not self.enabled or not self._ready or not self._chan:
            return
        cur = self._chan[self._cur] if self._current_track else None
        if self._current_track == key and cur is not None and cur.get_busy():
            return
        snd = self._file_sound(key)
        source = "file"
        if snd is None:
            snd, source = self._get_track(key), "generated"
        if not snd:
            return
        old = cur if cur is not None and cur.get_busy() else None
        self._cur = 1 - self._cur
        new = self._chan[self._cur]
        self._current_track, self._current_source = key, source
        self._music_channel = new
        new.set_volume(self._level())
        new.play(snd, loops=-1, fade_ms=fade_ms)
        new.set_volume(self._level())
        self._fade_left = fade_ms / 1000.0 + 0.1
        if old is not None:
            old.fadeout(fade_ms)

    def play_act_music(self, act_index: int) -> None:
        """Start looping act theme (crossfades from whatever is playing)."""
        idx = max(0, min(act_index, 9))
        self._play_track(f"act_{idx}", ACT_FADE_MS)

    def play_menu_music(self) -> None:
        """Start looping menu theme (separate from act 0)."""
        self._play_track("menu", MENU_FADE_MS)

    def stop_music(self) -> None:
        for channel in self._chan:
            channel.fadeout(350)
        self._current_track = None
        self._current_source = None


_audio: Optional[AudioManager] = None


def get_audio() -> AudioManager:
    """Return singleton audio manager."""
    global _audio
    if _audio is None:
        _audio = AudioManager()
    return _audio
