"""The StructuredLLM port: LLM calls that return typed pydantic objects.

Keeping the pipeline behind this port means the summarize/script code never
touches raw LLM strings or a specific provider SDK, and tests can inject a fake
that returns pre-built objects.
"""

from __future__ import annotations

import re
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from podcast_compactor.config import Settings

T = TypeVar("T", bound=BaseModel)

LLM_BACKENDS: tuple[str, ...] = ("anthropic", "ollama", "openrouter")


class LlmOverrides(BaseModel):
    """Persisted, user-picked LLM settings. A None field falls back to .env."""

    llm_backend: str | None = None
    openrouter_llm_model: str | None = None
    ollama_model: str | None = None


class EffectiveLlm(BaseModel):
    """The resolved LLM config (overrides layered over .env)."""

    backend: str
    openrouter_model: str
    ollama_model: str
    anthropic_map_model: str
    anthropic_reduce_model: str


def effective_llm(settings: Settings, overrides: LlmOverrides) -> EffectiveLlm:
    """Layer persisted overrides over the env-based settings, per field."""
    return EffectiveLlm(
        backend=overrides.llm_backend or settings.llm_backend,
        openrouter_model=overrides.openrouter_llm_model or settings.openrouter_llm_model,
        ollama_model=overrides.ollama_model or settings.ollama_model,
        anthropic_map_model=settings.map_model,
        anthropic_reduce_model=settings.reduce_model,
    )


def _multivoice_labels(user: str) -> list[str]:
    """Parse the cast ids the multi-voice script prompt lists, for the fake LLM."""
    m = re.search(r"these labels:\s*([^.]+)", user)
    return [s.strip() for s in m.group(1).split(",") if s.strip()] if m else []


@runtime_checkable
class StructuredLLM(Protocol):
    """Generates a structured object of type `schema` from a prompt."""

    def generate(self, system: str, user: str, schema: type[T]) -> T: ...


class AnthropicStructuredLLM:
    """Real backend: Claude via langchain-anthropic structured output."""

    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._api_key = api_key

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        from langchain_anthropic import ChatAnthropic  # lazy import

        chat = ChatAnthropic(model=self._model, api_key=self._api_key)
        structured = chat.with_structured_output(schema)
        result = structured.invoke([("system", system), ("human", user)])
        return result  # type: ignore[return-value]


class OllamaStructuredLLM:
    """Real backend: a local Ollama model via langchain-ollama structured output."""

    def __init__(self, model: str, base_url: str) -> None:
        self._model = model
        self._base_url = base_url

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        from langchain_ollama import ChatOllama  # lazy import

        # keep_alive=0 tells the Ollama daemon to unload the model from VRAM as
        # soon as the call returns, so its memory is freed before the TTS stage
        # instead of lingering for the default 5 minutes.
        chat = ChatOllama(model=self._model, base_url=self._base_url, keep_alive=0)
        structured = chat.with_structured_output(schema)
        result = structured.invoke([("system", system), ("human", user)])
        return result  # type: ignore[return-value]


class OpenRouterStructuredLLM:
    """Real backend: a hosted model on OpenRouter via its OpenAI-compatible chat
    completions API, using langchain-openai structured output.

    The chosen model must support tool / function calling (langchain's default
    structured-output method); models without it raise at call time.
    """

    def __init__(self, model: str, api_key: str, base_url: str) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = base_url

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        from langchain_openai import ChatOpenAI  # lazy import

        chat = ChatOpenAI(model=self._model, api_key=self._api_key, base_url=self._base_url)
        structured = chat.with_structured_output(schema)
        result = structured.invoke([("system", system), ("human", user)])
        return result  # type: ignore[return-value]


class FakeStructuredLLM:
    """Test backend: returns queued responses FIFO and records calls."""

    def __init__(self, responses: list[BaseModel]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, type]] = []

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        self.calls.append((system, user, schema))
        if not self._responses:
            raise RuntimeError("FakeStructuredLLM ran out of queued responses")
        return self._responses.pop(0)  # type: ignore[return-value]


class LocalStubLLM:
    """Fake backend for running the app without an API key.

    Unlike `FakeStructuredLLM`, it fabricates a valid, non-empty instance of any
    supported schema on demand, so the whole pipeline can run in fake mode over
    an arbitrary number of episodes. Output is placeholder text, not a real
    summary.
    """

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        from podcast_compactor.models.domain import (
            ArcBeat,
            ArcOutline,
            EpisodeSummary,
            Script,
            ScriptSegment,
        )

        excerpt = " ".join(user.split()[:40])
        if schema is EpisodeSummary:
            return EpisodeSummary(key_points=[excerpt or "placeholder"])  # type: ignore[return-value]
        if schema is ArcOutline:
            return ArcOutline(  # type: ignore[return-value]
                title="Fake-mode Digest",
                throughline="A placeholder chronological digest generated in fake mode.",
                beats=[ArcBeat(heading="Overview", episode_guids=[], narrative=excerpt)],
            )
        if schema is Script:
            line = "This is a placeholder digest generated in fake mode. "
            cast = _multivoice_labels(user)
            if cast:
                # Speaker-preserving mode: emit a segment per detected cast id so the
                # multi-voice validator is satisfied in fake mode.
                return Script(  # type: ignore[return-value]
                    segments=[ScriptSegment(speaker=c, text=line * 8) for c in cast]
                )
            # Emit both hosts: single-host mode normalizes these to the narrator,
            # two-host mode uses them as-is.
            return Script(  # type: ignore[return-value]
                segments=[
                    ScriptSegment(speaker="host_a", text=line * 10),
                    ScriptSegment(speaker="host_b", text=line * 10),
                ]
            )
        return schema()  # best-effort for unknown schemas
