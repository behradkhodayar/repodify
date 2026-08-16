"""pyannote-based voice cloner (real backend; requires the [gpu] extra + HF token).

Diarizes the downloaded episodes, picks the most-talkative speakers, cuts a short
reference clip per speaker with ffmpeg, and derives its reference text via the
transcriber. Heavy imports are deferred.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from podcast_compactor.ports.transcriber import Transcriber
from podcast_compactor.ports.tts import Voice
from podcast_compactor.storage.base import Storage


class PyannoteVoiceCloner:
    """Extracts cloned reference voices from episode audio via diarization."""

    def __init__(
        self,
        transcriber: Transcriber,
        hf_token: str | None,
        clip_seconds: float = 8.0,
        model: str = "pyannote/speaker-diarization-3.1",
    ) -> None:
        self._transcriber = transcriber
        self._hf_token = hf_token
        self._clip_seconds = clip_seconds
        self._model = model
        self._pipeline = None

    def _pipeline_(self):
        from pyannote.audio import Pipeline  # lazy: needs the [gpu] extra

        if self._pipeline is None:
            self._pipeline = Pipeline.from_pretrained(self._model, use_auth_token=self._hf_token)
        return self._pipeline

    def clone(
        self,
        audio_paths: list[Path],
        speaker_keys: list[str],
        storage: Storage,
        job_id: str,
    ) -> dict[str, Voice]:
        if not audio_paths:
            raise ValueError("no audio to clone from")
        source = audio_paths[0]
        diarization = self._pipeline_()(str(source))

        durations: dict[str, float] = {}
        longest_turn: dict[str, tuple[float, float]] = {}
        for turn, _track, speaker in diarization.itertracks(yield_label=True):
            durations[speaker] = durations.get(speaker, 0.0) + (turn.end - turn.start)
            best = longest_turn.get(speaker)
            if best is None or (turn.end - turn.start) > (best[1] - best[0]):
                longest_turn[speaker] = (turn.start, turn.end)

        top = sorted(durations, key=lambda s: durations[s], reverse=True)[: len(speaker_keys)]
        voices: dict[str, Voice] = {}
        for key, speaker in zip(speaker_keys, top, strict=False):
            start, end = longest_turn[speaker]
            end = min(end, start + self._clip_seconds)
            ref_key = f"{job_id}/refs/{key}.wav"
            clip_path = storage.local_path(ref_key)
            clip_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(source), "-ss", str(start), "-to", str(end),
                 "-ac", "1", "-ar", "24000", str(clip_path)],
                check=True,
                capture_output=True,
            )
            ref_text = self._transcriber.transcribe(clip_path).text
            voices[key] = Voice(name=key, ref_audio_path=clip_path, ref_text=ref_text)
        return voices
