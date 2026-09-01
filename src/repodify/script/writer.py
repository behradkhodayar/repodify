"""Turn a narrative arc into a spoken script sized to a target duration."""

from __future__ import annotations

import logging
import re

from repodify.models.domain import ArcOutline, Script, Speaker
from repodify.ports.llm import StructuredLLM
from repodify.summarize import prompts

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


_TRAILING_INT = re.compile(r"(\d+)$")


def _cast_by_int(cast_ids: set[str]) -> dict[int, str]:
    """Map each cast id's trailing integer to that id, dropping ambiguous ints.

    Diarization ids look like ``SPEAKER_00``; this lets a near-miss label the LLM
    emits (``SPEAKER_1``) be matched back to the canonical ``SPEAKER_01``. An
    integer shared by two cast ids is dropped so we never guess between them.
    """
    by_int: dict[int, str | None] = {}
    for cid in cast_ids:
        m = _TRAILING_INT.search(cid)
        if not m:
            continue
        n = int(m.group(1))
        by_int[n] = cid if n not in by_int else None  # None marks ambiguous
    return {n: cid for n, cid in by_int.items() if cid is not None}


def _canonical_speaker(label: str, cast_ids: set[str], by_int: dict[int, str]) -> str | None:
    """Return the cast id `label` denotes, canonicalizing a near-miss, or None."""
    if label in cast_ids:
        return label
    m = _TRAILING_INT.search(label)
    return by_int.get(int(m.group(1))) if m else None


def _normalize_multivoice(script: Script, cast_ids: set[str]) -> Script:
    """Validate a multi-speaker draft: non-empty and every speaker maps to the cast.

    LLMs (small local models especially) don't reliably echo the exact cast labels
    they're given — a segment for ``SPEAKER_01`` may come back as ``SPEAKER_1``. We
    canonicalize such near-misses back to the cast id before validating, and only
    reject a label that matches no cast member at all.
    """
    if not script.segments:
        raise ValueError("script writer produced no segments")
    by_int = _cast_by_int(cast_ids)
    segments = []
    for seg in script.segments:
        canon = _canonical_speaker(seg.speaker, cast_ids, by_int)
        segments.append(seg if canon in (None, seg.speaker) else seg.model_copy(
            update={"speaker": canon}
        ))
    if any(_canonical_speaker(s.speaker, cast_ids, by_int) is None for s in script.segments):
        raise ValueError(
            f"multi-voice script must use only cast {sorted(cast_ids)}, "
            f"got {sorted({s.speaker for s in script.segments})}"
        )
    return script.model_copy(update={"segments": segments})


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
    target_minutes: int | None,
    wpm: int,
    host_count: int = 1,
    cast: list[Speaker] | None = None,
    *,
    whole_prompt: str | None = None,
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
    smart = target_minutes is None
    word_budget = 0 if smart else target_minutes * wpm
    format_kwargs = dict(
        target_minutes="a natural" if smart else target_minutes,
        word_budget="no fixed count — choose a length that fits the material"
        if smart
        else word_budget,
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

    # Whole-digest guidance rides on the base prompt so it persists across the
    # expansion retries below (which rebuild `user` from `base_user`).
    base_user = prompts.with_guidance(base_user, whole=whole_prompt)

    if smart:
        script = normalize(llm.generate(system, base_user, Script))
        return script

    floor = word_budget * (1 - _BUDGET_TOLERANCE)

    best: Script | None = None
    last_error: ValueError | None = None
    user = base_user
    for _ in range(_MAX_SCRIPT_ATTEMPTS):
        try:
            script = normalize(llm.generate(system, user, Script))
        except ValueError as err:
            # A malformed draft (empty, or an unrecoverable speaker label) shouldn't
            # kill the run on its own — re-ask, echoing the error, until we run out
            # of attempts. Only then does the failure propagate.
            last_error = err
            user = base_user + "\n\n" + prompts.SCRIPT_FIX.format(error=err)
            continue
        if best is None or script.word_count > best.word_count:
            best = script
        if script.word_count >= floor:
            break
        # Too short — ask for a longer draft on the next pass. Only under-budget
        # drafts are retried; an over-budget draft is accepted (and warned on).
        user = base_user + "\n\n" + prompts.SCRIPT_EXPAND.format(
            words=script.word_count, word_budget=word_budget
        )

    if best is None:  # every attempt failed validation
        assert last_error is not None
        raise last_error
    _warn_on_budget_drift(best, word_budget)
    return best
