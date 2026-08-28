from pathlib import Path

from podcast_compactor.ports.diarizer import Diarizer, FakeDiarizer, SpeakerTurn


def test_fake_diarizer_returns_multi_speaker_turns():
    diarizer = FakeDiarizer()

    result = diarizer.diarize(Path("ep0.mp3"))
    turns = result.turns

    assert len(turns) >= 2
    assert {t.speaker for t in turns} == {"SPEAKER_00", "SPEAKER_01"}
    # Turns are ordered and non-negative in duration.
    for t in turns:
        assert t.end > t.start
    assert diarizer.calls == [Path("ep0.mp3")]
    # An embedding is produced per label, so cross-episode clustering is testable.
    assert set(result.embeddings) == {"SPEAKER_00", "SPEAKER_01"}


def test_fake_diarizer_honors_canned_turns():
    canned = [SpeakerTurn(start=0.0, end=1.0, speaker="A")]
    diarizer = FakeDiarizer(canned=canned)

    result = diarizer.diarize(Path("x.mp3"))
    assert result.turns == canned
    # Same label -> same embedding across calls (stable identity for clustering).
    assert diarizer.diarize(Path("y.mp3")).embeddings["A"] == result.embeddings["A"]


def test_fake_diarizer_satisfies_protocol():
    assert isinstance(FakeDiarizer(), Diarizer)
