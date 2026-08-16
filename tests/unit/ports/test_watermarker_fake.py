import io
import wave

from podcast_compactor.ports.tts import FakeTTS, Voice
from podcast_compactor.ports.watermarker import FakeWatermarker, Watermarker


def test_fake_watermarker_returns_valid_wav_and_records_call():
    wav = FakeTTS().synthesize("hello there world", Voice(name="n"))
    marker = FakeWatermarker()

    out = marker.embed(wav)

    assert marker.calls == 1
    with wave.open(io.BytesIO(out), "rb") as w:
        assert w.getnframes() > 0


def test_fake_watermarker_satisfies_protocol():
    assert isinstance(FakeWatermarker(), Watermarker)
