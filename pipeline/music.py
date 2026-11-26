"""Stage 5 — music: one track per cue, fitted to the exact span of its shots."""
from __future__ import annotations

from pathlib import Path

from .common.cache import run_model_cached
from .common.cli import stage_main
from .common.context import Ctx
from .common.media import fit_audio, probe_duration
from .common.storyboard import cue_spans, model_key
from .providers import get_provider

VERSION = "music/v1"


def run(ctx: Ctx) -> None:
    sb = ctx.sb
    cfg = sb["models"]["music"]
    provider = get_provider(cfg["provider"])
    spans = cue_spans(sb)
    out_dir = ctx.stage_dir("music")

    for cue in sb["music_cues"]:
        if cue["id"] not in spans:
            continue
        # --shots limits music to cues touching those shots
        if ctx.only_shots and not any(s["music_cue"] == cue["id"] for s in ctx.shots if ctx.selected(s["id"])):
            continue
        start, end = spans[cue["id"]]
        dur = round(end - start, 3)
        inputs = {"v": VERSION, "model": model_key(cfg), "prompt": cue["prompt"], "seed": cue["seed"],
                  "duration": dur}

        def fit(tmp: Path, dur=dur) -> dict:
            raw = probe_duration(tmp)
            fitted = tmp.with_name(tmp.name + ".fit.wav")
            fit_audio(tmp, fitted, dur)
            fitted.replace(tmp)
            return {"generated_duration_sec": round(raw, 3), "duration_sec": dur}

        run_model_cached(
            ctx, stage="music", shot_id=None, cfg=cfg, inputs=inputs, out=out_dir / f"{cue['id']}.wav",
            seed=cue["seed"],
            call=lambda tmp, cue=cue, dur=dur: provider.music(cfg=cfg, prompt=cue["prompt"], duration_sec=dur,
                                                             seed=cue["seed"], out=tmp),
            postprocess=fit)


if __name__ == "__main__":
    stage_main("music", run)
