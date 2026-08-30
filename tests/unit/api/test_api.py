import httpx
import respx
from fastapi.testclient import TestClient

from podcast_compactor.api.app import create_app
from podcast_compactor.config import Settings
from podcast_compactor.models.domain import MAX_PROMPT_CHARS, JobOptions
from podcast_compactor.models.enums import JobStatus
from podcast_compactor.storage.filesystem import FilesystemStorage


def _resolve_fn(url, http):
    return "https://feed.example.com/feed.xml"


def _app(repo, http, tmp_path, enqueue=lambda jid: None, token=None):
    storage = FilesystemStorage(tmp_path / "data")
    settings = Settings(_env_file=None, api_token=token)
    return create_app(repo, _resolve_fn, http, enqueue, storage, settings)


def test_resolve_lists_episodes_oldest_first(sample_feed_xml, repo, tmp_path):
    with respx.mock:
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        with httpx.Client() as http:
            client = TestClient(_app(repo, http, tmp_path))
            resp = client.post("/feeds/resolve", json={"url": "https://castbox.fm/x"})
    assert resp.status_code == 200
    titles = [e["title"] for e in resp.json()["episodes"]]
    assert titles == ["Trailer", "Episode 1: The Beginning", "Episode 2: The Middle"]


def test_create_job_enqueues_and_status_reports_queued(repo, tmp_path):
    enqueued: list[str] = []
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path, enqueue=enqueued.append))
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
        assert client.get(f"/jobs/{job_id}/result").status_code == 409
        # Unknown job.
        assert client.get("/jobs/does-not-exist").status_code == 404


def test_result_returned_when_completed(repo, tmp_path):
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"]))
    repo.add_artifact(job_id, "output_audio", "file:///out/digest.wav")
    repo.set_report(
        job_id,
        {"show_notes": {"summary": "the story", "chapters": [{"title": "Intro", "start_s": 0.0}]}},
    )
    repo.set_status(job_id, JobStatus.COMPLETED)

    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path))
        resp = client.get(f"/jobs/{job_id}/result")
    assert resp.status_code == 200
    body = resp.json()
    assert body["audio_mp3_url"] == f"/jobs/{job_id}/audio?format=mp3"
    assert body["audio_wav_url"] == f"/jobs/{job_id}/audio?format=wav"
    assert body["summary"] == "the story"
    assert body["chapters"][0]["title"] == "Intro"


def test_health_is_unauthenticated(repo, tmp_path):
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path, token="secret"))
        assert client.get("/health").status_code == 200


def test_protected_route_requires_token(repo, tmp_path):
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path, token="secret"))
        assert client.get("/jobs/does-not-exist").status_code == 401
        ok = client.get("/jobs/does-not-exist", headers={"Authorization": "Bearer secret"})
        assert ok.status_code == 404


def test_jobs_list_returns_created_jobs(repo, tmp_path):
    repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"], target_minutes=10))
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path))
        body = client.get("/jobs").json()
    assert body["total"] == 1
    assert body["jobs"][0]["target_minutes"] == 10


def test_voices_lists_stock_catalog(repo, tmp_path):
    from podcast_compactor.synth.stock_voices import (
        list_stock_voices,
        stock_voice_display_name,
        stock_voice_gender,
    )

    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path))
        body = client.get("/voices").json()
    assert body["stock_voices"] == list_stock_voices()
    catalog = {v["id"]: v for v in body["voices"]}
    for vid in list_stock_voices():
        assert catalog[vid]["name"] == stock_voice_display_name(vid)
        assert catalog[vid]["gender"] == stock_voice_gender(vid)
        assert catalog[vid]["sample_url"] == f"/voices/{vid}/sample"
    assert catalog["af_heart"]["gender"] == "female"
    assert catalog["am_adam"]["gender"] == "male"


def test_speakers_endpoint_reports_status_and_detected_cast(repo, tmp_path):
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"], review_voices=True))
    repo.set_report(job_id, {"speakers": [{"speaker_id": "SPEAKER_00", "speaking_seconds": 12.0}]})
    from podcast_compactor.models.enums import JobStatus as _JS

    repo.set_status(job_id, _JS.AWAITING_REVIEW)
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path))
        body = client.get(f"/jobs/{job_id}/speakers").json()
    assert body["status"] == "awaiting_review"
    assert body["speakers"][0]["speaker_id"] == "SPEAKER_00"


def test_submit_voices_rejects_when_not_awaiting_review(repo, tmp_path):
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"]))
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path))
        resp = client.post(
            f"/jobs/{job_id}/voices",
            json={"voice_assignments": [{"speaker_id": "SPEAKER_00", "mode": "clone"}]},
        )
    assert resp.status_code == 409


def test_submit_voices_rejects_unknown_speaker(repo, tmp_path):
    from podcast_compactor.models.enums import JobStatus as _JS

    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"], review_voices=True))
    repo.set_report(job_id, {"speakers": [{"speaker_id": "SPEAKER_00"}]})
    repo.set_status(job_id, _JS.AWAITING_REVIEW)
    resumed: list[str] = []
    with httpx.Client() as http:
        app = create_app(
            repo, _resolve_fn, http, lambda j: None,
            FilesystemStorage(tmp_path / "data"),
            Settings(_env_file=None), enqueue_resume=resumed.append,
        )
        client = TestClient(app)
        resp = client.post(
            f"/jobs/{job_id}/voices",
            json={"voice_assignments": [{"speaker_id": "SPEAKER_99", "mode": "clone"}]},
        )
    assert resp.status_code == 422
    assert resumed == []  # nothing scheduled on a bad request


def test_create_job_persists_voice_assignments(repo, tmp_path):
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path))
        resp = client.post(
            "/jobs",
            json={
                "feed_url": "https://feed",
                "episode_ids": ["ep-1"],
                "voice_assignments": [
                    {"speaker_id": "SPEAKER_00", "mode": "stock", "stock_voice": "af_heart"}
                ],
            },
        )
    assert resp.status_code == 200
    options = JobOptions.model_validate_json(repo.get_job(resp.json()["job_id"]).options_json)
    assert options.voice_assignments[0].speaker_id == "SPEAKER_00"
    assert options.voice_assignments[0].stock_voice == "af_heart"


def test_create_job_persists_custom_prompts(repo, tmp_path):
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path))
        resp = client.post(
            "/jobs",
            json={
                "feed_url": "https://feed",
                "episode_ids": ["ep-1"],
                "custom_prompt": "skip sponsor reads",
                "episode_prompts": {"ep-1": "keep the interview"},
            },
        )
    assert resp.status_code == 200
    options = JobOptions.model_validate_json(repo.get_job(resp.json()["job_id"]).options_json)
    assert options.custom_prompt == "skip sponsor reads"
    assert options.episode_prompts == {"ep-1": "keep the interview"}


def test_create_job_rejects_over_long_custom_prompt(repo, tmp_path):
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path))
        resp = client.post(
            "/jobs",
            json={
                "feed_url": "https://feed",
                "episode_ids": ["ep-1"],
                "custom_prompt": "x" * (MAX_PROMPT_CHARS + 1),
            },
        )
    assert resp.status_code == 422


def test_create_job_rejects_over_long_episode_prompt(repo, tmp_path):
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path))
        resp = client.post(
            "/jobs",
            json={
                "feed_url": "https://feed",
                "episode_ids": ["ep-1"],
                "episode_prompts": {"ep-1": "x" * (MAX_PROMPT_CHARS + 1)},
            },
        )
    assert resp.status_code == 422
