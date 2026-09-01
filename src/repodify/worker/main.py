"""Composition root (`build_deps`) and the arq worker task (`run_job`)."""

from __future__ import annotations

import json
import logging

import httpx
from arq.connections import RedisSettings
from langgraph.types import Command

from repodify.config import Settings, get_settings
from repodify.ingest.identity import USER_AGENT
from repodify.ingest.resolvers import resolve
from repodify.models.domain import JobOptions, Transcript, TranscriptSegment
from repodify.models.enums import JobStatus
from repodify.persistence.engine import init_db, make_engine, session_factory
from repodify.persistence.repo import JobRepository
from repodify.pipeline.checkpoint import open_checkpointer
from repodify.pipeline.graph import build_graph
from repodify.pipeline.state import Deps
from repodify.ports.llm import LlmOverrides, StructuredLLM
from repodify.ports.tts import FakeTTS, Voice

logger = logging.getLogger(__name__)


def _build_real_llms(
    settings: Settings, overrides: LlmOverrides | None = None
) -> tuple[StructuredLLM, StructuredLLM]:
    """Return (llm_map, llm_reduce) for the real path per the effective backend.

    `overrides` (persisted, from the Settings page) beats `settings` (.env) per
    field; the default means "use .env".
    """
    from repodify.ports.llm import LlmOverrides, effective_llm

    effective = effective_llm(settings, overrides or LlmOverrides())

    if effective.backend == "ollama":
        from repodify.ports.llm import OllamaStructuredLLM

        llm = OllamaStructuredLLM(effective.ollama_model, settings.ollama_base_url)
        return llm, llm  # one local model serves both map and reduce

    if effective.backend == "openrouter":
        from repodify.ports.llm import OpenRouterStructuredLLM

        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required when LLM_BACKEND=openrouter")
        llm = OpenRouterStructuredLLM(
            effective.openrouter_model,
            settings.openrouter_api_key,
            settings.openrouter_base_url,
        )
        return llm, llm  # one hosted model serves both map and reduce

    from repodify.ports.llm import AnthropicStructuredLLM

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_BACKEND=anthropic")
    return (
        AnthropicStructuredLLM(effective.anthropic_map_model, settings.anthropic_api_key),
        AnthropicStructuredLLM(effective.anthropic_reduce_model, settings.anthropic_api_key),
    )


def _build_real_tts(settings: Settings):
    """Return the real TTS backend per settings.tts_backend."""
    if settings.tts_backend == "openrouter":
        from repodify.synth.openrouter_tts import OpenRouterTTS

        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required when TTS_BACKEND=openrouter")
        return OpenRouterTTS(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_tts_model,
            base_url=settings.openrouter_base_url,
        )
    from repodify.synth.f5_tts import F5TTS
    from repodify.synth.kokoro import KokoroTTS
    from repodify.synth.routing_tts import RoutingTTS

    # Cloned voices go to F5-TTS (zero-shot); stock catalog voices go to Kokoro.
    return RoutingTTS(F5TTS(), KokoroTTS())


