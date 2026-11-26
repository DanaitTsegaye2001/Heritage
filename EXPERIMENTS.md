# Experiments

> Status: **TEMPLATE.** The hypotheses below are suggested starting points. Every **Result** must come from a real run, and must cite the `run_id`(s) from `runs.jsonl` and the commit. Leave `[PENDING]` until then.

How to run a controlled change: edit **one** field in `storyboard.json`, run `make film`, then compare the before/after outputs and `runs.jsonl` lines (`python -m pipeline.costs --last`). The cache means only the changed artifacts are regenerated, so each experiment costs only its delta.

Entry format:

```
### E-NN — short title
- Date / commit / run_id(s):
- Hypothesis:
- Change (exact field + old → new):
- Measure (what you'll look at, how judged):
- Result:            (observed, with numbers from report.json / runs.jsonl)
- Decision:          keep / revert / follow-up E-NN
```

---

### E-01 — Global style suffix vs per-shot style
- Date / commit / run_id(s): [PENDING]
- Hypothesis: one shared `style.image_prompt_suffix` keeps the 10 keyframes visually consistent.
- Change: [PENDING]
- Measure: side-by-side contact sheet of `outputs/keyframes/*.png`; rate consistency 1–5.
- Result: [PENDING]
- Decision: [PENDING]

### E-02 — Seed sensitivity
- Hypothesis: changing only `seed` on one shot changes composition but keeps the subject.
- Change: s03 seed 1003 → [PENDING]
- Measure: before/after keyframe; check that only `keyframes:s03` and `shots:s03` missed the cache.
- Result: [PENDING] · Decision: [PENDING]

### E-03 — Real video vs Ken Burns per shot
- Hypothesis: generated motion helps the people shots (s02, s07, s08) but not the object shots (s06).
- Change: `skip_video` toggled on [PENDING]
- Measure: viewer preference (user test) and GPU minutes per shot (`runs.jsonl`).
- Result: [PENDING] · Decision: [PENDING]

### E-04 — Ducking threshold / ratio
- Hypothesis: threshold 0.02 / ratio 8 keeps narration intelligible without audible pumping.
- Change: `audio.ducking` [PENDING]
- Measure: listening test on headphones and phone speaker; `report.json` LRA.
- Result: [PENDING] · Decision: [PENDING]

### E-05 — Loudness target compliance after AAC
- Hypothesis: the two-pass loudnorm result stays within ±1 LU of −14 and ≤ −1 dBTP after AAC encoding.
- Change: none (measurement), then `true_peak_db` −1 → −1.5 if it overshoots.
- Measure: `outputs/final/report.json` measured_lufs / measured_true_peak_db.
- Result: [PENDING] · Decision: [PENDING]

### E-06 — Narration pace vs Gemini TTS style instruction ✅ measured
- Date / commit / run_id(s): 2026-11-26, after commit 9061a45 (direct provider calls, same text, voice Kore).
- Hypothesis: the style instruction "warmly and unhurried" fits the tone without hurting timing.
- Change: style instruction varied on s01's 13-word line.
- Measure: audio duration → words/second; overflow against the 6.6 s available in s01.
- Result:

  | Model | Style instruction | Duration | Pace |
  |---|---|---|---|
  | gemini-3.8-flash-tts | "Read warmly and unhurried, like a grandchild remembering" | 11.91 s | 1.09 w/s |
  | gemini-3.8-flash-tts | "Read warmly at a natural conversational pace" | 9.52 s | 1.37 w/s |
  | gemini-3.8-flash-tts | *(none)* | 5.78 s | 2.25 w/s |
  | gemini-3.8-flash-lite-tts | *(none)* | 6.43 s | 2.02 w/s |

  With the "unhurried" style, all 10 shots overflowed (9.7–13.2 s of audio against 6.6–8.1 s slots, 1.13–1.66 w/s). At that pace 158 words need ~117 s, which can't fit a 90 s film.
- Decision: drop the pacing words from the style. Pacing words change speed far more than tone. Keep lines at ≤ 2 w/s × (shot − 0.4 s), or lengthen shots. Follow-up: listen for whether "warmly" alone keeps the tone (pending, TTS quota F-103).

### E-07 — Subtitle chunk size
- Hypothesis: `max_words_per_cue` 5 reads better on 9:16 than 7.
- Change: [PENDING]
- Measure: tester comments; cue count in `heritage.srt`.
- Result: [PENDING] · Decision: [PENDING]

### E-08 — 9:16 crop focus
- Hypothesis: tuning `vertical_focus_x` on s02, s04 and s07 keeps faces/hands in frame.
- Change: [PENDING]
- Measure: frame grabs from `heritage_9x16.mp4` at each shot's midpoint.
- Result: [PENDING] · Decision: [PENDING]

### E-09 — Reference image conditioning
- Hypothesis: a licensed reference image for the loom improves cultural/object accuracy.
- Change: `shots[0].reference.image` + `licence` [PENDING]
- Measure: accuracy check by someone with lived knowledge (consent in ETHICS.md).
- Result: [PENDING] · Decision: [PENDING]

### E-10 — Silence at the turn (s05–s06)
- Hypothesis: dropping music to `cue_silence` at −10 dB makes the loss land harder.
- Change: [PENDING]
- Measure: user-test Q2 ("which moment stuck").
- Result: [PENDING] · Decision: [PENDING]
