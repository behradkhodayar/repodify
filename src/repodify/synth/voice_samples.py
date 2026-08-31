"""On-disk previews of catalog voices.

Bundled WAVs in ``assets/voice-samples/`` are the source of truth — they play
in Settings/review even in fake mode, and hosted TTS clones them so gender is
audible. If a bundle file is missing, we synthesize once through the injected
TTS and cache under the data dir.
"""

from __future__ import annotations

from pathlib import Path

from repodify.ports.tts import TTS
from repodify.storage.base import Storage
from repodify.synth.stock_voices import (
    SAMPLE_LINE,
    bundled_sample_path,
    stock_voice,
)

__all__ = ["SAMPLE_LINE", "ensure_voice_sample", "resolve_sample_path", "sample_storage_key"]


def sample_storage_key(voice_id: str) -> str:
    return f"voice-samples/{voice_id}.wav"


def resolve_sample_path(voice_id: str, storage: Storage) -> Path | None:
    """Filesystem path of an existing sample, preferring the bundled preview."""
    bundled = bundled_sample_path(voice_id)
    if bundled.is_file():
        return bundled
    key = sample_storage_key(voice_id)
    if storage.exists(key):
        return storage.local_path(key)
    return None


def ensure_voice_sample(voice_id: str, storage: Storage, tts: TTS) -> bytes:
    """Return WAV bytes for ``voice_id``, synthesizing and caching if missing.

    Raises ``ValueError`` for an unknown catalog id (same as `stock_voice`).
    """
    existing = resolve_sample_path(voice_id, storage)
    if existing is not None:
        return existing.read_bytes()
    wav = tts.synthesize(SAMPLE_LINE, stock_voice(voice_id))
    storage.put_bytes(sample_storage_key(voice_id), wav)
    tts.release()
    return wav
