"""Local open-weights image generation with 🤗 diffusers (no network after download, no quota).

Default: stabilityai/sd-turbo (1–4 steps, fp16) on Apple Silicon (MPS) or CUDA, else CPU.
Optional dependency: pip install -r requirements-local.txt

Generates at the model's native size (params.width/height, default 768×432 for 16:9,
multiples of 8) and cover-resizes to the storyboard keyframe resolution.
Licence note: SD-Turbo is under the Stability AI Non-Commercial Research Community
licence — fine for this non-commercial short, recorded in ETHICS.md.
"""
from __future__ import annotations

import functools

from PIL import Image, ImageOps

from ..common.retry import PermanentError
from .base import Provider, ProviderResult


@functools.cache
def _pipeline(model: str):
    try:
        import torch
        from diffusers import AutoPipelineForText2Image
    except ImportError as e:
        raise PermanentError("diffusers/torch not installed: pip install -r requirements-local.txt") from e
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device != "cpu" else torch.float32
    pipe = AutoPipelineForText2Image.from_pretrained(model, torch_dtype=dtype,
                                                     variant="fp16" if dtype == torch.float16 else None)
    pipe = pipe.to(device)
    pipe.set_progress_bar_config(disable=True)
    return pipe, device


class LocalDiffusersProvider(Provider):
    name = "local_diffusers"

    def image(self, *, cfg, prompt, negative_prompt, seed, width, height, reference_image, out):
        import torch
        p = cfg.get("params", {})
        pipe, device = _pipeline(cfg["model"])
        gen = torch.Generator("cpu").manual_seed(seed)  # CPU generator: reproducible across devices
        img = pipe(prompt=prompt[:350], num_inference_steps=p.get("num_inference_steps", 4),
                   guidance_scale=p.get("guidance_scale", 0.0), width=p.get("width", 768),
                   height=p.get("height", 432), generator=gen).images[0]
        ImageOps.fit(img.convert("RGB"), (width, height), Image.Resampling.LANCZOS).save(out, format="PNG")
        return ProviderResult(gpu_seconds=None, provider_meta={"device": device})
