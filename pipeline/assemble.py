"""Stage 6 — assemble: deterministic FFmpeg post-production.

1. mix:   narration placed at shot start + lead; music cues placed and faded;
          music ducked under narration (sidechaincompress); two-pass loudnorm
          to the storyboard target (default -14 LUFS / -1 dBTP).
2. per export aspect (16:9, 9:16):
          normalise each shot clip (scale/crop/fps/exact length) — cached per shot;
          render end card; render safe-area subtitles + AI badge as PNG overlays;
          concat + overlay + mux -> outputs/final/heritage_<aspect>.mp4
3. report: measure the loudness of each final file -> outputs/final/report.json

Every step is input-hash cached, so editing one shot re-normalises only that
shot's clips and re-runs the cheap final mux.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .common.cache import cached_local, require_meta
from .common.cli import stage_main
from .common.context import Ctx
from .common.hashing import write_if_changed
from .common.media import BITEXACT, SAMPLE_RATE, X264, X264_FAST, check_ffmpeg, ffmpeg, loudness
from .common.storyboard import cue_spans, timeline, total_duration
from .common.text_render import badge_png, end_card_png, subtitle_png

# Bump only the step whose code changed so other cached steps stay valid.
MIX_VERSION = "assemble/v2"
CLIP_VERSION = "assemble/v2"
FINAL_VERSION = "assemble/v2"  # v2: half-open subtitle intervals (no overlap frame)


def aspect_tag(aspect: str) -> str:
    return aspect.replace(":", "x")


# ---------------------------------------------------------------- audio mix
def build_mix(ctx: Ctx) -> dict[str, Any]:
    sb, audio = ctx.sb, ctx.sb["audio"]
    total = total_duration(sb)
    starts = {r["shot_id"]: r["start"] for r in timeline(sb)}
    narr = []
    for s in ctx.shots:
        if s["narration"].strip():
            p = ctx.outputs / "narration" / f"{s['id']}.wav"
            m = require_meta(p, "make narration")
            narr.append({"path": p, "sha": m["output_hash"], "at": starts[s["id"]] + audio["narration_lead_sec"],
                         "dur": m["duration_sec"], "shot_id": s["id"]})
    spans = cue_spans(sb)
    music = []
    for c in sb["music_cues"]:
        if c["id"] in spans:
            p = ctx.outputs / "music" / f"{c['id']}.wav"
            m = require_meta(p, "make music")
            music.append({"path": p, "sha": m["output_hash"], "at": spans[c["id"]][0],
                          "dur": spans[c["id"]][1] - spans[c["id"]][0], "db": c["volume_db"]})

    inputs = {"v": MIX_VERSION, "total": total, "audio": audio,
              "narration": [{k: n[k] for k in ("sha", "at")} for n in narr],
              "music": [{k: m[k] for k in ("sha", "at", "dur", "db")} for m in music]}

    def build(tmp: Path) -> dict:
        args: list[str | Path] = []
        for _ in range(2):  # silent beds guarantee full length even with no narration/music
            args += ["-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=stereo:d={total:.3f}"]
        for item in narr + music:
            args += ["-i", item["path"]]
        fi, fo = audio.get("music_fade_in_sec", 1.0), audio.get("music_fade_out_sec", 2.0)
        fmt = f"aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo"
        g, n_labels, m_labels = [], ["[0:a]"], ["[1:a]"]
        for i, n in enumerate(narr):
            g.append(f"[{2 + i}:a]{fmt},adelay=delays={int(n['at'] * 1000)}:all=1[n{i}]")
            n_labels.append(f"[n{i}]")
        for j, m in enumerate(music):
            idx = 2 + len(narr) + j
            out_st = max(0.0, m["dur"] - fo)
            g.append(f"[{idx}:a]{fmt},volume={m['db']}dB,afade=t=in:d={fi},afade=t=out:st={out_st:.3f}:d={fo},"
                     f"adelay=delays={int(m['at'] * 1000)}:all=1[m{j}]")
            m_labels.append(f"[m{j}]")
        trim = f"apad=whole_dur={total:.3f},atrim=0:{total:.3f}"
        g.append(f"{''.join(n_labels)}amix=inputs={len(n_labels)}:normalize=0:duration=longest,{trim},asplit=2[narr][sc]")
        g.append(f"{''.join(m_labels)}amix=inputs={len(m_labels)}:normalize=0:duration=longest,{trim}[mus]")
        d = audio["ducking"]
        g.append(f"[mus][sc]sidechaincompress=threshold={d['threshold']}:ratio={d['ratio']}:"
                 f"attack={d['attack_ms']}:release={d['release_ms']}[duck]")
        g.append("[duck][narr]amix=inputs=2:normalize=0:duration=first[pre]")
        pre = tmp.with_name(tmp.name + ".pre.wav")
        try:
            ffmpeg(*args, "-filter_complex", ";".join(g), "-map", "[pre]", "-c:a", "pcm_s24le",
                   *BITEXACT, "-f", "wav", pre)
            # Two-pass loudnorm: measure, then apply linearly with the measured values.
            t = audio["loudness"]
            m1 = loudness(pre, t)
            ln = (f"loudnorm=I={t['integrated_lufs']}:TP={t['true_peak_db']}:LRA={t['lra']}:"
                  f"measured_I={m1['input_i']}:measured_TP={m1['input_tp']}:measured_LRA={m1['input_lra']}:"
                  f"measured_thresh={m1['input_thresh']}:offset={m1['target_offset']}:linear=true")
            ffmpeg("-i", pre, "-af", f"{ln},aresample={SAMPLE_RATE}", "-c:a", "pcm_s24le",
                   *BITEXACT, "-f", "wav", tmp)
            m2 = loudness(tmp, t)
        finally:
            pre.unlink(missing_ok=True)
        return {"pre_loudness": m1, "measured_lufs": m2["input_i"], "measured_true_peak_db": m2["input_tp"],
                "measured_lra": m2["input_lra"]}

    meta, cached = cached_local(ctx.stage_dir("assemble") / "mix.wav", inputs, build, ctx.force)
    print(f"  {'=' if cached else '+'} mix.wav  {meta['measured_lufs']:.1f} LUFS, {meta['measured_true_peak_db']:.1f} dBTP")
    return {**meta, "narr": narr}


# ---------------------------------------------------------------- subtitles
def subtitle_cues(ctx: Ctx, narr: list[dict]) -> list[dict]:
    """Split each line into ≤N-word chunks, timed proportionally to the measured audio."""
    max_words = ctx.sb["subtitles"]["max_words_per_cue"]
    by_id = {s["id"]: s["narration"].strip() for s in ctx.shots}
    cues = []
    for n in narr:
        words = by_id[n["shot_id"]].split()
        chunks, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) >= max_words or re.search(r"[.!?;:,]$", w) and len(cur) >= 3:
                chunks.append(cur)
                cur = []
        if cur:
            if chunks and len(cur) < 3:
                chunks[-1] += cur
            else:
                chunks.append(cur)
        t = n["at"]
        for ch in chunks:
            d = n["dur"] * len(ch) / len(words)
            cues.append({"start": round(t, 3), "end": round(t + d, 3), "text": " ".join(ch)})
            t += d
    return cues


def write_srt(cues: list[dict], path: Path) -> None:
    def ts(x: float) -> str:
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"
    write_if_changed(path, "".join(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n\n"
                            for i, c in enumerate(cues, 1)))


# ---------------------------------------------------------------- video
def normalise_clip(ctx: Ctx, shot: dict, w: int, h: int, tag: str) -> dict:
    src = ctx.outputs / "shots" / f"{shot['id']}.mp4"
    src_meta = require_meta(src, "make shots")
    fps, dur = ctx.sb["render"]["fps"], shot["duration_sec"]
    focus = shot.get("vertical_focus_x", 0.5) if h > w else 0.5
    inputs = {"v": CLIP_VERSION, "src": src_meta["output_hash"], "size": [w, h], "fps": fps, "dur": dur, "focus": focus,
              "crf": ctx.sb["render"].get("video_crf", 18)}

    def build(tmp: Path) -> None:
        vf = (f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,"
              f"crop={w}:{h}:x='(iw-ow)*{focus}':y='(ih-oh)/2',setsar=1,format=yuv420p,"
              f"tpad=stop_mode=clone:stop_duration={dur},trim=duration={dur},setpts=PTS-STARTPTS")
        ffmpeg("-i", src, "-vf", vf, "-an", *X264_FAST, "-crf", str(max(10, inputs["crf"] - 4)), *BITEXACT, "-f", "mp4", tmp)

    meta, _ = cached_local(ctx.stage_dir("assemble", "clips", tag) / f"{shot['id']}.mp4", inputs, build, ctx.force)
    return meta


def end_card_clip(ctx: Ctx, w: int, h: int, tag: str) -> dict:
    ec, fps = ctx.sb["end_card"], ctx.sb["render"]["fps"]
    inputs = {"v": CLIP_VERSION, "end_card": {k: ec.get(k) for k in ("duration_sec", "title", "ai_statement", "credits")},
              "size": [w, h], "fps": fps}

    def build(tmp: Path) -> None:
        png = tmp.with_name(tmp.name + ".png")
        try:
            end_card_png(png, w=w, h=h, title=ec["title"], statement=ec["ai_statement"], credits=ec.get("credits", []))
            ffmpeg("-loop", "1", "-i", png, "-t", str(ec["duration_sec"]), "-r", str(fps),
                   "-vf", "fade=t=in:d=0.6,setsar=1,format=yuv420p", *X264_FAST, "-crf", "14", *BITEXACT, "-f", "mp4", tmp)
        finally:
            png.unlink(missing_ok=True)

    meta, _ = cached_local(ctx.stage_dir("assemble", "clips", tag) / "end_card.mp4", inputs, build, ctx.force)
    return meta


def render_export(ctx: Ctx, export: dict, mix_meta: dict, cues: list[dict]) -> Path:
    sb = ctx.sb
    w, h = export["resolution"]
    tag = aspect_tag(export["aspect"])
    clip_dir = ctx.outputs / "assemble" / "clips" / tag
    clip_metas = [normalise_clip(ctx, s, w, h, tag) for s in ctx.shots]
    ec_meta = end_card_clip(ctx, w, h, tag)
    total = total_duration(sb)
    badge = sb["ai_disclosure"]
    end_card_start = total - sb["end_card"]["duration_sec"]
    subs_on = sb["subtitles"]["enabled"]

    inputs = {"v": FINAL_VERSION, "clips": [m["output_hash"] for m in clip_metas], "end_card": ec_meta["output_hash"],
              "mix": mix_meta["output_hash"], "cues": cues if subs_on else [], "badge": badge,
              "size": [w, h], "crf": sb["render"].get("video_crf", 18)}

    def build(tmp: Path) -> None:
        overlay_dir = ctx.stage_dir("assemble", "overlays", tag)
        for old in overlay_dir.glob("*.png"):
            old.unlink()
        args: list[str | Path] = []
        for s in ctx.shots:
            args += ["-i", clip_dir / f"{s['id']}.mp4"]
        args += ["-i", clip_dir / "end_card.mp4"]
        n_vid = len(ctx.shots) + 1
        g = [f"{''.join(f'[{i}:v]' for i in range(n_vid))}concat=n={n_vid}:v=1:a=0[v0]"]
        overlays: list[tuple[Path, int, int, float, float]] = []
        if subs_on:
            for i, c in enumerate(cues):
                png = overlay_dir / f"sub_{i:03}.png"
                x, y = subtitle_png(c["text"], png, frame_w=w, frame_h=h)
                overlays.append((png, x, y, c["start"], c["end"]))
        if badge["persistent_badge"]:
            png = overlay_dir / "badge.png"
            x, y = badge_png(badge["badge_text"], png, frame_w=w, frame_h=h)
            overlays.append((png, x, y, 0.0, end_card_start))
        cur = "v0"
        for k, (png, x, y, a, b) in enumerate(overlays):
            args += ["-i", png]
            g.append(f"[{cur}][{n_vid + k}:v]overlay=x={x}:y={y}:enable='gte(t,{a:.3f})*lt(t,{b:.3f})'[v{k + 1}]")
            cur = f"v{k + 1}"
        args += ["-i", ctx.outputs / "assemble" / "mix.wav"]
        audio_idx = n_vid + len(overlays)
        ffmpeg(*args, "-filter_complex", ";".join(g), "-map", f"[{cur}]", "-map", f"{audio_idx}:a",
               "-t", f"{total:.3f}", "-r", str(sb["render"]["fps"]), *X264, "-crf", str(inputs["crf"]),
               "-c:a", "aac", "-b:a", "192k", "-ar", str(SAMPLE_RATE), "-movflags", "+faststart",
               *BITEXACT, "-f", "mp4", tmp)

    out = ctx.stage_dir("final") / f"heritage_{tag}.mp4"
    _, cached = cached_local(out, inputs, build, ctx.force)
    print(f"  {'=' if cached else '+'} {out.name}")
    return out


def run(ctx: Ctx) -> None:
    check_ffmpeg()
    if ctx.only_shots:
        print("  (assemble always uses all shots; --shots only limits per-shot stages)")
    mix = build_mix(ctx)
    cues = subtitle_cues(ctx, mix["narr"])
    final_dir = ctx.stage_dir("final")
    write_srt(cues, final_dir / "heritage.srt")
    outputs = [render_export(ctx, e, mix, cues) for e in ctx.sb["render"]["exports"]]

    report = {"title": ctx.sb["title"], "duration_sec": total_duration(ctx.sb),
              "loudness_target": ctx.sb["audio"]["loudness"], "exports": {}}
    for p in outputs:
        m = loudness(p, ctx.sb["audio"]["loudness"])
        report["exports"][p.name] = {"measured_lufs": m["input_i"], "measured_true_peak_db": m["input_tp"],
                                     "measured_lra": m["input_lra"], "bytes": p.stat().st_size}
    write_if_changed(final_dir / "report.json", json.dumps(report, indent=2))
    for name, r in report["exports"].items():
        print(f"  ✓ {name}: {r['measured_lufs']:.1f} LUFS, {r['measured_true_peak_db']:.1f} dBTP (measured)")
    write_if_changed(final_dir / "storyboard.snapshot.json", ctx.storyboard_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    stage_main("assemble", run)
