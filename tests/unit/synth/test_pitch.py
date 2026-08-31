"""Tests for register (male/female) estimation from audio pitch."""

from __future__ import annotations

import importlib.util
import wave
from pathlib import Path

import pytest

from repodify.synth.pitch import estimate_register

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("librosa") is None, reason="librosa not installed"
)


def _write_tone(path: Path, f0: float, seconds: float = 1.5, sr: int = 16000) -> None:
    """Write a mono 16-bit WAV of a harmonic tone at ``f0`` (voice-like)."""
    import numpy as np

    t = np.arange(int(seconds * sr)) / sr
    # Fundamental + a couple of decaying harmonics so YIN locks onto f0 cleanly.
    wave_data = (
        np.sin(2 * np.pi * f0 * t)
        + 0.5 * np.sin(2 * np.pi * 2 * f0 * t)
        + 0.25 * np.sin(2 * np.pi * 3 * f0 * t)
    )
    wave_data = (wave_data / np.max(np.abs(wave_data)) * 0.9 * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(wave_data.tobytes())


def test_low_pitch_is_male_register(tmp_path: Path):
    p = tmp_path / "male.wav"
    _write_tone(p, 120.0)  # typical male speaking F0
    register, f0 = estimate_register(p, 0.0, 1.5)
    assert register == "low"
    assert 100 < f0 < 150


def test_high_pitch_is_female_register(tmp_path: Path):
    p = tmp_path / "female.wav"
    _write_tone(p, 210.0)  # typical female speaking F0
    register, f0 = estimate_register(p, 0.0, 1.5)
    assert register == "high"
    assert 180 < f0 < 240


def test_ambiguous_midrange_returns_none(tmp_path: Path):
    p = tmp_path / "mid.wav"
    _write_tone(p, 160.0)  # in the male/female no-man's-land (155-165)
    register, _ = estimate_register(p, 0.0, 1.5)
    assert register is None


def test_too_short_window_returns_none(tmp_path: Path):
    p = tmp_path / "x.wav"
    _write_tone(p, 120.0)
    assert estimate_register(p, 0.0, 0.2) == (None, 0.0)


def test_missing_file_never_raises(tmp_path: Path):
    assert estimate_register(tmp_path / "nope.wav", 0.0, 1.0) == (None, 0.0)
