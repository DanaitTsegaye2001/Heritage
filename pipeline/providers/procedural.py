"""Procedural score: an original, code-composed music cue (not AI).

Used because no free AI music source was available on 2026-11-26 (Lyria free quota 0,
ACE-Step needs a GPU; FAILURES F-100). Deterministic: same params + seed -> same audio.

Each cue: a I–V–vi–IV progression (or a variant chosen by seed), plucked arpeggio in
eighth notes with exponential decay, a soft sustained pad, and a bass root on each bar.
cfg.params per cue are taken from the cue prompt: tempo (… bpm) and mood words
("quiet"/"hushed" -> sparse and softer; "warm"/"nostalgic" -> lower register).
"""
from __future__ import annotations

import math
import random
import re
import wave

from ..common.media import SAMPLE_RATE
from .base import Provider, ProviderResult

PROGRESSIONS = [[0, 7, 9, 5], [0, 5, 9, 7], [9, 5, 0, 7], [0, 9, 5, 7]]  # semitone roots: I V vi IV etc.
MAJOR, MINOR = [0, 4, 7], [0, 3, 7]


def _note(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def compose(prompt: str, duration: float, seed: int):
    import numpy as np
    rng = random.Random(seed)
    sr = SAMPLE_RATE
    n = int(duration * sr)
    t = np.arange(n) / sr
    bpm = float(m.group(1)) if (m := re.search(r"(\d{2,3})\s*bpm", prompt)) else 84.0
    quiet = bool(re.search(r"quiet|hushed|sparse|soft", prompt))
    warm = bool(re.search(r"warm|nostalgic|golden", prompt))
    key = 60 + rng.choice([-5, -3, 0, 2]) - (5 if warm else 0)  # tonic around C4
    prog = rng.choice(PROGRESSIONS)
    beat = 60.0 / bpm
    bar = beat * 4
    out = np.zeros((n, 2))

    def add(start: float, freq: float, length: float, amp: float, decay: float, pan: float, bright: float):
        i0 = int(start * sr)
        if i0 >= n:
            return
        m_ = min(n - i0, int(length * sr))
        tt = np.arange(m_) / sr
        env = np.exp(-tt / decay) * np.minimum(1, tt / 0.005)
        sig = np.sin(2 * math.pi * freq * tt) + bright * np.sin(2 * math.pi * 2 * freq * tt) * np.exp(-tt / (decay / 3))
        sig *= env * amp
        out[i0:i0 + m_, 0] += sig * (1 - pan)
        out[i0:i0 + m_, 1] += sig * pan

    pattern = rng.choice([[0, 1, 2, 1, 0, 2, 1, 2], [0, 2, 1, 2, 0, 2, 1, 0], [0, 1, 2, 3, 2, 1, 0, 1]])
    nbars = int(math.ceil(duration / bar))
    for b in range(nbars):
        root = key + prog[b % 4]
        chord = MINOR if prog[b % 4] == 9 else MAJOR
        tones = [root + c for c in chord] + [root + 12]
        t0 = b * bar
        add(t0, _note(root - 24), bar * 1.2, 0.20, bar * 0.6, 0.5, 0.0)                 # bass
        for tone in tones[:3]:                                                          # pad
            add(t0, _note(tone - 12), bar * 1.1, 0.045, bar * 0.9, rng.random(), 0.0)
        for k, idx in enumerate(pattern):                                               # pluck arpeggio
            if quiet and k % 2:
                continue
            add(t0 + k * beat / 2, _note(tones[idx % len(tones)]), beat * 2,
                0.07 if quiet else 0.10, beat * 0.45, 0.3 + 0.4 * rng.random(), 0.35)
    peak = np.max(np.abs(out)) or 1.0
    return out / peak * 0.5


class ProceduralProvider(Provider):
    name = "procedural"

    def music(self, *, cfg, prompt, duration_sec, seed, out):
        import numpy as np
        audio = compose(prompt, duration_sec, seed)
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
        with wave.open(str(out), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm.tobytes())
        return ProviderResult(gpu_seconds=0.0, provider_meta={"note": "procedural, not AI"})
