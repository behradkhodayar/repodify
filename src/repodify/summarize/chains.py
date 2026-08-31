"""Summarization chains: per-episode map and cross-episode arc reduce."""

from __future__ import annotations

from repodify.models.domain import ArcOutline, EpisodeSummary, Transcript
from repodify.ports.llm import StructuredLLM
from repodify.summarize import prompts


def summarize_episode(
    transcript: Transcript,
    title: str,
    order_index: int,
    llm: StructuredLLM,
    *,
    whole_prompt: str | None = None,
    episode_prompt: str | None = None,
) -> EpisodeSummary:
    """Summarize one episode transcript into a structured `EpisodeSummary`.

    When either prompt carries guidance, the transcript is rendered with
    timestamps so time references are meaningful, and the guidance is appended to
    the user prompt. With no guidance, the input and prompt are unchanged.
    """
    whole = prompts.clean_prompt(whole_prompt)
    episode = prompts.clean_prompt(episode_prompt)
    if whole or episode:
        transcript_text = transcript.speaker_labeled_text_timestamped()
    else:
        transcript_text = transcript.speaker_labeled_text
    user = prompts.EPISODE_USER.format(title=title, transcript=transcript_text)
    user = prompts.with_guidance(user, whole=whole, episode=episode)
    summary = llm.generate(prompts.EPISODE_SYSTEM, user, EpisodeSummary)
    # The model summarizes content; identity fields are authoritative from us.
    return summary.model_copy(
        update={
            "episode_guid": transcript.episode_guid,
            "title": title,
            "order_index": order_index,
        }
    )


def _format_summaries(summaries: list[EpisodeSummary]) -> str:
    blocks = []
    for s in summaries:
        blocks.append(
            f"[{s.order_index}] guid={s.episode_guid} — {s.title}\n"
            f"  key_points: {s.key_points}\n"
            f"  themes: {s.themes}\n"
            f"  timeline_markers: {s.timeline_markers}"
        )
    return "\n\n".join(blocks)


def synthesize_arc(
    summaries: list[EpisodeSummary],
    llm: StructuredLLM,
    *,
    whole_prompt: str | None = None,
) -> ArcOutline:
    """Combine per-episode summaries into one chronological narrative arc."""
    ordered = sorted(summaries, key=lambda s: s.order_index)
    user = prompts.ARC_USER.format(summaries=_format_summaries(ordered))
    user = prompts.with_guidance(user, whole=whole_prompt)
    return llm.generate(prompts.ARC_SYSTEM, user, ArcOutline)
