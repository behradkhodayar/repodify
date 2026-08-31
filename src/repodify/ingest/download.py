"""Download episode audio into storage."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from repodify.models.domain import Episode
from repodify.storage.base import Storage

ProgressFn = Callable[[int, int | None], None]


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
    on_progress: ProgressFn | None = None,
) -> str:
    """Stream `episode.audio_url` into `storage`; return the storage URI.

    Raises `DownloadError` on any non-200 response. `on_progress`, when set, is
    called after each chunk with `(bytes_done, bytes_total)`; `bytes_total` is
    the Content-Length when present and parseable, otherwise `None`.
    """
    key = audio_key(job_id, episode)
    buffer = bytearray()
    with http.stream("GET", episode.audio_url, follow_redirects=True) as resp:
        if resp.status_code != 200:
            raise DownloadError(
                f"GET {episode.audio_url} returned {resp.status_code}"
            )
        raw = resp.headers.get("Content-Length")
        try:
            total: int | None = int(raw) if raw else None
        except ValueError:
            total = None
        done = 0
        for chunk in resp.iter_bytes():
            buffer.extend(chunk)
            done += len(chunk)
            if on_progress is not None:
                on_progress(done, total)
    return storage.put_bytes(key, bytes(buffer))
