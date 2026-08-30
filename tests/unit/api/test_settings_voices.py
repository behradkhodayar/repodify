import httpx
from fastapi.testclient import TestClient

from podcast_compactor.api.app import create_app
from podcast_compactor.config import Settings
from podcast_compactor.persistence.engine import init_db, make_engine, session_factory
from podcast_compactor.persistence.settings_repo import SettingsRepository
from podcast_compactor.storage.filesystem import FilesystemStorage


def _resolve_fn(url, http):
    return "https://feed.example.com/feed.xml"


def _client(repo, tmp_path, settings=None, tts=None):
    engine = make_engine(f"sqlite:///{tmp_path / 'settings.db'}")
    init_db(engine)
    settings_repo = SettingsRepository(session_factory(engine))
    storage = FilesystemStorage(tmp_path / "data")
    app = create_app(
        repo,
        _resolve_fn,
        httpx.Client(),
        lambda j: None,
        storage,
        settings or Settings(_env_file=None),
        settings_repo=settings_repo,
        tts=tts,
    )
    return TestClient(app)


def test_get_voice_settings_defaults_to_empty_preferred(repo, tmp_path):
    body = _client(repo, tmp_path).get("/settings/voices").json()
    assert body["preferred_stock_voices"] == []


def test_put_voice_settings_persists_preferred(repo, tmp_path):
    client = _client(repo, tmp_path)
    resp = client.put("/settings/voices", json={"preferred_stock_voices": ["am_adam", "af_heart"]})
    assert resp.status_code == 200
    assert resp.json()["preferred_stock_voices"] == ["am_adam", "af_heart"]
    assert client.get("/settings/voices").json()["preferred_stock_voices"] == [
        "am_adam",
        "af_heart",
    ]


def test_put_voice_settings_rejects_unknown_ids(repo, tmp_path):
    resp = _client(repo, tmp_path).put(
        "/settings/voices", json={"preferred_stock_voices": ["am_adam", "not_a_voice"]}
    )
    assert resp.status_code == 422
    assert "not_a_voice" in resp.text


def test_voice_sample_returns_wav(repo, tmp_path):
    from podcast_compactor.ports.tts import FakeTTS

    client = _client(repo, tmp_path, tts=FakeTTS())
    r = client.get("/voices/af_heart/sample")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert r.content[:4] == b"RIFF"


def test_voice_sample_unknown_is_404(repo, tmp_path):
    assert _client(repo, tmp_path).get("/voices/not_a_voice/sample").status_code == 404
