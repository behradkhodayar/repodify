"""Turn a narrative arc into a spoken script sized to a target duration."""

from __future__ import annotations

import logging

from podcast_compactor.models.domain import ArcOutline, Script
from podcast_compactor.ports.llm import StructuredLLM
from podcast_compactor.summarize import prompts

logger = logging.getLogger(__name__)

NARRATOR = "narrator"
_BUDGET_TOLERANCE = 0.25


def _format_beats(arc: ArcOutline) -> str:
    return "\n".join(
        f"- {beat.heading} (episodes {beat.episode_guids}): {beat.narrative}"
        for beat in arc.beats
    )


def write_script(
    arc: ArcOutline,
    llm: StructuredLLM,
    target_minutes: int,
    wpm: int,
    host_count: int = 1,
) -> Script:
    """Write a spoken script for the digest.

    Phase 1 supports a single narrator (`host_count == 1`); every returned
    segment is attributed to the narrator. A warning is logged if the script's
    length strays more than 25% from the word budget.
    """
    if host_count != 1:
        raise NotImplementedError("Phase 1 supports host_count=1 only")

    word_budget = target_minutes * wpm
    user = prompts.SCRIPT_USER.format(
        target_minutes=target_minutes,
        word_budget=word_budget,
        title=arc.title,
        throughline=arc.throughline,
        beats=_format_beats(arc),
    )
    script = llm.generate(prompts.SCRIPT_SYSTEM, user, Script)

    if not script.segments:
        raise ValueError("script writer produced no segments")

    # Single-narrator: normalize speaker attribution.
    script = script.model_copy(
        update={
            "segments": [seg.model_copy(update={"speaker": NARRATOR}) for seg in script.segments]
        }
    )

    drift = abs(script.word_count - word_budget) / word_budget
    if drift > _BUDGET_TOLERANCE:
        logger.warning(
            "script length %d words is %.0f%% off the %d-word budget",
            script.word_count,
            drift * 100,
            word_budget,
        )
    return script
