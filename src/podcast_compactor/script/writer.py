"""Turn a narrative arc into a spoken script sized to a target duration."""

from __future__ import annotations

import logging

from podcast_compactor.models.domain import ArcOutline, Script
from podcast_compactor.ports.llm import StructuredLLM
from podcast_compactor.summarize import prompts

logger = logging.getLogger(__name__)

NARRATOR = "narrator"
HOST_SPEAKERS = ("host_a", "host_b")
_BUDGET_TOLERANCE = 0.25


def _format_beats(arc: ArcOutline) -> str:
    return "\n".join(
        f"- {beat.heading} (episodes {beat.episode_guids}): {beat.narrative}"
        for beat in arc.beats
    )


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
) -> Script:
    """Write a spoken script for the digest.

    `host_count == 1` produces a single-narrator monologue (all segments
    attributed to `narrator`). `host_count == 2` produces a two-host dialogue
    with speakers `host_a`/`host_b`. A warning is logged if the script's length
    strays more than 25% from the word budget.
    """
    if host_count not in (1, 2):
        raise NotImplementedError("host_count must be 1 or 2")

    word_budget = target_minutes * wpm
    if host_count == 1:
        system, user_template = prompts.SCRIPT_SYSTEM, prompts.SCRIPT_USER
    else:
        system, user_template = prompts.SCRIPT_DIALOGUE_SYSTEM, prompts.SCRIPT_DIALOGUE_USER

    user = user_template.format(
        target_minutes=target_minutes,
        word_budget=word_budget,
        title=arc.title,
        throughline=arc.throughline,
        beats=_format_beats(arc),
    )
    script = llm.generate(system, user, Script)

    if not script.segments:
        raise ValueError("script writer produced no segments")

    if host_count == 1:
        script = script.model_copy(
            update={
                "segments": [
                    seg.model_copy(update={"speaker": NARRATOR}) for seg in script.segments
                ]
            }
        )
    else:
        speakers = {seg.speaker for seg in script.segments}
        if not speakers.issubset(set(HOST_SPEAKERS)):
            raise ValueError(
                f"two-host script must use only {HOST_SPEAKERS}, got {sorted(speakers)}"
            )
        if speakers != set(HOST_SPEAKERS):
            raise ValueError("two-host script must include both host_a and host_b")

    _warn_on_budget_drift(script, word_budget)
    return script
