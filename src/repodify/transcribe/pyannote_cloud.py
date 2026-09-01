"""pyannoteAI hosted diarizer (real backend; needs PYANNOTEAI_API_KEY).

Uploads the local file to pyannoteAI media storage, submits a diarize job, and
polls until it succeeds. Embeddings are empty — cross-episode clustering then
falls back to per-episode labels.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import httpx

from repodify.ports.diarizer import DiarizationResult, SpeakerTurn

_API = "https://api.pyannote.ai/v1"


class PyannoteCloudDiarizer:
    def __init__(
        self,
        api_key: str,
        model: str = "community-1",
        http: httpx.Client | None = None,
        poll_interval: float = 2.0,
        timeout: float = 600.0,
    ) -> None:
        if not api_key:
            raise ValueError("PyannoteCloudDiarizer requires a pyannoteAI API key")
        self.model_id = model
        self._api_key = api_key
        self._model = model
        self._http = http or httpx.Client(timeout=60.0)
        self._poll_interval = poll_interval
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def diarize(self, audio_path: Path) -> DiarizationResult:
        path = Path(audio_path)
        object_key = f"repodify/{uuid.uuid4().hex}/{path.name}"
        media_url = f"media://{object_key}"
        created = self._http.post(
            f"{_API}/media/input",
            headers=self._headers(),
            json={"url": media_url},
        )
        created.raise_for_status()
        put_url = created.json()["url"]
        put = self._http.put(put_url, content=path.read_bytes())
        put.raise_for_status()

        job = self._http.post(
            f"{_API}/diarize",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"url": media_url, "model": self._model},
        )
        job.raise_for_status()
        job_id = job.json()["jobId"]

        deadline = time.monotonic() + self._timeout
        while True:
            got = self._http.get(f"{_API}/jobs/{job_id}", headers=self._headers())
            got.raise_for_status()
            body = got.json()
            status = body.get("status")
            if status == "succeeded":
                turns = [
                    SpeakerTurn(
                        start=float(seg["start"]),
                        end=float(seg["end"]),
                        speaker=str(seg["speaker"]),
                    )
                    for seg in (body.get("output") or {}).get("diarization") or []
                ]
                return DiarizationResult(turns=turns, embeddings={})
            if status in {"failed", "canceled"}:
                raise RuntimeError(f"pyannoteAI job {job_id} {status}: {body.get('output')}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"pyannoteAI job {job_id} timed out")
            time.sleep(self._poll_interval)

    def release(self) -> None:
        """No-op: hosted diarization holds no GPU model."""
