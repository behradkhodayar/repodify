"""A TTS that routes each voice to the backend that owns it.

Stock (catalog) voices carry `kokoro_voice` and go to Kokoro; cloned/reference
voices carry `ref_audio_path`/`ref_text` and go to F5-TTS. Both backends emit
24kHz mono 16-bit WAV, so a single assembled output stays uniform — `RoutingTTS`
validates that invariant and fails fast rather than letting `assemble_wav` choke
on a mismatched segment.
"""

from __future__ import annotations

import io
import wave

from podcast_compactor.ports.tts import SAMPLE_RATE, TTS, Voice


class RoutingTTS:
    """Dispatches `synthesize` per voice; `release()` frees both backends."""

    def __init__(self, f5: TTS, kokoro: TTS, sample_rate: int = SAMPLE_RATE) -> None:
        self.model_id = "f5+kokoro"
        self._f5 = f5
        self._kokoro = kokoro
        self._sample_rate = sample_rate

    def synthesize(self, text: str, voice: Voice) -> bytes:
        backend = self._kokoro if voice.kokoro_voice else self._f5
        data = backend.synthesize(text, voice)
        self._check_format(data, voice)
        return data

    def release(self) -> None:
        self._f5.release()
        self._kokoro.release()

    def _check_format(self, data: bytes, voice: Voice) -> None:
        with wave.open(io.BytesIO(data), "rb") as w:
            params = (w.getnchannels(), w.getsampwidth(), w.getframerate())
        expected = (1, 2, self._sample_rate)
        if params != expected:
            raise ValueError(
                f"voice {voice.name!r} produced {params}, expected {expected} "
                "(24kHz mono 16-bit); backends must agree so segments assemble"
            )
