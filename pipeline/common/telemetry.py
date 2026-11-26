"""Append-only structured log: one JSON object per line in runs.jsonl."""
from __future__ import annotations

import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=False, ensure_ascii=False, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # safe if stages ever run in parallel
        try:
            f.write(line)
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def log_model_call(ctx: Any, *, stage: str, shot_id: str | None, provider: str, model: str,
                   parameters: dict[str, Any], seed: int | None, cache_hit: bool,
                   latency_sec: float, gpu_minutes: float | None,
                   list_price_equivalent_usd: float | None, status: str = "ok",
                   attempts: int = 0, input_hash: str | None = None,
                   error: str | None = None, extra: dict[str, Any] | None = None) -> None:
    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "run_id": ctx.run_id,
        "stage": stage,
        "shot_id": shot_id,
        "provider": provider,
        "model": model,
        "parameters": parameters,
        "seed": seed,
        "cache_hit": cache_hit,
        "latency_sec": round(latency_sec, 3),
        "gpu_minutes": None if gpu_minutes is None else round(gpu_minutes, 4),
        "list_price_equivalent_usd": None if list_price_equivalent_usd is None else round(list_price_equivalent_usd, 6),
        "status": status,
        "attempts": attempts,
        "input_hash": input_hash,
    }
    if error:
        record["error"] = error[:500]
    if extra:
        record.update(extra)
    append_jsonl(ctx.runs_log, record)


def price_usd(pricing: dict[str, Any] | None, gpu_seconds: float | None) -> float | None:
    """List-price equivalent from the storyboard's pricing block. None if unknown — never guessed."""
    if not pricing:
        return None
    if pricing.get("usd_per_call") is not None:
        return float(pricing["usd_per_call"])
    if pricing.get("usd_per_gpu_second") is not None and gpu_seconds is not None:
        return float(pricing["usd_per_gpu_second"]) * gpu_seconds
    return None
