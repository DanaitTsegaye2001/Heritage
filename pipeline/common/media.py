"""Thin, deterministic wrappers around ffmpeg/ffprobe."""
from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

# Strip encoder/creation metadata so identical inputs give identical files
# (byte-identical across machines also requires the same ffmpeg/x264 build).
BITEXACT = ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]
X264 = ["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-threads", "4"]
# Intermediates: faster preset at lower CRF (higher quality) — they are re-encoded once more.
X264_FAST = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-threads", "4"]
SAMPLE_RATE = 48000

REQUIRED_FILTERS = ["zoompan", "overlay", "concat", "sidechaincompress", "loudnorm", "amix", "adelay", "afade", "apad"]


class FFmpegError(RuntimeError):
    pass


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(list(cmd), capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise FFmpegError(f"{cmd[0]} failed ({proc.returncode}):\n{tail}")
    return proc


def ffmpeg(*args: str | Path, loglevel: str = "error") -> subprocess.CompletedProcess[str]:
    return _run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", loglevel, "-y", *map(str, args)])


def probe_duration(path: Path) -> float:
    proc = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(path)])
    return float(proc.stdout.strip())


@functools.cache
def check_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found on PATH. Install FFmpeg (e.g. `brew install ffmpeg`).")
    filters = _run(["ffmpeg", "-hide_banner", "-filters"]).stdout
    missing = [f for f in REQUIRED_FILTERS if not re.search(rf"\s{f}\s", filters)]
    encoders = _run(["ffmpeg", "-hide_banner", "-encoders"]).stdout
    if "libx264" not in encoders:
        missing.append("libx264 encoder")
    if missing:
        raise SystemExit(f"Your ffmpeg build lacks: {', '.join(missing)}")


def to_wav(src: Path, dst: Path, channels: int = 1) -> None:
    ffmpeg("-i", src, "-ac", str(channels), "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
           *BITEXACT, "-f", "wav", dst)


def fit_audio(src: Path, dst: Path, duration: float, channels: int = 2) -> None:
    """Pad with silence or trim so audio is exactly `duration` seconds."""
    ffmpeg("-i", src, "-af", f"apad=whole_dur={duration:.3f},atrim=0:{duration:.3f}",
           "-ac", str(channels), "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", *BITEXACT, "-f", "wav", dst)


def loudness(path: Path, target: dict[str, Any] | None = None) -> dict[str, float]:
    """EBU R128 analysis via loudnorm's measurement pass. Returns measured input_* values."""
    t = target or {"integrated_lufs": -14, "true_peak_db": -1, "lra": 11}
    proc = ffmpeg("-i", path, "-vn", "-af",
                  f"loudnorm=I={t['integrated_lufs']}:TP={t['true_peak_db']}:LRA={t['lra']}:print_format=json",
                  "-f", "null", "-", loglevel="info")
    match = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, flags=re.S)
    if not match:
        raise FFmpegError("could not parse loudnorm output")
    return {k: float(v) for k, v in json.loads(match[-1]).items() if k != "normalization_type"}
