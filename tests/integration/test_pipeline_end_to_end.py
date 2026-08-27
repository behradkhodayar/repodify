import io
import wave

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


def test_pipeline_produces_digest_end_to_end(tmp_path, sample_feed_xml, repo):
    storage = FilesystemStorage(tmp_path / "data")

    transcriber = FakeTranscriber(
        Transcript(
            episode_guid="",
            segments=[TranscriptSegment(start=0.0, end=3.0, text="some spoken words here")],
        )
    )
    # One summary per selected episode.
    llm_map = FakeStructuredLLM(
        [EpisodeSummary(key_points=["p1"]), EpisodeSummary(key_points=["p2"])]
    )
    # Reduce LLM answers the arc call, then the script call.
    arc = ArcOutline(
        title="The Arc",
        throughline="How the show evolved.",
        beats=[
            ArcBeat(heading="Beginnings", episode_guids=["ep-1"], narrative="It started."),
            ArcBeat(heading="Growth", episode_guids=["ep-2"], narrative="It grew."),
        ],
    )
    # Long enough (>= target_minutes * wpm words) that the writer accepts it in
    # one pass instead of retrying for expansion and draining the fake's queue.
    script = Script(
        segments=[
            ScriptSegment(speaker="narrator", text="welcome to the digest of the show"),
            ScriptSegment(speaker="narrator", text=" ".join(["word"] * 200)),
        ]
    )
    llm_reduce = FakeStructuredLLM([arc, script])

    options = JobOptions(episode_ids=["ep-1", "ep-2"], target_minutes=1)
    job_id = repo.create_job("https://castbox.fm/channel/xyz", options)
    settings = Settings(_env_file=None)

    def resolver_resolve(url, http):
        return "https://feed.example.com/feed.xml"

    with respx.mock:
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"AUDIO-1")
        respx.get("https://cdn.example.com/ep2.mp3").respond(content=b"AUDIO-2")
        with httpx.Client() as http:
            deps = Deps(
                resolver_resolve=resolver_resolve,
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
                settings=settings,
            )
            graph = build_graph(deps)
            final = graph.invoke(
                {
                    "job_id": job_id,
                    "feed_url": "https://castbox.fm/channel/xyz",
                    "options": options,
                },
                config={"configurable": {"thread_id": job_id}},
            )

    # A valid, non-empty WAV was produced.
    assert "output_uri" in final
    data = storage.get_bytes(f"{job_id}/output/digest.wav")
    with wave.open(io.BytesIO(data), "rb") as w:
        assert w.getnframes() > 0

    # Every stage completed.
    job = repo.get_job(job_id)
    states = {s.stage: s.state for s in job.stages}
    expected_stages = [
        "resolve", "download", "transcribe", "summarize",
        "arc", "script", "tts", "assemble",
    ]
    for stage in expected_stages:
        assert states.get(stage) == "done", f"stage {stage} was {states.get(stage)}"
    # No voice feature requested here, so diarization is skipped (no GPU cost).
    assert states.get("diarize") == "skipped"

    # Output artifact attached; both episodes were transcribed and summarized.
    kinds = {a.kind for a in job.artifacts}
    assert "output_audio" in kinds
    assert "output_audio_mp3" in kinds
    assert "show_notes" in kinds
    assert storage.get_bytes(f"{job_id}/output/digest.mp3")  # non-empty mp3 written
    assert transcriber.calls  # transcriber was actually invoked
    assert len(llm_map.calls) == 2
