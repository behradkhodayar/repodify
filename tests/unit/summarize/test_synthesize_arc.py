from podcast_compactor.models.domain import ArcBeat, ArcOutline, EpisodeSummary
from podcast_compactor.ports.llm import FakeStructuredLLM
from podcast_compactor.summarize.chains import synthesize_arc


def test_synthesize_arc_orders_summaries_chronologically():
    summaries = [
        EpisodeSummary(episode_guid="c", order_index=2, title="Third"),
        EpisodeSummary(episode_guid="a", order_index=0, title="First"),
        EpisodeSummary(episode_guid="b", order_index=1, title="Second"),
    ]
    arc = ArcOutline(
        title="The Journey",
        throughline="How it evolved.",
        beats=[ArcBeat(heading="Start", episode_guids=["a"], narrative="...")],
    )
    llm = FakeStructuredLLM([arc])

    out = synthesize_arc(summaries, llm)

    assert out.title == "The Journey"
    _system, user, schema = llm.calls[0]
    assert schema is ArcOutline
    # Summaries appear oldest-first in the prompt regardless of input order.
    assert user.index("First") < user.index("Second") < user.index("Third")
