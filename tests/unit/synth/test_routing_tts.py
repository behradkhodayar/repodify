import io
import wave

import pytest

from podcast_compactor.ports.tts import SAMPLE_RATE, TTS, Voice
from podcast_compactor.synth.routing_tts import RoutingTTS


def _wav(seconds=0.1, rate=SAMPLE_RATE, channels=1, width=2):
    n = int(seconds * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b"\x00" * width * channels * n)
    return buf.getvalue()


class Spy:
    def __init__(self, out):
        self._out = out
        self.calls: list[Voice] = []
        self.released = 0

    def synthesize(self, text, voice):
        self.calls.append(voice)
        return self._out

    def release(self):
        self.released += 1


def test_routes_stock_voice_to_kokoro_and_reference_to_f5():
    f5, kokoro = Spy(_wav()), Spy(_wav())
    router = RoutingTTS(f5, kokoro)

    router.synthesize("hi", Voice(name="s", kokoro_voice="af_heart"))
    router.synthesize("hi", Voice(name="c", ref_audio_path=None, ref_text="ref"))

    assert [v.name for v in kokoro.calls] == ["s"]
    assert [v.name for v in f5.calls] == ["c"]


def test_release_frees_both_backends():
    f5, kokoro = Spy(_wav()), Spy(_wav())
    RoutingTTS(f5, kokoro).release()
    assert f5.released == 1 and kokoro.released == 1


def test_rejects_backend_output_with_wrong_format():
    bad = Spy(_wav(rate=16000))  # not 24kHz
    router = RoutingTTS(bad, bad)
    with pytest.raises(ValueError, match="expected"):
        router.synthesize("hi", Voice(name="c", ref_text="ref"))


def test_satisfies_tts_protocol():
    assert isinstance(RoutingTTS(Spy(_wav()), Spy(_wav())), TTS)
