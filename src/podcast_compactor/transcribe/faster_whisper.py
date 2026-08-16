"""faster-whisper transcriber (real backend; requires the [gpu] extra)."""

from __future__ import annotations

from pathlib import Path

from podcast_compactor.models.domain import Transcript, TranscriptSegment


class FasterWhisperTranscriber:
    """Transcribes audio with faster-whisper (CTranslate2 Whisper).

    The heavy `faster_whisper` import is deferred to construction so the rest of
    the app — and the test suite — can run without the GPU extra installed.
    """

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "float16",
    ) -> None:
        from faster_whisper import WhisperModel  # lazy: needs the [gpu] extra

        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: Path, language: str = "en") -> Transcript:
        segments, _info = self._model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
        )
        return Transcript(
            episode_guid="",  # filled in by the caller
            segments=[
                TranscriptSegment(start=s.start, end=s.end, text=s.text)
                for s in segments
            ],
        )
