from podcast_compactor.models.domain import TranscriptSegment
from podcast_compactor.ports.diarizer import SpeakerTurn
from podcast_compactor.transcribe.diarization import assign_speakers, roster_from_turns


def _seg(start, end, text="x"):
    return TranscriptSegment(start=start, end=end, text=text)


def test_segment_labeled_by_max_overlap():
    segments = [_seg(0.0, 4.0), _seg(6.0, 9.0)]
    turns = [
        SpeakerTurn(start=0.0, end=5.0, speaker="SPEAKER_00"),
        SpeakerTurn(start=5.0, end=10.0, speaker="SPEAKER_01"),
    ]

    labeled = assign_speakers(segments, turns)

    assert [s.speaker for s in labeled] == ["SPEAKER_00", "SPEAKER_01"]


def test_segment_straddling_two_turns_picks_greater_overlap():
    # 3s in SPEAKER_00 (0-3) vs 1s in SPEAKER_01 (3-4) -> SPEAKER_00 wins.
    segments = [_seg(0.0, 4.0)]
    turns = [
        SpeakerTurn(start=0.0, end=3.0, speaker="SPEAKER_00"),
        SpeakerTurn(start=3.0, end=8.0, speaker="SPEAKER_01"),
    ]

    assert assign_speakers(segments, turns)[0].speaker == "SPEAKER_00"


def test_segment_with_no_overlap_stays_unlabeled():
    segments = [_seg(100.0, 105.0)]
    turns = [SpeakerTurn(start=0.0, end=5.0, speaker="SPEAKER_00")]

    assert assign_speakers(segments, turns)[0].speaker is None


def test_no_turns_returns_segments_unchanged():
    segments = [_seg(0.0, 5.0)]

    labeled = assign_speakers(segments, [])

    assert labeled[0].speaker is None
    assert labeled[0].text == "x"


def test_original_segments_not_mutated():
    segments = [_seg(0.0, 5.0)]
    turns = [SpeakerTurn(start=0.0, end=5.0, speaker="SPEAKER_00")]

    assign_speakers(segments, turns)

    assert segments[0].speaker is None  # input untouched; a copy is returned


def test_roster_from_turns_sums_and_sorts_by_talk_time():
    turns = [
        SpeakerTurn(start=0.0, end=2.0, speaker="SPEAKER_00"),
        SpeakerTurn(start=2.0, end=10.0, speaker="SPEAKER_01"),
        SpeakerTurn(start=10.0, end=13.0, speaker="SPEAKER_00"),
    ]

    roster = roster_from_turns(turns)

    assert [s.id for s in roster] == ["SPEAKER_01", "SPEAKER_00"]  # 8s > 5s
    by_id = {s.id: s.speaking_seconds for s in roster}
    assert by_id == {"SPEAKER_01": 8.0, "SPEAKER_00": 5.0}
