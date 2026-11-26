"""Stage 1 — script: compile the narration script and timeline from the storyboard.

Deterministic and model-free: the storyboard *is* the script. Outputs are for
humans (table read, user tests) and for later stages (timeline.json).
"""
from __future__ import annotations

import json

from .common.cli import stage_main
from .common.context import Ctx
from .common.hashing import write_if_changed
from .common.storyboard import WORDS_PER_SEC, cue_spans, timeline, total_duration


def run(ctx: Ctx) -> None:
    sb = ctx.sb
    out = ctx.stage_dir("script")
    tl = timeline(sb)
    words = sum(r["words"] for r in tl)

    write_if_changed(out / "timeline.json", json.dumps(
        {"shots": tl, "music_cues": cue_spans(sb), "end_card_start": tl[-1]["end"],
         "total_sec": total_duration(sb), "narration_words": words}, indent=2))

    write_if_changed(out / "narration.txt", "\n".join(s["narration"] for s in sb["shots"] if s["narration"]) + "\n")

    md = [f"# {sb['title']}", "", f"_{sb['logline']}_", "",
          f"**Runtime:** {total_duration(sb):.1f}s (incl. {sb['end_card']['duration_sec']}s end card) · "
          f"**Narration:** {words} words (~{words / WORDS_PER_SEC:.0f}s at {WORDS_PER_SEC} w/s)", "",
          "| Shot | Time | Dur | Cue | Purpose | Narration |", "|---|---|---|---|---|---|"]
    for s, r in zip(sb["shots"], tl):
        md.append(f"| {s['id']} | {r['start']:.1f}–{r['end']:.1f} | {s['duration_sec']}s | {s['music_cue'] or '—'} "
                  f"| {s['purpose']} | {s['narration'] or '_(silent)_'} |")
    write_if_changed(out / "script.md", "\n".join(md) + "\n")
    print(f"  ✓ {len(tl)} shots, {total_duration(sb):.1f}s, {words} words → {out.relative_to(ctx.root) if out.is_relative_to(ctx.root) else out}")


if __name__ == "__main__":
    stage_main("script", run)
