# Architecture

## 1. Contract

`storyboard.json` is the only creative/configuration input. `pipeline/common/storyboard.py` validates it in two steps on **every** run (every stage entry point calls it):

1. **JSON Schema** (`schema/storyboard.schema.json`, Draft 2020-12, `additionalProperties: false` everywhere): 8–12 shots, per-field types and ranges, shot id pattern `sNN`, model blocks, audio targets.
2. **Semantic rules** a schema can't express: total runtime (shots + end card) 60–90 s; 130–220 narration words; unique shot ids; music cues defined and covering *contiguous* shots; reference images exist on disk. **Warnings** (not errors): narration estimated not to fit its shot at 2.6 words/s, reference images without a recorded licence, unused cues.

`notes` and `pricing` fields are stripped before hashing, so annotating the storyboard never triggers regeneration.

## 2. Stages

| Stage | Reads | Writes | Model call |
|---|---|---|---|
| `script` | storyboard | `script/script.md`, `narration.txt`, `timeline.json` | none |
| `keyframes` | storyboard (+ reference image) | `keyframes/sNN.png` | image, per shot |
| `shots` | keyframe | `shots/sNN.mp4` (master res) | video, per shot, unless `skip_video` |
| `narration` | storyboard | `narration/sNN.wav` (+ measured duration) | TTS, per non-empty line |
| `music` | storyboard timeline | `music/cue_*.wav` fitted to cue span | music, per cue |
| `assemble` | all of the above | `assemble/mix.wav`, `assemble/clips/*`, `final/*` | none (FFmpeg + Pillow) |

Stages are separate modules with a `run(ctx)` function. `pipeline/run.py` calls them in order, and each one also runs on its own (`python -m pipeline.<stage>`).

## 3. Caching and selective regeneration

```
artifact:  outputs/<stage>/<name>.<ext>
sidecar:   outputs/<stage>/<name>.<ext>.meta.json  = {input_hash, output_hash, inputs, provider_meta, …}
```

- `input_hash = sha256(canonical JSON of inputs)`, where `inputs` includes a stage version string (`keyframes/v1`, …). Bump that string to invalidate a stage after a code change.
- Keyframe key: model (provider, id, params, input_map) · composed prompt · negative prompt · seed · resolution · reference-image sha256.
- Shot key: **keyframe output_hash** · motion prompt · video model · seed · duration · fps · resolution · camera · skip flag.
- Narration key: text · voice id · speed · seed · TTS model. Music key: prompt · seed · cue duration · model.
- Assemble: the mix key holds narration/music output hashes and placement times. The per-aspect normalised-clip key holds the shot output_hash, size, focus and duration. The final key holds the clip hashes, end-card hash, mix hash, subtitle cues and badge.
- A cache hit also requires the file's current sha256 to match `output_hash`, so a file edited by hand gets regenerated.
- Writes are atomic: generate to `.tmp-<pid>-name`, `os.replace`, then write the sidecar.
- Derived text files (`script/*`, `report.json`, `.srt`) are written only when their content changes, so a no-op run touches no files (asserted in the test suite).

## 4. Fallbacks and retries

`common/retry.py` defines `TransientError` (429, 5xx, timeouts, network; retried up to `max_attempts`, default 4, with exponential backoff starting at 2 s, capped at 30 s, ±50 % jitter), `PermanentError` (fail fast) and `ModelUnavailable` (the provider can't do the task).

Shot fallback: `skip_video` → Ken Burns, with no model call logged. Otherwise a `ModelUnavailable` or `PermanentError` → Ken Burns, cached under the same key. Exhausted transient retries → Ken Burns, with the sidecar marked `retry_next_run: true` so the next run tries the model again instead of locking in the fallback.

Ken Burns: the keyframe is upscaled 2× (to avoid zoompan's integer-pixel jitter), then zoompan applies a linear zoom from `zoom_start` to `zoom_end` and a pan direction from `camera`. The result is deterministic.

## 5. Post-production (assemble)

1. **Mix.** Each narration line goes at `shot.start + narration_lead_sec` (`adelay`). Each music cue goes at its span start, with `volume_db` and fade in/out. The music is ducked by `sidechaincompress` keyed on the narration (threshold/ratio/attack/release from `audio.ducking`) and then mixed with the narration.
2. **Loudness.** Two-pass `loudnorm`: pass 1 measures, pass 2 applies `linear=true` with the measured values toward `integrated_lufs` (−14) / `true_peak_db` (−1) / `lra`. The mix is measured again afterwards, and both final MP4s are measured after AAC encoding. Results go to `final/report.json`.
3. **Video per export.** Each shot is normalised (scale-to-cover, crop, using `vertical_focus_x` for 9:16; fps; exact duration). The end card is a Pillow PNG turned into a clip. Everything is joined with `concat`.
4. **Text.** Subtitles split narration into ≤ `max_words_per_cue` chunks, timed proportionally to the *measured* audio duration. They are rendered as PNGs inside the safe area (16:9: above the bottom 8 %, ≤ 78 % width; 9:16: above the bottom 22 % to clear platform UI, ≤ 84 % width) and overlaid with `enable=between(t,…)`. A persistent "AI-generated" badge sits top-right until the end card. A sidecar `heritage.srt` is also written.
5. **Encode.** libx264 CRF `render.video_crf`, yuv420p, AAC 192 k, `+faststart`, bitexact flags, metadata stripped. Intermediates use preset `veryfast` at a lower CRF; the final export uses `medium`.

Text is rendered by Pillow, not ffmpeg `drawtext`/`subtitles`, because many ffmpeg builds lack libfreetype/libass (see FAILURES.md F-001). Font: the first available of Arial/Helvetica/DejaVu, else Pillow's default. Output is identical on a given machine but may differ across machines with different fonts.

## 6. Telemetry (`runs.jsonl`)

One line per model call, including cache hits and failures:

```json
{"timestamp": "...Z", "run_id": "...", "stage": "keyframes", "shot_id": "s03", "provider": "stub",
 "model": "stub/placeholder-image-v1", "parameters": {}, "seed": 1003, "cache_hit": false,
 "latency_sec": 0.12, "gpu_minutes": 0.0, "list_price_equivalent_usd": 0.0,
 "status": "ok|cached|ModelUnavailable|PermanentError|TransientError", "attempts": 1, "input_hash": "..."}
```

Music lines add `cue_id`, and fallback cache hits add `fallback`. `gpu_minutes` and `list_price_equivalent_usd` are `null` whenever the provider or the pricing block doesn't supply them. The file is opened in append mode under `flock`, so concurrent writers are safe.

## 7. Determinism boundaries

The pipeline is deterministic *given its inputs*. Real generative models may not be bit-reproducible even with a fixed seed; the cache is what guarantees that untouched shots stay identical across runs. FFmpeg outputs are reproducible on the same ffmpeg/x264 build and thread count (`-threads 4` fixed).
