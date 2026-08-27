from pathlib import Path

from podcast_compactor.ports.diarizer import Diarizer, FakeDiarizer, SpeakerTurn


def test_fake_diarizer_returns_multi_speaker_turns():
    diarizer = FakeDiarizer()

    turns = diarizer.diarize(Path("ep0.mp3"))

    assert len(turns) >= 2
    assert {t.speaker for t in turns} == {"SPEAKER_00", "SPEAKER_01"}
    # Turns are ordered and non-negative in duration.
    for t in turns:
        assert t.end > t.start
    assert diarizer.calls == [Path("ep0.mp3")]


def test_fake_diarizer_honors_canned_turns():
    canned = [SpeakerTurn(start=0.0, end=1.0, speaker="A")]
    diarizer = FakeDiarizer(canned=canned)

    assert diarizer.diarize(Path("x.mp3")) == canned


def test_fake_diarizer_satisfies_protocol():
    assert isinstance(FakeDiarizer(), Diarizer)
