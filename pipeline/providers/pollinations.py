"""Pollinations image adapter (keyless public endpoint, stdlib only).

Last-resort free image source (FAILURES F-106): rate-limited (503/402 → retried),
returns ~1015×580 JPEG with a small watermark in the bottom-right corner even with
nologo=true. The adapter crops the bottom strip off before cover-resizing, so no
third-party mark ends up in the film.
"""
from __future__ import annotations

import io
import socket
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageOps

from ..common.retry import PermanentError, TransientError
from .base import Provider, ProviderResult

URL = "https://image.pollinations.ai/prompt/{prompt}?{query}"


class PollinationsProvider(Provider):
    name = "pollinations"

    def image(self, *, cfg, prompt, negative_prompt, seed, width, height, reference_image, out):
        p = cfg.get("params", {})
        query = urllib.parse.urlencode({"width": p.get("width", 1344), "height": p.get("height", 768), "seed": seed,
                                        "model": cfg["model"], "nologo": "true", "enhance": "false"})
        url = URL.format(prompt=urllib.parse.quote(prompt[:900]), query=query)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "heritage-short-pipeline"}),
                                        timeout=180) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (402, 429, 503) or e.code >= 500:
                raise TransientError(f"HTTP {e.code} (rate-limited)") from e
            raise PermanentError(f"HTTP {e.code}: {e.read()[:200]!r}") from e
        except (urllib.error.URLError, socket.timeout) as e:
            raise TransientError(f"network error: {e}") from e
        img = Image.open(io.BytesIO(data)).convert("RGB")
        crop = p.get("crop_bottom_frac", 0.08)  # remove watermark strip
        img = img.crop((0, 0, img.width, int(img.height * (1 - crop))))
        ImageOps.fit(img, (width, height), Image.Resampling.LANCZOS).save(out, format="PNG")
        return ProviderResult(gpu_seconds=None, provider_meta={"returned_size": [img.width, img.height]})
