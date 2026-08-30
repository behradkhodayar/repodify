"""Helpers for live, human-readable pipeline stage details."""

from __future__ import annotations

import time
from collections.abc import Callable

_UNITS = ("B", "KB", "MB", "GB", "TB")


def join_detail(*parts: object | None) -> str:
    """Join non-empty fragments with a middle dot."""
    bits = [str(p).strip() for p in parts if p is not None and str(p).strip()]
    return " · ".join(bits)


def format_bytes(n: int) -> str:
    """Compact byte count, e.g. ``512 B``, ``830.0 KB``, ``12.4 MB``."""
    size = float(n)
    unit = _UNITS[0]
    for unit in _UNITS:
        if size < 1024 or unit == _UNITS[-1]:
            break
        size /= 1024
    if unit == "B":
        return f"{int(size)} B"
    return f"{size:.1f} {unit}"


def format_percent(done: int, total: int) -> str | None:
    """Whole-number percent, or None when `total` is not positive."""
    if total <= 0:
        return None
    return f"{min(100, round(100 * done / total))}%"


def model_id(obj: object) -> str | None:
    """Public `model_id` on a backend, if it is a non-empty string."""
    value = getattr(obj, "model_id", None)
    if isinstance(value, str) and value.strip():
        return value
    return None


class DetailThrottler:
    """Rate-limit live detail writes; always emit the first call and `flush`."""

    def __init__(
        self,
        emit: Callable[[str], None],
        *,
        min_interval_s: float = 0.4,
        min_pct_delta: float = 2.0,
    ) -> None:
        self._emit = emit
        self._min_interval_s = min_interval_s
        self._min_pct_delta = min_pct_delta
        self._last_t: float | None = None
        self._last_pct: float | None = None

    def update(self, detail: str, pct: float | None = None) -> None:
        now = time.monotonic()
        first = self._last_t is None
        interval_ok = (
            self._last_t is not None and (now - self._last_t) >= self._min_interval_s
        )
        pct_ok = (
            pct is not None
            and self._last_pct is not None
            and abs(pct - self._last_pct) >= self._min_pct_delta
        )
        if first or interval_ok or pct_ok:
            self._flush(detail, now, pct)

    def flush(self, detail: str) -> None:
        self._flush(detail, time.monotonic(), pct=None)

    def _flush(self, detail: str, now: float, pct: float | None) -> None:
        self._emit(detail)
        self._last_t = now
        if pct is not None:
            self._last_pct = pct
