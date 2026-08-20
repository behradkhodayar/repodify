"""Request/response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ResolveRequest(BaseModel):
    url: str


class EpisodeOut(BaseModel):
    guid: str
    title: str
    published_at: datetime | None = None
    duration_s: int | None = None
    order_index: int
    is_short_or_trailer: bool


class ResolveResponse(BaseModel):
    feed_title: str
    rss_url: str
    episodes: list[EpisodeOut]


class CreateJobRequest(BaseModel):
    feed_url: str
    episode_ids: list[str]
    host_count: int = 1
    clone: bool = False
    target_minutes: int = 30


class CreateJobResponse(BaseModel):
    job_id: str


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
