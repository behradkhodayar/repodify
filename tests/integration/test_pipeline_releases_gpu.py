"""The pipeline must release each GPU-resident model as soon as its stage is
done, so faster-whisper, the LLM, and F5-TTS never pile up in VRAM at once.

These spies record `release()` calls; the real orchestration lives in
`pipeline/nodes.py`.
"""

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


class SpyTranscriber(FakeTranscriber):
    def __init__(self, canned):
        super().__init__(canned)
        self.releases = 0

    def release(self) -> None:
        self.releases += 1


class SpyTTS(FakeTTS):
    def __init__(self):
        super().__init__()
        self.releases = 0

    def release(self) -> None:
        self.releases += 1


def test_pipeline_releases_transcriber_and_tts(tmp_path, sample_feed_xml, repo):
    from repodify.storage.filesystem import FilesystemStorage

    storage = FilesystemStorage(tmp_path / "data")
    transcriber = SpyTranscriber(
        Transcript(
            episode_guid="",
            segments=[TranscriptSegment(start=0.0, end=3.0, text="some spoken words here")],
        )
    )
    tts = SpyTTS()
    llm_map = FakeStructuredLLM(
        [EpisodeSummary(key_points=["p1"]), EpisodeSummary(key_points=["p2"])]
    )
    arc = ArcOutline(
        title="The Arc",
        throughline="How the show evolved.",
        beats=[ArcBeat(heading="Beginnings", episode_guids=["ep-1"], narrative="It started.")],
    )
    # Long enough (>= target_minutes * wpm words) that the writer accepts it in
    # one pass instead of retrying for expansion and draining the fake's queue.
    script = Script(
        segments=[ScriptSegment(speaker="narrator", text=" ".join(["word"] * 200))]
    )
    llm_reduce = FakeStructuredLLM([arc, script])

    options = JobOptions(episode_ids=["ep-1", "ep-2"], target_minutes=1)
    job_id = repo.create_job("https://castbox.fm/channel/xyz", options)

    with respx.mock:
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"AUDIO-1")
        respx.get("https://cdn.example.com/ep2.mp3").respond(content=b"AUDIO-2")
        with httpx.Client() as http:
            deps = Deps(
                resolver_resolve=lambda url, client: "https://feed.example.com/feed.xml",
                http=http,
                storage=storage,
                transcriber=transcriber,
                diarizer=FakeDiarizer(),
                transcoder=FakeTranscoder(),
                llm_map=llm_map,
                llm_reduce=llm_reduce,
                tts=tts,
                voices={"narrator": Voice(name="narrator")},
                voice_cloner=FakeVoiceCloner(),
                watermarker=FakeWatermarker(),
                repo=repo,
                settings=Settings(_env_file=None),
            )
            build_graph(deps).invoke(
                {
                    "job_id": job_id,
                    "feed_url": "https://castbox.fm/channel/xyz",
                    "options": options,
                },
                config={"configurable": {"thread_id": job_id}},
            )

    assert transcriber.calls, "transcriber should have run"
    assert transcriber.releases >= 1, "transcriber not released after the transcribe stage"
    assert tts.releases >= 1, "TTS not released after the synth stage"
