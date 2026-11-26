"""Local TTS using macOS `say`. Free, offline, real speech; good for timing tests."""
from __future__ import annotations

import shutil
import subprocess

from ..common.media import to_wav
from ..common.retry import ModelUnavailable, PermanentError
from .base import Provider, ProviderResult


class MacOSSayProvider(Provider):
    name = "macos_say"

    def tts(self, *, cfg, text, voice_id, speed, seed, out):
        if not shutil.which("say"):
            raise ModelUnavailable("`say` not found (macOS only)")
        rate = int(175 * speed)  # say's default is ~175 wpm
        aiff = out.with_suffix(".aiff")
        cmd = ["say", "-r", str(rate), "-o", str(aiff)]
        if voice_id and not voice_id.endswith("_placeholder"):
            cmd[1:1] = ["-v", voice_id]
        proc = subprocess.run([*cmd, text], capture_output=True, text=True)
        if proc.returncode != 0:
            raise PermanentError(f"say failed: {proc.stderr.strip()}")
        try:
            to_wav(aiff, out)
        finally:
            aiff.unlink(missing_ok=True)
        return ProviderResult(gpu_seconds=0.0, provider_meta={"rate_wpm": rate})
