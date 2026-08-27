"""The TTS port, a Voice descriptor, and a silent test fake."""

from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

SAMPLE_RATE = 24000
_WPM = 130


class Voice(BaseModel):
    """A voice for synthesis, resolved by whichever backend owns it.

    Two kinds of voice share this shape:

    - **Cloned / reference voice** (F5-TTS, zero-shot): `ref_audio_path` + `ref_text`
      describe the clip to imitate. Even the "default" narrator is one of these.
    - **Stock catalog voice** (Kokoro): `kokoro_voice` names a built-in voice; no
      reference clip is needed.

    All fields are optional so the fake can run without any assets. `RoutingTTS`
    dispatches on `kokoro_voice` (set → Kokoro, unset → F5-TTS).
    """

    name: str
    ref_audio_path: Path | None = None
    ref_text: str | None = None
    kokoro_voice: str | None = None


@runtime_checkable
class TTS(Protocol):
    """Synthesizes speech for `text` in `voice`; returns 24kHz mono WAV bytes."""

    def synthesize(self, text: str, voice: Voice) -> bytes: ...

    def release(self) -> None:
        """Free any GPU-resident model so VRAM is available to the next stage.

        Idempotent and safe to call when nothing is loaded; a real backend
        reloads lazily on the next `synthesize`.
        """
        ...


class FakeTTS:
    """Returns valid silent WAV whose duration tracks the word count.

    Lets the whole pipeline (and assembly) run on CPU with no model.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate

    def release(self) -> None:
        """No-op: the fake holds no GPU model."""

    def synthesize(self, text: str, voice: Voice) -> bytes:
        words = max(1, len(text.split()))
        seconds = words / _WPM * 60
        n_frames = max(1, int(seconds * self.sample_rate))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)  # 16-bit PCM
            w.setframerate(self.sample_rate)
            w.writeframes(b"\x00\x00" * n_frames)
        return buf.getvalue()
