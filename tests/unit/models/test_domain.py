import pytest

from podcast_compactor.models.domain import (
    JobOptions,
    MAX_PROMPT_CHARS,
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


def test_speaker_labeled_text_groups_consecutive_speakers():
    t = Transcript(
        episode_guid="ep-1",
        segments=[
            TranscriptSegment(start=0.0, end=1.0, text="hi there", speaker="SPEAKER_00"),
            TranscriptSegment(start=1.0, end=2.0, text="and more", speaker="SPEAKER_00"),
            TranscriptSegment(start=2.0, end=3.0, text="my turn", speaker="SPEAKER_01"),
        ],
    )
    assert t.speaker_labeled_text == "SPEAKER_00: hi there and more\nSPEAKER_01: my turn"


def test_speaker_labeled_text_falls_back_to_plain_when_unlabeled():
    t = Transcript(
        episode_guid="ep-1",
        segments=[TranscriptSegment(start=0.0, end=1.0, text="no speaker here")],
    )
    assert t.speaker_labeled_text == "no speaker here"


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


def test_speaker_labeled_text_timestamped_prefixes_turns():
    t = Transcript(
        episode_guid="ep-1",
        segments=[
            TranscriptSegment(start=0.0, end=1.0, text="hi there", speaker="SPEAKER_00"),
            TranscriptSegment(start=1.0, end=2.0, text="and more", speaker="SPEAKER_00"),
            TranscriptSegment(start=260.0, end=262.0, text="my turn", speaker="SPEAKER_01"),
        ],
    )
    assert t.speaker_labeled_text_timestamped() == (
        "[00:00] SPEAKER_00: hi there and more\n[04:20] SPEAKER_01: my turn"
    )


def test_speaker_labeled_text_timestamped_minutes_over_59():
    t = Transcript(
        episode_guid="ep-1",
        segments=[TranscriptSegment(start=4384.0, end=4386.0, text="late", speaker="SPEAKER_00")],
    )
    assert t.speaker_labeled_text_timestamped() == "[73:04] SPEAKER_00: late"


def test_speaker_labeled_text_timestamped_unlabeled_is_per_segment():
    t = Transcript(
        episode_guid="ep-1",
        segments=[
            TranscriptSegment(start=0.0, end=1.0, text="first"),
            TranscriptSegment(start=90.0, end=92.0, text="second"),
        ],
    )
    assert t.speaker_labeled_text_timestamped() == "[00:00] first\n[01:30] second"


def test_enums_have_expected_members():
    assert StageName.TRANSCRIBE.value == "transcribe"
    assert StageName.DIARIZE.value == "diarize"
    assert JobStatus.COMPLETED.value == "completed"
    assert StageState.SKIPPED.value == "skipped"
    assert len(list(StageName)) == 10


def test_job_options_defaults_have_no_prompts():
    opts = JobOptions(episode_ids=["ep-1"])
    assert opts.custom_prompt is None
    assert opts.episode_prompts == {}


def test_job_options_episode_prompts_are_stripped_and_emptied():
    opts = JobOptions(
        episode_ids=["ep-1"],
        episode_prompts={"ep-1": "  keep the interview  ", "ep-2": "   "},
    )
    assert opts.episode_prompts == {"ep-1": "keep the interview"}


def test_job_options_rejects_overlong_custom_prompt():
    with pytest.raises(ValueError):
        JobOptions(episode_ids=["ep-1"], custom_prompt="x" * (MAX_PROMPT_CHARS + 1))


def test_job_options_rejects_overlong_episode_prompt():
    with pytest.raises(ValueError):
        JobOptions(episode_ids=["ep-1"], episode_prompts={"ep-1": "x" * (MAX_PROMPT_CHARS + 1)})
