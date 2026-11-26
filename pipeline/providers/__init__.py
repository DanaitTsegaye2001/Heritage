from __future__ import annotations

from .base import Provider, ProviderResult
from .cloudflare import CloudflareProvider
from .gemini import GeminiProvider
from .hf_space import HFSpaceProvider
from .macos_say import MacOSSayProvider
from .replicate import ReplicateProvider
from .stub import StubProvider

_REGISTRY: dict[str, type[Provider]] = {
    "stub": StubProvider,
    "replicate": ReplicateProvider,
    "macos_say": MacOSSayProvider,
    "cloudflare": CloudflareProvider,
    "gemini": GeminiProvider,
    "hf_space": HFSpaceProvider,
}


def get_provider(name: str) -> Provider:
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise SystemExit(f"Unknown provider '{name}'. Known: {', '.join(_REGISTRY)}") from None


__all__ = ["Provider", "ProviderResult", "get_provider"]
