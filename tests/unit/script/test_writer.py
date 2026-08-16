import pytest

from podcast_compactor.models.domain import ArcBeat, ArcOutline, Script, ScriptSegment
from podcast_compactor.ports.llm import FakeStructuredLLM
from podcast_compactor.script.writer import write_script


def _arc() -> ArcOutline:
    return ArcOutline(
        title="The Journey",
        throughline="How it evolved.",
        beats=[ArcBeat(heading="Start", episode_guids=["a"], narrative="It began.")],
    )


def test_write_script_passes_word_budget_and_normalizes_speaker():
    returned = Script(segments=[ScriptSegment(speaker="guest", text="one two three")])
    llm = FakeStructuredLLM([returned])

    script = write_script(_arc(), llm, target_minutes=30, wpm=130)

    assert script.segments[0].speaker == "narrator"
    _system, user, schema = llm.calls[0]
    assert schema is Script
    assert "3900" in user  # 30 * 130
    assert "30" in user


def test_write_script_rejects_empty_result():
    llm = FakeStructuredLLM([Script(segments=[])])
    with pytest.raises(ValueError):
        write_script(_arc(), llm, target_minutes=30, wpm=130)


def test_write_script_rejects_multi_host_in_phase_1():
    llm = FakeStructuredLLM([Script(segments=[ScriptSegment(speaker="a", text="hi")])])
    with pytest.raises(NotImplementedError):
        write_script(_arc(), llm, target_minutes=30, wpm=130, host_count=2)
