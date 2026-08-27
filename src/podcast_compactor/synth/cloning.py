"""Voice cloner that cuts a reference clip per speaker from a labeled transcript.

Diarization and transcription already ran upstream (the DIARIZE stage), so this
just picks each speaker's cleanest single-speaker window, cuts it out with ffmpeg,
and reuses the transcript text as the reference text — no second diarization or
Whisper pass. Requires ffmpeg on PATH.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from podcast_compactor.models.domain import Transcript, TranscriptSegment
from podcast_compactor.ports.tts import Voice
from podcast_compactor.storage.base import Storage


class ClipVoiceCloner:
    """Builds a cloned `Voice` for each requested key from the labeled transcript.

    Requested keys (e.g. the script's speakers) are matched to the most-talkative
    detected speakers in order, and each gets a clip cut from its best window.
    """

    def __init__(self, clip_seconds: float = 8.0) -> None:
        self._clip_seconds = clip_seconds

    def clone(
        self,
        audio_path: Path,
        transcript: Transcript,
        speaker_keys: list[str],
        storage: Storage,
        job_id: str,
    ) -> dict[str, Voice]:
        ranked = _rank_speakers(transcript.segments)
        if not ranked:
            raise ValueError("transcript has no speaker labels to clone from")

        voices: dict[str, Voice] = {}
        for key, diar_id in zip(speaker_keys, ranked, strict=False):
            start, end, ref_text = _best_window(
                transcript.segments, diar_id, self._clip_seconds
            )
            ref_key = f"{job_id}/refs/{key}.wav"
            clip_path = storage.local_path(ref_key)
            clip_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(audio_path), "-ss", str(start), "-to", str(end),
                 "-ac", "1", "-ar", "24000", str(clip_path)],
                check=True,
                capture_output=True,
            )
            voices[key] = Voice(name=key, ref_audio_path=clip_path, ref_text=ref_text)
        return voices


def _rank_speakers(segments: list[TranscriptSegment]) -> list[str]:
    """Speaker ids present in the transcript, most talkative first."""
    durations: dict[str, float] = {}
    for seg in segments:
        if seg.speaker is None:
            continue
        durations[seg.speaker] = durations.get(seg.speaker, 0.0) + (seg.end - seg.start)
    return sorted(durations, key=lambda s: durations[s], reverse=True)


def _best_window(
    segments: list[TranscriptSegment],
    speaker_id: str,
    clip_seconds: float,
) -> tuple[float, float, str]:
    """Pick a speaker's longest single-speaker run and return (start, end, text).

    Returns a window no longer than `clip_seconds`, and the transcript text of the
    segments it spans (its reference text).
    """
    runs: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    for seg in segments:
        if seg.speaker == speaker_id:
            current.append(seg)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    if not runs:
        return (0.0, clip_seconds, "")

    best = max(runs, key=lambda run: run[-1].end - run[0].start)
    start = best[0].start
    end = min(best[-1].end, start + clip_seconds)
    text = " ".join(seg.text.strip() for seg in best if seg.start < end and seg.text.strip())
    return (start, end, text)
