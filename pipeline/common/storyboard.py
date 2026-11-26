"""Load storyboard.json, validate it against the JSON Schema, then apply the
cross-field rules a schema cannot express."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_REL = Path("schema/storyboard.schema.json")
MIN_TOTAL_SEC, MAX_TOTAL_SEC = 60.0, 90.0
MIN_WORDS, MAX_WORDS = 130, 220
# Conservative narration pace used only for pre-flight fit warnings; real
# durations are measured from the generated audio in the narration stage.
WORDS_PER_SEC = 2.6


class StoryboardError(ValueError):
    pass


def word_count(text: str) -> int:
    return len(re.findall(r"[\w'’-]+", text))


def load_storyboard(path: Path, repo_root: Path) -> tuple[dict[str, Any], list[str]]:
    """Return (storyboard, warnings). Raises StoryboardError on any violation."""
    try:
        sb = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise StoryboardError(f"Storyboard not found: {path}") from e
    except json.JSONDecodeError as e:
        raise StoryboardError(f"{path}: invalid JSON at line {e.lineno}: {e.msg}") from e

    schema = json.loads((repo_root / SCHEMA_REL).read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(sb), key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"  - {'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in errors[:25]]
        raise StoryboardError("Storyboard failed schema validation:\n" + "\n".join(lines))

    return sb, semantic_checks(sb, repo_root)


def semantic_checks(sb: dict[str, Any], repo_root: Path) -> list[str]:
    errors: list[str] = []
    warnings: list[str] = []
    shots = sb["shots"]

    ids = [s["id"] for s in shots]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"duplicate shot ids: {dupes}")

    total = total_duration(sb)
    if not (MIN_TOTAL_SEC <= total <= MAX_TOTAL_SEC):
        errors.append(f"total runtime {total:.1f}s (shots + end card) must be {MIN_TOTAL_SEC:.0f}–{MAX_TOTAL_SEC:.0f}s")

    words = sum(word_count(s["narration"]) for s in shots)
    if not (MIN_WORDS <= words <= MAX_WORDS):
        errors.append(f"narration has {words} words; must be {MIN_WORDS}–{MAX_WORDS}")

    cue_ids = [c["id"] for c in sb["music_cues"]]
    if len(set(cue_ids)) != len(cue_ids):
        errors.append("duplicate music cue ids")
    used: list[str] = []
    for s in shots:
        cue = s["music_cue"]
        if cue is not None and cue not in cue_ids:
            errors.append(f"{s['id']}: music_cue '{cue}' is not defined in music_cues")
        if cue is not None and (not used or used[-1] != cue):
            if cue in used:
                errors.append(f"music cue '{cue}' must cover contiguous shots (reappears at {s['id']})")
            used.append(cue)
    for c in cue_ids:
        if c not in used:
            warnings.append(f"music cue '{c}' is defined but not used by any shot")

    char_ids = {c["id"] for c in sb.get("characters", [])}
    for s in shots:
        for c in s.get("characters", []):
            if c not in char_ids:
                errors.append(f"{s['id']}: character '{c}' is not defined in characters")

    lead = sb["audio"]["narration_lead_sec"]
    for s in shots:
        ref = s["reference"].get("image")
        if ref and not (repo_root / ref).is_file():
            errors.append(f"{s['id']}: reference image not found: {ref}")
        if ref and not s["reference"].get("licence"):
            warnings.append(f"{s['id']}: reference image has no licence recorded (see ETHICS.md)")
        est = word_count(s["narration"]) / WORDS_PER_SEC
        if est > s["duration_sec"] - lead:
            warnings.append(f"{s['id']}: ~{est:.1f}s of narration may not fit a {s['duration_sec']}s shot")

    if errors:
        raise StoryboardError("Storyboard failed semantic checks:\n" + "\n".join(f"  - {e}" for e in errors))
    return warnings


def total_duration(sb: dict[str, Any]) -> float:
    return sum(s["duration_sec"] for s in sb["shots"]) + sb["end_card"]["duration_sec"]


def timeline(sb: dict[str, Any]) -> list[dict[str, Any]]:
    """Shot start/end times on the final timeline (end card excluded)."""
    t, out = 0.0, []
    for s in sb["shots"]:
        out.append({"shot_id": s["id"], "start": round(t, 3), "end": round(t + s["duration_sec"], 3),
                    "duration": s["duration_sec"], "music_cue": s["music_cue"],
                    "words": word_count(s["narration"])})
        t += s["duration_sec"]
    return out


def cue_spans(sb: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """(start, end) per music cue. The cue playing on the last shot also covers the end card."""
    spans: dict[str, list[float]] = {}
    tl = timeline(sb)
    for row in tl:
        if row["music_cue"]:
            span = spans.setdefault(row["music_cue"], [row["start"], row["end"]])
            span[1] = row["end"]
    last = tl[-1]["music_cue"]
    if last:
        spans[last][1] = round(spans[last][1] + sb["end_card"]["duration_sec"], 3)
    return {k: (v[0], v[1]) for k, v in spans.items()}


def strip_notes(obj: Any) -> Any:
    """Remove human-only fields so they never affect cache keys."""
    if isinstance(obj, dict):
        return {k: strip_notes(v) for k, v in obj.items() if k not in ("notes", "pricing", "$schema")}
    if isinstance(obj, list):
        return [strip_notes(v) for v in obj]
    return obj


def model_key(cfg: dict[str, Any]) -> dict[str, Any]:
    """The parts of a model block that can change the output (pricing, notes, retries excluded)."""
    return {"provider": cfg["provider"], "model": cfg["model"],
            "params": cfg.get("params", {}), "input_map": cfg.get("input_map", {})}
