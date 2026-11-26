"""Stage 3 — shots: animate each keyframe into a clip.

Order of preference per shot:
  1. image-to-video model (unless shot.skip_video)
  2. deterministic Ken Burns pan-and-zoom on the keyframe (FFmpeg zoompan)

A fallback caused by ModelUnavailable or skip_video is cached normally. A
fallback caused by exhausted transient retries is marked `retry_next_run`, so
the next run tries the model again instead of locking in the fallback.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from .common.cache import lookup, require_meta, run_model_cached, store, tmp_path
from .common.cli import stage_main
from .common.context import Ctx
from .common.hashing import stable_hash
from .common.media import BITEXACT, X264_FAST, ffmpeg
from .common.retry import ModelUnavailable, PermanentError, TransientError
from .common.storyboard import model_key
from .providers import get_provider

VERSION = "shots/v1"
DEFAULT_CAMERA = {"zoom_start": 1.0, "zoom_end": 1.12, "pan": "none"}


def ken_burns(image: Path, out: Path, *, duration: float, fps: int, size: tuple[int, int],
              camera: dict, crf: int) -> None:
    w, h = size
    frames = max(2, round(duration * fps))
    zs, ze, pan = camera["zoom_start"], camera["zoom_end"], camera["pan"]
    p = f"(on/{frames - 1})"  # progress 0 -> 1
    z = f"{zs}+({ze}-{zs})*{p}"
    cx = {"left": f"(1-{p})", "right": p}.get(pan, "0.5")
    cy = {"up": f"(1-{p})", "down": p}.get(pan, "0.5")
    # Upscale 2x first to avoid zoompan's integer-pixel jitter.
    vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
          f"zoompan=z='{z}':x='(iw-iw/zoom)*{cx}':y='(ih-ih/zoom)*{cy}':d={frames}:s={w}x{h}:fps={fps},"
          f"setsar=1,format=yuv420p")
    ffmpeg("-loop", "1", "-i", image, "-vf", vf, "-frames:v", str(frames), "-r", str(fps),
           *X264_FAST, "-crf", str(crf), *BITEXACT, "-an", "-f", "mp4", out)


def run(ctx: Ctx) -> None:
    sb = ctx.sb
    cfg = sb["models"]["video"]
    provider = get_provider(cfg["provider"])
    fps = sb["render"]["fps"]
    mw, mh = sb["render"]["master_resolution"]
    crf = max(10, sb["render"].get("video_crf", 18) - 2)  # intermediates a little higher quality
    out_dir = ctx.stage_dir("shots")

    for shot in ctx.shots:
        sid = shot["id"]
        if not ctx.selected(sid):
            continue
        kf = ctx.outputs / "keyframes" / f"{sid}.png"
        kf_meta = require_meta(kf, "make keyframes")
        camera = {**DEFAULT_CAMERA, **shot.get("camera", {})}
        skip = shot.get("skip_video", False)
        inputs = {
            "v": VERSION, "keyframe_sha256": kf_meta["output_hash"], "motion_prompt": shot["motion_prompt"],
            "model": None if skip else model_key(cfg), "seed": shot["seed"], "duration": shot["duration_sec"],
            "fps": fps, "resolution": [mw, mh], "camera": camera, "skip_video": skip,
        }
        out = out_dir / f"{sid}.mp4"
        kb = lambda tmp, shot=shot, kf=kf, camera=camera: ken_burns(
            kf, tmp, duration=shot["duration_sec"], fps=fps, size=(mw, mh), camera=camera, crf=crf)

        if skip:  # no model call -> no runs.jsonl line; plain local cache
            h = stable_hash(inputs)
            if not ctx.force and lookup(out, h):
                print(f"  = shots:{sid} cached (ken burns)")
                continue
            tmp = tmp_path(out)
            try:
                kb(tmp)
                store(out, tmp, h, inputs, fallback="kenburns", fallback_reason="skip_video")
            finally:
                tmp.unlink(missing_ok=True)
            print(f"  + shots:{sid} ken burns (skip_video)")
            continue

        try:
            run_model_cached(
                ctx, stage="shots", shot_id=sid, cfg=cfg, inputs=inputs, out=out, seed=shot["seed"],
                call=lambda tmp, shot=shot, kf=kf: provider.video(
                    cfg=cfg, prompt=shot["motion_prompt"], image=kf, seed=shot["seed"],
                    duration_sec=shot["duration_sec"], fps=fps, width=mw, height=mh, out=tmp))
        except (PermanentError, TransientError) as e:
            transient = isinstance(e, TransientError)
            if not isinstance(e, ModelUnavailable) and not transient:
                print(f"  ! shots:{sid} video model refused ({e}); using Ken Burns", file=sys.stderr)
            tmp = tmp_path(out)
            t0 = time.monotonic()
            try:
                kb(tmp)
                store(out, tmp, stable_hash(inputs), inputs, fallback="kenburns",
                      fallback_reason=f"{type(e).__name__}: {e}"[:300], retry_next_run=transient)
            finally:
                tmp.unlink(missing_ok=True)
            print(f"  ~ shots:{sid} ken burns fallback ({type(e).__name__}) in {time.monotonic() - t0:.1f}s")


if __name__ == "__main__":
    stage_main("shots", run)
