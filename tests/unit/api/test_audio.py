import httpx
from fastapi.testclient import TestClient

from repodify.api.app import create_app
from repodify.config import Settings
from repodify.models.domain import JobOptions
from repodify.models.enums import JobStatus
from repodify.storage.filesystem import FilesystemStorage


def _resolve_fn(url, http):
    return "https://feed.example.com/feed.xml"


def _completed_job_with_audio(repo, storage):
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"]))
    storage.put_bytes(f"{job_id}/output/digest.wav", b"RIFF-fake-wav-bytes")
    storage.put_bytes(f"{job_id}/output/digest.mp3", b"ID3-fake-mp3-bytes!!")
    repo.set_status(job_id, JobStatus.COMPLETED)
    return job_id


def _client(repo, storage):
    settings = Settings(_env_file=None)
    return TestClient(
        create_app(repo, _resolve_fn, httpx.Client(), lambda j: None, storage, settings)
    )


def test_audio_full_download(repo, tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    job_id = _completed_job_with_audio(repo, storage)
    r = _client(repo, storage).get(f"/jobs/{job_id}/audio?format=mp3")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers.get("accept-ranges") == "bytes"
    assert r.content == b"ID3-fake-mp3-bytes!!"


def test_audio_range_request_returns_206(repo, tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    job_id = _completed_job_with_audio(repo, storage)
    r = _client(repo, storage).get(
        f"/jobs/{job_id}/audio?format=mp3", headers={"Range": "bytes=0-3"}
    )
    assert r.status_code == 206
    assert r.headers["content-range"].startswith("bytes 0-3/")
    assert r.content == b"ID3-"


def test_audio_bad_format_is_422(repo, tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    job_id = _completed_job_with_audio(repo, storage)
    assert _client(repo, storage).get(f"/jobs/{job_id}/audio?format=flac").status_code == 422


def test_audio_missing_file_is_404(repo, tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"]))
    repo.set_status(job_id, JobStatus.COMPLETED)  # completed but no files written
    assert _client(repo, storage).get(f"/jobs/{job_id}/audio?format=mp3").status_code == 404


def test_audio_not_complete_is_409(repo, tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"]))  # queued
    assert _client(repo, storage).get(f"/jobs/{job_id}/audio?format=mp3").status_code == 409
