import httpx
import respx
from fastapi.testclient import TestClient

from podcast_compactor.api.app import create_app
from podcast_compactor.models.domain import JobOptions
from podcast_compactor.models.enums import JobStatus


def _resolve_fn(url, http):
    return "https://feed.example.com/feed.xml"


def test_resolve_lists_episodes_oldest_first(sample_feed_xml, repo):
    with respx.mock:
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        with httpx.Client() as http:
            app = create_app(repo, _resolve_fn, http, enqueue=lambda jid: None)
            client = TestClient(app)
            resp = client.post("/feeds/resolve", json={"url": "https://castbox.fm/x"})
    assert resp.status_code == 200
    titles = [e["title"] for e in resp.json()["episodes"]]
    assert titles == ["Trailer", "Episode 1: The Beginning", "Episode 2: The Middle"]


def test_create_job_enqueues_and_status_reports_queued(repo):
    enqueued: list[str] = []
    with httpx.Client() as http:
        app = create_app(repo, _resolve_fn, http, enqueue=enqueued.append)
        client = TestClient(app)
        resp = client.post(
            "/jobs",
            json={"feed_url": "https://feed", "episode_ids": ["ep-1", "ep-2"]},
        )
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
        assert enqueued == [job_id]

        status = client.get(f"/jobs/{job_id}")
        assert status.status_code == 200
        assert status.json()["status"] == "queued"

        # Result is not ready for a queued job.
        assert client.get(f"/jobs/{job_id}/result").status_code == 404
        # Unknown job.
        assert client.get("/jobs/does-not-exist").status_code == 404


def test_result_returned_when_completed(repo):
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"]))
    repo.add_artifact(job_id, "output_audio", "file:///out/digest.wav")
    repo.set_report(
        job_id,
        {"show_notes": {"summary": "the story", "chapters": [{"title": "Intro", "start_s": 0.0}]}},
    )
    repo.set_status(job_id, JobStatus.COMPLETED)

    with httpx.Client() as http:
        app = create_app(repo, _resolve_fn, http, enqueue=lambda jid: None)
        client = TestClient(app)
        resp = client.get(f"/jobs/{job_id}/result")
    assert resp.status_code == 200
    body = resp.json()
    assert body["output_audio_uri"] == "file:///out/digest.wav"
    assert body["summary"] == "the story"
    assert body["chapters"][0]["title"] == "Intro"
