"""Pocket Persian TTS: lazy load, 24kHz WAV, chunked generate, release()."""

from __future__ import annotations

import io
import wave
from pathlib import Path

from repodify.ports.tts import SAMPLE_RATE, Voice
from repodify.synth.pocket_tts import PocketPersianTTS, chunk_text


class _StubModel:
    def __init__(self, *, long_first: bool = False) -> None:
        self.prompts: list[str] = []
        self.calls: list[tuple[object, str, dict]] = []
        self._long_first = long_first
        self._n = 0

    def get_state_for_audio_prompt(self, path: str) -> dict:
        self.prompts.append(path)
        return {"prompt": path}

    def generate_audio(self, state: object, text: str, **kwargs):
        self.calls.append((state, text, kwargs))
        self._n += 1
        if self._long_first and self._n == 1:
            return [0.1] * (SAMPLE_RATE * 8)
        n = max(4, min(len(text), 16))
        return [0.1] * n


def test_model_not_loaded_until_first_synthesize(tmp_path: Path):
    loads: list = []
    clip = tmp_path / "neda.wav"
    clip.write_bytes(b"fake")

    def loader(**kwargs):
        loads.append(kwargs)
        return _StubModel()

    tts = PocketPersianTTS(loader=loader)
    assert loads == []
    data = tts.synthesize("سلام", Voice(name="fa_neda", ref_audio_path=clip))
    assert len(loads) == 1
    with wave.open(io.BytesIO(data), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, SAMPLE_RATE)
        assert w.getnframes() > 0
    tts.synthesize("دوباره", Voice(name="fa_neda", ref_audio_path=clip))
    assert len(loads) == 1


def test_release_reloads_on_next_use(tmp_path: Path):
    loads: list = []
    clip = tmp_path / "neda.wav"
    clip.write_bytes(b"fake")

    def loader(**kwargs):
        loads.append(kwargs)
        return _StubModel()

    tts = PocketPersianTTS(loader=loader)
    tts.synthesize("سلام", Voice(name="n", ref_audio_path=clip))
    tts.release()
    tts.release()
    tts.synthesize("دوباره", Voice(name="n", ref_audio_path=clip))
    assert len(loads) == 2


def test_loader_receives_repo_id():
    seen: dict = {}

    def loader(**kwargs):
        seen.update(kwargs)
        return _StubModel()

    tts = PocketPersianTTS(repo_id="mehdi-hf/pocket-tts-farsi", loader=loader)
    clip = Path("/tmp/does-not-matter-until-synth")
    # synthesize will fail without a real clip path used by stub only as string
    tts.synthesize("سلام", Voice(name="n", ref_audio_path=clip))
    assert seen["repo_id"] == "mehdi-hf/pocket-tts-farsi"


def test_chunk_text_splits_long_persian_on_sentences():
    text = "جملهٔ اول. " + ("کلمه " * 40) + "جملهٔ آخر؟"
    chunks = chunk_text(text, max_chars=24)
    assert len(chunks) > 1
    assert all(len(c) <= 48 for c in chunks)


def test_synthesize_chunks_long_text(tmp_path: Path):
    model = _StubModel()
    clip = tmp_path / "neda.wav"
    clip.write_bytes(b"fake")
    tts = PocketPersianTTS(loader=lambda **k: model)
    tts.synthesize("سلام. " * 40, Voice(name="n", ref_audio_path=clip))
    assert len(model.calls) > 1


def test_uses_reference_clip(tmp_path: Path):
    model = _StubModel()
    clip = tmp_path / "ref.wav"
    clip.write_bytes(b"fake")
    tts = PocketPersianTTS(loader=lambda **k: model)
    tts.synthesize("سلام", Voice(name="n", ref_audio_path=clip))
    assert model.prompts == [str(clip)]
    assert model.calls[0][2].get("frames_after_eos") == 0


def test_requires_reference_clip():
    tts = PocketPersianTTS(loader=lambda **k: _StubModel())
    try:
        tts.synthesize("سلام", Voice(name="n"))
    except ValueError as exc:
        assert "ref_audio_path" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_retries_runaway_generation(tmp_path: Path):
    model = _StubModel(long_first=True)
    clip = tmp_path / "neda.wav"
    clip.write_bytes(b"fake")
    tts = PocketPersianTTS(loader=lambda **k: model)
    tts.synthesize("سلام", Voice(name="n", ref_audio_path=clip))
    assert len(model.calls) >= 2
