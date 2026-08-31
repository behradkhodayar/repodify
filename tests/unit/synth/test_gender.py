"""Tests for estimate_cast_registers (window selection + pitch, across episodes)."""

from __future__ import annotations

import importlib.util
import wave
from pathlib import Path

import pytest

from repodify.models.domain import Speaker, Transcript, TranscriptSegment
from repodify.synth.gender import estimate_cast_registers

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("librosa") is None, reason="librosa not installed"
)


def _tone_wav(path: Path, f0: float, seconds: float = 2.0, sr: int = 16000) -> None:
    import numpy as np

    t = np.arange(int(seconds * sr)) / sr
    data = (
        np.sin(2 * np.pi * f0 * t)
        + 0.5 * np.sin(2 * np.pi * 2 * f0 * t)
        + 0.25 * np.sin(2 * np.pi * 3 * f0 * t)
    )
    data = (data / np.max(np.abs(data)) * 0.9 * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def _transcript(speaker: str, start: float, end: float) -> Transcript:
    return Transcript(
        episode_guid="ep",
        segments=[TranscriptSegment(start=start, end=end, text="hello", speaker=speaker)],
        speakers=[Speaker(id=speaker, speaking_seconds=end - start)],
    )


def test_registers_inferred_per_speaker(tmp_path: Path):
    male = tmp_path / "m.wav"
    female = tmp_path / "f.wav"
    _tone_wav(male, 120.0)
    _tone_wav(female, 210.0)
    sources = [
        (male, _transcript("SPEAKER_00", 0.0, 2.0)),
        (female, _transcript("SPEAKER_01", 0.0, 2.0)),
    ]
    got = estimate_cast_registers(sources, ["SPEAKER_00", "SPEAKER_01"])
    assert got == {"SPEAKER_00": "low", "SPEAKER_01": "high"}


def test_speaker_absent_from_all_episodes_is_omitted(tmp_path: Path):
    male = tmp_path / "m.wav"
    _tone_wav(male, 120.0)
    sources = [(male, _transcript("SPEAKER_00", 0.0, 2.0))]
    # SPEAKER_09 never appears -> no register (caller falls back), no crash.
    got = estimate_cast_registers(sources, ["SPEAKER_00", "SPEAKER_09"])
    assert got == {"SPEAKER_00": "low"}
