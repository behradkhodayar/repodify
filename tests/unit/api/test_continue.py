"""POST /jobs/{id}/continue: merge a gate payload and enqueue resume."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from repodify.api.app import create_app
from repodify.config import Settings
from repodify.models.domain import JobOptions
from repodify.models.enums import JobStatus
from repodify.storage.filesystem import FilesystemStorage


def _resolve_fn(url, http):
    return "https://feed.example.com/feed.xml"


def _client(repo, tmp_path, enqueue=None, settings=None):
    storage = FilesystemStorage(tmp_path / "data")
    settings = settings or Settings(_env_file=None, data_dir=tmp_path / "appdata")
    app = create_app(
        repo, _resolve_fn, httpx.Client(), lambda j: None, storage, settings,
        enqueue_resume=enqueue,
    )
    return TestClient(app)


def _paused(repo, gate: str, extra: dict | None = None) -> str:
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"]))
    report = {"gate": gate, **(extra or {})}
    repo.set_report(job_id, report)
    repo.set_status(job_id, JobStatus.AWAITING_CONFIG)
    return job_id


def test_continue_rejects_when_not_paused(repo, tmp_path):
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"]))
    with httpx.Client():
        resp = _client(repo, tmp_path).post(
            f"/jobs/{job_id}/continue",
            json={"gate": "transcribe", "payload": {"mode": "local"}},
        )
    assert resp.status_code == 409


def test_continue_rejects_wrong_gate(repo, tmp_path):
    job_id = _paused(repo, "transcribe")
    resp = _client(repo, tmp_path).post(
        f"/jobs/{job_id}/continue",
        json={"gate": "diarize", "payload": {"assign_voices": False}},
    )
    assert resp.status_code == 409


def test_continue_transcribe_local_merges_options_and_enqueues(repo, tmp_path):
    job_id = _paused(repo, "transcribe")
    resumed: list[str] = []
    resp = _client(repo, tmp_path, enqueue=resumed.append).post(
        f"/jobs/{job_id}/continue",
        json={"gate": "transcribe", "payload": {"mode": "local", "model": "small"}},
    )
    assert resp.status_code == 200
    assert resumed == [job_id]
    job = repo.get_job(job_id)
    assert job.status == "queued"
    options = JobOptions.model_validate_json(job.options_json)
    assert options.transcribe is not None
    assert options.transcribe.mode == "local"
    assert options.transcribe.model == "small"
    report = json.loads(job.report_json)
    assert report["pending_resume"]["mode"] == "local"


def test_continue_byok_without_key_is_400(repo, tmp_path):
    job_id = _paused(repo, "transcribe")
    settings = Settings(_env_file=None, data_dir=tmp_path / "appdata", openrouter_api_key=None)
    resp = _client(repo, tmp_path, settings=settings).post(
        f"/jobs/{job_id}/continue",
        json={"gate": "transcribe", "payload": {"mode": "byok"}},
    )
    assert resp.status_code == 400
    assert "OPENROUTER" in resp.json()["detail"].upper() or "key" in resp.json()["detail"].lower()


def test_get_job_exposes_gate(repo, tmp_path):
    job_id = _paused(repo, "summarize")
    body = _client(repo, tmp_path).get(f"/jobs/{job_id}").json()
    assert body["status"] == "awaiting_config"
    assert body["gate"] == "summarize"
    assert "openrouter_configured" in body["gate_info"]
