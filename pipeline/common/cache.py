"""Input-hash cache.

Every artifact `outputs/<stage>/<name>.<ext>` has a sidecar
`<name>.<ext>.meta.json` recording the hash of the inputs that produced it and
the hash of the bytes produced. A stage regenerates an artifact only when the
input hash changes (or --force). Downstream stages put the *upstream
output_hash* into their own input hash, so invalidation propagates exactly
along the dependency graph and nowhere else.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from .hashing import file_hash, stable_hash
from .retry import PermanentError, TransientError, with_retries
from .telemetry import log_model_call, price_usd


def meta_path(out: Path) -> Path:
    return out.with_name(out.name + ".meta.json")


def tmp_path(out: Path) -> Path:
    return out.with_name(f".tmp-{os.getpid()}-{out.name}")


def read_meta(out: Path) -> dict[str, Any] | None:
    mp = meta_path(out)
    if not (mp.is_file() and out.is_file()):
        return None
    try:
        return json.loads(mp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def lookup(out: Path, input_hash: str) -> dict[str, Any] | None:
    meta = read_meta(out)
    if not meta or meta.get("input_hash") != input_hash or meta.get("retry_next_run"):
        return None
    if meta.get("output_hash") != file_hash(out):  # file edited/corrupted by hand
        return None
    return meta


def store(out: Path, tmp: Path, input_hash: str, inputs: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """Atomically move tmp -> out and write the sidecar."""
    os.replace(tmp, out)
    meta = {"input_hash": input_hash, "output_hash": file_hash(out), "inputs": inputs, **extra}
    mp = meta_path(out)
    mp_tmp = tmp_path(mp)
    mp_tmp.write_text(json.dumps(meta, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(mp_tmp, mp)
    return meta


def require_meta(out: Path, hint: str) -> dict[str, Any]:
    meta = read_meta(out)
    if meta is None:
        raise SystemExit(f"Missing upstream artifact {out}. Run `{hint}` first.")
    return meta


def cached_local(out: Path, inputs: dict[str, Any], build: Callable[[Path], dict[str, Any] | None],
                 force: bool = False) -> tuple[dict[str, Any], bool]:
    """Cache wrapper for deterministic local work (ffmpeg, Pillow). Returns (meta, was_cached)."""
    h = stable_hash(inputs)
    if not force and (meta := lookup(out, h)):
        return meta, True
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_path(out)
    try:
        extra = build(tmp) or {}
        return store(out, tmp, h, inputs, **extra), False
    finally:
        tmp.unlink(missing_ok=True)


def run_model_cached(ctx: Any, *, stage: str, shot_id: str | None, cfg: dict[str, Any],
                     inputs: dict[str, Any], out: Path, seed: int | None,
                     call: Callable[[Path], Any],
                     postprocess: Callable[[Path], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Cache lookup -> (retrying) model call -> store -> one runs.jsonl line.

    `call(tmp)` must write the artifact to `tmp` and return a ProviderResult.
    Raises PermanentError/TransientError after logging the failure.
    """
    h = stable_hash(inputs)
    params = cfg.get("params", {})
    label = f"{stage}:{shot_id or '-'}"
    common = dict(stage=stage, shot_id=shot_id, provider=cfg["provider"], model=cfg["model"],
                  parameters=params, seed=seed, input_hash=h)

    if not ctx.force and (meta := lookup(out, h)):
        log_model_call(ctx, **common, cache_hit=True, latency_sec=0.0, gpu_minutes=0.0,
                       list_price_equivalent_usd=0.0, status="cached", attempts=0,
                       extra={"fallback": meta["fallback"]} if meta.get("fallback") else None)
        print(f"  = {label} cached")
        return meta

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_path(out)
    t0 = time.monotonic()
    attempts = 0
    try:
        def attempt():
            nonlocal attempts
            attempts += 1
            return call(tmp)
        result, _ = with_retries(attempt, max_attempts=cfg.get("max_attempts", 4), label=label)
        extra = postprocess(tmp) if postprocess else {}
        latency = time.monotonic() - t0
        gpu_s = result.gpu_seconds
        meta = store(out, tmp, h, inputs, provider_meta=result.provider_meta, **extra)
        log_model_call(ctx, **common, cache_hit=False, latency_sec=latency,
                       gpu_minutes=None if gpu_s is None else gpu_s / 60,
                       list_price_equivalent_usd=price_usd(cfg.get("pricing"), gpu_s),
                       status="ok", attempts=attempts)
        print(f"  + {label} generated in {latency:.1f}s")
        return meta
    except (PermanentError, TransientError) as e:
        log_model_call(ctx, **common, cache_hit=False, latency_sec=time.monotonic() - t0,
                       gpu_minutes=None, list_price_equivalent_usd=None,
                       status=type(e).__name__, attempts=attempts, error=str(e))
        raise
    finally:
        tmp.unlink(missing_ok=True)
