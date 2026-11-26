"""Offline, deterministic placeholder provider. Zero cost, no GPU, no network.

Lets the whole pipeline (caching, telemetry, ducking, loudness, exports) be
exercised from a clean clone. It intentionally has NO video model, so every
shot goes through the Ken Burns fallback path.
"""
from __future__ import annotations

from pathlib import Path

from ..common.hashing import stable_hash
from ..common.media import BITEXACT, SAMPLE_RATE, ffmpeg
from ..common.storyboard import word_count
from ..common.text_render import placeholder_keyframe
from .base import Provider, ProviderResult

STUB_WORDS_PER_SEC = 2.5


class StubProvider(Provider):
    name = "stub"

    def image(self, *, cfg, prompt, negative_prompt, seed, width, height, reference_image, out):
        mix = int(stable_hash([prompt, seed])[:8], 16)
        placeholder_keyframe(out, w=width, h=height, prompt=prompt, seed=mix)
        return ProviderResult(gpu_seconds=0.0, provider_meta={"note": "placeholder image"})

    def tts(self, *, cfg, text, voice_id, speed, seed, out):
        dur = max(1.0, word_count(text) / (STUB_WORDS_PER_SEC * speed))
        # Syllable-rate amplitude modulation so sidechain ducking is audible in tests.
        expr = "0.35*sin(2*PI*190*t)*(0.55+0.45*sin(2*PI*4*t))"
        ffmpeg("-f", "lavfi", "-i", f"aevalsrc={expr}:s={SAMPLE_RATE}:d={dur:.3f}",
               "-af", "afade=t=in:d=0.05,afade=t=out:st=%.3f:d=0.1" % (dur - 0.1),
               "-ac", "1", "-c:a", "pcm_s16le", *BITEXACT, "-f", "wav", out)
        return ProviderResult(gpu_seconds=0.0, provider_meta={"note": "placeholder tone, not speech"})

    def music(self, *, cfg, prompt, duration_sec, seed, out):
        root = 110 + (int(stable_hash([prompt, seed])[:4], 16) % 110)
        f1, f2, f3 = root, root * 1.25, root * 1.5  # major triad
        expr = (f"0.12*(sin(2*PI*{f1:.2f}*t)+sin(2*PI*{f2:.2f}*t)+sin(2*PI*{f3:.2f}*t))"
                f"*(0.7+0.3*sin(2*PI*0.25*t))")
        ffmpeg("-f", "lavfi", "-i", f"aevalsrc={expr}|{expr}:s={SAMPLE_RATE}:d={duration_sec:.3f}",
               "-c:a", "pcm_s16le", *BITEXACT, "-f", "wav", out)
        return ProviderResult(gpu_seconds=0.0, provider_meta={"note": "placeholder chord pad"})
