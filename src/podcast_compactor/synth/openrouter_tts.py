"""OpenRouter TTS synthesizer (real backend; needs only an API key + ffmpeg).

Routes synthesis to a hosted text-to-speech model on OpenRouter's OpenAI-compatible
``POST /audio/speech`` endpoint — by default Fish Audio's ``fish-audio/s2.1-pro``.
Unlike the F5-TTS/Kokoro backends this holds no local model and needs no GPU, so
it is a drop-in `TTS` that trades VRAM for a network call.

Voice mapping: a reference `Voice` (``ref_audio_path`` + ``ref_text``, e.g. the
narrator or a per-host clip) is sent as Fish Audio ``input_references`` so the
output imitates that clip. A voice without a reference falls back to the model's
default voice. The endpoint returns mp3; we decode it to the port's canonical
24kHz mono 16-bit WAV via ffmpeg so segments assemble uniformly.
"""

from __future__ import annotations

import base64
import io
import subprocess
import wave
from functools import lru_cache
from pathlib import Path

import httpx

from podcast_compactor.ports.tts import SAMPLE_RATE, Voice


class OpenRouterTTSError(RuntimeError):
    """Raised when the OpenRouter speech endpoint returns a non-audio response."""


@lru_cache(maxsize=8)
def _encode_reference(path: Path) -> str:
    """Return the ``data:`` URI for a reference clip, cached per path."""
    data = Path(path).read_bytes()
    suffix = Path(path).suffix.lstrip(".").lower() or "wav"
    return f"data:audio/{suffix};base64," + base64.b64encode(data).decode()


class OpenRouterTTS:
    """Synthesizes speech via OpenRouter; returns 24kHz mono 16-bit WAV bytes.

    Stateless apart from a shared `httpx.Client`; `release()` is a no-op since
    there is no GPU-resident model to free.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "fish-audio/s2.1-pro",
        base_url: str = "https://openrouter.ai/api/v1",
        http: httpx.Client | None = None,
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouterTTS requires an OpenRouter API key")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._sample_rate = sample_rate
        self._http = http or httpx.Client(timeout=120.0)

    def _build_body(self, text: str, voice: Voice) -> dict:
        body: dict = {
            "model": self._model,
            "input": text,
            "response_format": "mp3",
        }
        if voice.ref_audio_path is not None:
            refs: list[dict] = [
                {
                    "type": "input_audio",
                    "input_audio": {"data": _encode_reference(Path(voice.ref_audio_path))},
                }
            ]
            if voice.ref_text:
                refs.append({"type": "text", "text": voice.ref_text})
            body["input_references"] = refs
        return body

    def synthesize(self, text: str, voice: Voice) -> bytes:
        resp = self._http.post(
            f"{self._base_url}/audio/speech",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=self._build_body(text, voice),
        )
        content_type = resp.headers.get("content-type", "")
        if resp.status_code != 200 or content_type.startswith("application/json"):
            detail = resp.text[:500]
            raise OpenRouterTTSError(
                f"OpenRouter TTS failed for voice {voice.name!r} "
                f"(HTTP {resp.status_code}, {content_type or 'no content-type'}): {detail}"
            )
        return self._mp3_to_wav(resp.content)

    def _mp3_to_wav(self, mp3: bytes) -> bytes:
        """Decode mp3 to raw PCM with ffmpeg, then wrap as 24kHz mono 16-bit WAV.

        ffmpeg writes raw s16le to stdout (no header to seek back and patch), so
        we frame it ourselves with known parameters — avoiding the truncated-size
        header ffmpeg emits for non-seekable WAV output.
        """
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", "pipe:0",
                "-ar", str(self._sample_rate), "-ac", "1",
                "-f", "s16le", "pipe:1",
            ],
            input=mp3,
            capture_output=True,
        )
        if result.returncode != 0 or not result.stdout:
            raise OpenRouterTTSError(
                f"ffmpeg mp3->wav decode failed ({result.returncode}): "
                f"{result.stderr.decode(errors='replace')[-500:]}"
            )
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._sample_rate)
            w.writeframes(result.stdout)
        return buf.getvalue()

    def release(self) -> None:
        """No-op: OpenRouter holds no local model, so there is no VRAM to free."""
