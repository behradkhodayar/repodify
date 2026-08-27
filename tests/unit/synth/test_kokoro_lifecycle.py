"""Kokoro must not load until first use, `release()` must drop the pipeline so it
reloads lazily, and output must be valid 24kHz mono WAV."""

import io
import sys
import types
import wave

from podcast_compactor.ports.tts import SAMPLE_RATE, Voice
from podcast_compactor.synth.kokoro import KokoroTTS


class _Chunk:
    """Mimics a Kokoro audio chunk exposing `.tolist()` (like a tensor/ndarray)."""

    def __init__(self, samples):
        self._samples = samples

    def tolist(self):
        return self._samples


def _install_fake_kokoro(monkeypatch, loads):
    class FakeKPipeline:
        def __init__(self, *args, **kwargs):
            loads.append((args, kwargs))

        def __call__(self, text, voice):
            # Two chunks: one tensor-like (.tolist), one plain list.
            return [("g", "p", _Chunk([0.0, 0.5, -0.5])), ("g", "p", [0.25, -0.25])]

    fake_pkg = types.ModuleType("kokoro")
    fake_pkg.KPipeline = FakeKPipeline
    monkeypatch.setitem(sys.modules, "kokoro", fake_pkg)


def _voice() -> Voice:
    return Voice(name="stock", kokoro_voice="af_heart")


def test_pipeline_not_loaded_until_first_synthesize(monkeypatch):
    loads: list = []
    _install_fake_kokoro(monkeypatch, loads)

    tts = KokoroTTS()
    assert loads == []

    data = tts.synthesize("hello there", _voice())
    assert len(loads) == 1

    # Output is a valid, non-empty 24kHz mono 16-bit WAV.
    with wave.open(io.BytesIO(data), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, SAMPLE_RATE)
        assert w.getnframes() == 5  # 3 + 2 samples across the two chunks

    tts.synthesize("again", _voice())
    assert len(loads) == 1  # reused, not reloaded


def test_release_reloads_on_next_use(monkeypatch):
    loads: list = []
    _install_fake_kokoro(monkeypatch, loads)

    tts = KokoroTTS()
    tts.synthesize("hi", _voice())
    tts.release()
    tts.release()  # idempotent
    tts.synthesize("again", _voice())
    assert len(loads) == 2


def test_requires_kokoro_voice(monkeypatch):
    _install_fake_kokoro(monkeypatch, [])
    tts = KokoroTTS()
    try:
        tts.synthesize("hi", Voice(name="c", ref_text="ref"))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "kokoro_voice" in str(exc)
