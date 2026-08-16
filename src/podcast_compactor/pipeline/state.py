"""Pipeline state schema and the dependency container."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypedDict

import httpx

from podcast_compactor.config import Settings
from podcast_compactor.models.domain import (
    ArcOutline,
    Episode,
    EpisodeSummary,
    Feed,
    JobOptions,
    Script,
    Transcript,
)
from podcast_compactor.persistence.repo import JobRepository
from podcast_compactor.ports.llm import StructuredLLM
from podcast_compactor.ports.transcriber import Transcriber
from podcast_compactor.ports.tts import TTS, Voice


class PipelineState(TypedDict, total=False):
    """State threaded through the LangGraph pipeline."""

    job_id: str
    feed_url: str
    options: JobOptions
    feed: Feed
    selected: list[Episode]
    transcripts: dict[str, Transcript]
    summaries: list[EpisodeSummary]
    arc: ArcOutline
    script: Script
    output_uri: str
    report: dict


@dataclass
class Deps:
    """Everything the pipeline nodes need, wired at the composition root."""

    resolver_resolve: Callable[[str, httpx.Client], str]
    http: httpx.Client
    storage: object  # Storage protocol (avoids a hard import cycle)
    transcriber: Transcriber
    llm_map: StructuredLLM
    llm_reduce: StructuredLLM
    tts: TTS
    voices: dict[str, Voice]
    repo: JobRepository
    settings: Settings
    intro_outro: dict[str, bytes] = field(default_factory=dict)
