"""End-to-end test of the interactive voice-review flow (`review_voices=True`).

The job pauses after diarization at `awaiting_review`; the client reads the
detected speakers, submits a voice per speaker, and the job resumes into a
speaker-preserving digest.
"""

import io
import json
import wave

import httpx
import respx
from fastapi.testclient import TestClient

from podcast_compactor.api.app import create_app
from podcast_compactor.config import Settings
from podcast_compactor.models.domain import JobOptions
from podcast_compactor.persistence.engine import init_db, make_engine, session_factory
from podcast_compactor.persistence.repo import JobRepository
from podcast_compactor.storage.filesystem import FilesystemStorage
from podcast_compactor.worker.main import run_pipeline, run_review_digest


def _resolve_fn(url, http):
    return "https://feed.example.com/feed.xml"


def test_interactive_review_pauses_then_resumes(tmp_path, sample_feed_xml):
    settings = Settings(
        _env_file=None,
        use_fakes=True,
        database_url=f"sqlite:///{tmp_path / 'w.db'}",
        data_dir=tmp_path / "data",
    )
    engine = make_engine(settings.database_url)
    init_db(engine)
    repo = JobRepository(session_factory(engine))
    storage = FilesystemStorage(settings.data_dir)
    job_id = repo.create_job(
        "https://castbox.fm/channel/xyz",
        JobOptions(episode_ids=["ep-1", "ep-2"], review_voices=True, target_minutes=1),
    )

    # --- Phase 1: ingest + diarize, then pause. ---
    castbox_page = '<link type="application/rss+xml" href="https://feed.example.com/feed.xml">'
    with respx.mock:
        respx.get("https://castbox.fm/channel/xyz").respond(text=castbox_page)
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"A1")
        respx.get("https://cdn.example.com/ep2.mp3").respond(content=b"A2")
        run_pipeline(job_id, settings)

    job = repo.get_job(job_id)
    assert job.status == "awaiting_review"
    # Diarization ran; summarize/synth did not (still pending/absent).
    states = {s.stage: s.state for s in job.stages}
    assert states.get("diarize") == "done"
    assert states.get("tts") != "done"

    enqueued: list[str] = []
    app = create_app(
        repo, _resolve_fn, httpx.Client(), lambda j: None, storage, settings,
        enqueue_resume=enqueued.append,
    )
    client = TestClient(app)

    # --- The client reads the detected cast. ---
    speakers = client.get(f"/jobs/{job_id}/speakers").json()
    assert speakers["status"] == "awaiting_review"
    ids = [s["speaker_id"] for s in speakers["speakers"]]
    assert set(ids) == {"SPEAKER_00", "SPEAKER_01"}

    # --- The client assigns a voice per speaker and resumes. ---
    resp = client.post(
        f"/jobs/{job_id}/voices",
        json={
            "voice_assignments": [
                {"speaker_id": "SPEAKER_00", "mode": "stock", "stock_voice": "af_heart"},
                {"speaker_id": "SPEAKER_01", "mode": "clone"},
            ]
        },
    )
    assert resp.status_code == 200
    assert enqueued == [job_id]  # a resume was scheduled
    job = repo.get_job(job_id)
    assert job.status == "queued"
    saved = JobOptions.model_validate_json(job.options_json)
    assert saved.preserve_speakers is True
    assert {a.speaker_id for a in saved.voice_assignments} == {"SPEAKER_00", "SPEAKER_01"}

    # --- Phase 2: resume into the digest. ---
    run_review_digest(job_id, settings)

    job = repo.get_job(job_id)
    assert job.status == "completed"
    # Only the cloned speaker produced a reference clip; the stock one did not.
    ref = {a.episode_guid for a in job.artifacts if a.kind == "reference_clip"}
    assert ref == {"SPEAKER_01"}
    # Cloned output carries the guardrails, and the script is voiced by the cast.
    notes = json.loads(storage.get_bytes(f"{job_id}/output/show_notes.json"))
    assert notes["synthetic"] is True
    script_json = json.loads(storage.get_bytes(f"{job_id}/output/script.json"))
    assert script_json["segments"][0]["speaker"] == "disclaimer"
    spoken = {s["speaker"] for s in script_json["segments"][1:]}
    assert spoken <= {"SPEAKER_00", "SPEAKER_01"} and spoken
    with wave.open(io.BytesIO(storage.get_bytes(f"{job_id}/output/digest.wav")), "rb") as w:
        assert w.getnframes() > 0
