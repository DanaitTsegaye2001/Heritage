"""Stage 4 — narration: one TTS clip per shot line (silent shots are skipped)."""
from __future__ import annotations

import sys
from pathlib import Path

from .common.cache import run_model_cached
from .common.cli import stage_main
from .common.context import Ctx
from .common.media import probe_duration
from .common.storyboard import model_key
from .providers import get_provider

VERSION = "narration/v1"


def run(ctx: Ctx) -> None:
    sb = ctx.sb
    default_cfg = sb["models"]["tts"]
    voice = sb["voice"]
    lead = sb["audio"]["narration_lead_sec"]
    out_dir = ctx.stage_dir("narration")

    for shot in ctx.shots:
        sid, text = shot["id"], shot["narration"].strip()
        if not ctx.selected(sid) or not text:
            continue
        cfg = shot.get("tts_model") or default_cfg
        provider = get_provider(cfg["provider"])
        seed = voice.get("seed")
        inputs = {"v": VERSION, "model": model_key(cfg), "text": text, "voice_id": voice["voice_id"],
                  "speed": voice.get("speed", 1.0), "seed": seed}

        def measure(tmp: Path) -> dict:
            return {"duration_sec": round(probe_duration(tmp), 3)}

        meta = run_model_cached(
            ctx, stage="narration", shot_id=sid, cfg=cfg, inputs=inputs, out=out_dir / f"{sid}.wav", seed=seed,
            call=lambda tmp, text=text, cfg=cfg, provider=provider: provider.tts(cfg=cfg, text=text, voice_id=voice["voice_id"],
                                                     speed=voice.get("speed", 1.0), seed=seed, out=tmp),
            postprocess=measure)
        room = shot["duration_sec"] - lead
        if meta["duration_sec"] > room:
            print(f"  ⚠ {sid}: narration is {meta['duration_sec']:.1f}s but only {room:.1f}s fits; "
                  f"it will overlap the next shot. Shorten the line or lengthen the shot.", file=sys.stderr)


if __name__ == "__main__":
    stage_main("narration", run)
