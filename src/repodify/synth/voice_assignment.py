"""Resolve detected speakers to voice assignments (pure, no backends).

Given the speakers diarization found and the job's options, decide how each is
voiced. Precedence: an explicit per-speaker assignment wins; otherwise `clone=True`
clones everyone; otherwise speakers get stock catalog voices round-robin. Kept
pure so it is trivially testable and reused by the synth stage.
"""

from __future__ import annotations

from repodify.models.domain import JobOptions, Speaker, Transcript, VoiceAssignment

# The speaker-preserving digest caps its cast so the dialogue stays coherent and
# cloning work stays bounded; the most-talkative speakers are kept.
MAX_CAST = 4


def select_cast(transcript: Transcript, max_cast: int = MAX_CAST) -> list[Speaker]:
    """The digest cast: the transcript's most-talkative speakers, capped.

    `transcript.speakers` is already ordered by talk time (see `roster_from_turns`).
    """
    return transcript.speakers[:max_cast]


def resolve_voice_assignments(
    speaker_ids: list[str],
    options: JobOptions,
    stock_catalog: list[str],
    default_stock_voice: str,
    preferred_stock: dict[str, str] | None = None,
) -> dict[str, VoiceAssignment]:
    """Return a `VoiceAssignment` for every detected speaker, keyed by speaker id.

    Precedence for a speaker's stock voice: an explicit user assignment wins;
    otherwise a `preferred_stock` pick (e.g. gender-matched) is used; otherwise the
    speaker takes the next voice from `stock_catalog` round-robin. `preferred_stock`
    only affects speakers that would be voiced from the catalog (not `clone`).
    """
    explicit = {a.speaker_id: a for a in options.voice_assignments}
    preferred = preferred_stock or {}
    catalog = stock_catalog or [default_stock_voice]

    resolved: dict[str, VoiceAssignment] = {}
    stock_i = 0
    for speaker_id in speaker_ids:
        if speaker_id in explicit:
            a = explicit[speaker_id]
            if a.mode == "stock" and not a.stock_voice:
                a = a.model_copy(update={"stock_voice": default_stock_voice})
            resolved[speaker_id] = a
        elif options.clone:
            resolved[speaker_id] = VoiceAssignment(speaker_id=speaker_id, mode="clone")
        elif speaker_id in preferred:
            resolved[speaker_id] = VoiceAssignment(
                speaker_id=speaker_id, mode="stock", stock_voice=preferred[speaker_id]
            )
        else:
            resolved[speaker_id] = VoiceAssignment(
                speaker_id=speaker_id,
                mode="stock",
                stock_voice=catalog[stock_i % len(catalog)],
            )
            stock_i += 1
    return resolved
