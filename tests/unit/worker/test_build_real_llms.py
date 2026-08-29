import pytest

from podcast_compactor.config import Settings
from podcast_compactor.ports.llm import (
    AnthropicStructuredLLM,
    LlmOverrides,
    OllamaStructuredLLM,
    OpenRouterStructuredLLM,
)
from podcast_compactor.worker.main import _build_real_llms


def test_ollama_backend_needs_no_api_key():
    settings = Settings(
        _env_file=None,
        use_fakes=False,
        llm_backend="ollama",
        ollama_model="qwen2.5-coder:7b",
        anthropic_api_key=None,
    )
    llm_map, llm_reduce = _build_real_llms(settings)
    assert isinstance(llm_map, OllamaStructuredLLM)
    assert isinstance(llm_reduce, OllamaStructuredLLM)
    # One local model serves both stages, wired from the ollama_* settings.
    assert llm_map is llm_reduce
    assert llm_map._model == "qwen2.5-coder:7b"
    assert llm_map._base_url == "http://localhost:11434"


def test_anthropic_backend_requires_api_key():
    settings = Settings(
        _env_file=None,
        use_fakes=False,
        llm_backend="anthropic",
        anthropic_api_key=None,
    )
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        _build_real_llms(settings)


def test_anthropic_backend_uses_map_and_reduce_models():
    settings = Settings(
        _env_file=None,
        use_fakes=False,
        llm_backend="anthropic",
        anthropic_api_key="sk-test",
        map_model="claude-haiku-4-5-20251001",
        reduce_model="claude-opus-4-8",
    )
    llm_map, llm_reduce = _build_real_llms(settings)
    assert isinstance(llm_map, AnthropicStructuredLLM)
    assert isinstance(llm_reduce, AnthropicStructuredLLM)
    assert llm_map._model == "claude-haiku-4-5-20251001"
    assert llm_reduce._model == "claude-opus-4-8"


def test_openrouter_backend_from_env_builds_one_model_for_both_stages():
    settings = Settings(
        _env_file=None,
        use_fakes=False,
        llm_backend="openrouter",
        openrouter_api_key="sk-or-test",
        openrouter_llm_model="openai/gpt-4o-mini",
    )
    llm_map, llm_reduce = _build_real_llms(settings)
    assert isinstance(llm_map, OpenRouterStructuredLLM)
    assert llm_map is llm_reduce  # one model serves map and reduce, like ollama
    assert llm_map._model == "openai/gpt-4o-mini"
    assert llm_map._base_url == "https://openrouter.ai/api/v1"


def test_openrouter_backend_requires_api_key():
    settings = Settings(
        _env_file=None, use_fakes=False, llm_backend="openrouter", openrouter_api_key=None
    )
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        _build_real_llms(settings)


def test_persisted_override_selects_openrouter_over_env_anthropic():
    settings = Settings(
        _env_file=None,
        use_fakes=False,
        llm_backend="anthropic",  # env default
        anthropic_api_key="sk-ant",
        openrouter_api_key="sk-or-test",
    )
    overrides = LlmOverrides(llm_backend="openrouter", openrouter_llm_model="x/y")
    llm_map, llm_reduce = _build_real_llms(settings, overrides)
    assert isinstance(llm_map, OpenRouterStructuredLLM)
    assert llm_map._model == "x/y"
