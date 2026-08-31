from repodify.ports.tts import FakeTTS
from repodify.storage.filesystem import FilesystemStorage
from repodify.synth.stock_voices import bundled_sample_path
from repodify.synth.voice_samples import (
    SAMPLE_LINE,
    ensure_voice_sample,
    sample_storage_key,
)


class _BoomTTS:
    def synthesize(self, text, voice):
        raise AssertionError("bundled preview should not hit TTS")

    def release(self):
        pass


def test_ensure_voice_sample_prefers_bundled_preview(tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    wav = ensure_voice_sample("af_heart", storage, _BoomTTS())
    assert wav[:4] == b"RIFF"
    assert wav == bundled_sample_path("af_heart").read_bytes()
    assert not storage.exists(sample_storage_key("af_heart"))


def test_ensure_voice_sample_synthesizes_when_bundle_missing(tmp_path, monkeypatch):
    from repodify.synth import voice_samples

    missing = tmp_path / "missing.wav"
    monkeypatch.setattr(voice_samples, "bundled_sample_path", lambda name: missing)
    storage = FilesystemStorage(tmp_path / "data")
    wav = ensure_voice_sample("af_heart", storage, FakeTTS())
    assert wav[:4] == b"RIFF"
    assert storage.exists(sample_storage_key("af_heart"))
    assert ensure_voice_sample("af_heart", storage, FakeTTS()) == wav


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
    assert "hello" in lowered
    assert "preview" in lowered
