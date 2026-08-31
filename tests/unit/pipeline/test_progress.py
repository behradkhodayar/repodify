from types import SimpleNamespace

from repodify.pipeline.progress import (
    DetailThrottler,
    format_bytes,
    format_percent,
    join_detail,
    model_id,
)


def test_join_detail_drops_empty_and_joins_with_middle_dot():
    assert join_detail("ep", "1/3", None, "", "40%") == "ep · 1/3 · 40%"
    assert join_detail(None, "") == ""
    assert join_detail(2, "of", 5) == "2 · of · 5"


def test_format_bytes():
    assert format_bytes(512) == "512 B"
    assert format_bytes(830 * 1024) == "830.0 KB"
    assert format_bytes(int(12.4 * 1024 * 1024)) == "12.4 MB"


def test_format_percent():
    assert format_percent(34, 100) == "34%"
    assert format_percent(1, 3) == "33%"
    assert format_percent(10, 0) is None
    assert format_percent(10, -1) is None


def test_model_id_reads_public_attr():
    assert model_id(SimpleNamespace(model_id="whisper-small")) == "whisper-small"
    assert model_id(SimpleNamespace(model_id=None)) is None
    assert model_id(SimpleNamespace(model_id="")) is None
    assert model_id(SimpleNamespace()) is None


def test_throttler_emits_first_call_then_respects_interval(monkeypatch):
    emitted: list[str] = []
    now = {"t": 0.0}
    monkeypatch.setattr("repodify.pipeline.progress.time.monotonic", lambda: now["t"])

    t = DetailThrottler(emitted.append, min_interval_s=0.4, min_pct_delta=2.0)
    t.update("a", pct=1.0)
    t.update("b", pct=1.5)  # too soon, pct delta 0.5
    now["t"] = 0.4
    t.update("c", pct=1.6)
    assert emitted == ["a", "c"]


def test_throttler_emits_on_pct_jump_even_inside_interval(monkeypatch):
    emitted: list[str] = []
    now = {"t": 0.0}
    monkeypatch.setattr("repodify.pipeline.progress.time.monotonic", lambda: now["t"])

    t = DetailThrottler(emitted.append, min_interval_s=1.0, min_pct_delta=2.0)
    t.update("a", pct=10.0)
    now["t"] = 0.1
    t.update("b", pct=12.0)
    assert emitted == ["a", "b"]


def test_throttler_flush_always_emits(monkeypatch):
    emitted: list[str] = []
    now = {"t": 0.0}
    monkeypatch.setattr("repodify.pipeline.progress.time.monotonic", lambda: now["t"])

    t = DetailThrottler(emitted.append, min_interval_s=10.0, min_pct_delta=50.0)
    t.update("a", pct=1.0)
    t.flush("done")
    assert emitted == ["a", "done"]
