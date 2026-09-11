"""Continue-payload validation for local vs BYOK backends."""

from __future__ import annotations

import pytest

from repodify.models.domain import JobOptions
from repodify.pipeline.gates import GateError, apply_gate_payload


def test_tts_accepts_pocket_and_chatterbox_backends():
    options = JobOptions(episode_ids=["e"], target_language="fa")
    for engine in ("pocket", "chatterbox"):
        out = apply_gate_payload(
            options,
            "tts",
            {"mode": "local", "backend": engine, "narrator_voice": "fa_neda"},
        )
        assert out.tts is not None
        assert out.tts.mode == "local"
        assert out.tts.backend == engine
        assert out.narrator_voice == "fa_neda"


def test_tts_rejects_unknown_backend():
    options = JobOptions(episode_ids=["e"])
    with pytest.raises(GateError, match="unknown backend"):
        apply_gate_payload(options, "tts", {"mode": "local", "backend": "xtts"})


def test_summarize_still_rejects_pocket_as_llm_backend():
    options = JobOptions(episode_ids=["e"])
    with pytest.raises(GateError, match="unknown backend"):
        apply_gate_payload(
            options,
            "summarize",
            {"mode": "byok", "backend": "pocket", "length_mode": "manual", "target_minutes": 10},
        )
