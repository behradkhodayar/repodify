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
