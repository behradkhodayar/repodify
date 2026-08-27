"""End-to-end test of the speaker-preserving digest (`preserve_speakers=True`).

With a diarized cast of three, the digest is voiced per speaker: the script is
labeled with the real speaker ids, each gets a reference clip cloned, and the
cloned-output guardrails (disclaimer, synthetic notes) apply.
"""

import io
import json
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
from podcast_compactor.ports.diarizer import FakeDiarizer, SpeakerTurn
from podcast_compactor.ports.llm import FakeStructuredLLM
from podcast_compactor.ports.transcoder import FakeTranscoder
from podcast_compactor.ports.transcriber import FakeTranscriber
from podcast_compactor.ports.tts import FakeTTS, Voice
from podcast_compactor.ports.voice_cloner import FakeVoiceCloner
from podcast_compactor.ports.watermarker import FakeWatermarker
from podcast_compactor.storage.filesystem import FilesystemStorage

CAST = ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"]


def test_speaker_preserving_pipeline_voices_the_real_cast(tmp_path, sample_feed_xml, repo):
    storage = FilesystemStorage(tmp_path / "data")

    transcriber = FakeTranscriber(
        Transcript(
            episode_guid="",
            segments=[
                TranscriptSegment(start=0.0, end=9.0, text="first speaker talks a while"),
                TranscriptSegment(start=10.0, end=17.0, text="second speaker responds"),
                TranscriptSegment(start=18.0, end=23.0, text="third speaker adds a point"),
            ],
        )
    )
    # Three speakers with distinct talk time -> roster order 00, 01, 02.
    diarizer = FakeDiarizer(
        canned=[
            SpeakerTurn(start=0.0, end=10.0, speaker="SPEAKER_00"),
            SpeakerTurn(start=10.0, end=18.0, speaker="SPEAKER_01"),
            SpeakerTurn(start=18.0, end=24.0, speaker="SPEAKER_02"),
        ]
    )
    llm_map = FakeStructuredLLM(
        [EpisodeSummary(key_points=["p1"]), EpisodeSummary(key_points=["p2"])]
    )
    arc = ArcOutline(
        title="The Arc",
        throughline="How it evolved.",
        beats=[ArcBeat(heading="Beginnings", episode_guids=["ep-1"], narrative="It started.")],
    )
    # A multi-voice draft that labels segments with the real cast ids, long enough
    # to clear the budget floor in one pass.
    script = Script(
        segments=[
            ScriptSegment(speaker="SPEAKER_00", text=" ".join(["word"] * 80)),
            ScriptSegment(speaker="SPEAKER_01", text=" ".join(["word"] * 70)),
            ScriptSegment(speaker="SPEAKER_02", text=" ".join(["word"] * 70)),
        ]
    )
    llm_reduce = FakeStructuredLLM([arc, script])

    options = JobOptions(
        episode_ids=["ep-1", "ep-2"],
        preserve_speakers=True,
        clone=True,  # clone every detected speaker
        target_minutes=1,
    )
    job_id = repo.create_job("https://castbox.fm/channel/xyz", options)

    with respx.mock:
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"AUDIO-1")
        respx.get("https://cdn.example.com/ep2.mp3").respond(content=b"AUDIO-2")
        with httpx.Client() as http:
            deps = Deps(
                resolver_resolve=lambda url, http: "https://feed.example.com/feed.xml",
                http=http,
                storage=storage,
                transcriber=transcriber,
                diarizer=diarizer,
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
            build_graph(deps).invoke(
                {
                    "job_id": job_id,
                    "feed_url": "https://castbox.fm/channel/xyz",
                    "options": options,
                },
                config={"configurable": {"thread_id": job_id}},
            )

    job = repo.get_job(job_id)
    states = {s.stage: s.state for s in job.stages}
    for stage in ["resolve", "download", "transcribe", "diarize", "summarize",
                  "arc", "script", "tts", "assemble"]:
        assert states.get(stage) == "done", f"stage {stage} was {states.get(stage)}"

    # A reference clip was cloned for each real cast speaker.
    ref_speakers = {a.episode_guid for a in job.artifacts if a.kind == "reference_clip"}
    assert ref_speakers == set(CAST)

    # The script is voiced by the real cast, with the AI disclaimer prepended.
    script_json = json.loads(storage.get_bytes(f"{job_id}/output/script.json"))
    assert script_json["segments"][0]["speaker"] == "disclaimer"
    spoken = {s["speaker"] for s in script_json["segments"][1:]}
    assert spoken <= set(CAST) and spoken  # every line attributed to a real speaker

    # Cloned output carries the guardrails.
    notes = json.loads(storage.get_bytes(f"{job_id}/output/show_notes.json"))
    assert notes["synthetic"] is True

    with wave.open(io.BytesIO(storage.get_bytes(f"{job_id}/output/digest.wav")), "rb") as w:
        assert w.getnframes() > 0


def test_speaker_preserving_with_stock_voices_has_no_clone_guardrails(
    tmp_path, sample_feed_xml, repo
):
    """preserve_speakers without cloning voices the cast with stock voices only."""
    storage = FilesystemStorage(tmp_path / "data")
    transcriber = FakeTranscriber(
        Transcript(
            episode_guid="",
            segments=[TranscriptSegment(start=0.0, end=9.0, text="one speaker talks")],
        )
    )
    diarizer = FakeDiarizer(
        canned=[
            SpeakerTurn(start=0.0, end=10.0, speaker="SPEAKER_00"),
            SpeakerTurn(start=10.0, end=16.0, speaker="SPEAKER_01"),
        ]
    )
    llm_map = FakeStructuredLLM(
        [EpisodeSummary(key_points=["p1"]), EpisodeSummary(key_points=["p2"])]
    )
    arc = ArcOutline(
        title="A", throughline="t",
        beats=[ArcBeat(heading="B", episode_guids=["ep-1"], narrative="n")],
    )
    script = Script(
        segments=[
            ScriptSegment(speaker="SPEAKER_00", text=" ".join(["word"] * 120)),
            ScriptSegment(speaker="SPEAKER_01", text=" ".join(["word"] * 80)),
        ]
    )
    llm_reduce = FakeStructuredLLM([arc, script])

    options = JobOptions(
        episode_ids=["ep-1", "ep-2"], preserve_speakers=True, clone=False, target_minutes=1
    )
    job_id = repo.create_job("https://castbox.fm/channel/xyz", options)

    with respx.mock:
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"AUDIO-1")
        respx.get("https://cdn.example.com/ep2.mp3").respond(content=b"AUDIO-2")
        with httpx.Client() as http:
            deps = Deps(
                resolver_resolve=lambda url, http: "https://feed.example.com/feed.xml",
                http=http, storage=storage, transcriber=transcriber, diarizer=diarizer,
                transcoder=FakeTranscoder(), llm_map=llm_map, llm_reduce=llm_reduce,
                tts=FakeTTS(), voices={"narrator": Voice(name="narrator")},
                voice_cloner=FakeVoiceCloner(), watermarker=FakeWatermarker(),
                repo=repo, settings=Settings(_env_file=None),
            )
            build_graph(deps).invoke(
                {"job_id": job_id, "feed_url": "https://castbox.fm/channel/xyz",
                 "options": options},
                config={"configurable": {"thread_id": job_id}},
            )

    job = repo.get_job(job_id)
    # Stock voices only: nothing cloned, so no clone guardrails.
    assert not [a for a in job.artifacts if a.kind == "reference_clip"]
    notes = json.loads(storage.get_bytes(f"{job_id}/output/show_notes.json"))
    assert notes["synthetic"] is False
    script_json = json.loads(storage.get_bytes(f"{job_id}/output/script.json"))
    assert script_json["segments"][0]["speaker"] != "disclaimer"
