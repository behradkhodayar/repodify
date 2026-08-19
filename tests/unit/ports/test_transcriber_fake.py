from pathlib import Path

from podcast_compactor.models.domain import Transcript, TranscriptSegment
from podcast_compactor.ports.transcriber import FakeTranscriber, Transcriber


def _transcript() -> Transcript:
    return Transcript(
        episode_guid="ep-1",
        segments=[TranscriptSegment(start=0.0, end=1.0, text="hello world")],
    )


def test_fake_returns_single_canned_transcript():
    fake = FakeTranscriber(_transcript())
    out = fake.transcribe(Path("/audio/0.mp3"))
    assert out.text == "hello world"
    assert fake.calls == [Path("/audio/0.mp3")]


def test_fake_returns_keyed_transcript():
    fake = FakeTranscriber({"0.mp3": _transcript()})
    out = fake.transcribe(Path("/audio/0.mp3"))
    assert out.episode_guid == "ep-1"


def test_fake_satisfies_protocol():
    assert isinstance(FakeTranscriber(_transcript()), Transcriber)


def test_fake_release_is_noop_and_keeps_working():
    fake = FakeTranscriber(_transcript())
    assert fake.release() is None
    # Releasing a fake frees nothing; it stays usable afterwards.
    out = fake.transcribe(Path("/audio/0.mp3"))
    assert out.text == "hello world"
