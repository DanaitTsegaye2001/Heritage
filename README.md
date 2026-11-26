# The Heritage Short

A 60–90 second short film generated end to end from one contract file, `storyboard.json`,
by a cached, modular pipeline. It reproduces from a clean clone with **one command**.

```bash
make film
```

→ `outputs/final/heritage_16x9.mp4` and `outputs/final/heritage_9x16.mp4`, plus `heritage.srt` and a
`report.json` holding the **measured** loudness of each export.

`storyboard.json` uses **Cloudflare Workers AI** for keyframes (`@cf/leonardo/lucid-origin`) and
narration (`@cf/deepgram/aura-2-en`). It needs `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` in `.env`.
Video uses the Ken Burns fallback because Workers AI has no video model, and music uses the placeholder
until Lyria billing or a licensed track is set up (FAILURES.md F-100).

**No keys?** Run `make film-offline`. Every model swaps to the free, deterministic **stub** provider
(placeholder images, a tone for the voice, a chord pad). Everything else still runs for real: caching,
telemetry, ducking, loudness, subtitles, AI labelling, both exports. Offline and real artifacts have
different cache keys, so they never mix.

---

## Requirements

| Tool | Version | Notes |
|---|---|---|
| Python | ≥ 3.10 | `make` creates `.venv` and installs `requirements.txt` (jsonschema, Pillow) |
| FFmpeg + ffprobe | ≥ 6 with `libx264` | needs the `zoompan`, `sidechaincompress` and `loudnorm` filters. **Not** needed: `drawtext`/`libass` (text is rendered with Pillow) |
| make | any | |

macOS: `brew install ffmpeg python`. Debian/Ubuntu: `apt install ffmpeg python3-venv`.

## Setup

```bash
git clone <repo> && cd <repo>
cp .env.example .env        # only needed for paid providers; .env is git-ignored
make film                   # creates .venv on first run
```

## Commands

| Command | What it does |
|---|---|
| `make film` | validate → script → keyframes → shots → narration → music → assemble |
| `make film-offline` | same, with stub providers only (no keys, no network, $0) |
| `make validate` | schema + semantic checks only (also writes `outputs/script/script.md`) |
| `make keyframes SHOTS=s03` | run one stage, optionally only for some shots (`script`, `keyframes`, `shots`, `narration`, `music`, `assemble`) |
| `make reroll SHOTS=s03` | ignore the cache for one shot's artifacts, then reassemble |
| `make costs` | summarise `runs.jsonl`: calls, cache hits, latency, GPU minutes, list-price USD |
| `make test` | validation tests + end-to-end selective-regeneration test (always offline/stub, low-res, ~1–2 min) |
| `make clean-outputs` | delete generated media (keeps `runs.jsonl`) |

Underlying CLI: `.venv/bin/python -m pipeline.run [STAGE ...] [--shots s01,s02] [--force] [--storyboard path]`.
Each stage also runs standalone: `python -m pipeline.keyframes --shots s03`.

## Editing the film and verifying single-shot regeneration

1. Edit one shot's `narration` (or its `image_prompt`, `seed`, `camera`, …) in `storyboard.json`.
2. Run `make film`. The console marks each artifact `=` (cached), `+` (generated) or `~` (fallback).
3. Check the log: only the shots you edited show `cache_hit: false` for this run:

```bash
tail -n 40 runs.jsonl | python3 -c 'import sys,json; [print(r["stage"], r["shot_id"] or r.get("cue_id"), "HIT" if r["cache_hit"] else "MISS") for r in map(json.loads, sys.stdin)]'
```

What regenerates for each kind of edit:

| You change… | Regenerates |
|---|---|
| `shots[i].image_prompt` / `seed` / `style.*` / reference image | keyframe *i* → shot clip *i* → its normalised clips → final mux |
| `shots[i].motion_prompt` / `camera` / `skip_video` | shot clip *i* → its normalised clips → final mux |
| `shots[i].narration` | narration *i* → mix → subtitles → final mux |
| `shots[i].duration_sec` | shot *i*, music cue(s) spanning it, mix, final mux |
| `music_cues[j]` | cue *j* → mix → final mux |
| `notes`, `pricing` | nothing (excluded from hashes) |

