import pytest

from podcast_compactor.config import Settings
from podcast_compactor.ports.llm import AnthropicStructuredLLM, OllamaStructuredLLM
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
