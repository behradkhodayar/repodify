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
    # A within-budget draft (>= 3900 words) so the writer accepts it in one pass.
    returned = Script(
        segments=[ScriptSegment(speaker="guest", text=" ".join(["word"] * 3900))]
    )
    llm = FakeStructuredLLM([returned])

    script = write_script(_arc(), llm, target_minutes=30, wpm=130)

    assert script.segments[0].speaker == "narrator"
    assert len(llm.calls) == 1  # within budget -> no expansion retry
    _system, user, schema = llm.calls[0]
    assert schema is Script
    assert "3900" in user  # 30 * 130
    assert "30" in user


def test_write_script_rejects_empty_result():
    llm = FakeStructuredLLM([Script(segments=[])])
    with pytest.raises(ValueError):
        write_script(_arc(), llm, target_minutes=30, wpm=130)


def test_write_script_two_hosts_uses_dialogue_and_keeps_speakers():
    # A within-budget draft (1950 + 1950 = 3900 words) so no expansion retry.
    returned = Script(
        segments=[
            ScriptSegment(speaker="host_a", text=" ".join(["word"] * 1950)),
            ScriptSegment(speaker="host_b", text=" ".join(["word"] * 1950)),
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


def test_write_script_expands_a_short_first_draft():
    # budget = 2 * 10 = 20 words; 25% tolerance -> floor of 15 words.
    short = Script(segments=[ScriptSegment(speaker="narrator", text="too short")])  # 2 words
    full = Script(
        segments=[ScriptSegment(speaker="narrator", text=" ".join(["word"] * 20))]
    )
    llm = FakeStructuredLLM([short, full])

    script = write_script(_arc(), llm, target_minutes=2, wpm=10)

    assert script.word_count == 20  # returned the expanded draft, not the short one
    assert len(llm.calls) == 2  # retried once after the under-budget draft
    _system, retry_user, _schema = llm.calls[1]
    assert "only 2 words" in retry_user  # tells the model how short its draft was
    assert "expand" in retry_user.lower()  # ...and asks it to expand


def test_write_script_stops_after_max_attempts_and_keeps_longest():
    # budget = 10 * 10 = 100 words; floor 75 -> every draft below stays short.
    drafts = [
        Script(segments=[ScriptSegment(speaker="narrator", text="one two")]),  # 2
        Script(segments=[ScriptSegment(speaker="narrator", text="one two three four")]),  # 4
        Script(segments=[ScriptSegment(speaker="narrator", text="one two three")]),  # 3
    ]
    llm = FakeStructuredLLM(list(drafts))

    script = write_script(_arc(), llm, target_minutes=10, wpm=10)

    assert len(llm.calls) == 3  # capped at 3 attempts, no runaway loop
    assert script.word_count == 4  # kept the longest draft across attempts, not the last
