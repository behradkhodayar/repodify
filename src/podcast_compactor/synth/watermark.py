"""AudioSeal watermarker (real backend; requires the [gpu] extra).

Embeds Meta's AudioSeal inaudible watermark into synthesized audio. Heavy imports
are deferred to construction.
"""

from __future__ import annotations

import io
import wave


class AudioSealWatermarker:
    """Embeds an AudioSeal watermark into 16-bit mono WAV bytes."""

    def __init__(self, model: str = "audioseal_wm_16bits") -> None:
        from audioseal import AudioSeal  # lazy: needs the [gpu] extra

        self._generator = AudioSeal.load_generator(model)

    def embed(self, wav: bytes) -> bytes:
        import numpy as np  # lazy
        import torch  # lazy

        with wave.open(io.BytesIO(wav), "rb") as r:
            channels, width, rate, frames = (
                r.getnchannels(),
                r.getsampwidth(),
                r.getframerate(),
                r.getnframes(),
            )
            raw = r.readframes(frames)

        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        tensor = torch.from_numpy(samples).view(1, 1, -1)
        watermarked = self._generator(tensor, sample_rate=rate, alpha=1.0) + tensor
        out = (watermarked.squeeze().clamp(-1.0, 1.0).numpy() * 32767.0).astype("<i2").tobytes()

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(width)
            w.setframerate(rate)
            w.writeframes(out)
        return buf.getvalue()
