"""Estimate a speaker's vocal register (male/female) from a window of their audio.

Used to pick a same-gender stock voice by default on the speaker-preserving digest.
We measure the **median fundamental frequency (F0)** over a short window of the
speaker's speech with probabilistic YIN, then classify: clearly-low -> ``"low"``
(male), clearly-high -> ``"high"`` (female). Readings in the ambiguous middle (or
too little voiced audio) return ``None`` so the caller can fall back rather than
guess. The median over many frames is robust to the occasional octave error that
makes per-frame F0 unreliable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

# F0 boundaries (Hz). Adult male speech medians cluster ~100-150, female ~165-220;
# the ~155-165 overlap is genuinely ambiguous, so we decline to classify there.
_MALE_MAX_HZ = 155.0
_FEMALE_MIN_HZ = 165.0
# YIN search range — wide enough for low male and high female voices.
_FMIN_HZ = 65.0
_FMAX_HZ = 350.0
_SR = 16000


def estimate_register(
    audio_path: str | Path,
    start: float,
    end: float,
) -> tuple[Literal["high", "low"] | None, float]:
    """Return ``(register, median_f0)`` for the speech in ``[start, end]``.

    ``register`` is ``"low"`` (male), ``"high"`` (female), or ``None`` when the
    window is too short/unvoiced or the pitch is ambiguous. Never raises for audio
    problems — it returns ``(None, 0.0)`` so gender inference can't break a digest.
    """
    duration = max(0.0, float(end) - float(start))
    if duration < 0.5:
        return None, 0.0
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(
            str(audio_path), sr=_SR, offset=float(start), duration=duration, mono=True
        )
        if y.size < int(sr * 0.3):
            return None, 0.0
        f0, _voiced, _prob = librosa.pyin(y, fmin=_FMIN_HZ, fmax=_FMAX_HZ, sr=sr)
        voiced = f0[np.isfinite(f0)]
        if voiced.size < 5:
            return None, 0.0
        median = float(np.median(voiced))
    except Exception:  # noqa: BLE001 - pitch is best-effort; never fail the digest
        return None, 0.0

    if median <= _MALE_MAX_HZ:
        return "low", median
    if median >= _FEMALE_MIN_HZ:
        return "high", median
    return None, median  # ambiguous middle -> caller falls back
