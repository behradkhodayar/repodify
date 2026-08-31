# Ollama LLM backend (local, no Anthropic key)

## Goal

Let the pipeline run its LLM stages (per-episode summary "map" and cross-episode
arc/script "reduce") against a **local Ollama** model instead of the Anthropic
API, so the system can run with no `ANTHROPIC_API_KEY`. The rest of a real run
(faster-whisper STT and F5-TTS, both on GPU) is unchanged.

The Anthropic path stays the default and keeps working. Ollama is opt-in via a
single `LLM_BACKEND` toggle.

## Non-goals

- Replacing or removing the Anthropic backend.
- Per-stage Ollama model selection (map vs reduce). One `OLLAMA_MODEL` is used
  for both stages. A separate reduce model can be added later if needed (YAGNI).
- Running the Ollama LLM with faked STT/TTS. `LLM_BACKEND` is only consulted on
  the real path (`USE_FAKES=false`); fake mode remains all-fakes as today.
- Verifying the Ollama path end-to-end in CI. Ollama needs a running server and
  a pulled model; tests use mocks, and the real run happens on the user's host.

## Approach

Mirror the existing `AnthropicStructuredLLM`. The `StructuredLLM` port already
abstracts the LLM as `generate(system, user, schema) -> T` returning a typed
pydantic object, so the change is a new adapter plus wiring — no changes to the
summarize/script chains or the pipeline graph.

Structured output uses **`langchain-ollama`'s `ChatOllama.with_structured_output(schema)`**,
which passes the pydantic model's JSON schema to Ollama's `format` parameter for
schema-constrained decoding. This is the direct analog of the Anthropic adapter.

## Changes

### 1. Config — `src/repodify/config.py`

Add three settings (all env-overridable, `.env`-driven like the rest):

| Setting | Type | Default |
| --- | --- | --- |
| `llm_backend` | `Literal["anthropic", "ollama"]` | `"anthropic"` |
| `ollama_model` | `str` | `"qwen2.5-coder:7b"` |
| `ollama_base_url` | `str` | `"http://localhost:11434"` |

`map_model` / `reduce_model` are ignored when `llm_backend == "ollama"`.

### 2. Port — `src/repodify/ports/llm.py`

Add `OllamaStructuredLLM` alongside `AnthropicStructuredLLM`, same shape:

```python
class OllamaStructuredLLM:
    """Real backend: a local Ollama model via langchain-ollama structured output."""

    def __init__(self, model: str, base_url: str) -> None:
        self._model = model
        self._base_url = base_url

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        from langchain_ollama import ChatOllama  # lazy import

        chat = ChatOllama(model=self._model, base_url=self._base_url)
        structured = chat.with_structured_output(schema)
        return structured.invoke([("system", system), ("human", user)])
```

Lazy import keeps `ports/llm.py` importable without `langchain-ollama` present
(consistent with the Anthropic adapter's lazy import).

### 3. Wiring — `src/repodify/worker/main.py`

Extract LLM construction from `build_deps`' real branch into a small helper so
backend selection is testable without triggering the GPU STT/TTS imports:

```python
def _build_real_llms(settings: Settings) -> tuple[StructuredLLM, StructuredLLM]:
    """Return (map_llm, reduce_llm) for the real path, per settings.llm_backend."""
    if settings.llm_backend == "ollama":
        from repodify.ports.llm import OllamaStructuredLLM
        llm = OllamaStructuredLLM(settings.ollama_model, settings.ollama_base_url)
        return llm, llm  # one 7B model for both map and reduce
    # default: anthropic
    from repodify.ports.llm import AnthropicStructuredLLM
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_BACKEND=anthropic")
    return (
        AnthropicStructuredLLM(settings.map_model, settings.anthropic_api_key),
        AnthropicStructuredLLM(settings.reduce_model, settings.anthropic_api_key),
    )
```

`build_deps`' real branch calls `llm_map, llm_reduce = _build_real_llms(settings)`
instead of constructing the Anthropic LLMs inline. The existing
`ANTHROPIC_API_KEY is required` guard moves into the `anthropic` branch of this
helper (so it no longer fires when on Ollama). Fake mode is untouched.

Note: on Ollama, `llm_map` and `llm_reduce` are the **same** `OllamaStructuredLLM`
instance. That is safe — the adapter is stateless and constructs a fresh
`ChatOllama` per `generate` call.

### 4. Dependency — `pyproject.toml`

Add `langchain-ollama` to the **core** `dependencies` (next to
`langchain-anthropic`). It is a lightweight HTTP client for the Ollama server —
no GPU/torch — so it does not belong in the `gpu` extra.

### 5. Docs — `.env.example` and `README.md`

- `.env.example`: add `LLM_BACKEND=anthropic` (with an `ollama` comment),
  `OLLAMA_MODEL=qwen2.5-coder:7b`, `OLLAMA_BASE_URL=http://localhost:11434`, and
  a note that `ANTHROPIC_API_KEY` is not needed when `LLM_BACKEND=ollama`.
- `README.md`: a short "Local LLM via Ollama" note under the real-mode section —
  set `LLM_BACKEND=ollama`, have Ollama running with the model pulled
  (`ollama pull qwen2.5-coder:7b`), and the pipeline uses it for both LLM stages.

## Testing

- **`OllamaStructuredLLM.generate`** (`tests/`): monkeypatch the lazy
  `langchain_ollama.ChatOllama` import with a stub whose
  `.with_structured_output(schema).invoke(...)` returns a known pydantic object.
  Assert the adapter passes the configured `model` / `base_url` and returns the
  object unchanged.
- **`_build_real_llms`**: with `llm_backend="ollama"` and **no** API key, it
  returns two `OllamaStructuredLLM`-typed objects without raising; with
  `llm_backend="anthropic"` and no key, it raises `RuntimeError`; with a key, it
  returns two `AnthropicStructuredLLM` using `map_model` / `reduce_model`.
- Full existing suite still passes (fake mode is unchanged).

## Risks / caveats

- **Model quality:** `qwen2.5-coder:7b` is code-specialized. It emits valid JSON
  but narrative summaries/scripts are weaker than Claude, and small models can
  occasionally fail schema-constrained decoding on nested schemas
  (`ArcOutline`→`ArcBeat`, `Script`→`ScriptSegment`). An instruct/general 7B+ or
  larger model summarizes better. Model is a config value, so it is a one-line
  change to swap.
- **GPU memory:** on the real path, faster-whisper (large-v3, ~float16) stays
  resident in the worker while Ollama serves the LLM in its own process. Stages
  run sequentially (transcribe → summarize → script → TTS), so peak overlap is
  bounded, but a small GPU may be tight running Whisper + Ollama + F5-TTS.
- **No end-to-end verification here:** the dev box has no Ollama server or GPU;
  correctness of the live Ollama call is validated on the user's machine.
