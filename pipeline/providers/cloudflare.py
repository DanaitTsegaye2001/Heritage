"""Cloudflare Workers AI adapter (REST, stdlib only).

Endpoint: POST https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{model}
Auth:     CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN from .env

Workers AI offers text-to-image and text-to-speech models but (as of 2026-11-26) no
image-to-video or music models, so `video` and `music` stay ModelUnavailable and the
pipeline uses Ken Burns / another provider for those.

Responses come in two shapes depending on the model: raw bytes (image/jpeg,
audio/mpeg) or JSON {"result": {"image"|"audio": <base64>}}. Both are handled.
Workers AI does not report GPU time, so gpu_seconds is None (logged as null).
"""
from __future__ import annotations

import base64
import io
import json
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

from ..common.env import require_env
from ..common.media import to_wav
from ..common.retry import PermanentError, TransientError
from .base import Provider, ProviderResult

API = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"


def _run(cfg: dict, standard: dict[str, Any]) -> tuple[bytes, str]:
    mapping = cfg.get("input_map", {})
    body: dict[str, Any] = {}
    for key, value in standard.items():
        target = mapping.get(key, key)
        if target is not None and value is not None:
            body[target] = value
    body.update(cfg.get("params", {}))

    url = API.format(account=require_env("CLOUDFLARE_ACCOUNT_ID"), model=cfg["model"])
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {require_env('CLOUDFLARE_API_TOKEN')}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code == 429 and ("daily free allocation" in detail or '"code":4006' in detail.replace(" ", "")):
            raise PermanentError(f"daily free allocation used up (resets 00:00 UTC): {detail}") from e
        if e.code in (408, 429) or e.code >= 500:
            raise TransientError(f"HTTP {e.code}: {detail}") from e
        raise PermanentError(f"HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        raise TransientError(f"network error: {e}") from e


def _payload(raw: bytes, content_type: str, key: str) -> bytes:
    if "application/json" not in content_type:
        return raw
    data = json.loads(raw)
    if not data.get("success", True):
        raise PermanentError(f"Workers AI error: {data.get('errors')}")
    result = data.get("result", data)
    if key not in result:
        raise PermanentError(f"no '{key}' in Workers AI response: {list(result)[:5]}")
    return base64.b64decode(result[key])


class CloudflareProvider(Provider):
    name = "cloudflare"

    def image(self, *, cfg, prompt, negative_prompt, seed, width, height, reference_image, out):
        if reference_image is not None:
            raise PermanentError("cloudflare image adapter does not support reference images yet")
        raw, ctype = _run(cfg, {"prompt": prompt, "negative_prompt": negative_prompt, "seed": seed,
                                "width": width, "height": height})
        img = Image.open(io.BytesIO(_payload(raw, ctype, "image"))).convert("RGB")
        img.save(out, format="PNG")
        return ProviderResult(gpu_seconds=None, provider_meta={"returned_size": list(img.size)})

    def tts(self, *, cfg, text, voice_id, speed, seed, out):
        raw, ctype = _run(cfg, {"text": text, "speaker": voice_id, "speed": speed, "seed": seed})
        audio = _payload(raw, ctype, "audio")
        tmp = out.with_name(out.name + ".download.mp3")
        try:
            tmp.write_bytes(audio)
            to_wav(tmp, out, channels=1)
        finally:
            tmp.unlink(missing_ok=True)
        return ProviderResult(gpu_seconds=None, provider_meta={"bytes": len(audio)})
