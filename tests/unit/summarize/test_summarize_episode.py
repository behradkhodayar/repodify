from podcast_compactor.models.domain import EpisodeSummary, Transcript, TranscriptSegment
from podcast_compactor.ports.llm import FakeStructuredLLM
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
