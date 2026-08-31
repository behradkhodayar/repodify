import httpx
from fastapi.testclient import TestClient

from repodify.api.app import create_app
from repodify.config import Settings
from repodify.storage.filesystem import FilesystemStorage


def _resolve_fn(url, http):
    return "https://feed.example.com/feed.xml"


def _app(repo, tmp_path, static_dir=None):
    storage = FilesystemStorage(tmp_path / "data")
    settings = Settings(_env_file=None)
    return create_app(
        repo, _resolve_fn, httpx.Client(), lambda j: None, storage, settings,
        static_dir=static_dir,
    )


def test_serves_spa_when_static_dir_given(repo, tmp_path):
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>app</title>")
    client = TestClient(_app(repo, tmp_path, static_dir=static))

    root = client.get("/", follow_redirects=False)
    assert root.status_code in (307, 308)
    assert root.headers["location"] == "/app/"

    deep = client.get("/app/jobs/123")  # SPA fallback to index.html
    assert deep.status_code == 200
    assert "app" in deep.text

    # API still works.
    assert client.get("/health").status_code == 200


def test_no_static_dir_leaves_api_unchanged(repo, tmp_path):
    client = TestClient(_app(repo, tmp_path, static_dir=None))
    assert client.get("/", follow_redirects=False).status_code == 404
    assert client.get("/health").status_code == 200
