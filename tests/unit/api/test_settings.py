"""GET/PUT /settings — Local + BYOK runtime config, never leaking secrets."""

from __future__ import annotations

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
        repo,
        _resolve_fn,
        httpx.Client(),
        lambda j: None,
        storage,
        settings,
        settings_repo=settings_repo,
    )
    return TestClient(app)


def test_get_settings_returns_env_defaults(repo, tmp_path):
    settings = Settings(_env_file=None, openrouter_api_key=None, hf_token=None)
    body = _client(repo, tmp_path, settings).get("/settings").json()
    assert body["whisper_model"] == settings.whisper_model
    assert "tiny" in body["whisper_models"]
    assert body["ollama_model"] == "qwen2.5-coder:7b"
    assert body["ollama_base_url"] == "http://localhost:11434"
    assert body["openrouter_stt_model"] == "openai/whisper-large-v3"
    assert body["openrouter_llm_model"] == "openai/gpt-4o-mini"
    assert body["openrouter_tts_model"] == "fish-audio/s2.1-pro"
    assert body["openrouter_configured"] is False
    assert body["anthropic_configured"] is False
    assert body["pyannoteai_configured"] is False
    assert body["hf_token_configured"] is False


def test_get_settings_never_leaks_secrets(repo, tmp_path):
    settings = Settings(
        _env_file=None,
        openrouter_api_key="sk-or-secret",
        anthropic_api_key="sk-ant-secret",
        pyannoteai_api_key="pyannote-secret",
        hf_token="hf_secret",
    )
    resp = _client(repo, tmp_path, settings).get("/settings")
    assert resp.status_code == 200
    text = resp.text
    for secret in ("sk-or-secret", "sk-ant-secret", "pyannote-secret", "hf_secret"):
        assert secret not in text
    body = resp.json()
    assert body["openrouter_configured"] is True
    assert body["anthropic_configured"] is True
    assert body["pyannoteai_configured"] is True
    assert body["hf_token_configured"] is True
    assert "openrouter_api_key" not in body
    assert "anthropic_api_key" not in body
    assert "hf_token" not in body


def test_put_persists_local_and_byok_models(repo, tmp_path):
    settings = Settings(_env_file=None)
    client = _client(repo, tmp_path, settings)
    resp = client.put(
        "/settings",
        json={
            "whisper_model": "small",
            "ollama_model": "llama3.1:8b",
            "ollama_base_url": "http://gpu:11434",
            "openrouter_stt_model": "openai/whisper-large-v3",
            "openrouter_llm_model": "anthropic/claude-3.5-haiku",
            "openrouter_tts_model": "fish-audio/s2.1-pro",
            "map_model": "claude-haiku-4-5-20251001",
            "reduce_model": "claude-opus-4-8",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["whisper_model"] == "small"
    assert body["ollama_model"] == "llama3.1:8b"
    assert body["ollama_base_url"] == "http://gpu:11434"
    assert body["openrouter_llm_model"] == "anthropic/claude-3.5-haiku"
    assert client.get("/settings").json()["ollama_model"] == "llama3.1:8b"


def test_put_keys_set_configured_flags_without_echoing(repo, tmp_path):
    settings = Settings(_env_file=None, openrouter_api_key=None)
    client = _client(repo, tmp_path, settings)
    resp = client.put(
        "/settings",
        json={
            "openrouter_api_key": "sk-or-from-ui",
            "hf_token": "hf_from_ui",
        },
    )
    assert resp.status_code == 200
    assert "sk-or-from-ui" not in resp.text
    assert "hf_from_ui" not in resp.text
    body = resp.json()
    assert body["openrouter_configured"] is True
    assert body["hf_token_configured"] is True
    assert client.get("/settings").json()["openrouter_configured"] is True


def test_put_openrouter_key_unlocks_llm_backend(repo, tmp_path):
    settings = Settings(_env_file=None, openrouter_api_key=None)
    client = _client(repo, tmp_path, settings)
    assert client.put("/settings/llm", json={"backend": "openrouter"}).status_code == 400
    assert client.put("/settings", json={"openrouter_api_key": "sk-or-ui"}).status_code == 200
    resp = client.put("/settings/llm", json={"backend": "openrouter"})
    assert resp.status_code == 200
    assert resp.json()["backend"] == "openrouter"


def test_put_rejects_unknown_whisper_model(repo, tmp_path):
    settings = Settings(_env_file=None)
    client = _client(repo, tmp_path, settings)
    resp = client.put("/settings", json={"whisper_model": "huge-v4"})
    assert resp.status_code == 422


def test_put_rejects_blank_model_ids(repo, tmp_path):
    settings = Settings(_env_file=None)
    client = _client(repo, tmp_path, settings)
    assert client.put("/settings", json={"ollama_model": "  "}).status_code == 422
    assert client.put("/settings", json={"openrouter_llm_model": ""}).status_code == 422
