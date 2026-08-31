"""Prompt templates for the summarization and scripting stages."""

from __future__ import annotations

EPISODE_SYSTEM = (
    "You are a meticulous podcast analyst. You read one episode transcript and "
    "extract a structured summary. Be faithful to what was actually said; do not "
    "invent facts. Capture the substance a listener would want to remember."
)

EPISODE_USER = """\
Episode title: {title}

Summarize this single episode. Provide:
- key_points: the main things discussed or argued
- themes: recurring topics or ideas
- notable_quotes: memorable verbatim lines (short)
- timeline_markers: concrete developments, events, or turning points mentioned

The transcript may be labeled by speaker (e.g. "SPEAKER_00:"). When it is, note who
said or argued what where it matters, and attribute notable quotes to their speaker.

Transcript:
{transcript}
"""

ARC_SYSTEM = (
    "You are a narrative editor building a chronological through-line across a run "
    "of podcast episodes. You are given per-episode summaries in chronological "
    "order. Produce a single arc that lets a listener live through how the show — "
    "and the topic it covers — evolved from the earliest episode forward."
)

ARC_USER = """\
Here are the per-episode summaries in chronological order (oldest first).

Produce:
- title: a title for the digest
- throughline: 2-4 sentences describing the overall arc across these episodes
- beats: an ordered list of narrative beats. Each beat covers one or more
  consecutive episodes (reference them by guid) and explains, in chronological
  order, what changed or developed.

Episode summaries:
{summaries}
"""

SCRIPT_SYSTEM = (
    "You are a scriptwriter for a spoken-word podcast digest. You turn a narrative "
    "arc into a natural, engaging monologue that a single narrator reads aloud. "
    "Write for the ear: clear, conversational, chronological. Do not use headings, "
    "stage directions, or bullet points in the spoken text."
)

SCRIPT_USER = """\
Write a single-narrator script for a digest episode of about {target_minutes}
minutes. Aim for roughly {word_budget} spoken words total (this is a target, not
a hard limit).

Walk the listener through the arc in chronological order, making clear how things
developed from the earliest episode onward. Produce the script as an ordered list
of segments; every segment has speaker "narrator" and the spoken text.

Narrative arc:
Title: {title}
Through-line: {throughline}

Beats:
{beats}
"""

SCRIPT_EXPAND = (
    "Your previous draft was only {words} words, well short of the "
    "~{word_budget}-word target. Expand it substantially: develop each beat with "
    "more detail, concrete context, and natural spoken transitions until it "
    "reaches roughly {word_budget} words. Keep it chronological and written for "
    "the ear; do not pad with filler or repeat yourself."
)

SCRIPT_FIX = (
    "Your previous draft was rejected: {error}. Rewrite the script using only the "
    "exact speaker labels specified above — every segment's speaker must be one of "
    "them, spelled identically (including any leading zeros). Keep it chronological "
    "and written for the ear."
)

SCRIPT_DIALOGUE_SYSTEM = (
    "You are a scriptwriter for a two-host conversational podcast digest. Two "
    "co-hosts talk through a narrative arc together: they hand off naturally, "
    "react to each other, and build on each other's points. Write for the ear — "
    "clear, warm, chronological. No headings, stage directions, or bullet points "
    "in the spoken text."
)

SCRIPT_DIALOGUE_USER = """\
Write a two-host dialogue script for a digest episode of about {target_minutes}
minutes. Aim for roughly {word_budget} spoken words total (a target, not a hard
limit).

There are exactly two speakers. Label every segment's speaker as either
"host_a" or "host_b" (use those exact strings). Alternate turns naturally so it
reads as a real conversation, and make sure both hosts speak. Walk the listener
through the arc in chronological order, making clear how things developed from
the earliest episode onward. Produce the script as an ordered list of segments;
each segment has a speaker ("host_a" or "host_b") and the spoken text.

Narrative arc:
Title: {title}
Through-line: {throughline}

Beats:
{beats}
"""

SCRIPT_MULTIVOICE_SYSTEM = (
    "You are a scriptwriter for a multi-speaker podcast digest voiced by the show's "
    "actual cast. Each speaker keeps their own perspective and voice; they hand off "
    "naturally, react to each other, and build on each other's points. Write for the "
    "ear — clear, warm, chronological. No headings, stage directions, or bullet "
    "points in the spoken text."
)

SCRIPT_MULTIVOICE_USER = """\
Write a multi-speaker dialogue script for a digest episode of about
{target_minutes} minutes. Aim for roughly {word_budget} spoken words total (a
target, not a hard limit).

The speakers are exactly these labels: {speakers}. Label every segment's speaker
with one of those exact strings and no others. Give the most prominent speakers
the most time, but let the conversation feel natural. Walk the listener through
the arc in chronological order, making clear how things developed from the
earliest episode onward. Produce the script as an ordered list of segments; each
segment has a speaker (one of {speakers}) and the spoken text.

Narrative arc:
Title: {title}
Through-line: {throughline}

Beats:
{beats}
"""


def clean_prompt(s: str | None) -> str | None:
    """Return the stripped prompt text, or ``None`` when empty/whitespace/None."""
    if s is None:
        return None
    s = s.strip()
    return s or None


_GUIDANCE_HEADER = (
    "Editorial guidance from the user — follow it where it does not conflict "
    "with producing the required structured output. Transcript lines may be "
    "prefixed with a timestamp like [MM:SS]; you may act on time references."
)


def with_guidance(
    base_user: str, *, whole: str | None = None, episode: str | None = None
) -> str:
    """Append an editorial-guidance block to a base user prompt.

    Returns ``base_user`` unchanged when no meaningful guidance is given, so
    callers that pass nothing reproduce the built-in prompt exactly.
    """
    whole = clean_prompt(whole)
    episode = clean_prompt(episode)
    if not whole and not episode:
        return base_user
    lines = [_GUIDANCE_HEADER]
    if whole:
        lines.append(f"- Whole digest: {whole}")
    if episode:
        lines.append(f"- This episode: {episode}")
    return base_user + "\n\n" + "\n".join(lines)
