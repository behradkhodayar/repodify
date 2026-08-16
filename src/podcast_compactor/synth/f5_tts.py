"""F5-TTS synthesizer (real backend; requires the [gpu] extra).

F5-TTS is zero-shot: `voice.ref_audio_path` and `voice.ref_text` describe the
reference clip to imitate. Heavy imports are deferred to construction.
"""

from __future__ import annotations

import io
import wave

from podcast_compactor.ports.tts import Voice


class F5TTS:
    """Synthesizes speech with F5-TTS and returns 16-bit mono WAV bytes."""

    def __init__(
        self,
        model: str = "F5TTS_v1_Base",
        device: str = "cuda",
    ) -> None:
        from f5_tts.api import F5TTS as _F5TTS  # lazy: needs the [gpu] extra

        self._api = _F5TTS(model=model, device=device)

    def synthesize(self, text: str, voice: Voice) -> bytes:
        if voice.ref_audio_path is None or voice.ref_text is None:
            raise ValueError("F5-TTS requires voice.ref_audio_path and voice.ref_text")

        import numpy as np  # lazy

        wav, sr, _spec = self._api.infer(
            ref_file=str(voice.ref_audio_path),
            ref_text=voice.ref_text,
            gen_text=text,
        )
        pcm = (np.clip(wav, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(sr))
            w.writeframes(pcm)
        return buf.getvalue()