def build_deps(settings: Settings) -> Deps:
    """Wire the pipeline's dependencies, choosing fakes or real backends."""
    from repodify.persistence.settings_repo import SettingsRepository

    engine = make_engine(settings.database_url)
    init_db(engine)
    sf = session_factory(engine)
    repo = JobRepository(sf)
    settings_repo = SettingsRepository(sf)
    storage = _import_filesystem_storage()(settings.data_dir)
    http = httpx.Client(timeout=60.0, headers={"User-Agent": USER_AGENT})

    if settings.use_fakes:
        from repodify.ports.diarizer import FakeDiarizer
        from repodify.ports.llm import LocalStubLLM
        from repodify.ports.transcoder import FakeTranscoder
        from repodify.ports.transcriber import FakeTranscriber
        from repodify.ports.voice_cloner import FakeVoiceCloner
        from repodify.ports.watermarker import FakeWatermarker

        transcriber = FakeTranscriber(
            Transcript(
                episode_guid="",
                segments=[TranscriptSegment(start=0.0, end=5.0, text="placeholder transcript")],
            )
        )
        diarizer = FakeDiarizer()
        llm_map = LocalStubLLM()
        llm_reduce = LocalStubLLM()
        tts = FakeTTS()
        voices = {
            "narrator": Voice(name="narrator"),
            "host_a": Voice(name="host_a"),
            "host_b": Voice(name="host_b"),
        }
        voice_cloner = FakeVoiceCloner()
        watermarker = FakeWatermarker()
        transcoder = FakeTranscoder()
    else:
        from repodify.synth.cloning import ClipVoiceCloner
        from repodify.synth.transcode import FfmpegTranscoder
        from repodify.synth.watermark import AudioSealWatermarker
        from repodify.transcribe.diarization import PyannoteDiarizer
        from repodify.transcribe.faster_whisper import FasterWhisperTranscriber

        transcriber = FasterWhisperTranscriber(settings.whisper_model)
        diarizer = PyannoteDiarizer(settings.hf_token, settings.diarization_model)
        llm_map, llm_reduce = _build_real_llms(settings, settings_repo.get_llm_overrides())
        tts = _build_real_tts(settings)
        # `instructions` is a fallback voice description used only by a hosted
        # backend (OpenRouter) when no reference clip is configured, so the two
        # hosts stay distinct. F5-TTS ignores it and requires a real ref clip.
        voices = {
            "narrator": Voice(
                name="narrator",
                ref_audio_path=settings.narrator_ref_audio,
                ref_text=settings.narrator_ref_text,
                instructions="a clear, professional narrator voice",
            ),
            "host_a": Voice(
                name="host_a",
                ref_audio_path=settings.host_a_ref_audio,
                ref_text=settings.host_a_ref_text,
                instructions="a deep, low-pitched, warm male podcast host",
            ),
            "host_b": Voice(
                name="host_b",
                ref_audio_path=settings.host_b_ref_audio,
                ref_text=settings.host_b_ref_text,
                instructions="a high-pitched, bright female podcast host",
            ),
        }
        voice_cloner = ClipVoiceCloner()
        watermarker = AudioSealWatermarker()
        transcoder = FfmpegTranscoder()

    from repodify.synth.stock_voices import effective_stock_catalog

    stock_catalog = effective_stock_catalog(settings_repo.get_preferred_stock_voices())

    return Deps(
        resolver_resolve=resolve,
        http=http,
        storage=storage,
        transcriber=transcriber,
        diarizer=diarizer,
        llm_map=llm_map,
        llm_reduce=llm_reduce,
        tts=tts,
        voices=voices,
        voice_cloner=voice_cloner,
        watermarker=watermarker,
        repo=repo,
        settings=settings,
        transcoder=transcoder,
        stock_catalog=stock_catalog,
    )


def apply_job_backends(deps: Deps, settings: Settings, options: JobOptions) -> Deps:
    """Swap STT/diarize/LLM/TTS for this job's local vs BYOK choices.

    Fake mode is unchanged so pytest and ``./launch --fake`` stay offline.
    """
    if settings.use_fakes:
        return deps
    if options.transcribe is not None:
        if options.transcribe.mode == "byok":
            from repodify.transcribe.openrouter import OpenRouterTranscriber

            if not settings.openrouter_api_key:
                raise RuntimeError("OPENROUTER_API_KEY is required for BYOK transcription")
            deps.transcriber = OpenRouterTranscriber(
                api_key=settings.openrouter_api_key,
                model=options.transcribe.model or "openai/whisper-large-v3",
                base_url=settings.openrouter_base_url,
            )
        else:
            from repodify.transcribe.faster_whisper import FasterWhisperTranscriber

            deps.transcriber = FasterWhisperTranscriber(
                options.transcribe.model or settings.whisper_model
            )
    if options.diarize is not None and options.assign_voices:
        if options.diarize.mode == "byok":
            from repodify.transcribe.pyannote_cloud import PyannoteCloudDiarizer

            if not settings.pyannoteai_api_key:
                raise RuntimeError("PYANNOTEAI_API_KEY is required for BYOK diarization")
            deps.diarizer = PyannoteCloudDiarizer(
                api_key=settings.pyannoteai_api_key,
                model=options.diarize.model or "community-1",
            )
        else:
            from repodify.transcribe.diarization import PyannoteDiarizer

            deps.diarizer = PyannoteDiarizer(
                settings.hf_token,
                options.diarize.model or settings.diarization_model,
            )
    if options.llm is not None:
        if options.llm.mode == "local":
            from repodify.ports.llm import LlmOverrides

            llm_map, llm_reduce = _build_real_llms(
                settings,
                LlmOverrides(llm_backend="ollama", ollama_model=options.llm.model),
            )
        else:
            from repodify.ports.llm import LlmOverrides

            backend = options.llm.backend or "openrouter"
            if backend not in ("anthropic", "openrouter"):
                raise RuntimeError(f"unknown LLM backend: {backend}")
            ov = LlmOverrides(
                llm_backend=backend,
                openrouter_llm_model=options.llm.model if backend == "openrouter" else None,
            )
            llm_map, llm_reduce = _build_real_llms(settings, ov)
        deps.llm_map = llm_map
        deps.llm_reduce = llm_reduce
    if options.tts is not None:
        if options.tts.mode == "byok":
            from repodify.synth.openrouter_tts import OpenRouterTTS

            if not settings.openrouter_api_key:
                raise RuntimeError("OPENROUTER_API_KEY is required for BYOK TTS")
            deps.tts = OpenRouterTTS(
                api_key=settings.openrouter_api_key,
                model=options.tts.model or settings.openrouter_tts_model,
                base_url=settings.openrouter_base_url,
            )
        else:
            deps.tts = _build_real_tts(
                settings.model_copy(update={"tts_backend": "f5"})
            )
    return deps


