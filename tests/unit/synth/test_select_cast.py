from podcast_compactor.models.domain import Speaker, Transcript
from podcast_compactor.synth.voice_assignment import select_cast


def _t(*ids):
    return Transcript(
        episode_guid="e", speakers=[Speaker(id=i, speaking_seconds=s) for i, s in ids]
    )


def test_select_cast_keeps_roster_order():
    cast = select_cast(_t(("SPEAKER_00", 30.0), ("SPEAKER_01", 20.0)))
    assert [s.id for s in cast] == ["SPEAKER_00", "SPEAKER_01"]


def test_select_cast_caps_size():
    roster = [(f"S{i}", float(50 - i)) for i in range(8)]
    cast = select_cast(_t(*roster), max_cast=3)
    assert [s.id for s in cast] == ["S0", "S1", "S2"]
