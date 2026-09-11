"""_build_real_tts / apply_job_backends pick Chatterbox vs OpenRouter by language."""

from __future__ import annotations

import httpx

from repodify.config import Settings
from repodify.models.domain import (
    ExecutionChoice,
    JobOptions,
    Transcript,
    TranscriptSegment,
)
from repodify.pipeline.state import Deps
from repodify.ports.diarizer import FakeDiarizer
from repodify.ports.llm import LocalStubLLM
from repodify.ports.transcoder import FakeTranscoder
from repodify.ports.transcriber import FakeTranscriber
from repodify.ports.tts import FakeTTS, Voice
from repodify.ports.voice_cloner import FakeVoiceCloner
from repodify.ports.watermarker import FakeWatermarker
from repodify.worker.main import _build_real_tts, apply_job_backends


class _StubTTS:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.model_id = kwargs.get("repo_id") or kwargs.get("model") or "stub"

    def release(self) -> None:
        return None


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, use_fakes=False, openrouter_api_key="sk-or", **kwargs)


def _deps(settings: Settings) -> Deps:
    return Deps(
        resolver_resolve=lambda url, http: url,
        http=httpx.Client(),
        storage=None,  # type: ignore[arg-type]
        transcriber=FakeTranscriber(
            Transcript(
                episode_guid="",
                segments=[TranscriptSegment(start=0.0, end=1.0, text="x")],
            )
        ),
        diarizer=FakeDiarizer(),
        llm_map=LocalStubLLM(),
        llm_reduce=LocalStubLLM(),
        tts=FakeTTS(),
        voices={"narrator": Voice(name="narrator")},
        voice_cloner=FakeVoiceCloner(),
        watermarker=FakeWatermarker(),
        repo=None,  # type: ignore[arg-type]
        settings=settings,
        transcoder=FakeTranscoder(),
    )


def test_local_persian_uses_pocket_by_default(monkeypatch):
    monkeypatch.setattr(
        "repodify.synth.pocket_tts.PocketPersianTTS",
        _StubTTS,
    )
    tts = _build_real_tts(_settings(tts_backend="f5"), language="fa")
    assert isinstance(tts, _StubTTS)
    assert tts.kwargs["repo_id"] == "mehdi-hf/pocket-tts-farsi"


def test_local_persian_uses_chatterbox_when_engine_set(monkeypatch):
    monkeypatch.setattr(
        "repodify.synth.chatterbox_tts.ChatterboxPersianTTS",
        _StubTTS,
    )
    tts = _build_real_tts(
        _settings(tts_backend="f5", persian_tts_engine="chatterbox"),
        language="fa",
    )
    assert isinstance(tts, _StubTTS)
    assert tts.kwargs["repo_id"] == "Thomcles/Chatterbox-TTS-Persian-Farsi"


def test_unknown_persian_engine_raises():
    import pytest

    settings = _settings(tts_backend="f5")
    object.__setattr__(settings, "persian_tts_engine", "xtts")
    with pytest.raises(RuntimeError, match="unknown Persian TTS engine"):
        _build_real_tts(settings, language="fa")


def test_byok_persian_uses_openrouter_fa_model(monkeypatch):
    monkeypatch.setattr("repodify.synth.openrouter_tts.OpenRouterTTS", _StubTTS)
    tts = _build_real_tts(
        _settings(tts_backend="openrouter", openrouter_tts_model_fa="fish-audio/s1"),
        language="fa",
    )
    assert isinstance(tts, _StubTTS)
    assert tts.kwargs["model"] == "fish-audio/s1"
    assert tts.kwargs["language"] == "fa"


def test_apply_job_backends_local_persian_swaps_tts(monkeypatch):
    monkeypatch.setattr(
        "repodify.synth.pocket_tts.PocketPersianTTS",
        _StubTTS,
    )
    settings = _settings()
    deps = _deps(settings)
    try:
        options = JobOptions(
            episode_ids=["e"],
            target_language="fa",
            tts=ExecutionChoice(mode="local"),
        )
        out = apply_job_backends(deps, settings, options)
        assert isinstance(out.tts, _StubTTS)
        assert out.tts.kwargs["repo_id"] == "mehdi-hf/pocket-tts-farsi"
    finally:
        deps.http.close()


def test_apply_job_backends_local_persian_honors_chatterbox_backend(monkeypatch):
    monkeypatch.setattr(
        "repodify.synth.chatterbox_tts.ChatterboxPersianTTS",
        _StubTTS,
    )
    settings = _settings(persian_tts_engine="pocket")
    deps = _deps(settings)
    try:
        options = JobOptions(
            episode_ids=["e"],
            target_language="fa",
            tts=ExecutionChoice(mode="local", backend="chatterbox"),
        )
        out = apply_job_backends(deps, settings, options)
        assert isinstance(out.tts, _StubTTS)
        assert out.tts.kwargs["repo_id"] == "Thomcles/Chatterbox-TTS-Persian-Farsi"
    finally:
        deps.http.close()


def test_apply_job_backends_byok_persian_uses_fa_model(monkeypatch):
    monkeypatch.setattr("repodify.synth.openrouter_tts.OpenRouterTTS", _StubTTS)
    settings = _settings(openrouter_tts_model_fa="fish-audio/s1")
    deps = _deps(settings)
    try:
        options = JobOptions(
            episode_ids=["e"],
            target_language="fa",
            tts=ExecutionChoice(mode="byok"),
        )
        out = apply_job_backends(deps, settings, options)
        assert isinstance(out.tts, _StubTTS)
        assert out.tts.kwargs["model"] == "fish-audio/s1"
        assert out.tts.kwargs["language"] == "fa"
    finally:
        deps.http.close()


def test_apply_job_backends_fake_mode_unchanged():
    settings = Settings(_env_file=None, use_fakes=True)
    deps = _deps(settings)
    try:
        out = apply_job_backends(
            deps,
            settings,
            JobOptions(episode_ids=["e"], target_language="fa", tts=ExecutionChoice(mode="local")),
        )
        assert isinstance(out.tts, FakeTTS)
    finally:
        deps.http.close()


def test_openrouter_persian_seed_is_farsi():
    from repodify.synth.openrouter_tts import _SEED_TEXT, _SEED_TEXT_FA, OpenRouterTTS

    tts = OpenRouterTTS(api_key="sk", language="fa")
    assert tts._seed_text() == _SEED_TEXT_FA
    assert tts._seed_text() != _SEED_TEXT


def test_english_local_is_not_chatterbox(monkeypatch):
    class _Routing:
        def __init__(self, *args, **kwargs) -> None:
            self.model_id = "f5+kokoro"

        def release(self) -> None:
            return None

    monkeypatch.setattr("repodify.synth.f5_tts.F5TTS", lambda *a, **k: object())
    monkeypatch.setattr("repodify.synth.kokoro.KokoroTTS", lambda *a, **k: object())
    monkeypatch.setattr("repodify.synth.routing_tts.RoutingTTS", _Routing)
    tts = _build_real_tts(_settings(tts_backend="f5"), language="en")
    assert isinstance(tts, _Routing)
