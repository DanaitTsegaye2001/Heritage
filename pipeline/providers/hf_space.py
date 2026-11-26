"""Hugging Face Space adapter (gradio_client): free hosted demos, no key required.

Default: black-forest-labs/FLUX.1-schnell, endpoint /infer (Apache-2.0 model).
Verified 2026-11-26: anonymous call, seed respected, 1344x768 WebP in 15.8 s.

The Space returns its own size; the adapter cover-crops and resizes to the
storyboard's keyframe resolution. Anonymous ZeroGPU usage has a GPU-time quota —
quota errors fail fast (PermanentError) instead of burning retries. Set HF_TOKEN in
.env to use your own (larger) quota.

cfg.params: space (str), api_name (str), width/height (request size, multiples of 32),
num_inference_steps (int).
"""
from __future__ import annotations

import os

from PIL import Image, ImageOps

from ..common.retry import PermanentError, TransientError
from .base import Provider, ProviderResult

QUOTA_HINTS = ("quota", "exceeded your gpu", "zerogpu")


class HFSpaceProvider(Provider):
    name = "hf_space"

    def image(self, *, cfg, prompt, negative_prompt, seed, width, height, reference_image, out):
        try:
            from gradio_client import Client
        except ImportError as e:  # pragma: no cover
            raise PermanentError("gradio_client not installed (pip install -r requirements.txt)") from e
        p = cfg.get("params", {})
        space = p.get("space", cfg["model"])
        try:
            client = Client(space, token=os.environ.get("HF_TOKEN") or None, verbose=False)
            # Any extra params (guidance_scale, num_inference_steps, …) pass straight to the Space.
            extra = {k: v for k, v in p.items() if k not in ("space", "api_name", "width", "height")}
            path, used_seed = client.predict(
                prompt=prompt, seed=seed, randomize_seed=False,
                width=p.get("width", 1344), height=p.get("height", 768),
                api_name=p.get("api_name", "/infer"), **extra)
        except (TypeError, AttributeError, ImportError) as e:  # our bug / API change: retrying won't help
            raise PermanentError(f"{type(e).__name__}: {e}") from e
        except Exception as e:  # gradio AppError, httpx/network errors, queue timeouts
            msg = f"{type(e).__name__}: {e}"
            if any(h in msg.lower() for h in QUOTA_HINTS):
                raise PermanentError("HF Space GPU quota exhausted — " + msg[:300]) from e
            raise TransientError(msg[:300]) from e
        img = ImageOps.fit(Image.open(path).convert("RGB"), (width, height), Image.Resampling.LANCZOS)
        img.save(out, format="PNG")
        return ProviderResult(gpu_seconds=None, provider_meta={"space": space, "seed_used": used_seed,
                                                               "requested": [p.get("width", 1344), p.get("height", 768)]})
