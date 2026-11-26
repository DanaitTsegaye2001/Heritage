"""Google Gemini API adapter (AI Studio key, stdlib only).

TTS:   gemini-3.8-flash-tts (free tier; verified 2026-11-26: 200 OK, 24 kHz mono WAV).
       A plain-language style instruction (voice.style) steers delivery.
Music: Lyria models exist on the API but the free tier has a quota of 0 (FAILURES.md F-100),
       so music() reports a clear PermanentError instead of retrying.

GPU time is not reported by the API, so gpu_seconds is None (logged as null).
"""
from __future__ import annotations

import base64
import json
import socket
import urllib.error
import urllib.request
from typing import Any

from ..common.env import require_env
from ..common.media import to_wav
from ..common.retry import PermanentError, TransientError
from .base import Provider, ProviderResult

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
QUOTA_HINTS = ("limit: 0", "requests per day")  # per-minute limits stay transient (retried)


def _generate(model: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(API.format(model=model), data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": require_env("GEMINI_API_KEY"),
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        msg = f"HTTP {e.code}: {detail[:300]}"
        # Daily / zero quotas won't recover within a retry window: fail fast.
        if e.code == 429 and any(h in detail for h in QUOTA_HINTS):
            raise PermanentError("quota exhausted — " + msg) from e
        if e.code in (408, 429) or e.code >= 500:
            raise TransientError(msg) from e
        raise PermanentError(msg) from e
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        raise TransientError(f"network error: {e}") from e


def _inline_audio(data: dict[str, Any]) -> tuple[bytes, str]:
    try:
        for part in data["candidates"][0]["content"]["parts"]:
            if "inlineData" in part:
                return base64.b64decode(part["inlineData"]["data"]), part["inlineData"].get("mimeType", "")
    except (KeyError, IndexError):
        pass
    reason = (data.get("candidates") or [{}])[0].get("finishReason") or data.get("promptFeedback")
    raise PermanentError(f"no audio in Gemini response (reason: {reason})")


class GeminiProvider(Provider):
    name = "gemini"

    def tts(self, *, cfg, text, voice_id, speed, seed, out):
        style = cfg.get("params", {}).get("style", "").strip()
        prompt = f"{style}: {text}" if style else text
        data = _generate(cfg["model"], {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_id}}}},
        })
        audio, mime = _inline_audio(data)
        raw = out.with_name(out.name + ".download")
        try:
            if "pcm" in mime.lower() or "l16" in mime.lower():  # headerless PCM: wrap via ffmpeg raw input
                from ..common.media import ffmpeg, BITEXACT, SAMPLE_RATE
                rate = next((p.split("=")[1] for p in mime.split(";") if "rate=" in p), "24000")
                raw.write_bytes(audio)
                ffmpeg("-f", "s16le", "-ar", rate, "-ac", "1", "-i", raw, "-ar", str(SAMPLE_RATE),
                       "-c:a", "pcm_s16le", *BITEXACT, "-f", "wav", out)
            else:
                raw.write_bytes(audio)
                to_wav(raw, out, channels=1)
        finally:
            raw.unlink(missing_ok=True)
        return ProviderResult(gpu_seconds=None, provider_meta={"mime": mime, "usage": data.get("usageMetadata")})

    def music(self, *, cfg, prompt, duration_sec, seed, out):
        raise PermanentError("Lyria has no free-tier quota on this project (FAILURES.md F-100); "
                             "use the import provider with the Kaggle ACE-Step notebook")
