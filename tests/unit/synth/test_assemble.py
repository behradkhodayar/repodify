import io
import wave

import pytest

from repodify.models.domain import (
    ArcBeat,
    ArcOutline,
    Script,
    ScriptSegment,
)
from repodify.ports.tts import FakeTTS, Voice
from repodify.synth.assemble import (
    assemble_wav,
    build_show_notes,
    disclaimer_segment,
    synthesize_script,
)


def _frames(data: bytes) -> int:
    with wave.open(io.BytesIO(data), "rb") as w:
        return w.getnframes()


def _script() -> Script:
    return Script(
        segments=[
            ScriptSegment(speaker="narrator", text="chapter one words here"),
            ScriptSegment(speaker="narrator", text="chapter two more words now"),
        ]
    )


def _voices() -> dict[str, Voice]:
    return {"narrator": Voice(name="narrator")}


def test_assemble_wav_frame_count_is_sum_of_inputs():
    segments = synthesize_script(_script(), FakeTTS(), _voices())
    combined = assemble_wav(segments)
    assert _frames(combined) == sum(_frames(s) for s in segments)


def test_synthesize_script_reports_segment_progress():
    seen: list[tuple[int, int]] = []
    segments = synthesize_script(
        _script(), FakeTTS(), _voices(), on_progress=lambda i, n: seen.append((i, n))
    )
    assert len(segments) == 2
    assert seen == [(1, 2), (2, 2)]


def test_build_show_notes_one_chapter_per_beat_ascending():
    segments = synthesize_script(_script(), FakeTTS(), _voices())
    arc = ArcOutline(
        title="T",
        throughline="the whole story",
        beats=[
            ArcBeat(heading="Beat A", episode_guids=["a"], narrative="..."),
            ArcBeat(heading="Beat B", episode_guids=["b"], narrative="..."),
        ],
    )
    notes = build_show_notes(arc, _script(), segments)
    assert notes.summary == "the whole story"
    assert [c.title for c in notes.chapters] == ["Beat A", "Beat B"]
    assert notes.chapters[0].start_s < notes.chapters[1].start_s


def test_build_show_notes_synthetic_labeling():
    segments = synthesize_script(_script(), FakeTTS(), _voices())
    arc = ArcOutline(title="T", throughline="story", beats=[])
    notes = build_show_notes(arc, _script(), segments, synthetic=True, disclaimer="AI voices")
    assert notes.synthetic is True
    assert notes.disclaimer == "AI voices"


def test_disclaimer_segment_uses_reserved_speaker():
    seg = disclaimer_segment("this is AI")
    assert seg.speaker == "disclaimer"
    assert seg.text == "this is AI"


def test_synthesize_script_missing_voice_raises():
    with pytest.raises(KeyError):
        synthesize_script(_script(), FakeTTS(), {})


def test_assemble_empty_raises():
    with pytest.raises(ValueError):
        assemble_wav([])
