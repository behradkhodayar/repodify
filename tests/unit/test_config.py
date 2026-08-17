from podcast_compactor.config import Settings


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("USE_FAKES", raising=False)
    monkeypatch.delenv("WPM", raising=False)
    s = Settings(_env_file=None)
    assert s.wpm == 130
    assert s.use_fakes is True
    assert str(s.database_url).startswith("sqlite")


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("WPM", "150")
    monkeypatch.setenv("USE_FAKES", "false")
    s = Settings(_env_file=None)
    assert s.wpm == 150
    assert s.use_fakes is False


def test_llm_backend_defaults_to_anthropic(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    s = Settings(_env_file=None)
    assert s.llm_backend == "anthropic"
    assert s.ollama_model == "qwen2.5-coder:7b"
    assert s.ollama_base_url == "http://localhost:11434"


def test_llm_backend_ollama_env_override(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu-host:11434")
    s = Settings(_env_file=None)
    assert s.llm_backend == "ollama"
    assert s.ollama_model == "qwen2.5:7b-instruct"
    assert s.ollama_base_url == "http://gpu-host:11434"
