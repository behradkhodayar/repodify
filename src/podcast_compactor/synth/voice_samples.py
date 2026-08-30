"""On-disk previews of catalog voices, synthesized once and then served as files.

The API plays these from Settings and the voice-review picker. Generation goes
through the injected TTS (FakeTTS in tests/fake mode, Kokoro in real mode) so
the API stays a thin cache in front of whatever backend the process was wired
with. Cache hits never touch the model.
"""

from __future__ import annotations

from podcast_compactor.ports.tts import TTS
from podcast_compactor.storage.base import Storage
from podcast_compactor.synth.stock_voices import stock_voice

SAMPLE_LINE = "Hi, this is a short preview of my voice."


def sample_storage_key(voice_id: str) -> str:
    return f"voice-samples/{voice_id}.wav"


def ensure_voice_sample(voice_id: str, storage: Storage, tts: TTS) -> bytes:
    """Return WAV bytes for ``voice_id``, synthesizing and caching if missing.

    Raises ``ValueError`` for an unknown catalog id (same as `stock_voice`).
    """
    key = sample_storage_key(voice_id)
    if storage.exists(key):
        return storage.get_bytes(key)
    wav = tts.synthesize(SAMPLE_LINE, stock_voice(voice_id))
    storage.put_bytes(key, wav)
    tts.release()
    return wav
