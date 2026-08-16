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


def test_write_script_two_hosts_uses_dialogue_and_keeps_speakers():
    returned = Script(
        segments=[
            ScriptSegment(speaker="host_a", text="one two three"),
            ScriptSegment(speaker="host_b", text="four five six"),
        ]
    )
    llm = FakeStructuredLLM([returned])

    script = write_script(_arc(), llm, target_minutes=30, wpm=130, host_count=2)

    assert {s.speaker for s in script.segments} == {"host_a", "host_b"}
    _system, user, schema = llm.calls[0]
    assert schema is Script
    assert "host_a" in user and "host_b" in user
    assert "3900" in user


def test_write_script_two_hosts_rejects_bad_speaker():
    llm = FakeStructuredLLM(
        [
            Script(
                segments=[
                    ScriptSegment(speaker="narrator", text="hi there friend"),
                    ScriptSegment(speaker="host_b", text="hello back to you"),
                ]
            )
        ]
    )
    with pytest.raises(ValueError):
        write_script(_arc(), llm, target_minutes=30, wpm=130, host_count=2)


def test_write_script_two_hosts_requires_both_hosts():
    llm = FakeStructuredLLM(
        [Script(segments=[ScriptSegment(speaker="host_a", text="only me talking")])]
    )
    with pytest.raises(ValueError):
        write_script(_arc(), llm, target_minutes=30, wpm=130, host_count=2)


def test_write_script_rejects_three_hosts():
    llm = FakeStructuredLLM([Script(segments=[ScriptSegment(speaker="host_a", text="hi")])])
    with pytest.raises(NotImplementedError):
        write_script(_arc(), llm, target_minutes=30, wpm=130, host_count=3)
