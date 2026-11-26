"""Generic Replicate adapter (HTTP API, stdlib only).

STATUS: written against Replicate's documented predictions API but NOT yet
exercised against the live service in this repo. Verify with one cheap call
and record the outcome in EXPERIMENTS.md / FAILURES.md before a full run.

Model input names differ per model, so each storyboard model block can set
`input_map` to rename (or null-out) the pipeline's standard inputs, and
`params` for any extra model-specific inputs.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

from ..common.env import require_env
from ..common.media import to_wav
from ..common.retry import PermanentError, TransientError
from .base import Provider, ProviderResult

API = "https://api.replicate.com/v1"
POLL_SEC = 3.0
TIMEOUT_SEC = 900.0
TRANSIENT_HINTS = ("timeout", "timed out", "overloaded", "unavailable", "capacity", "out of memory", "cuda")


def _request(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> Any:
    token = require_env("REPLICATE_API_TOKEN")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code == 429 or e.code >= 500:
            raise TransientError(f"HTTP {e.code}: {detail}") from e
        raise PermanentError(f"HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        raise TransientError(f"network error: {e}") from e


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _first_url(output: Any) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, list) and output:
        return _first_url(output[0])
    if isinstance(output, dict):
        for v in output.values():
            try:
                return _first_url(v)
            except PermanentError:
                continue
    raise PermanentError(f"no file URL in model output: {str(output)[:200]}")


def _download(url: str, dest: Path) -> None:
    try:
        with urllib.request.urlopen(url, timeout=300) as resp, open(dest, "wb") as f:
            f.write(resp.read())
    except (urllib.error.URLError, socket.timeout) as e:
        raise TransientError(f"download failed: {e}") from e


class ReplicateProvider(Provider):
    name = "replicate"

    def _predict(self, cfg: dict, standard: dict[str, Any]) -> tuple[str, ProviderResult]:
        mapping = cfg.get("input_map", {})
        inputs: dict[str, Any] = {}
        for key, value in standard.items():
            target = mapping.get(key, key)
            if target is not None and value is not None:
                inputs[target] = value
        inputs.update(cfg.get("params", {}))

        model = cfg["model"]
        if ":" in model:  # owner/name:version
            pred = _request("POST", f"{API}/predictions", {"version": model.split(":", 1)[1], "input": inputs},
                            headers={"Prefer": "wait=60"})
        else:
            pred = _request("POST", f"{API}/models/{model}/predictions", {"input": inputs},
                            headers={"Prefer": "wait=60"})

        deadline = time.monotonic() + TIMEOUT_SEC
        while pred.get("status") not in ("succeeded", "failed", "canceled"):
            if time.monotonic() > deadline:
                raise TransientError(f"prediction {pred.get('id')} still {pred.get('status')} after {TIMEOUT_SEC:.0f}s")
            time.sleep(POLL_SEC)
            pred = _request("GET", pred["urls"]["get"])

        if pred["status"] != "succeeded":
            err = str(pred.get("error") or pred["status"])
            cls = TransientError if any(h in err.lower() for h in TRANSIENT_HINTS) or pred["status"] == "canceled" else PermanentError
            raise cls(f"prediction {pred.get('id')} {pred['status']}: {err}")

        metrics = pred.get("metrics") or {}
        return _first_url(pred.get("output")), ProviderResult(
            gpu_seconds=metrics.get("predict_time"),
            provider_meta={"prediction_id": pred.get("id"), "metrics": metrics})

    def _save(self, url: str, out: Path, kind: str) -> None:
        raw = out.with_name(out.name + ".download" + (Path(url.split("?")[0]).suffix or ".bin"))
        try:
            _download(url, raw)
            if kind == "image":
                Image.open(raw).convert("RGB").save(out, format="PNG")
            elif kind in ("speech", "music"):
                to_wav(raw, out, channels=1 if kind == "speech" else 2)
            else:
                raw.replace(out)
        finally:
            raw.unlink(missing_ok=True)

    def image(self, *, cfg, prompt, negative_prompt, seed, width, height, reference_image, out):
        url, res = self._predict(cfg, {"prompt": prompt, "negative_prompt": negative_prompt, "seed": seed,
                                       "width": width, "height": height,
                                       "image": _data_uri(reference_image) if reference_image else None})
        self._save(url, out, "image")
        return res

    def video(self, *, cfg, prompt, image, seed, duration_sec, fps, width, height, out):
        url, res = self._predict(cfg, {"prompt": prompt, "image": _data_uri(image), "seed": seed,
                                       "duration": duration_sec, "width": width, "height": height})
        self._save(url, out, "video")
        return res

    def tts(self, *, cfg, text, voice_id, speed, seed, out):
        url, res = self._predict(cfg, {"text": text, "voice": voice_id, "speed": speed, "seed": seed})
        self._save(url, out, "speech")
        return res

    def music(self, *, cfg, prompt, duration_sec, seed, out):
        url, res = self._predict(cfg, {"prompt": prompt, "duration": int(round(duration_sec)) + 1, "seed": seed})
        self._save(url, out, "music")
        return res
