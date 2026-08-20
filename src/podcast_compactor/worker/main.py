"""Composition root (`build_deps`) and the arq worker task (`run_job`)."""

from __future__ import annotations

import logging

import httpx
from arq.connections import RedisSettings

from podcast_compactor.config import Settings, get_settings
from podcast_compactor.ingest.resolvers import resolve
from podcast_compactor.models.domain import JobOptions, Transcript, TranscriptSegment
from podcast_compactor.models.enums import JobStatus
from podcast_compactor.persistence.engine import init_db, make_engine, session_factory
from podcast_compactor.persistence.repo import JobRepository
from podcast_compactor.pipeline.graph import build_graph
from podcast_compactor.pipeline.state import Deps
from podcast_compactor.ports.llm import StructuredLLM
from podcast_compactor.ports.tts import FakeTTS, Voice

logger = logging.getLogger(__name__)


def _build_real_llms(settings: Settings) -> tuple[StructuredLLM, StructuredLLM]:
    """Return (llm_map, llm_reduce) for the real path per settings.llm_backend."""
    if settings.llm_backend == "ollama":
        from podcast_compactor.ports.llm import OllamaStructuredLLM

        llm = OllamaStructuredLLM(settings.ollama_model, settings.ollama_base_url)
        return llm, llm  # one local model serves both map and reduce
    from podcast_compactor.ports.llm import AnthropicStructuredLLM

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_BACKEND=anthropic")
    return (
        AnthropicStructuredLLM(settings.map_model, settings.anthropic_api_key),
        AnthropicStructuredLLM(settings.reduce_model, settings.anthropic_api_key),
    )


def build_deps(settings: Settings) -> Deps:
    """Wire the pipeline's dependencies, choosing fakes or real backends."""
    engine = make_engine(settings.database_url)
    init_db(engine)
    repo = JobRepository(session_factory(engine))
    storage = _import_filesystem_storage()(settings.data_dir)
    http = httpx.Client(timeout=60.0)

    if settings.use_fakes:
        from podcast_compactor.ports.llm import LocalStubLLM
        from podcast_compactor.ports.transcoder import FakeTranscoder
        from podcast_compactor.ports.transcriber import FakeTranscriber
        from podcast_compactor.ports.voice_cloner import FakeVoiceCloner
        from podcast_compactor.ports.watermarker import FakeWatermarker

        transcriber = FakeTranscriber(
            Transcript(
                episode_guid="",
                segments=[TranscriptSegment(start=0.0, end=5.0, text="placeholder transcript")],
            )
        )
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
        from podcast_compactor.synth.cloning import PyannoteVoiceCloner
        from podcast_compactor.synth.f5_tts import F5TTS
        from podcast_compactor.synth.transcode import FfmpegTranscoder
        from podcast_compactor.synth.watermark import AudioSealWatermarker
        from podcast_compactor.transcribe.faster_whisper import FasterWhisperTranscriber

        transcriber = FasterWhisperTranscriber(settings.whisper_model)
        llm_map, llm_reduce = _build_real_llms(settings)
        tts = F5TTS()
        voices = {
            "narrator": Voice(
                name="narrator",
                ref_audio_path=settings.narrator_ref_audio,
                ref_text=settings.narrator_ref_text,
            ),
            "host_a": Voice(
                name="host_a",
                ref_audio_path=settings.host_a_ref_audio,
                ref_text=settings.host_a_ref_text,
            ),
            "host_b": Voice(
                name="host_b",
                ref_audio_path=settings.host_b_ref_audio,
                ref_text=settings.host_b_ref_text,
            ),
        }
        voice_cloner = PyannoteVoiceCloner(transcriber, settings.hf_token)
        watermarker = AudioSealWatermarker()
        transcoder = FfmpegTranscoder()

    return Deps(
        resolver_resolve=resolve,
        http=http,
        storage=storage,
        transcriber=transcriber,
        llm_map=llm_map,
        llm_reduce=llm_reduce,
        tts=tts,
        voices=voices,
        voice_cloner=voice_cloner,
        watermarker=watermarker,
        repo=repo,
        settings=settings,
        transcoder=transcoder,
    )


def _import_filesystem_storage():
    from podcast_compactor.storage.filesystem import FilesystemStorage

    return FilesystemStorage


def run_pipeline(job_id: str, settings: Settings | None = None) -> str:
    """Run the whole pipeline for one job. Returns the output audio URI.

    Shared by the arq task and any synchronous caller (e.g. a smoke script).
    """
    settings = settings or get_settings()
    deps = build_deps(settings)
    job = deps.repo.get_job(job_id)
    options = JobOptions.model_validate_json(job.options_json)
    try:
        graph = build_graph(deps)
        final = graph.invoke(
            {"job_id": job_id, "feed_url": job.feed_url, "options": options},
            config={"configurable": {"thread_id": job_id}},
        )
        deps.repo.set_status(job_id, JobStatus.COMPLETED)
        return final.get("output_uri", "")
    except Exception:
        deps.repo.set_status(job_id, JobStatus.FAILED)
        logger.exception("job %s failed", job_id)
        raise
    finally:
        deps.http.close()


async def run_job(ctx: dict, job_id: str) -> str:
    """arq task entrypoint."""
    return run_pipeline(job_id)


class WorkerSettings:
    """arq worker configuration. Run with: `arq podcast_compactor.worker.main.WorkerSettings`."""

    functions = [run_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
