"""FastAPI application factory.

`create_app` takes its collaborators as arguments so tests can inject fakes and
the worker/composition root can inject real ones.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from podcast_compactor.api.audio import audio_response
from podcast_compactor.api.auth import make_require_token
from podcast_compactor.api.schemas import (
    CreateJobRequest,
    CreateJobResponse,
    EpisodeOut,
    JobListResponse,
    JobStatusResponse,
    JobSummaryOut,
    ResolveRequest,
    ResolveResponse,
    ResultResponse,
    StageOut,
    VoicesResponse,
)
from podcast_compactor.config import Settings, get_settings
from podcast_compactor.ingest.feed import parse_feed
from podcast_compactor.ingest.resolvers import resolve
from podcast_compactor.models.domain import JobOptions
from podcast_compactor.models.enums import JobStatus
from podcast_compactor.persistence.engine import init_db, make_engine, session_factory
from podcast_compactor.persistence.repo import JobRepository
from podcast_compactor.storage.base import Storage
from podcast_compactor.storage.filesystem import FilesystemStorage

ResolveFn = Callable[[str, httpx.Client], str]
EnqueueFn = Callable[[str], None]


def create_app(
    repo: JobRepository,
    resolve_fn: ResolveFn,
    http: httpx.Client,
    enqueue: EnqueueFn,
    storage: Storage,
    settings: Settings,
    static_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Podcast Compactor")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    router = APIRouter(dependencies=[Depends(make_require_token(settings.api_token))])

    @router.post("/feeds/resolve", response_model=ResolveResponse)
    def resolve_feed(req: ResolveRequest) -> ResolveResponse:
        try:
            rss_url = resolve_fn(req.url, http)
            resp = http.get(rss_url, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"feed fetch failed: {exc}") from exc
        feed = parse_feed(req.url, rss_url, resp.content)
        return ResolveResponse(
            feed_title=feed.title,
            rss_url=feed.rss_url,
            episodes=[EpisodeOut(**e.model_dump()) for e in feed.episodes],
        )

    @router.post("/jobs", response_model=CreateJobResponse)
    def create_job(req: CreateJobRequest) -> CreateJobResponse:
        options = JobOptions(
            episode_ids=req.episode_ids,
            host_count=req.host_count,
            clone=req.clone,
            target_minutes=req.target_minutes,
            voice_assignments=req.voice_assignments,
            preserve_speakers=req.preserve_speakers,
        )
        job_id = repo.create_job(req.feed_url, options)
        enqueue(job_id)
        return CreateJobResponse(job_id=job_id)

    @router.get("/voices", response_model=VoicesResponse)
    def list_voices() -> VoicesResponse:
        from podcast_compactor.synth.stock_voices import list_stock_voices

        return VoicesResponse(stock_voices=list_stock_voices())

    @router.get("/jobs", response_model=JobListResponse)
    def list_jobs(limit: int = 50, offset: int = 0) -> JobListResponse:
        jobs, total = repo.list_jobs(limit=limit, offset=offset)
        return JobListResponse(
            jobs=[
                JobSummaryOut(
                    id=j.id,
                    status=j.status,
                    current_stage=j.current_stage,
                    target_minutes=JobOptions.model_validate_json(j.options_json).target_minutes,
                    created_at=j.created_at,
                )
                for j in jobs
            ],
            total=total,
        )

    @router.get("/jobs/{job_id}", response_model=JobStatusResponse)
    def get_status(job_id: str) -> JobStatusResponse:
        try:
            job = repo.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return JobStatusResponse(
            id=job.id,
            status=job.status,
            current_stage=job.current_stage,
            stages=[
                StageOut(
                    stage=s.stage,
                    state=s.state,
                    detail=s.detail,
                    started_at=s.started_at,
                    finished_at=s.finished_at,
                )
                for s in job.stages
            ],
            report=json.loads(job.report_json or "{}"),
        )

    @router.get("/jobs/{job_id}/result", response_model=ResultResponse)
    def get_result(job_id: str) -> ResultResponse:
        job = _require_completed(repo, job_id)
        report = json.loads(job.report_json or "{}")
        show_notes = report.get("show_notes") or {}
        return ResultResponse(
            audio_mp3_url=f"/jobs/{job_id}/audio?format=mp3",
            audio_wav_url=f"/jobs/{job_id}/audio?format=wav",
            summary=show_notes.get("summary", ""),
            chapters=show_notes.get("chapters", []),
        )

    @router.get("/jobs/{job_id}/audio")
    def get_audio(job_id: str, format: str = "mp3"):
        _require_completed(repo, job_id)
        return audio_response(storage, job_id, format)

    app.include_router(router)

    if static_dir is not None and Path(static_dir).is_dir():
        index = Path(static_dir) / "index.html"

        @app.get("/")
        def _root() -> RedirectResponse:
            return RedirectResponse(url="/app/")

        @app.get("/app/{path:path}")
        def _spa(path: str) -> FileResponse:
            candidate = Path(static_dir) / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index)  # SPA client-side routing fallback

    return app


def _require_completed(repo: JobRepository, job_id: str):
    try:
        job = repo.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if job.status != JobStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="job not complete")
    return job


def _arq_enqueue(job_id: str) -> None:
    """Enqueue a job onto arq/Redis. Opens a short-lived pool per call."""
    import asyncio

    from arq import create_pool
    from arq.connections import RedisSettings

    async def _go() -> None:
        pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        try:
            await pool.enqueue_job("run_job", job_id)
        finally:
            await pool.aclose()

    asyncio.run(_go())


def build_default_app() -> FastAPI:
    """Composition root for the API. Use with `uvicorn ... --factory`."""
    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    repo = JobRepository(session_factory(engine))
    http = httpx.Client(timeout=60.0)
    storage = FilesystemStorage(settings.data_dir)
    static_dir = Path("web/dist")
    return create_app(
        repo, resolve, http, _arq_enqueue, storage, settings,
        static_dir=static_dir if static_dir.is_dir() else None,
    )
