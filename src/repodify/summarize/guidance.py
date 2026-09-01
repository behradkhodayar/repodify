"""Structured facts appended to summarizer/script prompts from later gate choices."""

from __future__ import annotations

from repodify.models.domain import JobOptions, Speaker


def runtime_guidance(options: JobOptions, cast: list[Speaker]) -> str:
    """Facts the user did not type: length mode and how the digest is voiced."""
    parts: list[str] = []
    if options.length_mode == "smart" or options.target_minutes is None:
        parts.append(
            "Length: choose a natural runtime for this material; do not pad or "
            "compress to a minute target."
        )
    else:
        parts.append(f"Length: write about {options.target_minutes} minutes of spoken audio.")

    if options.assign_voices or options.preserve_speakers:
        if options.use_original_voices or options.clone:
            parts.append("Voices: keep the original speakers (cloned).")
        else:
            parts.append("Voices: replace original speakers with stock voices.")
        for speaker in cast:
            gender = speaker.gender or "unknown gender"
            label = speaker.label or speaker.id
            line = f"  {label} ({gender}, {speaker.speaking_seconds:.0f}s)"
            assignment = next(
                (a for a in options.voice_assignments if a.speaker_id == speaker.id),
                None,
            )
            if assignment is not None and assignment.mode == "stock" and assignment.stock_voice:
                line += f" → {assignment.stock_voice}"
            parts.append(line)
    else:
        parts.append("Voices: single narrator.")
        if options.narrator_voice:
            parts.append(f"  Narrator stock voice: {options.narrator_voice}")
    return "\n".join(parts)
