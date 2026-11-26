"""Bounded retries with exponential backoff and jitter."""
from __future__ import annotations

import random
import sys
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class TransientError(RuntimeError):
    """Worth retrying: rate limits, 5xx, timeouts, queue hiccups."""


class PermanentError(RuntimeError):
    """Retrying will not help: bad input, auth failure, content refusal."""


class ModelUnavailable(PermanentError):
    """The configured provider cannot do this task (e.g. stub has no video model)."""


def with_retries(fn: Callable[[], T], *, max_attempts: int = 4, base_delay: float = 2.0,
                 max_delay: float = 30.0, label: str = "") -> tuple[T, int]:
    """Run fn, retrying TransientError up to max_attempts total. Returns (result, attempts)."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(), attempt
        except TransientError as e:
            if attempt == max_attempts:
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1)) * (0.5 + random.random() / 2)
            print(f"    ! {label} transient failure (attempt {attempt}/{max_attempts}): {e}; "
                  f"retrying in {delay:.1f}s", file=sys.stderr)
            time.sleep(delay)
    raise AssertionError("unreachable")
