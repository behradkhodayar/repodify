"""Speaker diarization: a pyannote backend plus a pure transcript-fusion helper.

`PyannoteDiarizer` answers "who spoke when" (heavy, GPU, lazy import). `assign_speakers`
is pure Python — it labels each transcript segment with the speaker who overlaps it
most, so the two concerns stay independently testable.
"""

from __future__ import annotations

from pathlib import Path

from repodify.models.domain import Speaker, TranscriptSegment
from repodify.ports.diarizer import DiarizationResult, SpeakerTurn


class PyannoteDiarizer:
    """Diarizes audio with pyannote (requires the [gpu] extra + a HF token).

    Heavy imports are deferred; the pipeline loads lazily on first `diarize` and is
    dropped by `release()` so its VRAM is available to the next stage.
    """

    def __init__(
        self,
        hf_token: str | None,
        model: str = "pyannote/speaker-diarization-community-1",
    ) -> None:
        self.model_id = model
        self._hf_token = hf_token
        self._model = model
        self._pipeline = None

    def _pipeline_(self):
        import torch
        from pyannote.audio import Pipeline  # lazy: needs the [gpu] extra

        if self._pipeline is None:
            # pyannote.audio 4.x renamed the auth kwarg `use_auth_token` -> `token`.
            pipeline = Pipeline.from_pretrained(self._model, token=self._hf_token)
            if pipeline is None:
                raise RuntimeError(
                    f"could not load diarization pipeline {self._model!r} "
                    "(check the HF token and that its license is accepted)"
                )
            # Pipelines load on CPU by default; move to GPU or diarization crawls.
            if torch.cuda.is_available():
                pipeline.to(torch.device("cuda"))
            self._pipeline = pipeline
        return self._pipeline

    def diarize(self, audio_path: Path) -> DiarizationResult:
        result = self._pipeline_()(str(audio_path))
        # pyannote 4.x returns a `DiarizeOutput` (annotation + per-speaker
        # embeddings); 3.x returned a bare `Annotation`. Accept either.
        annotation = getattr(result, "speaker_diarization", result)
        turns = [
            SpeakerTurn(start=turn.start, end=turn.end, speaker=speaker)
            for turn, _track, speaker in annotation.itertracks(yield_label=True)
        ]
        # `speaker_embeddings` is (num_speakers, dim), row i aligned with the i-th
        # sorted label; used to match the same speaker across episodes.
        embeddings: dict[str, list[float]] = {}
        raw = getattr(result, "speaker_embeddings", None)
        if raw is not None:
            for idx, label in enumerate(annotation.labels()):
                if idx < len(raw):
                    embeddings[label] = [float(x) for x in raw[idx]]
        return DiarizationResult(turns=turns, embeddings=embeddings)

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


def unify_speakers_across_episodes(
    results: dict[str, DiarizationResult],
    threshold: float,
) -> tuple[dict[str, list[SpeakerTurn]], list[Speaker]]:
    """Collapse independently-diarized episodes into one shared speaker space.

    Diarization runs per file, so its labels are not consistent across episodes.
    This matches each episode's speakers to cross-episode identities by voice
    embedding, then relabels every episode's turns with the shared global ids.

    Returns ``(relabeled_turns_by_guid, pooled_roster)`` — the pooled roster
    (most-talkative speaker first) is the digest's cast. When embeddings are
    unavailable it is an identity relabeling, so callers keep the per-episode labels.
    """
    # Lazy: numpy lives in speaker_clustering. Importing it at module load
    # takes down the fake-mode worker (`./launch --fake` used to `uv sync`
    # without numpy).
    from repodify.transcribe.speaker_clustering import LocalSpeaker, cluster_speakers

    locals_ = [
        LocalSpeaker(guid, sp.id, res.embeddings[sp.id], sp.speaking_seconds)
        for guid, res in results.items()
        for sp in roster_from_turns(res.turns)
        if sp.id in res.embeddings
    ]
    mapping = cluster_speakers(locals_, threshold)
    relabeled = {
        guid: [
            t.model_copy(update={"speaker": mapping.get((guid, t.speaker), t.speaker)})
            for t in res.turns
        ]
        for guid, res in results.items()
    }
    pooled = [t for turns in relabeled.values() for t in turns]
    return relabeled, roster_from_turns(pooled)
