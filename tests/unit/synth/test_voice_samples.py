from podcast_compactor.ports.tts import FakeTTS
from podcast_compactor.storage.filesystem import FilesystemStorage
from podcast_compactor.synth.voice_samples import (
    SAMPLE_LINE,
    ensure_voice_sample,
    sample_storage_key,
)


def test_ensure_voice_sample_synthesizes_and_caches(tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    tts = FakeTTS()
    wav = ensure_voice_sample("af_heart", storage, tts)
    assert wav[:4] == b"RIFF"
    assert storage.exists(sample_storage_key("af_heart"))
    # Second call hits the cache — FakeTTS has no call counter, so identity of
    # the stored bytes is the contract.
    assert ensure_voice_sample("af_heart", storage, tts) == wav


def test_ensure_voice_sample_rejects_unknown_voice(tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    try:
        ensure_voice_sample("not_a_voice", storage, FakeTTS())
    except ValueError as exc:
        assert "unknown stock voice" in str(exc)
    else:
        raise AssertionError("expected unknown stock voice to raise")


def test_sample_line_is_short_preview_copy():
    lowered = SAMPLE_LINE.lower()
    assert "hi" in lowered
    assert "preview" in lowered
