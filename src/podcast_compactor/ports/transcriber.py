"""The Transcriber port and a test fake."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from podcast_compactor.models.domain import Transcript


@runtime_checkable
class Transcriber(Protocol):
    """Turns an audio file into a `Transcript`."""

    def transcribe(self, audio_path: Path, language: str = "en") -> Transcript: ...


class FakeTranscriber:
    """Returns canned transcripts. Used for CPU-only tests.

    `canned` may be a single `Transcript` (returned for any input) or a dict
    keyed by the audio file name.
    """

    def __init__(self, canned: Transcript | dict[str, Transcript]) -> None:
        self._canned = canned
        self.calls: list[Path] = []

    def transcribe(self, audio_path: Path, language: str = "en") -> Transcript:
        self.calls.append(audio_path)
        if isinstance(self._canned, dict):
            return self._canned[Path(audio_path).name]
        return self._canned.model_copy(deep=True)
