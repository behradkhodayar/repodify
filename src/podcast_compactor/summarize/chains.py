"""Summarization chains: per-episode map and cross-episode arc reduce."""

from __future__ import annotations

from podcast_compactor.models.domain import ArcOutline, EpisodeSummary, Transcript
from podcast_compactor.ports.llm import StructuredLLM
from podcast_compactor.summarize import prompts


def summarize_episode(
    transcript: Transcript,
    title: str,
    order_index: int,
    llm: StructuredLLM,
) -> EpisodeSummary:
    """Summarize one episode transcript into a structured `EpisodeSummary`."""
    user = prompts.EPISODE_USER.format(
        title=title, transcript=transcript.speaker_labeled_text
    )
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


def synthesize_arc(summaries: list[EpisodeSummary], llm: StructuredLLM) -> ArcOutline:
    """Combine per-episode summaries into one chronological narrative arc."""
    ordered = sorted(summaries, key=lambda s: s.order_index)
    user = prompts.ARC_USER.format(summaries=_format_summaries(ordered))
    return llm.generate(prompts.ARC_SYSTEM, user, ArcOutline)
