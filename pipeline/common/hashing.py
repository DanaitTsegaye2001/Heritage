"""Deterministic hashing of cache inputs and files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def stable_hash(obj: Any) -> str:
    """SHA-256 of canonical JSON (sorted keys, no whitespace)."""
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
