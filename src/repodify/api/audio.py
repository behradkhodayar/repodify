"""Serve a job's rendered audio, with HTTP Range support via FileResponse."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import FileResponse

from repodify.storage.base import Storage

_MEDIA_TYPES = {"mp3": "audio/mpeg", "wav": "audio/wav"}


def audio_response(storage: Storage, job_id: str, fmt: str) -> FileResponse:
    media_type = _MEDIA_TYPES.get(fmt)
    if media_type is None:
        raise HTTPException(status_code=422, detail="format must be 'mp3' or 'wav'")
    key = f"{job_id}/output/digest.{fmt}"
    if not storage.exists(key):
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(
        storage.local_path(key), media_type=media_type, filename=f"digest.{fmt}"
    )
