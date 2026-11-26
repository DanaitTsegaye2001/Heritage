# Failures and workarounds

Log every failure that cost time: model errors, queue timeouts, bad generations, tooling problems.
Cite `run_id` / `input_hash` from `runs.jsonl` where applicable. The entries below F-100 are real
issues hit while building the pipeline itself (2026-11-26). Add production-run entries from F-100 on.

Entry format:

```
### F-NNN — title
- When / run_id / stage / shot:
- Symptom (exact error text):
- Cause:
- Workaround / fix (commit):
- Prevention:
```

---

## Build-time (pipeline development)

### F-001 — FFmpeg build has no `drawtext` / `subtitles` filters
- When: 2026-11-26, initial environment check (Homebrew ffmpeg 9.1, macOS).
- Symptom: `ffmpeg -filters` lists neither `drawtext` nor `subtitles`; the build lacks libfreetype/libass.
- Cause: common in minimal/default ffmpeg builds.
- Workaround / fix: all text (subtitles, AI badge, end card) is rendered as PNGs with Pillow and composited with the `overlay` filter. `check_ffmpeg()` verifies only the filters the pipeline really uses.
- Prevention: no dependency on font-enabled ffmpeg; this also makes text rendering identical across builds that share a font.

### F-002 — Assemble stage slow at full resolution
- When: 2026-11-26, first full stub run.
- Symptom: `assemble` took 234.9 s of a 308.6 s run. Profiling showed ~8 s per normalised clip (22 clips over two aspects) at x264 preset `medium`.
- Fix: intermediates (Ken Burns clips, normalised clips, end card) use preset `veryfast` at a lower CRF; only the final export uses `medium`. Clips are cached per aspect, so later runs re-encode only changed shots.
- Prevention: keep heavy work in per-shot cached steps.

### F-003 — No-op re-run touched derived files
- When: 2026-11-26, first run of `tests/test_pipeline.py`.
- Symptom: a second run with an unchanged storyboard rewrote `script/*.md|json` and `final/report.json` (mtime changed), so the test failed.
- Fix: `write_if_changed()` for all derived text artifacts.
- Prevention: the test asserts a no-op run changes no file mtimes.

## Production runs

### F-100 — [TODO]
- When / run_id / stage / shot:
- Symptom:
- Cause:
- Workaround / fix:
- Prevention:
