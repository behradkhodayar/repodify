"""End-to-end test of the two-host (`host_count=2`) pipeline through run_pipeline."""

import io
import json
import wave

import respx

from repodify.config import Settings
from repodify.models.domain import JobOptions
from repodify.persistence.engine import init_db, make_engine, session_factory
from repodify.persistence.repo import JobRepository
from repodify.storage.filesystem import FilesystemStorage
from repodify.worker.main import run_pipeline

CASTBOX_PAGE = (
    '<link type="application/rss+xml" href="https://feed.example.com/feed.xml">'
)


def test_two_host_pipeline_uses_both_hosts(tmp_path, sample_feed_xml):
    settings = Settings(
        _env_file=None,
        use_fakes=True,
        database_url=f"sqlite:///{tmp_path / 'w.db'}",
        data_dir=tmp_path / "data",
    )
    engine = make_engine(settings.database_url)
    init_db(engine)
    repo = JobRepository(session_factory(engine))
    job_id = repo.create_job(
        "https://castbox.fm/channel/xyz",
        JobOptions(episode_ids=["ep-1", "ep-2"], host_count=2, target_minutes=1),
    )

    with respx.mock:
        respx.get("https://castbox.fm/channel/xyz").respond(text=CASTBOX_PAGE)
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"A1")
        respx.get("https://cdn.example.com/ep2.mp3").respond(content=b"A2")
        output_uri = run_pipeline(job_id, settings)

    assert output_uri.startswith("file://")

    job = repo.get_job(job_id)
    assert job.status == "completed"

    # Output audio is a valid, non-empty WAV.
    store = FilesystemStorage(settings.data_dir)
    with wave.open(io.BytesIO(store.get_bytes(f"{job_id}/output/digest.wav")), "rb") as w:
        assert w.getnframes() > 0

    # The persisted script actually used both distinct host voices.
    script = json.loads(store.get_bytes(f"{job_id}/output/script.json"))
    speakers = {seg["speaker"] for seg in script["segments"]}
    assert speakers == {"host_a", "host_b"}
    assert {a.kind for a in job.artifacts} >= {"output_audio", "show_notes", "script"}
