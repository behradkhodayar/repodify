"""The Transcoder port and a test fake."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Transcoder(Protocol):
    """Transcodes a WAV file to a compressed mp3 rendition."""

    def to_mp3(self, src_wav: Path, dst_mp3: Path) -> None: ...


class FakeTranscoder:
    """Writes a tiny stub mp3 so pipeline tests need no ffmpeg."""

    def to_mp3(self, src_wav: Path, dst_mp3: Path) -> None:
        dst_mp3.parent.mkdir(parents=True, exist_ok=True)
        dst_mp3.write_bytes(b"ID3fake-mp3")
