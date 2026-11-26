"""Provider interface. Each method writes its artifact to `out` and returns a ProviderResult."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..common.retry import ModelUnavailable


@dataclass
class ProviderResult:
    gpu_seconds: float | None = None  # None = provider did not report it
    provider_meta: dict[str, Any] = field(default_factory=dict)


class Provider:
    name = "base"

    def image(self, *, cfg: dict, prompt: str, negative_prompt: str, seed: int, width: int,
              height: int, reference_image: Path | None, out: Path) -> ProviderResult:
        raise ModelUnavailable(f"{self.name} provider has no image model")

    def video(self, *, cfg: dict, prompt: str, image: Path, seed: int, duration_sec: float,
              fps: int, width: int, height: int, out: Path) -> ProviderResult:
        raise ModelUnavailable(f"{self.name} provider has no video model")

    def tts(self, *, cfg: dict, text: str, voice_id: str, speed: float, seed: int | None,
            out: Path) -> ProviderResult:
        raise ModelUnavailable(f"{self.name} provider has no TTS model")

    def music(self, *, cfg: dict, prompt: str, duration_sec: float, seed: int, out: Path) -> ProviderResult:
        raise ModelUnavailable(f"{self.name} provider has no music model")
