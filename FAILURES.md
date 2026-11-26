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

### F-004 — Two subtitle cues visible on the boundary frame
- When: 2026-11-26, visual check of a 9:16 frame at t=16.5 s.
- Symptom: a faint second line showed through the subtitle box. The SRT showed a cue boundary at exactly 16.500 s.
- Cause: `enable='between(t,a,b)'` is inclusive at both ends, so the outgoing and incoming cues overlapped for one frame, and the semi-transparent box let the other text show.
- Fix: half-open interval `gte(t,a)*lt(t,b)`. Assemble versions are now split per step (mix / clips / final), so a final-mux fix doesn't force clips to re-encode.

## Production runs

### F-100 — Gemini API: Lyria music has zero free-tier quota; no Veo access
- When: 2026-11-26, provider probing (direct API call, not a pipeline run).
- Symptom: `POST models/lyria-3-clip-preview:generateContent` → `HTTP 429 … generate_content_free_tier_input_token_count, limit: 0, model: lyria-3-clip`. The key's model list shows no `veo-*` / `imagen-*` models.
- Cause: the AI Studio project is on the free tier; Lyria (and Veo) need billing enabled.
- Workaround: music stays on `stub` until billing is on, or until a licensed track is used. Video uses the Ken Burns fallback. Cloudflare Workers AI covers images (`@cf/leonardo/lucid-origin`) and narration (`@cf/deepgram/aura-2-en`); both verified live (1920×1080 image in 11.9 s; 5.09 s of speech in 4.4 s).
- Prevention: probe each provider with one call before switching the storyboard to it.

### F-101 — Cloudflare Workers AI daily allocation used up after 2 images
- When: 2026-11-26 ~18:20 EAT, probing FLUX.2 klein after two `lucid-origin` test images (1920×1080) and two `aura-2-en` clips.
- Symptom: `HTTP 429 … code 4006: you have used up your daily free allocation of 10,000 neurons`.
- Cause: `@cf/leonardo/lucid-origin` at 1920×1080 costs far more neurons per image than the distilled FLUX models the brief budgets for (50–170 images/day).
- Workaround: the Cloudflare adapter now raises PermanentError on code 4006 instead of retrying a quota that resets at 00:00 UTC (03:00 EAT). Keyframes move to FLUX.2 klein-4B on a Kaggle GPU (notebook + import provider).
- Prevention: draft at 1024 px with a distilled model (klein/schnell); check the neuron cost of one call before batching.

### F-102 — Gemini image models: free-tier quota 0
- When: 2026-11-26 ~18:30 EAT.
- Symptom: `gemini-2.5-flash-image` → `429 … generate_content_free_tier_requests, limit: 0`. Adding `imageConfig` to the request returned an empty 404.
- Cause: Nano Banana image models need billing (as the brief says).
- Workaround: see F-101.

### F-103 — Gemini TTS: 10 requests/day per model on the free tier
- When: 2026-11-26 ~18:50 EAT, during the narration-pace experiment (EXPERIMENTS E-06).
- Symptom: `429 … GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 10, model: gemini-3.8-flash-tts … retry in 16h25m`.
- Cause: the free tier allows 10 TTS requests per model per day. 13 narration calls plus 4 style probes used them up.
- Workaround: the quota is per model, so `gemini-3.8-flash-lite-tts` still works (verified: 2.02 w/s, 5.1 s latency). The Gemini adapter fails fast on `limit: 0` / per-day messages but still retries per-minute limits. Plan: iterate the radio cut with free local TTS (`macos_say`) and spend Gemini requests only on locked lines (one per shot, plus few retakes).
- Prevention: count TTS calls in `runs.jsonl` before regenerating everything; editing one line costs one request thanks to the cache.

### F-104 — [TODO]
- When / run_id / stage / shot:
- Symptom:
- Cause:
- Workaround / fix:
- Prevention:
