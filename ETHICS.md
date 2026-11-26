# Ethics: consent, licences, AI labelling

> Status: **TEMPLATE.** Consent records must be real and stored privately. This file holds
> only participant codes and a pointer to where the signed forms live. Never commit personal data.

## 1. Informed consent

Who needs consent: user-test participants (DESIGN.md §4), anyone whose story, likeness, voice, craft or
family history inspires the film, and anyone who supplies reference images.

Consent covers: the purpose of the film; that it is AI-generated; where it will be shown; whether their
words may be quoted (verbatim or paraphrased); their right to withdraw and how; retention period.

| Code | Role | Consent type (written/recorded) | Date | Scope (quote? likeness? story?) | Withdrawal contact given | Form stored at (private) |
|---|---|---|---|---|---|---|
| P1 | user test round 1 | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| P2 | user test round 1 | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| P3 | user test round 1 | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| P4 | user test round 2 | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| P5 | user test round 2 | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| P6 | user test round 2 | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| C1 | story / cultural source | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |

## 2. Cultural representation

- Whose heritage is depicted, and who reviewed it: [TODO]
- Motifs and meanings checked with someone who holds that knowledge (consent above): [TODO]
- Things deliberately *not* generated (sacred patterns, real people's faces, …): [TODO]

## 3. Licences and terms

| Asset / model | Used for | Licence or terms of service | Commercial use allowed? | Attribution required | Link | Checked on |
|---|---|---|---|---|---|---|
| image model [TODO] | keyframes | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| video model [TODO] | shots | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| TTS model / voice [TODO] | narration | [TODO — voice cloning? whose voice, with consent?] | [TODO] | [TODO] | [TODO] | [TODO] |
| music model [TODO] | score | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] |
| reference images | conditioning | record per shot in `storyboard.json → shots[].reference.licence` | | | | |
| fonts | subtitles / end card | system font on the render machine (see ARCHITECTURE §5) | [TODO] | | | |

The validator warns when a shot has a reference image but no `licence`.

## 4. AI labelling (implemented)

- **End card.** `end_card.ai_statement` is shown full-screen for `end_card.duration_sec` in both exports. The schema requires it (≥ 20 characters).
- **Persistent badge.** `ai_disclosure.persistent_badge` puts an "AI-generated" label top-right in the safe area for the whole film, before the end card.
- **Platform labels.** When uploading, also set the platform's AI-content disclosure flag: [TODO — which platforms, done Y/N].
- **Metadata.** Encoder metadata is stripped for determinism. The disclosure therefore lives in the picture, not in metadata.

## 5. Data and secrets

- API keys stay only in `.env` (git-ignored). `runs.jsonl` holds no tokens or personal data.
- User-test notes in DESIGN.md use participant codes only.
