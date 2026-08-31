import pytest

from repodify.models.domain import EpisodeSummary
from repodify.ports.llm import FakeStructuredLLM, StructuredLLM


def test_fake_returns_queued_response_and_records_call():
    fake = FakeStructuredLLM([EpisodeSummary(episode_guid="x", order_index=2)])
    out = fake.generate("sys", "usr", EpisodeSummary)
    assert out.episode_guid == "x"
    assert out.order_index == 2
    assert fake.calls == [("sys", "usr", EpisodeSummary)]


def test_fake_raises_when_exhausted():
    fake = FakeStructuredLLM([])
    with pytest.raises(RuntimeError):
        fake.generate("s", "u", EpisodeSummary)


def test_fake_satisfies_protocol():
    assert isinstance(FakeStructuredLLM([]), StructuredLLM)
