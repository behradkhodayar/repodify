"""Jobs pause at each ML gate and resume from a SQLite checkpointer.

A first `run_pipeline` stops after download at the transcribe gate. A later
call with the stored resume payload continues from the checkpoint, even if
the graph object is rebuilt (simulating a process restart).
"""

from __future__ import annotations

import json

import respx

from repodify.config import Settings
from repodify.models.domain import JobOptions
from repodify.persistence.engine import init_db, make_engine, session_factory
from repodify.persistence.repo import JobRepository
from repodify.worker.main import run_pipeline

CASTBOX_PAGE = (
    "<html><head>"
    '<link type="application/rss+xml" href="https://feed.example.com/feed.xml">'
    "</head></html>"
)


def _settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        use_fakes=True,
        database_url=f"sqlite:///{tmp_path / 'w.db'}",
        data_dir=tmp_path / "data",
    )


def _repo(settings: Settings) -> JobRepository:
    engine = make_engine(settings.database_url)
    init_db(engine)
    return JobRepository(session_factory(engine))


def _mock_feed(sample_feed_xml: bytes):
    respx.get("https://castbox.fm/channel/xyz").respond(text=CASTBOX_PAGE)
    respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
    respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"AUDIO-1")
    respx.get("https://cdn.example.com/ep2.mp3").respond(content=b"AUDIO-2")


def test_run_pipeline_pauses_after_download_at_transcribe_gate(tmp_path, sample_feed_xml):
    settings = _settings(tmp_path)
    repo = _repo(settings)
    job_id = repo.create_job(
        "https://castbox.fm/channel/xyz",
        JobOptions(episode_ids=["ep-1", "ep-2"], target_minutes=1),
    )

    with respx.mock:
        _mock_feed(sample_feed_xml)
        output = run_pipeline(job_id, settings)

    assert output == ""
    job = repo.get_job(job_id)
    assert job.status == "awaiting_config"
    report = json.loads(job.report_json)
    assert report["gate"] == "transcribe"
    states = {s.stage: s.state for s in job.stages}
    assert states["resolve"] == "done"
    assert states["download"] == "done"
    assert states.get("transcribe") != "done"
    assert (settings.data_dir / "checkpoints.db").exists()


def test_resume_from_sqlite_checkpoint_after_rebuild(tmp_path, sample_feed_xml):
    """Shut the worker down at the transcribe gate; a new run_pipeline resumes it."""
    settings = _settings(tmp_path)
    repo = _repo(settings)
    job_id = repo.create_job(
        "https://castbox.fm/channel/xyz",
        JobOptions(episode_ids=["ep-1", "ep-2"], target_minutes=1),
    )

    with respx.mock:
        _mock_feed(sample_feed_xml)
        run_pipeline(job_id, settings)

        report = json.loads(repo.get_job(job_id).report_json)
        report["pending_resume"] = {"mode": "local"}
        repo.set_report(job_id, report)
        run_pipeline(job_id, settings)

    job = repo.get_job(job_id)
    assert job.status == "awaiting_config"
    report = json.loads(job.report_json)
    assert report["gate"] == "diarize"
    states = {s.stage: s.state for s in job.stages}
    assert states["transcribe"] == "done"
    assert states.get("summarize") != "done"
