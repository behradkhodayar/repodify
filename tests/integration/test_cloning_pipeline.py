"""End-to-end test of opt-in voice cloning (`clone=True`) via run_pipeline.

Verifies the guardrails end to end: a spoken disclaimer is prepended, the output
is labeled synthetic, reference clips are produced, and a valid WAV results.
"""

import io
import json
import wave

import respx

from podcast_compactor.config import Settings
from podcast_compactor.models.domain import JobOptions
from podcast_compactor.persistence.engine import init_db, make_engine, session_factory
from podcast_compactor.persistence.repo import JobRepository
from podcast_compactor.storage.filesystem import FilesystemStorage
from podcast_compactor.worker.main import run_pipeline

CASTBOX_PAGE = '<link type="application/rss+xml" href="https://feed.example.com/feed.xml">'


def test_cloning_pipeline_applies_guardrails(tmp_path, sample_feed_xml):
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
        JobOptions(episode_ids=["ep-1", "ep-2"], host_count=2, clone=True, target_minutes=1),
    )

    with respx.mock:
        respx.get("https://castbox.fm/channel/xyz").respond(text=CASTBOX_PAGE)
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"A1")
        respx.get("https://cdn.example.com/ep2.mp3").respond(content=b"A2")
        run_pipeline(job_id, settings)

    job = repo.get_job(job_id)
    assert job.status == "completed"

    # Cloning needs to know who said what, so diarization ran (not skipped).
    states = {s.stage: s.state for s in job.stages}
    assert states.get("diarize") == "done"

    store = FilesystemStorage(settings.data_dir)
    with wave.open(io.BytesIO(store.get_bytes(f"{job_id}/output/digest.wav")), "rb") as w:
        assert w.getnframes() > 0

    # Disclaimer is the first spoken segment.
    script = json.loads(store.get_bytes(f"{job_id}/output/script.json"))
    assert script["segments"][0]["speaker"] == "disclaimer"
    assert script["segments"][0]["text"] == settings.clone_disclaimer

    # Output is labeled synthetic with the disclaimer text.
    notes = json.loads(store.get_bytes(f"{job_id}/output/show_notes.json"))
    assert notes["synthetic"] is True
    assert notes["disclaimer"] == settings.clone_disclaimer

    # Reference clips were produced for both cloned hosts.
    ref_kinds = [a for a in job.artifacts if a.kind == "reference_clip"]
    assert {a.episode_guid for a in ref_kinds} == {"host_a", "host_b"}
