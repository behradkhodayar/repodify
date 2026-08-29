from pathlib import Path

from sqlalchemy.engine import make_url

from podcast_compactor.config import Settings

# The repo root, derived from this test file (tests/unit/test_config.py -> repo).
# Persistence must anchor here regardless of the process working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _sqlite_path(database_url) -> Path:
    return Path(make_url(str(database_url)).database)


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
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
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


# Issue #27: a run launched from any working directory must use the same
# database and data dir as the API server, or its jobs never appear in the web
# UI. The default sqlite path and data dir are relative, so they used to resolve
# against the process CWD — a run from another directory got its own private
# app.db. Persistence must anchor to the project root instead.


def test_sqlite_database_path_is_absolute_and_cwd_independent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(_env_file=None)
    db = _sqlite_path(s.database_url)
    assert db.is_absolute(), f"expected an absolute sqlite path, got {db!r}"
    assert db == _REPO_ROOT / "data" / "app.db"


def test_data_dir_is_absolute_and_cwd_independent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(_env_file=None)
    assert s.data_dir.is_absolute()
    assert s.data_dir == _REPO_ROOT / "data"


def test_relative_sqlite_url_is_anchored_to_project_root(tmp_path, monkeypatch):
    # The value shipped in .env / .env.example is relative; it must still land in
    # the project data dir no matter where the process was started.
    monkeypatch.chdir(tmp_path)
    s = Settings(_env_file=None, database_url="sqlite:///./data/app.db")
    assert _sqlite_path(s.database_url) == _REPO_ROOT / "data" / "app.db"


def test_explicit_absolute_paths_are_preserved(tmp_path):
    db = tmp_path / "w.db"
    s = Settings(
        _env_file=None,
        database_url=f"sqlite:///{db}",
        data_dir=tmp_path / "d",
    )
    assert _sqlite_path(s.database_url) == db
    assert s.data_dir == tmp_path / "d"


def test_non_sqlite_url_is_left_unchanged():
    pg = "postgresql+psycopg://u:p@localhost:5432/db"
    assert str(Settings(_env_file=None, database_url=pg).database_url) == pg


def test_openrouter_is_a_valid_llm_backend():
    from podcast_compactor.config import Settings

    s = Settings(_env_file=None, llm_backend="openrouter")
    assert s.llm_backend == "openrouter"
    # Default model id is present and overridable.
    assert s.openrouter_llm_model == "openai/gpt-4o-mini"
    assert (
        Settings(_env_file=None, openrouter_llm_model="anthropic/claude-3.5-haiku").openrouter_llm_model
        == "anthropic/claude-3.5-haiku"
    )
