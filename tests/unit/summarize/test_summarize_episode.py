from podcast_compactor.models.domain import EpisodeSummary, Transcript, TranscriptSegment
from podcast_compactor.ports.llm import FakeStructuredLLM
from podcast_compactor.summarize import prompts
from podcast_compactor.summarize.chains import summarize_episode


def test_summarize_episode_forces_identity_and_passes_transcript():
    transcript = Transcript(
        episode_guid="ep-42",
        segments=[TranscriptSegment(start=0, end=1, text="the quick brown fox")],
    )
    # The model returns content but blank identity fields; we overwrite them.
    llm = FakeStructuredLLM(
        [EpisodeSummary(key_points=["a point"], themes=["a theme"])]
    )

    out = summarize_episode(transcript, title="My Episode", order_index=3, llm=llm)

    assert out.episode_guid == "ep-42"
    assert out.title == "My Episode"
    assert out.order_index == 3
    assert out.key_points == ["a point"]

    # Transcript text was actually included in the user prompt.
    _system, user, schema = llm.calls[0]
    assert "the quick brown fox" in user
    assert schema is EpisodeSummary


def test_summarize_episode_no_prompts_matches_builtin_exactly():
    # Regression guard: no guidance -> today's exact prompt and untimestamped text.
    transcript = Transcript(
        episode_guid="ep-1",
        segments=[TranscriptSegment(start=5.0, end=6.0, text="the quick brown fox")],
    )
    llm = FakeStructuredLLM([EpisodeSummary(key_points=["p"])])

    summarize_episode(transcript, title="T", order_index=0, llm=llm)

    _system, user, _schema = llm.calls[0]
    expected = prompts.EPISODE_USER.format(
        title="T", transcript=transcript.speaker_labeled_text
    )
    assert user == expected
    assert "[00:05]" not in user  # no timestamps on the default path


def test_summarize_episode_with_prompts_adds_guidance_and_timestamps():
    transcript = Transcript(
        episode_guid="ep-1",
        segments=[TranscriptSegment(start=260.0, end=262.0, text="interview part")],
    )
    llm = FakeStructuredLLM([EpisodeSummary(key_points=["p"])])

    summarize_episode(
        transcript, title="T", order_index=0, llm=llm,
        whole_prompt="skip ads", episode_prompt="cut 4:20 to 6:09",
    )

    _system, user, _schema = llm.calls[0]
    assert "[04:20]" in user            # timestamped transcript
    assert "Whole digest: skip ads" in user
    assert "This episode: cut 4:20 to 6:09" in user
