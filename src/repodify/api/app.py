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
from pydantic import ValidationError

from repodify.api.audio import audio_response
from repodify.api.auth import make_require_token
from repodify.api.schemas import (
    CandidateOut,
    ContinueJobRequest,
    CreateJobRequest,
    CreateJobResponse,
    EpisodeOut,
    JobListResponse,
    JobStatusResponse,
    JobSummaryOut,
    LlmSettingsResponse,
    LlmSettingsUpdate,
    ResolveRequest,
    ResolveResponse,
    ResultResponse,
    SearchResponse,
    SpeakerOut,
    SpeakersResponse,
    StageOut,
    StockVoiceOut,
    SubmitVoicesRequest,
    VoiceSettingsResponse,
    VoiceSettingsUpdate,
    VoicesResponse,
)
from repodify.config import Settings, get_settings
from repodify.ingest.cache import JsonCache
from repodify.ingest.feed import parse_feed
from repodify.ingest.fetch import FeedFetchError, PrivateFeedError, SsrfBlocked, fetch_feed
from repodify.ingest.identity import USER_AGENT
from repodify.ingest.normalize import identity_keys
from repodify.ingest.podcastindex import add_by_feed_url
from repodify.ingest.resolvers import resolve
from repodify.ingest.search import search_podcasts
from repodify.models.domain import JobOptions
from repodify.models.enums import JobStatus
from repodify.persistence.engine import init_db, make_engine, session_factory
from repodify.persistence.repo import JobRepository
from repodify.persistence.settings_repo import SettingsRepository
from repodify.pipeline.gates import GateError, apply_gate_payload
from repodify.ports.llm import LLM_BACKENDS, LlmOverrides, effective_llm
from repodify.ports.tts import TTS
from repodify.storage.base import Storage
from repodify.storage.filesystem import FilesystemStorage

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
    enqueue_resume: EnqueueFn | None = None,
    *,
    settings_repo: SettingsRepository | None = None,
    tts: TTS | None = None,
) -> FastAPI:
    app = FastAPI(title="Repodify")
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
    if tts is None:
        from repodify.ports.tts import FakeTTS

        sample_tts: TTS = FakeTTS()
    else:
        sample_tts = tts

    cache = JsonCache(settings.data_dir / "cache")

    @router.get("/feeds/search", response_model=SearchResponse)
    def search_feeds(q: str) -> SearchResponse:
        result = search_podcasts(q, http, settings=settings, cache=cache)
        return SearchResponse(
            query=result.query,
            kind=result.kind,
            candidates=[
                CandidateOut(
                    title=c.title,
                    author=c.author,
                    feed_url=c.feed_url,
                    artwork=c.artwork,
                    itunes_id=c.itunes_id,
                    pi_feed_id=c.pi_feed_id,
                    newest_item=c.newest_item,
                    episode_count=c.episode_count,
                    language=c.language,
                    sources=c.sources,
                    identity=identity_keys(c)[0],
                    cached=c.cached,
                    dead=c.dead,
                )
                for c in result.candidates
            ],
            degraded=result.degraded,
            cached=result.cached,
            warning=result.warning,
        )

    @router.post("/feeds/resolve", response_model=ResolveResponse)
    def resolve_feed(req: ResolveRequest) -> ResolveResponse:
        try:
            rss_url = resolve_fn(req.url, http)
            fetched = fetch_feed(rss_url, http, cache=cache)
        except SsrfBlocked as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PrivateFeedError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (FeedFetchError, httpx.HTTPError) as exc:
            raise HTTPException(status_code=502, detail=f"feed fetch failed: {exc}") from exc
        if (
            settings.podcastindex_write_key
            and settings.podcastindex_api_key
            and settings.podcastindex_api_secret
        ):
            add_by_feed_url(
                fetched.url,
                http,
                key=settings.podcastindex_api_key,
                secret=settings.podcastindex_api_secret,
            )
        feed = parse_feed(req.url, fetched.url, fetched.body)
        return ResolveResponse(
            feed_title=feed.title,
            rss_url=feed.rss_url,
            episodes=[EpisodeOut(**e.model_dump()) for e in feed.episodes],
            cached=fetched.from_cache,
        )

    @router.post("/jobs", response_model=CreateJobResponse)
    def create_job(req: CreateJobRequest) -> CreateJobResponse:
        try:
            options = JobOptions(
                episode_ids=req.episode_ids,
                host_count=req.host_count,
                clone=req.clone,
                target_minutes=req.target_minutes,
                voice_assignments=req.voice_assignments,
                preserve_speakers=req.preserve_speakers,
                review_voices=req.review_voices,
                custom_prompt=req.custom_prompt,
                episode_prompts=req.episode_prompts,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        job_id = repo.create_job(req.feed_url, options)
        enqueue(job_id)
        return CreateJobResponse(job_id=job_id)

    @router.get("/voices", response_model=VoicesResponse)
    def list_voices() -> VoicesResponse:
        from repodify.synth.stock_voices import (
            list_stock_voices,
            stock_voice_display_name,
            stock_voice_gender,
        )

        ids = list_stock_voices()
        return VoicesResponse(
            stock_voices=ids,
            voices=[
                StockVoiceOut(
                    id=vid,
                    name=stock_voice_display_name(vid),
                    gender=stock_voice_gender(vid),
                    sample_url=f"/voices/{vid}/sample",
                )
                for vid in ids
            ],
        )

    @router.get("/voices/{voice_id}/sample")
    def voice_sample(voice_id: str) -> FileResponse:
        from repodify.synth.stock_voices import STOCK_VOICES
        from repodify.synth.voice_samples import (
            ensure_voice_sample,
            resolve_sample_path,
        )

        if voice_id not in STOCK_VOICES:
            raise HTTPException(status_code=404, detail="unknown stock voice")
        ensure_voice_sample(voice_id, storage, sample_tts)
        path = resolve_sample_path(voice_id, storage)
        if path is None:
            raise HTTPException(status_code=404, detail="sample not found")
        return FileResponse(path, media_type="audio/wav", filename=f"{voice_id}.wav")

    def _llm_settings_response() -> LlmSettingsResponse:
        eff = effective_llm(settings, settings_repo.get_llm_overrides())
        return LlmSettingsResponse(
            backend=eff.backend,
            openrouter_model=eff.openrouter_model,
            ollama_model=eff.ollama_model,
            anthropic_map_model=eff.anthropic_map_model,
            anthropic_reduce_model=eff.anthropic_reduce_model,
            available_backends=list(LLM_BACKENDS),
            openrouter_configured=bool(settings.openrouter_api_key),
        )

    @router.get("/settings/llm", response_model=LlmSettingsResponse)
    def get_llm_settings() -> LlmSettingsResponse:
        if settings_repo is None:
            raise HTTPException(status_code=503, detail="settings store unavailable")
        return _llm_settings_response()

    @router.put("/settings/llm", response_model=LlmSettingsResponse)
    def put_llm_settings(req: LlmSettingsUpdate) -> LlmSettingsResponse:
        if settings_repo is None:
            raise HTTPException(status_code=503, detail="settings store unavailable")
        if req.backend is not None and req.backend not in LLM_BACKENDS:
            raise HTTPException(status_code=422, detail=f"unknown backend: {req.backend}")
        if req.backend == "openrouter" and not settings.openrouter_api_key:
            raise HTTPException(
                status_code=400, detail="OPENROUTER_API_KEY is not configured on the server"
            )
        for field in (req.openrouter_model, req.ollama_model):
            if field is not None and not field.strip():
                raise HTTPException(status_code=422, detail="model id must not be empty")
        settings_repo.set_llm_overrides(
            LlmOverrides(
                llm_backend=req.backend,
                openrouter_llm_model=req.openrouter_model,
                ollama_model=req.ollama_model,
            )
        )
        return _llm_settings_response()

    @router.get("/settings/voices", response_model=VoiceSettingsResponse)
    def get_voice_settings() -> VoiceSettingsResponse:
        if settings_repo is None:
            raise HTTPException(status_code=503, detail="settings store unavailable")
        return VoiceSettingsResponse(
            preferred_stock_voices=settings_repo.get_preferred_stock_voices()
        )

    @router.put("/settings/voices", response_model=VoiceSettingsResponse)
    def put_voice_settings(req: VoiceSettingsUpdate) -> VoiceSettingsResponse:
        if settings_repo is None:
            raise HTTPException(status_code=503, detail="settings store unavailable")
        from repodify.synth.stock_voices import list_stock_voices

        known = set(list_stock_voices())
        unknown = [v for v in req.preferred_stock_voices if v not in known]
        if unknown:
            raise HTTPException(status_code=422, detail=f"unknown stock voices: {unknown}")
        settings_repo.set_preferred_stock_voices(req.preferred_stock_voices)
        return VoiceSettingsResponse(
            preferred_stock_voices=settings_repo.get_preferred_stock_voices()
        )

    @router.get("/jobs/{job_id}/speakers", response_model=SpeakersResponse)
    def get_speakers(job_id: str) -> SpeakersResponse:
        try:
            job = repo.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        report = json.loads(job.report_json or "{}")
        speakers = [SpeakerOut(**s) for s in report.get("speakers", [])]
        return SpeakersResponse(status=job.status, speakers=speakers)

    @router.post("/jobs/{job_id}/voices", response_model=CreateJobResponse)
    def submit_voices(job_id: str, req: SubmitVoicesRequest) -> CreateJobResponse:
        try:
            job = repo.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        paused = {JobStatus.AWAITING_CONFIG.value, JobStatus.AWAITING_REVIEW.value}
        if job.status not in paused:
            raise HTTPException(status_code=409, detail="job is not awaiting voice review")

        report = json.loads(job.report_json or "{}")
        detected = {s["speaker_id"] for s in report.get("speakers", [])}
        unknown = [a.speaker_id for a in req.voice_assignments if a.speaker_id not in detected]
        if unknown:
            raise HTTPException(status_code=422, detail=f"unknown speakers: {unknown}")

        options = JobOptions.model_validate_json(job.options_json).model_copy(
            update={
                "voice_assignments": req.voice_assignments,
                "preserve_speakers": True,
            }
        )
        repo.set_options(job_id, options)
        report["pending_resume"] = {
            "voice_assignments": [a.model_dump() for a in req.voice_assignments],
        }
        repo.set_report(job_id, report)
        repo.set_status(job_id, JobStatus.QUEUED)
        (enqueue_resume or enqueue)(job_id)
        return CreateJobResponse(job_id=job_id)

    def _require_byok_key(gate: str, payload: dict) -> None:
        if payload.get("mode") != "byok":
            return
        backend = payload.get("backend")
        if gate in ("transcribe", "tts") or backend == "openrouter":
            if not settings.openrouter_api_key:
                raise HTTPException(
                    status_code=400,
                    detail="OPENROUTER_API_KEY is not configured on the server",
                )
        elif gate == "diarize":
            if not settings.pyannoteai_api_key:
                raise HTTPException(
                    status_code=400,
                    detail="PYANNOTEAI_API_KEY is not configured on the server",
                )
        elif gate == "summarize" and backend == "anthropic":
            if not settings.anthropic_api_key:
                raise HTTPException(
                    status_code=400,
                    detail="ANTHROPIC_API_KEY is not configured on the server",
                )

    @router.post("/jobs/{job_id}/continue", response_model=CreateJobResponse)
    def continue_job(job_id: str, req: ContinueJobRequest) -> CreateJobResponse:
        try:
            job = repo.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        paused = {JobStatus.AWAITING_CONFIG.value, JobStatus.AWAITING_REVIEW.value}
        if job.status not in paused:
            raise HTTPException(status_code=409, detail="job is not awaiting configuration")
        report = json.loads(job.report_json or "{}")
        current = report.get("gate")
        if current and current != req.gate:
            raise HTTPException(
                status_code=409, detail=f"job is awaiting {current}, not {req.gate}"
            )
        try:
            _require_byok_key(req.gate, req.payload)
            options = apply_gate_payload(
                JobOptions.model_validate_json(job.options_json),
                req.gate,
                req.payload,
            )
        except GateError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        repo.set_options(job_id, options)
        report["pending_resume"] = req.payload
        repo.set_report(job_id, report)
        repo.set_status(job_id, JobStatus.QUEUED)
        (enqueue_resume or enqueue)(job_id)
        return CreateJobResponse(job_id=job_id)

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
        report = json.loads(job.report_json or "{}")
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
            report=report,
            gate=report.get("gate"),
            gate_info={
                "openrouter_configured": bool(settings.openrouter_api_key),
                "anthropic_configured": bool(settings.anthropic_api_key),
                "pyannoteai_configured": bool(settings.pyannoteai_api_key),
                "hf_token_configured": bool(settings.hf_token),
                "whisper_model": settings.whisper_model,
                "ollama_model": settings.ollama_model,
                "openrouter_llm_model": settings.openrouter_llm_model,
                "openrouter_tts_model": settings.openrouter_tts_model,
                "speakers": report.get("speakers") or [],
            },
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


def _arq_enqueue_task(task: str, job_id: str) -> None:
    """Enqueue an arq task onto Redis. Opens a short-lived pool per call."""
    import asyncio

    from arq import create_pool
    from arq.connections import RedisSettings

    async def _go() -> None:
        pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        try:
            await pool.enqueue_job(task, job_id)
        finally:
            await pool.aclose()

    asyncio.run(_go())


def _arq_enqueue(job_id: str) -> None:
    _arq_enqueue_task("run_job", job_id)


def _arq_enqueue_resume(job_id: str) -> None:
    _arq_enqueue_task("resume_job", job_id)


def build_default_app() -> FastAPI:
    """Composition root for the API. Use with `uvicorn ... --factory`."""
    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    sf = session_factory(engine)
    repo = JobRepository(sf)
    settings_repo = SettingsRepository(sf)
    http = httpx.Client(timeout=60.0, headers={"User-Agent": USER_AGENT})
    storage = FilesystemStorage(settings.data_dir)
    static_dir = Path("web/dist")
    if settings.use_fakes:
        from repodify.ports.tts import FakeTTS

        sample_tts: TTS = FakeTTS()
    else:
        from repodify.synth.kokoro import KokoroTTS

        sample_tts = KokoroTTS()
    return create_app(
        repo,
        resolve,
        http,
        _arq_enqueue,
        storage,
        settings,
        static_dir=static_dir if static_dir.is_dir() else None,
        enqueue_resume=_arq_enqueue_resume,
        settings_repo=settings_repo,
        tts=sample_tts,
    )
