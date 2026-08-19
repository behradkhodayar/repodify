"""faster-whisper must not touch VRAM until first use, and `release()` must
drop the model so it reloads lazily afterwards."""

import sys
import types
from pathlib import Path

from podcast_compactor.transcribe.faster_whisper import FasterWhisperTranscriber


def _install_fake_whisper(monkeypatch, loads):
    class FakeWhisperModel:
        def __init__(self, *args, **kwargs):
            loads.append((args, kwargs))

        def transcribe(self, audio, language="en", vad_filter=True):
            return ([], None)  # (segments, info)

    fake_mod = types.ModuleType("faster_whisper")
    fake_mod.WhisperModel = FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)


def test_model_not_loaded_until_first_transcribe(monkeypatch):
    loads: list = []
    _install_fake_whisper(monkeypatch, loads)

    t = FasterWhisperTranscriber("small")
    assert loads == []  # construction is cheap — no VRAM yet

    t.transcribe(Path("/a.mp3"))
    assert len(loads) == 1  # loaded on first use
    assert loads[0][0][0] == "small"  # the requested model size

    t.transcribe(Path("/b.mp3"))
    assert len(loads) == 1  # reused, not reloaded


def test_release_frees_model_and_next_use_reloads(monkeypatch):
    loads: list = []
    _install_fake_whisper(monkeypatch, loads)

    t = FasterWhisperTranscriber("small")
    t.transcribe(Path("/a.mp3"))
    assert len(loads) == 1

    t.release()
    t.release()  # idempotent when nothing is loaded

    t.transcribe(Path("/c.mp3"))
    assert len(loads) == 2  # reloaded after release
