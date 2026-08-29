from podcast_compactor.config import Settings
from podcast_compactor.ports.llm import LLM_BACKENDS, EffectiveLlm, LlmOverrides, effective_llm


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_backend="anthropic",
        map_model="claude-haiku-4-5-20251001",
        reduce_model="claude-opus-4-8",
        ollama_model="qwen2.5-coder:7b",
        openrouter_llm_model="openai/gpt-4o-mini",
    )


def test_backends_are_the_three_supported():
    assert LLM_BACKENDS == ("anthropic", "ollama", "openrouter")


def test_no_overrides_falls_back_to_env():
    eff = effective_llm(_settings(), LlmOverrides())
    assert isinstance(eff, EffectiveLlm)
    assert eff.backend == "anthropic"
    assert eff.openrouter_model == "openai/gpt-4o-mini"
    assert eff.ollama_model == "qwen2.5-coder:7b"
    assert eff.anthropic_map_model == "claude-haiku-4-5-20251001"
    assert eff.anthropic_reduce_model == "claude-opus-4-8"


def test_override_wins_per_field():
    eff = effective_llm(
        _settings(),
        LlmOverrides(llm_backend="openrouter", openrouter_llm_model="anthropic/claude-3.5-haiku"),
    )
    assert eff.backend == "openrouter"
    assert eff.openrouter_model == "anthropic/claude-3.5-haiku"
    # Unset override field still comes from env.
    assert eff.ollama_model == "qwen2.5-coder:7b"
