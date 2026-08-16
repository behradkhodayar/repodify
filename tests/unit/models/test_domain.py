import pytest

from podcast_compactor.models.domain import (
    Script,
    ScriptSegment,
    ShowNotes,
    Transcript,
    TranscriptSegment,
)
from podcast_compactor.models.enums import JobStatus, StageName, StageState


def test_transcript_text_joins_segments():
    t = Transcript(
        episode_guid="ep-1",
        segments=[
            TranscriptSegment(start=0.0, end=1.0, text="hello "),
            TranscriptSegment(start=1.0, end=2.0, text=" world"),
            TranscriptSegment(start=2.0, end=3.0, text="  "),
        ],
    )
    assert t.text == "hello world"


def test_script_word_count_and_minutes():
    script = Script(
        segments=[
            ScriptSegment(speaker="narrator", text="one two three"),
            ScriptSegment(speaker="narrator", text="four five"),
        ]
    )
    assert script.word_count == 5
    assert script.estimated_minutes(130) == pytest.approx(5 / 130)


def test_estimated_minutes_rejects_nonpositive_wpm():
    with pytest.raises(ValueError):
        Script(segments=[]).estimated_minutes(0)


def test_show_notes_synthetic_fields():
    plain = ShowNotes(summary="s")
    assert plain.synthetic is False
    assert plain.disclaimer is None

    labeled = ShowNotes(summary="s", synthetic=True, disclaimer="AI voices")
    assert labeled.synthetic is True
    assert labeled.disclaimer == "AI voices"


def test_enums_have_expected_members():
    assert StageName.TRANSCRIBE.value == "transcribe"
    assert JobStatus.COMPLETED.value == "completed"
    assert StageState.SKIPPED.value == "skipped"
    assert len(list(StageName)) == 9
