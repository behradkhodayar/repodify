"""Kokoro-82M synthesizer (real backend; requires the [gpu] extra).

Kokoro is a catalog TTS: `voice.kokoro_voice` names a built-in voice (no reference
clip). It provides the project's stock voices, alongside F5-TTS for cloned voices —
`RoutingTTS` picks between them. Heavy imports are deferred to first use.
"""

from __future__ import annotations

import array
import io
import sys
import wave

from repodify.gpu import empty_cuda_cache
from repodify.ports.tts import SAMPLE_RATE, Voice


class KokoroTTS:
    """Synthesizes speech from a named Kokoro voice; returns 24kHz mono WAV bytes.

    The pipeline loads lazily on first `synthesize`, so wiring costs no VRAM, and
    `release()` hands it back once synthesis is done.
    """

    def __init__(self, lang_code: str = "a", sample_rate: int = SAMPLE_RATE) -> None:
        self._lang_code = lang_code
        self._sample_rate = sample_rate
        self._pipeline = None

    def _ensure_pipeline(self):
        if self._pipeline is None:
            from kokoro import KPipeline  # lazy: needs the [gpu] extra

            self._pipeline = KPipeline(lang_code=self._lang_code)
        return self._pipeline

    def synthesize(self, text: str, voice: Voice) -> bytes:
        if not voice.kokoro_voice:
            raise ValueError("KokoroTTS requires voice.kokoro_voice")

        pipeline = self._ensure_pipeline()
        samples: list[float] = []
        for _graphemes, _phonemes, audio in pipeline(text, voice=voice.kokoro_voice):
            samples.extend(_as_float_list(audio))
        return _floats_to_wav(samples, self._sample_rate)

    def release(self) -> None:
        """Drop the pipeline so its VRAM is freed; reloads lazily next synthesize."""
        self._pipeline = None
        empty_cuda_cache()


def _as_float_list(audio) -> list[float]:
    """Normalize a Kokoro audio chunk (torch tensor / numpy array / list) to floats."""
    to_list = getattr(audio, "tolist", None)
    return list(to_list()) if callable(to_list) else list(audio)


def _floats_to_wav(samples: list[float], sample_rate: int) -> bytes:
    """Pack float samples in [-1, 1] into little-endian 16-bit mono WAV bytes."""
    pcm = array.array(
        "h", (max(-32768, min(32767, int(x * 32767.0))) for x in samples)
    )
    if sys.byteorder == "big":
        pcm.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
