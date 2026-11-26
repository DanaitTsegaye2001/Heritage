# Costs, latency and GPU time

> Status: **TEMPLATE for real runs.** Numbers here must come from `runs.jsonl`. Do not estimate.
> `null`/"unknown" in the log means the provider didn't report it, or `pricing` wasn't filled in.

## How to produce these tables

```bash
make costs                                  # all runs, console table
.venv/bin/python -m pipeline.costs --last --markdown   # latest run as a Markdown table to paste below
```

Fill `models.<kind>.pricing` in `storyboard.json` from the provider's pricing page, and record `source` + `checked_on`. List prices change; the log keeps whatever was configured at the time of each call.

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
