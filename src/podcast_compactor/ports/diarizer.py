"""The Diarizer port, a SpeakerTurn descriptor, and a test fake.

A Diarizer answers "who spoke when" for one audio file: it returns time-stamped
speaker turns (anonymous labels like ``SPEAKER_00``). Fusing those turns onto a
transcript (`transcribe.diarization.assign_speakers`) is what makes the transcript
know who said what — the prerequisite for per-speaker voice cloning and stock voices.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class SpeakerTurn(BaseModel):
    """A contiguous span attributed to one diarized speaker."""

    start: float
    end: float
    speaker: str  # diarization label, e.g. "SPEAKER_00"


@runtime_checkable
class Diarizer(Protocol):
    """Segments an audio file into per-speaker turns."""

    def diarize(self, audio_path: Path) -> list[SpeakerTurn]: ...

    def release(self) -> None:
        """Free any GPU-resident model so VRAM is available to the next stage.

        Idempotent and safe to call when nothing is loaded; a real backend
        reloads lazily on the next `diarize`.
        """
        ...


class FakeDiarizer:
    """Returns canned speaker turns. Used for CPU-only tests and fake mode.

    Defaults to two speakers alternating in fixed 5-second turns, which is enough
    to exercise speaker labeling and the two-voice paths without any model.
    """

    def __init__(self, canned: list[SpeakerTurn] | None = None) -> None:
        self._canned = canned if canned is not None else _default_turns()
        self.calls: list[Path] = []

    def diarize(self, audio_path: Path) -> list[SpeakerTurn]:
        self.calls.append(audio_path)
        return [turn.model_copy(deep=True) for turn in self._canned]

    def release(self) -> None:
        """No-op: the fake holds no GPU model."""


def _default_turns() -> list[SpeakerTurn]:
    return [
        SpeakerTurn(start=0.0, end=5.0, speaker="SPEAKER_00"),
        SpeakerTurn(start=5.0, end=10.0, speaker="SPEAKER_01"),
        SpeakerTurn(start=10.0, end=15.0, speaker="SPEAKER_00"),
        SpeakerTurn(start=15.0, end=20.0, speaker="SPEAKER_01"),
    ]