def _import_filesystem_storage():
    from repodify.storage.filesystem import FilesystemStorage

    return FilesystemStorage


def _interrupt_payload(result: dict) -> dict | None:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0]
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {"gate": str(value)}


def _paused_statuses() -> set[str]:
    return {JobStatus.AWAITING_CONFIG.value, JobStatus.AWAITING_REVIEW.value}


def run_pipeline(job_id: str, settings: Settings | None = None) -> str:
    """Run or resume one job until the next gate or completion.

    Returns the output audio URI, or ``""`` when the graph is paused at a
    local/BYOK gate (`awaiting_config`). Resume by writing ``pending_resume``
    onto the job report and calling this again (process restart is fine: the
    SQLite checkpointer holds the thread).
    """
    settings = settings or get_settings()
    deps = build_deps(settings)
    job = deps.repo.get_job(job_id)
    options = JobOptions.model_validate_json(job.options_json)
    deps = apply_job_backends(deps, settings, options)
    try:
        with open_checkpointer(settings.data_dir) as saver:
            graph = build_graph(deps, checkpointer=saver)
            config = {"configurable": {"thread_id": job_id}}
            report = json.loads(job.report_json or "{}")
            pending = report.pop("pending_resume", None)
            if pending is not None:
                deps.repo.set_report(job_id, report)
                result = graph.invoke(
                    Command(resume=pending, update={"options": options}),
                    config,
                )
            else:
                snapshot = graph.get_state(config)
                if snapshot.next:
                    if job.status in _paused_statuses():
                        return ""
                    result = graph.invoke(None, config)
                else:
                    result = graph.invoke(
                        {
                            "job_id": job_id,
                            "feed_url": job.feed_url,
                            "options": options,
                        },
                        config=config,
                    )

        gate = _interrupt_payload(result) if isinstance(result, dict) else None
        if gate is not None:
            report = dict(result.get("report") or report)
            report["gate"] = gate.get("gate")
            report["gate_payload"] = gate
            if gate.get("speakers"):
                report["speakers"] = gate["speakers"]
            deps.repo.set_report(job_id, report)
            deps.repo.set_status(job_id, JobStatus.AWAITING_CONFIG)
            return ""
        deps.repo.set_status(job_id, JobStatus.COMPLETED)
        return (result or {}).get("output_uri", "")
    except Exception:
        deps.repo.set_status(job_id, JobStatus.FAILED)
        logger.exception("job %s failed", job_id)
        raise
    finally:
        deps.http.close()


def run_review_digest(job_id: str, settings: Settings | None = None) -> str:
    """Resume a paused job. Kept as an alias for existing callers."""
    return run_pipeline(job_id, settings)


async def run_job(ctx: dict, job_id: str) -> str:
    """arq task entrypoint (first phase or resume)."""
    return run_pipeline(job_id)


async def resume_job(ctx: dict, job_id: str) -> str:
    """arq task entrypoint to resume a gated job."""
    return run_pipeline(job_id)


class WorkerSettings:
    """arq worker configuration. Run with: `arq repodify.worker.main.WorkerSettings`."""

    functions = [run_job, resume_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # Heavy ML jobs (diarization + cloning across episodes) exceed arq's 300s
    # default; size the timeout from settings and avoid retry storms.
    job_timeout = get_settings().job_timeout_seconds
    max_tries = get_settings().job_max_tries
