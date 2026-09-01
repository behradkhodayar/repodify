"""Validate and apply per-gate continue payloads onto JobOptions."""

from __future__ import annotations

from typing import Any

from repodify.models.domain import ExecutionChoice, JobOptions, VoiceAssignment

GATES = ("transcribe", "diarize", "voices", "summarize", "tts")


class GateError(ValueError):
    """User-facing continue-payload problem."""


def _choice(payload: dict[str, Any], *, require_mode: bool = True) -> ExecutionChoice | None:
    mode = payload.get("mode")
    if mode is None:
        if require_mode:
            raise GateError("mode is required (local or byok)")
        return None
    if mode not in ("local", "byok"):
        raise GateError("mode must be local or byok")
    backend = payload.get("backend")
    if backend is not None and backend not in ("anthropic", "ollama", "openrouter"):
        raise GateError(f"unknown backend: {backend}")
    return ExecutionChoice(
        mode=mode,
        model=payload.get("model"),
        backend=backend,
    )


def apply_gate_payload(options: JobOptions, gate: str, payload: dict[str, Any]) -> JobOptions:
    """Return a copy of ``options`` with this gate's choices merged in."""
    payload = dict(payload or {})
    if gate == "transcribe":
        return options.model_copy(update={"transcribe": _choice(payload)})
    if gate == "diarize":
        if "assign_voices" not in payload:
            raise GateError("assign_voices is required")
        assign = bool(payload["assign_voices"])
        choice = _choice(payload, require_mode=assign) if assign else None
        return options.model_copy(
            update={
                "assign_voices": assign,
                "diarize": choice,
                "preserve_speakers": assign,
                "review_voices": assign,
            }
        )
    if gate == "voices":
        if "use_original" not in payload:
            raise GateError("use_original is required")
        use_original = bool(payload["use_original"])
        raw = payload.get("voice_assignments") or payload.get("assignments") or []
        assignments = [VoiceAssignment.model_validate(a) for a in raw]
        if use_original:
            assignments = [
                VoiceAssignment(speaker_id=a.speaker_id, mode="clone")
                if a.mode != "clone"
                else a
                for a in assignments
            ] or assignments
        return options.model_copy(
            update={
                "use_original_voices": use_original,
                "clone": use_original,
                "preserve_speakers": True,
                "assign_voices": True,
                "voice_assignments": assignments,
            }
        )
    if gate == "summarize":
        length_mode = payload.get("length_mode", "manual")
        if length_mode not in ("manual", "smart"):
            raise GateError("length_mode must be manual or smart")
        target = payload.get("target_minutes")
        if length_mode == "smart":
            target = None
        elif target is None:
            target = options.target_minutes or 30
        return options.model_copy(
            update={
                "length_mode": length_mode,
                "target_minutes": target,
                "llm": _choice(payload),
            }
        )
    if gate == "tts":
        return options.model_copy(
            update={
                "tts": _choice(payload),
                "narrator_voice": payload.get("narrator_voice"),
            }
        )
    raise GateError(f"unknown gate: {gate}")
