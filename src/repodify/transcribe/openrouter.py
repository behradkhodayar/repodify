"""OpenRouter speech-to-text adapter (real backend; needs an API key).

Calls ``POST /audio/transcriptions`` with the same OpenRouter key used for LLM
and TTS. Prefers verbose JSON with segment timestamps; falls back to one
segment covering the whole file when the provider only returns ``text``.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from repodify.models.domain import Transcript, TranscriptSegment


class OpenRouterTranscriber:
    def __init__(
        self,
        api_key: str,
        model: str = "openai/whisper-large-v3",
        base_url: str = "https://openrouter.ai/api/v1",
        http: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouterTranscriber requires an OpenRouter API key")
        self.model_id = model
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=120.0)

    def transcribe(self, audio_path: Path, language: str = "en") -> Transcript:
        path = Path(audio_path)
        with path.open("rb") as fh:
            resp = self._http.post(
                f"{self._base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                files={"file": (path.name, fh, "application/octet-stream")},
                data={
                    "model": self._model,
                    "language": language,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
            )
        resp.raise_for_status()
        body = resp.json()
        raw_segments = body.get("segments") or []
        if raw_segments:
            segments = [
                TranscriptSegment(
                    start=float(s.get("start") or 0.0),
                    end=float(s.get("end") or 0.0),
                    text=str(s.get("text") or "").strip(),
                )
                for s in raw_segments
                if str(s.get("text") or "").strip()
            ]
        else:
            text = str(body.get("text") or "").strip()
            segments = [TranscriptSegment(start=0.0, end=0.0, text=text)] if text else []
        return Transcript(episode_guid="", segments=segments)

    def release(self) -> None:
        """No-op: hosted STT holds no GPU model."""
