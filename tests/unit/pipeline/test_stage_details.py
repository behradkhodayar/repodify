"""Pipeline nodes write live and finish details onto each stage row."""

from __future__ import annotations

import re

import httpx
import respx

from podcast_compactor.config import Settings
from podcast_compactor.models.domain import (
    ArcBeat,
    ArcOutline,
    EpisodeSummary,
    JobOptions,
    Script,
    ScriptSegment,
    Transcript,
    TranscriptSegment,
)
from podcast_compactor.models.enums import StageName
from podcast_compactor.pipeline.graph import build_graph
from podcast_compactor.pipeline.state import Deps
from podcast_compactor.ports.diarizer import FakeDiarizer
from podcast_compactor.ports.llm import FakeStructuredLLM
from podcast_compactor.ports.transcoder import FakeTranscoder
from podcast_compactor.ports.transcriber import FakeTranscriber
from podcast_compactor.ports.tts import FakeTTS, Voice
from podcast_compactor.ports.voice_cloner import FakeVoiceCloner
from podcast_compactor.ports.watermarker import FakeWatermarker
from podcast_compactor.storage.filesystem import FilesystemStorage


def _script() -> Script:
    return Script(
        segments=[
            ScriptSegment(speaker="narrator", text="welcome to the digest of the show"),
            ScriptSegment(speaker="narrator", text=" ".join(["word"] * 200)),
        ]
    )


def _arc() -> ArcOutline:
    return ArcOutline(
        title="The Arc",
        throughline="How the show evolved.",
        beats=[
            ArcBeat(heading="Beginnings", episode_guids=["ep-1"], narrative="It started."),
            ArcBeat(heading="Growth", episode_guids=["ep-2"], narrative="It grew."),
        ],
    )


def _run_pipeline(tmp_path, sample_feed_xml, repo, *, clone=False, live=None):
    storage = FilesystemStorage(tmp_path / "data")
    transcriber = FakeTranscriber(
        Transcript(
            episode_guid="",
            segments=[TranscriptSegment(start=0.0, end=3.0, text="some spoken words here")],
        )
    )
    llm_map = FakeStructuredLLM(
        [EpisodeSummary(key_points=["p1"]), EpisodeSummary(key_points=["p2"])]
    )
    llm_reduce = FakeStructuredLLM([_arc(), _script()])
    options = JobOptions(episode_ids=["ep-1", "ep-2"], target_minutes=1, clone=clone)
    job_id = repo.create_job("https://castbox.fm/channel/xyz", options)

    if live is not None:
        orig = repo.update_stage_detail

        def capture(job_id, stage, detail):
            live.append((stage, detail))
            return orig(job_id, stage, detail)

        repo.update_stage_detail = capture  # type: ignore[method-assign]

    with respx.mock:
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"AUDIO-1")
        respx.get("https://cdn.example.com/ep2.mp3").respond(content=b"AUDIO-2")
        with httpx.Client() as http:
            deps = Deps(
                resolver_resolve=lambda url, h: "https://feed.example.com/feed.xml",
                http=http,
                storage=storage,
                transcriber=transcriber,
                diarizer=FakeDiarizer(),
                transcoder=FakeTranscoder(),
                llm_map=llm_map,
                llm_reduce=llm_reduce,
                tts=FakeTTS(),
                voices={"narrator": Voice(name="narrator")},
                voice_cloner=FakeVoiceCloner(),
                watermarker=FakeWatermarker(),
                repo=repo,
                settings=Settings(_env_file=None),
            )
            graph = build_graph(deps)
            graph.invoke(
                {
                    "job_id": job_id,
                    "feed_url": "https://castbox.fm/channel/xyz",
                    "options": options,
                },
                config={"configurable": {"thread_id": job_id}},
            )
    return repo.get_job(job_id)


def _detail(job, stage: StageName) -> str | None:
    for row in job.stages:
        if row.stage == stage.value:
            return row.detail
    return None


def test_finish_details_cover_each_stage(tmp_path, sample_feed_xml, repo):
    job = _run_pipeline(tmp_path, sample_feed_xml, repo)
    assert "episodes selected" in (_detail(job, StageName.RESOLVE) or "")
    assert "downloaded" in (_detail(job, StageName.DOWNLOAD) or "")
    assert "transcribed" in (_detail(job, StageName.TRANSCRIBE) or "")
    assert "no voice feature requested" in (_detail(job, StageName.DIARIZE) or "")
    assert "summaries" in (_detail(job, StageName.SUMMARIZE) or "")
    assert "beat" in (_detail(job, StageName.ARC) or "").lower()
    assert "word" in (_detail(job, StageName.SCRIPT) or "")
    assert "segment" in (_detail(job, StageName.TTS) or "")
    assert _detail(job, StageName.ASSEMBLE)


def test_download_emits_live_episode_index(tmp_path, sample_feed_xml, repo):
    live: list[tuple] = []
    _run_pipeline(tmp_path, sample_feed_xml, repo, live=live)
    download_details = [d for stage, d in live if stage == StageName.DOWNLOAD]
    assert any(re.search(r"\d+/\d+", d) for d in download_details)


def test_diarize_finish_mentions_speakers_when_cloned(tmp_path, sample_feed_xml, repo):
    job = _run_pipeline(tmp_path, sample_feed_xml, repo, clone=True)
    detail = _detail(job, StageName.DIARIZE) or ""
    assert "cast" in detail or "speaker" in detail
