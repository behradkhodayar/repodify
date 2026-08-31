"""Request/response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from repodify.models.domain import VoiceAssignment


class ResolveRequest(BaseModel):
    url: str


class EpisodeOut(BaseModel):
    guid: str
    title: str
    published_at: datetime | None = None
    duration_s: int | None = None
    order_index: int
    is_short_or_trailer: bool


class CandidateOut(BaseModel):
    title: str
    author: str = ""
    feed_url: str
    artwork: str | None = None
    itunes_id: int | None = None
    pi_feed_id: int | None = None
    newest_item: int | None = None
    episode_count: int | None = None
    language: str | None = None
    sources: list[str] = Field(default_factory=list)
    identity: str
    cached: bool = False
    dead: bool = False


class SearchResponse(BaseModel):
    query: str
    kind: str
    candidates: list[CandidateOut]
    degraded: bool = False
    cached: bool = False
    warning: str | None = None


class ResolveResponse(BaseModel):
    feed_title: str
    rss_url: str
    episodes: list[EpisodeOut]
    cached: bool = False


class CreateJobRequest(BaseModel):
    feed_url: str
    episode_ids: list[str]
    host_count: int = 1
    clone: bool = False
    target_minutes: int = 30
    voice_assignments: list[VoiceAssignment] = []
    preserve_speakers: bool = False
    review_voices: bool = False
    custom_prompt: str | None = None
    episode_prompts: dict[str, str] = {}


class CreateJobResponse(BaseModel):
    job_id: str


class StockVoiceOut(BaseModel):
    id: str
    name: str
    gender: Literal["female", "male"] | None = None
    sample_url: str


class VoicesResponse(BaseModel):
    stock_voices: list[str]
    voices: list[StockVoiceOut] = []


class VoiceSettingsResponse(BaseModel):
    preferred_stock_voices: list[str]


class VoiceSettingsUpdate(BaseModel):
    preferred_stock_voices: list[str]


class SpeakerOut(BaseModel):
    speaker_id: str
    speaking_seconds: float = 0.0
    display_name: str | None = None


class SpeakersResponse(BaseModel):
    status: str
    speakers: list[SpeakerOut]


class SubmitVoicesRequest(BaseModel):
    voice_assignments: list[VoiceAssignment]


class StageOut(BaseModel):
    stage: str
    state: str
    detail: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobStatusResponse(BaseModel):
    id: str
    status: str
    current_stage: str | None = None
    stages: list[StageOut]
    report: dict


class ChapterOut(BaseModel):
    title: str
    start_s: float


class ResultResponse(BaseModel):
    audio_mp3_url: str
    audio_wav_url: str
    summary: str
    chapters: list[ChapterOut]


class JobSummaryOut(BaseModel):
    id: str
    status: str
    current_stage: str | None = None
    target_minutes: int
    created_at: datetime


class JobListResponse(BaseModel):
    jobs: list[JobSummaryOut]
    total: int


class LlmSettingsResponse(BaseModel):
    backend: str
    openrouter_model: str
    ollama_model: str
    anthropic_map_model: str
    anthropic_reduce_model: str
    available_backends: list[str]
    openrouter_configured: bool


class LlmSettingsUpdate(BaseModel):
    backend: str | None = None
    openrouter_model: str | None = None
    ollama_model: str | None = None
