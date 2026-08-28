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


class DiarizationResult(BaseModel):
    """One episode's diarization: who-spoke-when plus a voice embedding per speaker.

    ``embeddings`` maps each per-episode label to its speaker-centroid vector. It
    powers cross-episode speaker identity (matching the same person across episodes,
    whose per-file labels are otherwise inconsistent); it may be empty for backends
    that cannot produce embeddings, in which case callers fall back to per-episode
    labels.
    """

    turns: list[SpeakerTurn]
    embeddings: dict[str, list[float]] = {}  # per-episode label -> centroid embedding


@runtime_checkable
class Diarizer(Protocol):
    """Segments an audio file into per-speaker turns (with per-speaker embeddings)."""

    def diarize(self, audio_path: Path) -> DiarizationResult: ...

    def release(self) -> None:
        """Free any GPU-resident model so VRAM is available to the next stage.

        Idempotent and safe to call when nothing is loaded; a real backend
        reloads lazily on the next `diarize`.
        """
        ...


def _fake_embedding(label: str, dim: int = 8) -> list[float]:
    """A deterministic unit-ish embedding per label: same label -> same vector.

    Lets the fake exercise cross-episode clustering — identical labels across
    episodes cluster together, distinct labels stay apart — with no model.
    """
    seed = sum(ord(c) for c in label)
    return [((seed * (i + 1)) % 97) / 97.0 for i in range(dim)]


class FakeDiarizer:
    """Returns canned speaker turns + deterministic embeddings. For CPU-only tests.

    Defaults to two speakers alternating in fixed 5-second turns, which is enough
    to exercise speaker labeling and the two-voice paths without any model. Each
    label gets a fixed synthetic embedding so the cross-episode clustering path is
    testable too.
    """

    def __init__(self, canned: list[SpeakerTurn] | None = None) -> None:
        self._canned = canned if canned is not None else _default_turns()
        self.calls: list[Path] = []

    def diarize(self, audio_path: Path) -> DiarizationResult:
        self.calls.append(audio_path)
        turns = [turn.model_copy(deep=True) for turn in self._canned]
        labels = {t.speaker for t in turns}
        return DiarizationResult(
            turns=turns,
            embeddings={label: _fake_embedding(label) for label in labels},
        )

    def release(self) -> None:
        """No-op: the fake holds no GPU model."""


def _default_turns() -> list[SpeakerTurn]:
    return [
        SpeakerTurn(start=0.0, end=5.0, speaker="SPEAKER_00"),
        SpeakerTurn(start=5.0, end=10.0, speaker="SPEAKER_01"),
        SpeakerTurn(start=10.0, end=15.0, speaker="SPEAKER_00"),
        SpeakerTurn(start=15.0, end=20.0, speaker="SPEAKER_01"),
    ]
