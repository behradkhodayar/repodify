"""F5-TTS must not touch VRAM until first use, and `release()` must drop the
model so it reloads lazily afterwards."""

import sys
import types
from pathlib import Path

from repodify.ports.tts import Voice
from repodify.synth.f5_tts import F5TTS


def _install_fake_f5(monkeypatch, loads):
    import numpy as np

    class FakeApi:
        def __init__(self, *args, **kwargs):
            loads.append((args, kwargs))

        def infer(self, ref_file, ref_text, gen_text):
            return (np.zeros(8, dtype="float32"), 24000, None)

    fake_api_mod = types.ModuleType("f5_tts.api")
    fake_api_mod.F5TTS = FakeApi
    fake_pkg = types.ModuleType("f5_tts")
    fake_pkg.api = fake_api_mod
    monkeypatch.setitem(sys.modules, "f5_tts", fake_pkg)
    monkeypatch.setitem(sys.modules, "f5_tts.api", fake_api_mod)


def _voice() -> Voice:
    return Voice(name="narrator", ref_audio_path=Path("/ref.wav"), ref_text="hello")


def test_model_not_loaded_until_first_synthesize(monkeypatch):
    loads: list = []
    _install_fake_f5(monkeypatch, loads)

    tts = F5TTS()
    assert loads == []  # construction is cheap — no VRAM yet

    tts.synthesize("one two three", _voice())
    assert len(loads) == 1  # loaded on first use

    tts.synthesize("four five", _voice())
    assert len(loads) == 1  # reused, not reloaded


def test_release_frees_model_and_next_use_reloads(monkeypatch):
    loads: list = []
    _install_fake_f5(monkeypatch, loads)

    tts = F5TTS()
    tts.synthesize("hi", _voice())
    assert len(loads) == 1

    tts.release()
    tts.release()  # idempotent when nothing is loaded

    tts.synthesize("again", _voice())
    assert len(loads) == 2  # reloaded after release
