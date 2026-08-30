"""OpenRouter TTS synthesizer (real backend; needs only an API key + ffmpeg).

Routes synthesis to a hosted text-to-speech model on OpenRouter's OpenAI-compatible
``POST /audio/speech`` endpoint — by default Fish Audio's ``fish-audio/s2.1-pro``.
Unlike the F5-TTS/Kokoro backends this holds no local model and needs no GPU, so
it is a drop-in `TTS` that trades VRAM for a network call.

Voice mapping — every voice is resolved to a **stable reference clip** so a given
speaker sounds identical across all their segments:

- A `Voice` with ``ref_audio_path`` (narrator / per-host clip / a diarized clone)
  is cloned directly via Fish Audio ``input_references``.
- A voice without a clip (stock catalog / multi-host) is described in natural
  language (``instructions`` / a Kokoro-id fallback). Fish Audio's text-style
  control is a soft nudge that re-rolls a *different* voice on every call, so
  instead of sending the description per segment we generate one **seed clip** from
  it once, cache it per speaker, and clone that seed via ``input_references`` for
  every segment. This locks the identity — the fix for a speaker's voice drifting
  between segments — while keeping distinct speakers distinct (each seeds from its
  own description). A bare voice with neither clip nor description uses the model's
  default voice.

The endpoint returns mp3; we decode it to the port's canonical 24kHz mono 16-bit
WAV via ffmpeg so segments assemble uniformly.
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

# A short, phonetically varied line spoken by each seed clip. Its only job is to
# give Fish Audio a consistent voice reference to clone; the words don't matter.
_SEED_TEXT = "Hello there, this is a quick voice sample to keep the speaker steady."


class OpenRouterTTSError(RuntimeError):
    """Raised when the OpenRouter speech endpoint returns a non-audio response."""


@lru_cache(maxsize=8)
def _encode_reference(path: Path) -> str:
    """Return the ``data:`` URI for a reference clip file, cached per path."""
    data = Path(path).read_bytes()
    suffix = Path(path).suffix.lstrip(".").lower() or "wav"
    return f"data:audio/{suffix};base64," + base64.b64encode(data).decode()


def _wav_data_uri(wav_bytes: bytes) -> str:
    return "data:audio/wav;base64," + base64.b64encode(wav_bytes).decode()


def _fallback_instructions(kokoro_voice: str | None) -> str | None:
    """Derive a natural-language voice description from a Kokoro voice id.

    Kokoro ids encode accent + gender in their first two letters (``a``/``b`` =
    American/British, ``f``/``m`` = female/male), e.g. ``bm_george``. Used only
    when a stock voice reaches this backend without an explicit `instructions`.
    """
    if not kokoro_voice or len(kokoro_voice) < 2:
        return None
    accent = {"a": "American", "b": "British"}.get(kokoro_voice[0], "")
    gender = {"f": "female", "m": "male"}.get(kokoro_voice[1])
    if gender is None:
        return None
    return f"a clear {accent} {gender} voice".replace("  ", " ").strip()


def _voice_description(voice: Voice) -> str | None:
    return voice.instructions or _fallback_instructions(voice.kokoro_voice)


class OpenRouterTTS:
    """Synthesizes speech via OpenRouter; returns 24kHz mono 16-bit WAV bytes.

    Holds a per-instance cache of seed reference clips so each speaker keeps one
    voice for the whole job. `build_deps` constructs a fresh instance per job, so
    the cache is naturally job-scoped; `release()` clears it and frees no GPU (there
    is none).
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
        self.model_id = model
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._sample_rate = sample_rate
        self._http = http or httpx.Client(timeout=120.0)
        # speaker key -> (reference data URI, reference text)
        self._seed_refs: dict[str, tuple[str, str]] = {}

    def synthesize(self, text: str, voice: Voice) -> bytes:
        body: dict = {"model": self._model, "input": text, "response_format": "mp3"}
        reference = self._reference_for(voice)
        if reference is not None:
            data_uri, ref_text = reference
            refs: list[dict] = [{"type": "input_audio", "input_audio": {"data": data_uri}}]
            if ref_text:
                refs.append({"type": "text", "text": ref_text})
            body["input_references"] = refs
        return self._request_audio(body, label=voice.name)

    def _reference_for(self, voice: Voice) -> tuple[str, str] | None:
        """Resolve a voice to a (reference data URI, reference text), or None.

        A configured clip is used directly. A described voice is seeded once and
        reused so the speaker stays consistent. A bare voice returns None (the
        model's default voice).
        """
        if voice.ref_audio_path is not None:
            return (_encode_reference(Path(voice.ref_audio_path)), voice.ref_text or "")

        description = _voice_description(voice)
        if not description:
            return None

        key = voice.name or description
        if key not in self._seed_refs:
            self._seed_refs[key] = self._make_seed(description)
        return self._seed_refs[key]

    def _make_seed(self, description: str) -> tuple[str, str]:
        """Generate one clip from a natural-language description, to clone later."""
        wav = self._request_audio(
            {
                "model": self._model,
                "input": _SEED_TEXT,
                "response_format": "mp3",
                "instructions": description,
            },
            label=f"seed:{description}",
        )
        return (_wav_data_uri(wav), _SEED_TEXT)

    def _request_audio(self, body: dict, label: str) -> bytes:
        resp = self._http.post(
            f"{self._base_url}/audio/speech",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=body,
        )
        content_type = resp.headers.get("content-type", "")
        if resp.status_code != 200 or content_type.startswith("application/json"):
            detail = resp.text[:500]
            raise OpenRouterTTSError(
                f"OpenRouter TTS failed for voice {label!r} "
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
        """Drop cached seed clips; no GPU model to free."""
        self._seed_refs.clear()
