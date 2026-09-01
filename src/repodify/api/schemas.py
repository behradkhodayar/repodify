"""Request/response models for the HTTP API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, PlainSerializer

from repodify.models.domain import VoiceAssignment


def _utc_json(dt: datetime) -> str:
    """ISO-8601 UTC. SQLite round-trips as naive; treat naive values as UTC."""
    aware = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[datetime, PlainSerializer(_utc_json, return_type=str, when_used="json")]


class ResolveRequest(BaseModel):
    url: str


class EpisodeOut(BaseModel):
    guid: str
    title: str
    published_at: UtcDateTime | None = None
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
    gender: Literal["female", "male"] | None = None


class SpeakersResponse(BaseModel):
    status: str
    speakers: list[SpeakerOut]


class SubmitVoicesRequest(BaseModel):
    voice_assignments: list[VoiceAssignment]


class ContinueJobRequest(BaseModel):
    gate: Literal["transcribe", "diarize", "voices", "summarize", "tts"]
    payload: dict[str, Any] = {}


class StageOut(BaseModel):
    stage: str
    state: str
    detail: str | None = None
    started_at: UtcDateTime | None = None
    finished_at: UtcDateTime | None = None


class JobStatusResponse(BaseModel):
    id: str
    status: str
    current_stage: str | None = None
    stages: list[StageOut]
    report: dict
    gate: str | None = None
    gate_info: dict[str, Any] = {}


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
    target_minutes: int | None = None
    created_at: UtcDateTime


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


class AppSettingsResponse(BaseModel):
    """Effective Local + BYOK runtime config. Secrets are flags only."""

    whisper_model: str
    whisper_models: list[str]
    ollama_model: str
    ollama_base_url: str
    diarization_model: str
    hf_token_configured: bool
    openrouter_stt_model: str
    openrouter_llm_model: str
    openrouter_tts_model: str
    openrouter_configured: bool
    anthropic_map_model: str
    anthropic_reduce_model: str
    anthropic_configured: bool
    pyannoteai_model: str
    pyannoteai_configured: bool


class AppSettingsUpdate(BaseModel):
    """Partial update. Omitted fields stay as-is; empty secrets clear the override."""

    whisper_model: str | None = None
    ollama_model: str | None = None
    ollama_base_url: str | None = None
    diarization_model: str | None = None
    hf_token: str | None = None
    openrouter_stt_model: str | None = None
    openrouter_llm_model: str | None = None
    openrouter_tts_model: str | None = None
    openrouter_api_key: str | None = None
    map_model: str | None = None
    reduce_model: str | None = None
    anthropic_api_key: str | None = None
    pyannoteai_model: str | None = None
    pyannoteai_api_key: str | None = None