`make test` checks this automatically (`tests/test_pipeline.py::SelectiveRegenerationTest`).

## Architecture (summary)

```
storyboard.json ──validate──► script ─► keyframes ─► shots ─┐
   (schema/…json)                         │                 ├─► assemble ─► final/*.mp4
                                          narration ────────┤      (mix, duck, loudnorm,
                                          music ────────────┘       subtitles, end card)
             every model call ─► runs.jsonl        every artifact ─► .meta.json (input/output hash)
```

- **One contract.** Every stage reads only `storyboard.json` plus upstream artifacts in `outputs/`.
- **Input-hash cache.** Each artifact's key is a hash of exactly the inputs that affect it. Downstream
  keys include the upstream *output* hash, so an edit invalidates its dependents and nothing else.
- **Resilience.** Transient errors (HTTP 429/5xx, timeouts) are retried with bounded exponential backoff.
  If the video model is unavailable or fails, the shot falls back to a deterministic Ken Burns move.
- **Telemetry.** One JSON line per model call (cache hits included) in `runs.jsonl`.

Details: [ARCHITECTURE.md](ARCHITECTURE.md).

## Providers

Set per model in `storyboard.json → models.{image,video,tts,music}`:

| provider | image | video | tts | music | cost | status |
|---|---|---|---|---|---|---|
| `cloudflare` | ✓ (`lucid-origin`, up to 2500 px, seeded) | — | ✓ (`aura-2-en`, 40 speakers) | — | Workers AI pricing; GPU time not reported | **verified live** |
| `stub` | placeholder | — (forces Ken Burns) | tone | chord pad | $0 | tested |
| `macos_say` | — | — | real speech | — | $0 | tested on macOS |
| `replicate` | ✓ | ✓ | ✓ | ✓ | per model | **written against the documented API, not yet run live in this repo** |

Replicate example (look up the model ID and its input names on its model page first):

```json
"image": {
  "provider": "replicate",
  "model": "<owner>/<model-name>",
  "params": { "aspect_ratio": "16:9" },
  "input_map": { "width": null, "height": null, "negative_prompt": null },
  "pricing": { "usd_per_call": null, "usd_per_gpu_second": null, "source": "<pricing URL>", "checked_on": "YYYY-MM-DD" }
}
```

Gemini API (`GEMINI_API_KEY`) has Lyria music models, but this project's free tier allows 0 requests,
and its key has no access to Veo video models (FAILURES.md F-100). There's no adapter yet; once billing is on,
adding one is the next step for music.

Put `REPLICATE_API_TOKEN` in `.env`. Make one cheap call first (`make keyframes SHOTS=s01`) and record
the result in EXPERIMENTS.md / FAILURES.md before a full run.

## Cost and quota notes

- The stub run costs $0 and uses no GPU. With real providers, `runs.jsonl` records `gpu_minutes` as the
  provider reports it (Replicate `metrics.predict_time`) and `list_price_equivalent_usd` from the
  `pricing` block you fill in. If either is unknown it is logged as `null`, **never estimated**.
- Cache hits are logged with `cost 0` so you can see how much a re-run saved.
- Video generation is typically the dominant cost. Develop with `skip_video: true`, or with `stub` video,
  and switch shots to real video one at a time.
- Rate limits: retries back off up to 30 s, 4 attempts by default (`max_attempts` per model).
- Write up your real numbers in [COSTS.md](COSTS.md) (`make costs` / `python -m pipeline.costs --markdown`).

## Secrets

`.env` is git-ignored, and keys are read only from the environment, never from `storyboard.json`.
Telemetry logs model parameters but never headers or tokens. Before every push, run
`git diff --cached | grep -iE 'token|api_key|secret'`.

## Repository map

```
storyboard.json            the contract (starter content; rewrite it)
schema/                    strict JSON Schema for the contract
pipeline/                  stages + common/ (validation, hashing, cache, retry, telemetry, media) + providers/
tests/                     unittest suite
outputs/                   generated (git-ignored except README/.gitkeep)
runs.jsonl                 append-only telemetry
DESIGN.md ARCHITECTURE.md EXPERIMENTS.md FAILURES.md COSTS.md ETHICS.md
```
