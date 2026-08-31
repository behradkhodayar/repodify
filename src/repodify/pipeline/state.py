"""Pipeline state schema and the dependency container."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypedDict

import httpx

from repodify.config import Settings
from repodify.models.domain import (
    ArcOutline,
    Episode,
    EpisodeSummary,
    Feed,
    JobOptions,
    Script,
    Speaker,
    Transcript,
)
from repodify.persistence.repo import JobRepository
from repodify.ports.diarizer import Diarizer
from repodify.ports.llm import StructuredLLM
from repodify.ports.transcoder import Transcoder
from repodify.ports.transcriber import Transcriber
from repodify.ports.tts import TTS, Voice
from repodify.ports.voice_cloner import VoiceCloner
from repodify.ports.watermarker import Watermarker
from repodify.storage.base import Storage


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
    cast: list[Speaker]
    output_uri: str
    report: dict


@dataclass
class Deps:
    """Everything the pipeline nodes need, wired at the composition root."""

    resolver_resolve: Callable[[str, httpx.Client], str]
    http: httpx.Client
    storage: Storage
    transcriber: Transcriber
    diarizer: Diarizer
    llm_map: StructuredLLM
    llm_reduce: StructuredLLM
    tts: TTS
    voices: dict[str, Voice]
    voice_cloner: VoiceCloner
    watermarker: Watermarker
    repo: JobRepository
    settings: Settings
    transcoder: Transcoder
    intro_outro: dict[str, bytes] = field(default_factory=dict)
    # Ordered catalog used for gender-matching / round-robin stock assignment.
    # Empty means "use the built-in catalog".
    stock_catalog: list[str] = field(default_factory=list)
