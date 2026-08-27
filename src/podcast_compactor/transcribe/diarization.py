"""Speaker diarization: a pyannote backend plus a pure transcript-fusion helper.

`PyannoteDiarizer` answers "who spoke when" (heavy, GPU, lazy import). `assign_speakers`
is pure Python — it labels each transcript segment with the speaker who overlaps it
most, so the two concerns stay independently testable.
"""

from __future__ import annotations

from pathlib import Path

from podcast_compactor.models.domain import Speaker, TranscriptSegment
from podcast_compactor.ports.diarizer import SpeakerTurn


class PyannoteDiarizer:
    """Diarizes audio with pyannote (requires the [gpu] extra + a HF token).

    Heavy imports are deferred; the pipeline loads lazily on first `diarize` and is
    dropped by `release()` so its VRAM is available to the next stage.
    """

    def __init__(
        self,
        hf_token: str | None,
        model: str = "pyannote/speaker-diarization-3.1",
    ) -> None:
        self._hf_token = hf_token
        self._model = model
        self._pipeline = None

    def _pipeline_(self):
        from pyannote.audio import Pipeline  # lazy: needs the [gpu] extra

        if self._pipeline is None:
            self._pipeline = Pipeline.from_pretrained(
                self._model, use_auth_token=self._hf_token
            )
        return self._pipeline

    def diarize(self, audio_path: Path) -> list[SpeakerTurn]:
        diarization = self._pipeline_()(str(audio_path))
        return [
            SpeakerTurn(start=turn.start, end=turn.end, speaker=speaker)
            for turn, _track, speaker in diarization.itertracks(yield_label=True)
        ]

    def release(self) -> None:
        """Drop the pipeline and free VRAM. Idempotent; reloads lazily next call."""
        self._pipeline = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 - best-effort cleanup, never fatal
            pass


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speakers(
    segments: list[TranscriptSegment],
    turns: list[SpeakerTurn],
) -> list[TranscriptSegment]:
    """Return segments labeled with the speaker whose turns overlap them most.

    Each segment is attributed to the speaker with the greatest total temporal
    overlap. A segment overlapping no turn keeps its existing `speaker` (usually
    ``None``). Ties resolve to the speaker whose turn appears first.
    """
    labeled: list[TranscriptSegment] = []
    for seg in segments:
        overlaps: dict[str, float] = {}
        for turn in turns:
            ov = _overlap(seg.start, seg.end, turn.start, turn.end)
            if ov > 0:
                overlaps[turn.speaker] = overlaps.get(turn.speaker, 0.0) + ov
        if overlaps:
            best = max(overlaps, key=lambda s: overlaps[s])
            labeled.append(seg.model_copy(update={"speaker": best}))
        else:
            labeled.append(seg.model_copy())
    return labeled


def roster_from_turns(turns: list[SpeakerTurn]) -> list[Speaker]:
    """Build the per-episode `Speaker` roster (with total talk time) from turns."""
    durations: dict[str, float] = {}
    for turn in turns:
        durations[turn.speaker] = durations.get(turn.speaker, 0.0) + (turn.end - turn.start)
    return [
        Speaker(id=speaker, speaking_seconds=round(seconds, 3))
        for speaker, seconds in sorted(durations.items(), key=lambda kv: kv[1], reverse=True)
    ]
