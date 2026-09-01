import pytest

from repodify.models.db import AppSetting  # noqa: F401  (ensure the table exists)
from repodify.persistence.engine import init_db, make_engine, session_factory
from repodify.persistence.settings_repo import SettingsRepository
from repodify.ports.llm import LlmOverrides


@pytest.fixture
def settings_repo(tmp_path) -> SettingsRepository:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    return SettingsRepository(session_factory(engine))


def test_unset_overrides_read_back_as_none(settings_repo):
    ov = settings_repo.get_llm_overrides()
    assert ov == LlmOverrides()
    assert ov.llm_backend is None and ov.openrouter_llm_model is None and ov.ollama_model is None


def test_set_then_get_round_trips(settings_repo):
    settings_repo.set_llm_overrides(
        LlmOverrides(llm_backend="openrouter", openrouter_llm_model="openai/gpt-4o-mini")
    )
    ov = settings_repo.get_llm_overrides()
    assert ov.llm_backend == "openrouter"
    assert ov.openrouter_llm_model == "openai/gpt-4o-mini"
    assert ov.ollama_model is None  # never set


def test_set_upserts_and_leaves_unspecified_fields(settings_repo):
    settings_repo.set_llm_overrides(LlmOverrides(llm_backend="ollama", ollama_model="llama3"))
    # A second call changes only the backend; ollama_model (None here) is left as-is.
    settings_repo.set_llm_overrides(LlmOverrides(llm_backend="openrouter"))
    ov = settings_repo.get_llm_overrides()
    assert ov.llm_backend == "openrouter"
    assert ov.ollama_model == "llama3"


def test_preferred_stock_voices_default_empty(settings_repo):
    assert settings_repo.get_preferred_stock_voices() == []


def test_preferred_stock_voices_round_trip(settings_repo):
    settings_repo.set_preferred_stock_voices(["am_adam", "af_bella"])
    assert settings_repo.get_preferred_stock_voices() == ["am_adam", "af_bella"]


def test_preferred_stock_voices_can_clear(settings_repo):
    settings_repo.set_preferred_stock_voices(["af_heart"])
    settings_repo.set_preferred_stock_voices([])
    assert settings_repo.get_preferred_stock_voices() == []


def test_overrides_round_trip_and_partial_update(settings_repo):
    settings_repo.set_overrides({"whisper_model": "small", "ollama_model": "llama3"})
    assert settings_repo.get_overrides()["whisper_model"] == "small"
    settings_repo.set_overrides({"whisper_model": "base"})
    ov = settings_repo.get_overrides()
    assert ov["whisper_model"] == "base"
    assert ov["ollama_model"] == "llama3"


def test_empty_override_clears_key(settings_repo):
    settings_repo.set_overrides({"openrouter_api_key": "sk-or"})
    settings_repo.set_overrides({"openrouter_api_key": ""})
    assert "openrouter_api_key" not in settings_repo.get_overrides()


def test_apply_overrides_beats_env_per_field():
    from repodify.config import Settings
    from repodify.persistence.settings_repo import apply_overrides

    base = Settings(_env_file=None, whisper_model="large-v3", openrouter_api_key=None)
    eff = apply_overrides(base, {"whisper_model": "small", "openrouter_api_key": "sk-or"})
    assert eff.whisper_model == "small"
    assert eff.openrouter_api_key == "sk-or"
    assert eff.ollama_model == base.ollama_model
