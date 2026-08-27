"""The VoiceCloner port and a test fake.

A VoiceCloner turns one episode's already speaker-labeled transcript (plus its
audio) into cloned reference voices — one per requested speaker key — by cutting a
reference clip from each speaker's speech. Diarization ran upstream (the DIARIZE
stage); this is the seam behind which clip extraction lives.
"""

from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Protocol, runtime_checkable

from podcast_compactor.models.domain import Transcript
from podcast_compactor.ports.tts import SAMPLE_RATE, Voice
from podcast_compactor.storage.base import Storage


@runtime_checkable
class VoiceCloner(Protocol):
    """Builds a cloned `Voice` for each requested speaker key."""

    def clone(
        self,
        audio_path: Path,
        transcript: Transcript,
        speaker_keys: list[str],
        storage: Storage,
        job_id: str,
    ) -> dict[str, Voice]: ...


def _silent_wav(seconds: float = 1.0, sample_rate: int = SAMPLE_RATE) -> bytes:
    n_frames = max(1, int(seconds * sample_rate))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


class FakeVoiceCloner:
    """Writes a silent reference clip per speaker; no real audio needed."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, list[str], str]] = []

    def clone(
        self,
        audio_path: Path,
        transcript: Transcript,
        speaker_keys: list[str],
        storage: Storage,
        job_id: str,
    ) -> dict[str, Voice]:
        self.calls.append((audio_path, list(speaker_keys), job_id))
        voices: dict[str, Voice] = {}
        for key in speaker_keys:
            ref_key = f"{job_id}/refs/{key}.wav"
            storage.put_bytes(ref_key, _silent_wav())
            voices[key] = Voice(
                name=key,
                ref_audio_path=storage.local_path(ref_key),
                ref_text=f"reference for {key}",
            )
        return voices
