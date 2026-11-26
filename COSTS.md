# Costs, latency and GPU time

> Status: **TEMPLATE for real runs.** Numbers here must come from `runs.jsonl`. Do not estimate.
> `null`/"unknown" in the log means the provider didn't report it, or `pricing` wasn't filled in.

## How to produce these tables

```bash
make costs                                  # all runs, console table
.venv/bin/python -m pipeline.costs --last --markdown   # latest run as a Markdown table to paste below
```

Fill `models.<kind>.pricing` in `storyboard.json` from the provider's pricing page, and record `source` + `checked_on`. List prices change; the log keeps whatever was configured at the time of each call.

## Free-tier limits actually found (2026-11-26)

| Service / model | Limit hit | Evidence |
|---|---|---|
| Cloudflare Workers AI (`lucid-origin` 1920×1080, `aura-2-en`) | 10,000 neurons/day, used up after 2 images + 2 short TTS clips | FAILURES F-101 |
| Gemini `gemini-3.8-flash-tts` | 10 requests/day/model | FAILURES F-103 |
| Gemini `gemini-3.8-flash-lite-tts` | separate 10/day quota (works) | FAILURES F-103 |
| Gemini image (`gemini-2.5-flash-image`) | 0 (billing needed) | FAILURES F-102 |
| Gemini Lyria (`lyria-3-clip-preview`) | 0 (billing needed) | FAILURES F-100 |

Measured latencies (single calls, from `runs.jsonl` / direct probes): lucid-origin 1920×1080 image 10.1–11.9 s; aura-2-en 4.3–4.4 s; gemini-3.8-flash-tts 5.0–7.2 s per line; flash-lite-tts 5.1 s.

## Pricing configured

| Kind | Provider / model | usd_per_call | usd_per_gpu_second | Source | Checked on |
|---|---|---|---|---|---|
| image | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| video | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| tts | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| music | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |

## Run log

| Date | run_id | Commit | What changed | Calls (miss / hit) | Latency s | GPU min | List USD | Notes |
|---|---|---|---|---|---|---|---|---|
| [TODO] | [TODO] | [TODO] | first full real-model run | [TODO] | [TODO] | [TODO] | [TODO] | |
| [TODO] | [TODO] | [TODO] | single-shot edit (cache check) | [TODO] | [TODO] | [TODO] | [TODO] | expect 1–3 misses |

## Per-stage breakdown (latest real run)

<!-- paste output of: python -m pipeline.costs --last --markdown -->
[TODO]

## Cache savings

Total list-price cost of all misses vs what a cold re-run would have cost: [TODO — from runs.jsonl]

## Reference: stub-provider baseline (not a real cost)

Measured on the development machine (macOS, Apple Silicon, ffmpeg 9.1) on 2026-11-26. This was a cold run of the starter storyboard with all-stub providers at x264 preset `medium` everywhere, before the F-002 speed-up: **308.6 s wall time, $0, 0 GPU minutes** (local FFmpeg/Pillow only). Use it only as a sanity check for local post-production time.
