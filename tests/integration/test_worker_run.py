"""End-to-end test through the real worker composition root (`run_pipeline`).

Exercises build_deps in fake mode plus the real resolver, feed parser, and
downloader (network mocked). Only the GPU/LLM stages are faked.
"""

import respx

from podcast_compactor.config import Settings
from podcast_compactor.models.domain import JobOptions
from podcast_compactor.persistence.engine import init_db, make_engine, session_factory
from podcast_compactor.persistence.repo import JobRepository
from podcast_compactor.worker.main import run_pipeline

CASTBOX_PAGE = (
    '<html><head>'
    '<link type="application/rss+xml" href="https://feed.example.com/feed.xml">'
    '</head></html>'
)


def test_run_pipeline_fake_mode_end_to_end(tmp_path, sample_feed_xml):
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
        JobOptions(episode_ids=["ep-1", "ep-2"], target_minutes=1),
    )

    with respx.mock:
        respx.get("https://castbox.fm/channel/xyz").respond(text=CASTBOX_PAGE)
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"AUDIO-1")
        respx.get("https://cdn.example.com/ep2.mp3").respond(content=b"AUDIO-2")
        output_uri = run_pipeline(job_id, settings)

    assert output_uri.startswith("file://")
    job = repo.get_job(job_id)
    assert job.status == "completed"
    assert {a.kind for a in job.artifacts} >= {"output_audio", "show_notes"}
