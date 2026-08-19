import io
import wave

from podcast_compactor.ports.tts import SAMPLE_RATE, TTS, FakeTTS, Voice


def test_fake_tts_returns_valid_wav():
    fake = FakeTTS()
    data = fake.synthesize("one two three", Voice(name="narrator"))
    with wave.open(io.BytesIO(data), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == SAMPLE_RATE
        assert w.getnframes() > 0


def test_fake_tts_duration_tracks_word_count():
    fake = FakeTTS()
    short = fake.synthesize("one", Voice(name="n"))
    long = fake.synthesize("one two three four five six", Voice(name="n"))
    with wave.open(io.BytesIO(short), "rb") as s, wave.open(io.BytesIO(long), "rb") as ln:
        assert ln.getnframes() > s.getnframes()


def test_fake_satisfies_protocol():
    assert isinstance(FakeTTS(), TTS)


def test_fake_release_is_noop_and_keeps_working():
    fake = FakeTTS()
    assert fake.release() is None
    # Releasing a fake frees nothing; it stays usable afterwards.
    data = fake.synthesize("one two three", Voice(name="narrator"))
    assert len(data) > 0
