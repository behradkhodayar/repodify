"""Download episode audio into storage."""

from __future__ import annotations

import httpx

from podcast_compactor.models.domain import Episode
from podcast_compactor.storage.base import Storage


class DownloadError(Exception):
    """Raised when an episode's audio cannot be fetched."""


def audio_key(job_id: str, episode: Episode) -> str:
    """Storage key for an episode's downloaded audio."""
    return f"{job_id}/audio/{episode.order_index}.mp3"


def download_episode(
    episode: Episode,
    storage: Storage,
    http: httpx.Client,
    job_id: str,
) -> str:
    """Stream `episode.audio_url` into `storage`; return the storage URI.

    Raises `DownloadError` on any non-200 response.
    """
    key = audio_key(job_id, episode)
    buffer = bytearray()
    with http.stream("GET", episode.audio_url, follow_redirects=True) as resp:
        if resp.status_code != 200:
            raise DownloadError(
                f"GET {episode.audio_url} returned {resp.status_code}"
            )
        for chunk in resp.iter_bytes():
            buffer.extend(chunk)
    return storage.put_bytes(key, bytes(buffer))
