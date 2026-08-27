"""Turn a narrative arc into a spoken script sized to a target duration."""

from __future__ import annotations

import logging

from podcast_compactor.models.domain import ArcOutline, Script, Speaker
from podcast_compactor.ports.llm import StructuredLLM
from podcast_compactor.summarize import prompts

logger = logging.getLogger(__name__)

NARRATOR = "narrator"
HOST_SPEAKERS = ("host_a", "host_b")
_BUDGET_TOLERANCE = 0.25
# How many times to (re)ask the LLM for a longer draft before giving up and
# shipping the best one we got. 1 initial attempt + up to 2 expansions.
_MAX_SCRIPT_ATTEMPTS = 3


def _format_beats(arc: ArcOutline) -> str:
    return "\n".join(
        f"- {beat.heading} (episodes {beat.episode_guids}): {beat.narrative}"
        for beat in arc.beats
    )


def _normalize_speakers(script: Script, host_count: int) -> Script:
    """Validate a raw draft and normalize its speakers; raises on bad output."""
    if not script.segments:
        raise ValueError("script writer produced no segments")
    if host_count == 1:
        return script.model_copy(
            update={
                "segments": [
                    seg.model_copy(update={"speaker": NARRATOR}) for seg in script.segments
                ]
            }
        )
    speakers = {seg.speaker for seg in script.segments}
    if not speakers.issubset(set(HOST_SPEAKERS)):
        raise ValueError(
            f"two-host script must use only {HOST_SPEAKERS}, got {sorted(speakers)}"
        )
    if speakers != set(HOST_SPEAKERS):
        raise ValueError("two-host script must include both host_a and host_b")
    return script


def _normalize_multivoice(script: Script, cast_ids: set[str]) -> Script:
    """Validate a multi-speaker draft: non-empty and every speaker is in the cast."""
    if not script.segments:
        raise ValueError("script writer produced no segments")
    speakers = {seg.speaker for seg in script.segments}
    if not speakers.issubset(cast_ids):
        raise ValueError(
            f"multi-voice script must use only cast {sorted(cast_ids)}, "
            f"got {sorted(speakers)}"
        )
    return script


def _warn_on_budget_drift(script: Script, word_budget: int) -> None:
    drift = abs(script.word_count - word_budget) / word_budget
    if drift > _BUDGET_TOLERANCE:
        logger.warning(
            "script length %d words is %.0f%% off the %d-word budget",
            script.word_count,
            drift * 100,
            word_budget,
        )


def write_script(
    arc: ArcOutline,
    llm: StructuredLLM,
    target_minutes: int,
    wpm: int,
    host_count: int = 1,
    cast: list[Speaker] | None = None,
) -> Script:
    """Write a spoken script for the digest.

    When `cast` is given (speaker-preserving mode) the digest is a multi-speaker
    dialogue whose segment speakers are the cast's diarization ids. Otherwise
    `host_count == 1` produces a single-narrator monologue (all segments attributed
    to `narrator`) and `host_count == 2` a two-host `host_a`/`host_b` dialogue.

    A single LLM pass tends to under-write the word budget, yielding a digest
    much shorter than `target_minutes`. When a draft comes back below the budget
    (beyond the tolerance), we re-ask the model to expand it, up to
    `_MAX_SCRIPT_ATTEMPTS` times, and keep the longest draft. A warning is logged
    if the best draft still strays more than 25% from the word budget.
    """
    word_budget = target_minutes * wpm
    format_kwargs = dict(
        target_minutes=target_minutes,
        word_budget=word_budget,
        title=arc.title,
        throughline=arc.throughline,
        beats=_format_beats(arc),
    )

    if cast is not None:
        if not cast:
            raise ValueError("speaker-preserving script needs a non-empty cast")
        cast_ids = {s.id for s in cast}
        system = prompts.SCRIPT_MULTIVOICE_SYSTEM
        base_user = prompts.SCRIPT_MULTIVOICE_USER.format(
            speakers=", ".join(s.id for s in cast), **format_kwargs
        )

        def normalize(script: Script) -> Script:
            return _normalize_multivoice(script, cast_ids)
    else:
        if host_count not in (1, 2):
            raise NotImplementedError("host_count must be 1 or 2")
        if host_count == 1:
            system, user_template = prompts.SCRIPT_SYSTEM, prompts.SCRIPT_USER
        else:
            system, user_template = (
                prompts.SCRIPT_DIALOGUE_SYSTEM,
                prompts.SCRIPT_DIALOGUE_USER,
            )
        base_user = user_template.format(**format_kwargs)

        def normalize(script: Script) -> Script:
            return _normalize_speakers(script, host_count)

    floor = word_budget * (1 - _BUDGET_TOLERANCE)

    best: Script | None = None
    user = base_user
    for _ in range(_MAX_SCRIPT_ATTEMPTS):
        script = normalize(llm.generate(system, user, Script))
        if best is None or script.word_count > best.word_count:
            best = script
        if script.word_count >= floor:
            break
        # Too short — ask for a longer draft on the next pass. Only under-budget
        # drafts are retried; an over-budget draft is accepted (and warned on).
        user = base_user + "\n\n" + prompts.SCRIPT_EXPAND.format(
            words=script.word_count, word_budget=word_budget
        )

    assert best is not None  # loop runs at least once
    _warn_on_budget_drift(best, word_budget)
    return best
