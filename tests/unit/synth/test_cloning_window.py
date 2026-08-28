"""The clip-selection logic in the voice cloner (pure; ffmpeg is not exercised)."""

from podcast_compactor.models.domain import TranscriptSegment
from podcast_compactor.synth.cloning import best_window


def _seg(start, end, speaker, text="x"):
    return TranscriptSegment(start=start, end=end, text=text, speaker=speaker)


def test_best_window_picks_longest_run_and_caps_length():
    segs = [
        _seg(0, 1, "A", "short one"),
        _seg(1, 2, "B", "other"),
        _seg(2, 8, "A", "the long run here"),  # longest A run: 6s
        _seg(8, 9, "A", "still A"),  # contiguous with the above -> run is 2-9 = 7s
    ]
    start, end, text = best_window(segs, "A", clip_seconds=4.0)
    assert start == 2.0
    assert end == 6.0  # capped at start + clip_seconds
    # Only the segment starting before the window end contributes text.
    assert text == "the long run here"


def test_best_window_for_missing_speaker_returns_empty():
    start, end, text = best_window([_seg(0, 5, "A")], "Z", clip_seconds=8.0)
    assert (start, end, text) == (0.0, 8.0, "")
