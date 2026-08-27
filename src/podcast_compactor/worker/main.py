"""Composition root (`build_deps`) and the arq worker task (`run_job`)."""

from __future__ import annotations

import json
import logging

import httpx
from arq.connections import RedisSettings

from podcast_compactor.config import Settings, get_settings
from podcast_compactor.ingest.resolvers import resolve
from podcast_compactor.models.domain import (
    Episode,
    Feed,
    JobOptions,
    Speaker,
    Transcript,
    TranscriptSegment,
)
from podcast_compactor.models.enums import JobStatus
from podcast_compactor.persistence.engine import init_db, make_engine, session_factory
from podcast_compactor.persistence.repo import JobRepository
from podcast_compactor.pipeline.graph import build_digest_graph, build_graph, build_ingest_graph
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


def _build_real_tts(settings: Settings):
    """Return the real TTS backend per settings.tts_backend."""
    if settings.tts_backend == "openrouter":
        from podcast_compactor.synth.openrouter_tts import OpenRouterTTS

        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required when TTS_BACKEND=openrouter")
        return OpenRouterTTS(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_tts_model,
            base_url=settings.openrouter_base_url,
        )
    from podcast_compactor.synth.f5_tts import F5TTS
    from podcast_compactor.synth.kokoro import KokoroTTS
    from podcast_compactor.synth.routing_tts import RoutingTTS

    # Cloned voices go to F5-TTS (zero-shot); stock catalog voices go to Kokoro.
    return RoutingTTS(F5TTS(), KokoroTTS())


def build_deps(settings: Settings) -> Deps:
    """Wire the pipeline's dependencies, choosing fakes or real backends."""
    engine = make_engine(settings.database_url)
    init_db(engine)
    repo = JobRepository(session_factory(engine))
    storage = _import_filesystem_storage()(settings.data_dir)
    http = httpx.Client(timeout=60.0)

    if settings.use_fakes:
        from podcast_compactor.ports.diarizer import FakeDiarizer
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
        from podcast_compactor.synth.cloning import ClipVoiceCloner
        from podcast_compactor.synth.transcode import FfmpegTranscoder
        from podcast_compactor.synth.watermark import AudioSealWatermarker
        from podcast_compactor.transcribe.diarization import PyannoteDiarizer
        from podcast_compactor.transcribe.faster_whisper import FasterWhisperTranscriber

        transcriber = FasterWhisperTranscriber(settings.whisper_model)
        diarizer = PyannoteDiarizer(settings.hf_token)
        llm_map, llm_reduce = _build_real_llms(settings)
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
    )


def _import_filesystem_storage():
    from podcast_compactor.storage.filesystem import FilesystemStorage

    return FilesystemStorage


def _ingest_state_key(job_id: str) -> str:
    return f"{job_id}/state/ingest.json"


def _dump_ingest_state(state: dict) -> bytes:
    """Serialize the pipeline state needed to resume the digest after a voice review."""
    payload = {
        "job_id": state["job_id"],
        "feed_url": state["feed_url"],
        "options": state["options"].model_dump(mode="json"),
        "feed": state["feed"].model_dump(mode="json"),
        "selected": [e.model_dump(mode="json") for e in state["selected"]],
        "transcripts": {k: v.model_dump(mode="json") for k, v in state["transcripts"].items()},
        "cast": [s.model_dump(mode="json") for s in state.get("cast", [])],
        "report": state.get("report", {}),
    }
    return json.dumps(payload).encode()


def _load_ingest_state(data: bytes) -> dict:
    p = json.loads(data)
    return {
        "job_id": p["job_id"],
        "feed_url": p["feed_url"],
        "options": JobOptions.model_validate(p["options"]),
        "feed": Feed.model_validate(p["feed"]),
        "selected": [Episode.model_validate(e) for e in p["selected"]],
        "transcripts": {k: Transcript.model_validate(v) for k, v in p["transcripts"].items()},
        "cast": [Speaker.model_validate(s) for s in p["cast"]],
        "report": p["report"],
    }


def _ingest_and_pause(deps: Deps, job_id: str, feed_url: str, options: JobOptions) -> None:
    """Run resolve→download→diarize, persist state + detected speakers, then pause."""
    final = build_ingest_graph(deps).invoke(
        {"job_id": job_id, "feed_url": feed_url, "options": options},
        config={"configurable": {"thread_id": job_id}},
    )
    report = dict(final.get("report") or {})
    report["speakers"] = [
        {"speaker_id": s.id, "speaking_seconds": s.speaking_seconds, "display_name": s.label}
        for s in final.get("cast", [])
    ]
    final["report"] = report
    deps.storage.put_bytes(_ingest_state_key(job_id), _dump_ingest_state(final))
    deps.repo.set_report(job_id, report)
    deps.repo.set_status(job_id, JobStatus.AWAITING_REVIEW)


def run_pipeline(job_id: str, settings: Settings | None = None) -> str:
    """Run one job's first phase. Returns the output audio URI (empty when paused).

    A `review_voices` job runs only up to diarization and pauses at
    `AWAITING_REVIEW`; `run_review_digest` resumes it. Every other job runs the
    whole pipeline through to completion. Shared by the arq task and synchronous
    callers (e.g. a smoke script).
    """
    settings = settings or get_settings()
    deps = build_deps(settings)
    job = deps.repo.get_job(job_id)
    options = JobOptions.model_validate_json(job.options_json)
    try:
        if options.review_voices:
            _ingest_and_pause(deps, job_id, job.feed_url, options)
            return ""
        final = build_graph(deps).invoke(
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


def run_review_digest(job_id: str, settings: Settings | None = None) -> str:
    """Resume a reviewed job: load the paused state and run the digest to completion.

    The job's options are re-read fresh, so the voice assignments submitted during
    the review take effect.
    """
    settings = settings or get_settings()
    deps = build_deps(settings)
    job = deps.repo.get_job(job_id)
    options = JobOptions.model_validate_json(job.options_json)
    try:
        state = _load_ingest_state(deps.storage.get_bytes(_ingest_state_key(job_id)))
        state["options"] = options
        final = build_digest_graph(deps).invoke(
            state, config={"configurable": {"thread_id": job_id}}
        )
        deps.repo.set_status(job_id, JobStatus.COMPLETED)
        return final.get("output_uri", "")
    except Exception:
        deps.repo.set_status(job_id, JobStatus.FAILED)
        logger.exception("job %s digest failed", job_id)
        raise
    finally:
        deps.http.close()


async def run_job(ctx: dict, job_id: str) -> str:
    """arq task entrypoint (first phase)."""
    return run_pipeline(job_id)


async def resume_job(ctx: dict, job_id: str) -> str:
    """arq task entrypoint to resume a reviewed job into its digest phase."""
    return run_review_digest(job_id)


class WorkerSettings:
    """arq worker configuration. Run with: `arq podcast_compactor.worker.main.WorkerSettings`."""

    functions = [run_job, resume_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
