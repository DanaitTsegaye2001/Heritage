"""Radio cut: narration + (placeholder) score over black, with subtitles.

The brief's Phase 1 checkpoint. Lets you test story and timing with your audience
before any picture exists. Reuses the real mix (ducking + loudness) from assemble,
so it needs only the narration and music stages:

    make radio-cut   ->  outputs/final/radio_cut.mp4
"""
from __future__ import annotations

from pathlib import Path

from .assemble import build_mix, subtitle_cues
from .common.cache import cached_local
from .common.cli import stage_main
from .common.context import Ctx
from .common.media import BITEXACT, SAMPLE_RATE, X264_FAST, check_ffmpeg, ffmpeg
from .common.storyboard import total_duration
from .common.text_render import subtitle_png

VERSION = "radio_cut/v1"
W, H = 1280, 720


def run(ctx: Ctx) -> None:
    check_ffmpeg()
    mix = build_mix(ctx)
    cues = subtitle_cues(ctx, mix["narr"])
    total = total_duration(ctx.sb)
    inputs = {"v": VERSION, "mix": mix["output_hash"], "cues": cues, "size": [W, H]}

    def build(tmp: Path) -> None:
        overlay_dir = ctx.stage_dir("assemble", "overlays", "radio")
        args: list[str | Path] = ["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r=24:d={total:.3f}"]
        graph, cur = [], "0:v"
        for i, c in enumerate(cues):
            png = overlay_dir / f"sub_{i:03}.png"
            x, y = subtitle_png(c["text"], png, frame_w=W, frame_h=H)
            args += ["-i", png]
            graph.append(f"[{cur}][{i + 1}:v]overlay=x={x}:y={y}:enable='gte(t,{c['start']:.3f})*lt(t,{c['end']:.3f})'[v{i}]")
            cur = f"v{i}"
        args += ["-i", ctx.outputs / "assemble" / "mix.wav"]
        maps = ["-map", f"[{cur}]"] if graph else ["-map", "0:v"]
        ffmpeg(*args, *(["-filter_complex", ";".join(graph)] if graph else []), *maps, "-map", f"{len(cues) + 1}:a",
               "-t", f"{total:.3f}", *X264_FAST, "-crf", "28", "-c:a", "aac", "-b:a", "160k",
               "-ar", str(SAMPLE_RATE), "-movflags", "+faststart", *BITEXACT, "-f", "mp4", tmp)

    out = ctx.stage_dir("final") / "radio_cut.mp4"
    _, cached = cached_local(out, inputs, build, ctx.force)
    print(f"  {'=' if cached else '+'} {out.name}  ({total:.1f}s, {mix['measured_lufs']:.1f} LUFS)")


if __name__ == "__main__":
    stage_main("radio_cut", run)
