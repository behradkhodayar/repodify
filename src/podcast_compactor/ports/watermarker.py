"""The Watermarker port and a test fake.

A Watermarker embeds an inaudible mark into synthesized audio so cloned output is
detectable as AI-generated.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Watermarker(Protocol):
    """Embeds an inaudible watermark into WAV bytes; returns WAV bytes."""

    def embed(self, wav: bytes) -> bytes: ...


class FakeWatermarker:
    """No-op watermarker for CPU tests; records that it was applied."""

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, wav: bytes) -> bytes:
        self.calls += 1
        return wav
