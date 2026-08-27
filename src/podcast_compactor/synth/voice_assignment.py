"""Resolve detected speakers to voice assignments (pure, no backends).

Given the speakers diarization found and the job's options, decide how each is
voiced. Precedence: an explicit per-speaker assignment wins; otherwise `clone=True`
clones everyone; otherwise speakers get stock catalog voices round-robin. Kept
pure so it is trivially testable and reused by the synth stage.
"""

from __future__ import annotations

from podcast_compactor.models.domain import JobOptions, VoiceAssignment


def resolve_voice_assignments(
    speaker_ids: list[str],
    options: JobOptions,
    stock_catalog: list[str],
    default_stock_voice: str,
) -> dict[str, VoiceAssignment]:
    """Return a `VoiceAssignment` for every detected speaker, keyed by speaker id."""
    explicit = {a.speaker_id: a for a in options.voice_assignments}
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
        else:
            resolved[speaker_id] = VoiceAssignment(
                speaker_id=speaker_id,
                mode="stock",
                stock_voice=catalog[stock_i % len(catalog)],
            )
            stock_i += 1
    return resolved
