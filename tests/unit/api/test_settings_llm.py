import httpx
from fastapi.testclient import TestClient

from repodify.api.app import create_app
from repodify.config import Settings
from repodify.persistence.engine import init_db, make_engine, session_factory
from repodify.persistence.settings_repo import SettingsRepository
from repodify.storage.filesystem import FilesystemStorage


def _resolve_fn(url, http):
    return "https://feed.example.com/feed.xml"


def _client(repo, tmp_path, settings):
    engine = make_engine(f"sqlite:///{tmp_path / 'settings.db'}")
    init_db(engine)
    settings_repo = SettingsRepository(session_factory(engine))
    storage = FilesystemStorage(tmp_path / "data")
    app = create_app(
        repo, _resolve_fn, httpx.Client(), lambda j: None, storage, settings,
        settings_repo=settings_repo,
    )
    return TestClient(app)


def test_get_settings_llm_returns_env_defaults(repo, tmp_path):
    settings = Settings(_env_file=None, llm_backend="anthropic", openrouter_api_key=None)
    client = _client(repo, tmp_path, settings)
    body = client.get("/settings/llm").json()
    assert body["backend"] == "anthropic"
    assert body["openrouter_model"] == "openai/gpt-4o-mini"
    assert body["available_backends"] == ["anthropic", "ollama", "openrouter"]
    assert body["openrouter_configured"] is False


def test_get_settings_llm_never_leaks_secrets(repo, tmp_path):
    settings = Settings(
        _env_file=None, openrouter_api_key="sk-or-secret", anthropic_api_key="sk-ant"
    )
    client = _client(repo, tmp_path, settings)
    resp = client.get("/settings/llm")
    assert "sk-or-secret" not in resp.text
    assert "sk-ant" not in resp.text
    assert resp.json()["openrouter_configured"] is True


def test_put_persists_and_is_reflected(repo, tmp_path):
    settings = Settings(_env_file=None, openrouter_api_key="sk-or-secret")
    client = _client(repo, tmp_path, settings)
    resp = client.put(
        "/settings/llm",
        json={"backend": "openrouter", "openrouter_model": "anthropic/claude-3.5-haiku"},
    )
    assert resp.status_code == 200
    assert resp.json()["backend"] == "openrouter"
    assert client.get("/settings/llm").json()["openrouter_model"] == "anthropic/claude-3.5-haiku"


def test_put_openrouter_without_key_is_rejected(repo, tmp_path):
    settings = Settings(_env_file=None, openrouter_api_key=None)
    client = _client(repo, tmp_path, settings)
    resp = client.put("/settings/llm", json={"backend": "openrouter"})
    assert resp.status_code == 400
    assert "OPENROUTER_API_KEY" in resp.text


def test_put_rejects_unknown_backend(repo, tmp_path):
    settings = Settings(_env_file=None)
    client = _client(repo, tmp_path, settings)
    assert client.put("/settings/llm", json={"backend": "not-a-backend"}).status_code == 422


def test_put_rejects_whitespace_model(repo, tmp_path):
    settings = Settings(_env_file=None, openrouter_api_key="sk-or-secret")
    client = _client(repo, tmp_path, settings)
    assert client.put("/settings/llm", json={"openrouter_model": "   "}).status_code == 422
    assert client.put("/settings/llm", json={"ollama_model": ""}).status_code == 422
