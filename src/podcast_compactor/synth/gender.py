"""Infer each cast speaker's vocal register across episodes, for stock voicing.

Ties together diarization (which episode window a speaker speaks in) and pitch
estimation (`synth.pitch`) to label each cast speaker ``"high"``/``"low"``. The
speaker-preserving digest uses this to pick a same-gender stock voice by default,
so a male host gets a male voice even without cloning.
"""

from __future__ import annotations

from pathlib import Path

from podcast_compactor.models.domain import Transcript
from podcast_compactor.synth.cloning import best_window
from podcast_compactor.synth.pitch import estimate_register


def estimate_cast_registers(
    sources: list[tuple[Path, Transcript]],
    cast_ids: list[str],
    clip_seconds: float = 6.0,
) -> dict[str, str]:
    """Map each cast speaker to ``"high"``/``"low"`` where pitch is confident.

    For each speaker, measure their longest single-speaker window across the
    episodes they actually appear in, and estimate its register. Speakers with too
    little audio or an ambiguous pitch are omitted, so the caller falls back.
    """
    registers: dict[str, str] = {}
    for sid in cast_ids:
        best: tuple[Path, float, float] | None = None
        best_len = 0.0
        for audio_path, transcript in sources:
            if not any(s.id == sid for s in transcript.speakers):
                continue  # speaker didn't appear in this episode
            start, end, _ = best_window(transcript.segments, sid, clip_seconds)
            if end - start > best_len:
                best_len = end - start
                best = (audio_path, start, end)
        if best is None or best_len <= 0.0:
            continue
        register, _f0 = estimate_register(*best)
        if register is not None:
            registers[sid] = register
    return registers
