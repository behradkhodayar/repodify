import httpx
import respx

from repodify.config import Settings
from repodify.models.domain import (
    ArcBeat,
    ArcOutline,
    EpisodeSummary,
    JobOptions,
    Script,
    ScriptSegment,
    Transcript,
    TranscriptSegment,
)
from repodify.pipeline.graph import build_graph
from repodify.pipeline.state import Deps
from repodify.ports.diarizer import FakeDiarizer
from repodify.ports.llm import FakeStructuredLLM
from repodify.ports.transcoder import FakeTranscoder
from repodify.ports.transcriber import FakeTranscriber
from repodify.ports.tts import FakeTTS, Voice
from repodify.ports.voice_cloner import FakeVoiceCloner
from repodify.ports.watermarker import FakeWatermarker
from repodify.storage.filesystem import FilesystemStorage


def test_pipeline_forwards_custom_prompts_to_llms(tmp_path, sample_feed_xml, repo):
    storage = FilesystemStorage(tmp_path / "data")
    transcriber = FakeTranscriber(
        Transcript(
            episode_guid="",
            segments=[TranscriptSegment(start=260.0, end=263.0, text="spoken words here")],
        )
    )
    llm_map = FakeStructuredLLM(
        [EpisodeSummary(key_points=["p1"]), EpisodeSummary(key_points=["p2"])]
    )
    arc = ArcOutline(
        title="The Arc",
        throughline="How the show evolved.",
        beats=[ArcBeat(heading="B", episode_guids=["ep-1"], narrative="It started.")],
    )
    script = Script(
        segments=[ScriptSegment(speaker="narrator", text=" ".join(["word"] * 200))]
    )
    llm_reduce = FakeStructuredLLM([arc, script])

    options = JobOptions(
        episode_ids=["ep-1", "ep-2"],
        target_minutes=1,
        custom_prompt="skip sponsor reads",
        episode_prompts={"ep-1": "cut 4:20 to 6:09"},
    )
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
            build_graph(deps).invoke(
                {
                    "job_id": job_id,
                    "feed_url": "https://castbox.fm/channel/xyz",
                    "options": options,
                },
                config={"configurable": {"thread_id": job_id}},
            )

    # ep-1's map call has whole + episode guidance and a timestamped transcript.
    ep1_user = llm_map.calls[0][1]
    assert "Whole digest: skip sponsor reads" in ep1_user
    assert "This episode: cut 4:20 to 6:09" in ep1_user
    assert "[04:20]" in ep1_user
    # ep-2 has only the whole-digest guidance (no per-episode note).
    ep2_user = llm_map.calls[1][1]
    assert "Whole digest: skip sponsor reads" in ep2_user
    assert "This episode:" not in ep2_user
    # Arc (reduce call 0) and script (reduce call 1) both carry the whole prompt.
    assert "Whole digest: skip sponsor reads" in llm_reduce.calls[0][1]
    assert "Whole digest: skip sponsor reads" in llm_reduce.calls[1][1]
