"""Chatterbox Persian TTS: lazy load, 24kHz WAV, chunked generate, release()."""

from __future__ import annotations

import io
import wave

from repodify.ports.tts import SAMPLE_RATE, Voice
from repodify.synth.chatterbox_tts import ChatterboxPersianTTS, chunk_text


class _Tensor:
    """Mimics a torch tensor enough for the adapter's float conversion."""

    def __init__(self, samples: list[float]) -> None:
        self._samples = samples

    def detach(self):
        return self

    def cpu(self):
        return self

    def squeeze(self):
        return self

    def numpy(self):
        return self

    def tolist(self):
        return self._samples


class _StubModel:
    sr = SAMPLE_RATE

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def generate(self, text: str, **kwargs):
        self.calls.append((text, kwargs))
        n = max(4, min(len(text), 16))
        return _Tensor([0.1] * n)


def test_model_not_loaded_until_first_synthesize():
    loads: list = []

    def loader(**kwargs):
        loads.append(kwargs)
        return _StubModel()

    tts = ChatterboxPersianTTS(loader=loader)
    assert loads == []
    data = tts.synthesize("سلام", Voice(name="fa_neda"))
    assert len(loads) == 1
    with wave.open(io.BytesIO(data), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, SAMPLE_RATE)
        assert w.getnframes() > 0
    tts.synthesize("دوباره", Voice(name="fa_neda"))
    assert len(loads) == 1


def test_release_reloads_on_next_use():
    loads: list = []

    def loader(**kwargs):
        loads.append(kwargs)
        return _StubModel()

    tts = ChatterboxPersianTTS(loader=loader)
    tts.synthesize("سلام", Voice(name="n"))
    tts.release()
    tts.release()
    tts.synthesize("دوباره", Voice(name="n"))
    assert len(loads) == 2


def test_loader_receives_repo_and_token():
    seen: dict = {}

    def loader(**kwargs):
        seen.update(kwargs)
        return _StubModel()

    tts = ChatterboxPersianTTS(
        repo_id="Thomcles/Chatterbox-TTS-Persian-Farsi",
        hf_token="hf_test",
        loader=loader,
    )
    tts.synthesize("سلام", Voice(name="n"))
    assert seen["repo_id"] == "Thomcles/Chatterbox-TTS-Persian-Farsi"
    assert seen["hf_token"] == "hf_test"


def test_chunk_text_splits_long_persian_on_sentences():
    text = "جملهٔ اول. " + ("کلمه " * 80) + "جملهٔ آخر؟"
    chunks = chunk_text(text, max_chars=40)
    assert len(chunks) > 1
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")
    assert all(len(c) <= 80 for c in chunks)  # sentence may slightly exceed


def test_synthesize_chunks_long_text():
    model = _StubModel()

    def loader(**kwargs):
        return model

    tts = ChatterboxPersianTTS(loader=loader)
    long = "سلام. " * 80
    tts.synthesize(long, Voice(name="n"))
    assert len(model.calls) > 1


def test_uses_reference_clip_when_present(tmp_path):
    model = _StubModel()
    clip = tmp_path / "ref.wav"
    clip.write_bytes(b"fake")

    def loader(**kwargs):
        return model

    tts = ChatterboxPersianTTS(loader=loader)
    tts.synthesize("سلام", Voice(name="n", ref_audio_path=clip))
    assert model.calls[0][1].get("audio_prompt_path") == str(clip)
