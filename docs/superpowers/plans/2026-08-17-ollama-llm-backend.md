# Ollama LLM Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the pipeline's LLM stages run against a local Ollama model (default `qwen2.5-coder:7b`) with no Anthropic API key, via an opt-in `LLM_BACKEND=ollama` toggle.

**Architecture:** Add an `OllamaStructuredLLM` adapter mirroring the existing `AnthropicStructuredLLM` behind the `StructuredLLM` port, driven by new config settings. Extract LLM construction from `build_deps` into a small `_build_real_llms(settings)` helper that selects the backend, so selection is unit-testable without importing the GPU STT/TTS backends.

**Tech Stack:** Python 3.12+, pydantic-settings, langchain-ollama (`ChatOllama.with_structured_output`), pytest, uv.

## Global Constraints

- Anthropic stays the **default** backend; Ollama is opt-in. Do not remove the Anthropic path.
- `LLM_BACKEND` is only consulted on the real path (`use_fakes=False`). Fake mode stays all-fakes — do not touch it.
- One Ollama model serves **both** map and reduce stages; `map_model`/`reduce_model` are ignored when `llm_backend == "ollama"`.
- `langchain-ollama` goes in **core** `dependencies` (it is an HTTP client, no GPU) — not the `gpu` extra.
- Adapters lazy-import their provider SDK inside `generate` (match `AnthropicStructuredLLM`), so `ports/llm.py` stays importable without the SDK.
- Line length 100, ruff `E,F,I,UP,B`. Tests construct settings with `Settings(_env_file=None, ...)`.
- Commit messages: imperative mood, no emojis, no Claude co-authoring.

---

### Task 1: Config settings for backend selection

**Files:**
- Modify: `src/podcast_compactor/config.py`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `Settings.llm_backend: Literal["anthropic", "ollama"]` (default `"anthropic"`), `Settings.ollama_model: str` (default `"qwen2.5-coder:7b"`), `Settings.ollama_base_url: str` (default `"http://localhost:11434"`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_config.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'llm_backend'`.

- [ ] **Step 3: Add the settings**

In `src/podcast_compactor/config.py`, add `from typing import Literal` to the imports, then add these fields to the `Settings` class right after the `use_fakes` field (the "Dependency selection" block):

```python
    # LLM backend selection. "anthropic" (default) uses the Claude API and needs
    # ANTHROPIC_API_KEY; "ollama" uses a local Ollama server and needs no key.
    llm_backend: Literal["anthropic", "ollama"] = "anthropic"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_base_url: str = "http://localhost:11434"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: PASS (all config tests).

- [ ] **Step 5: Commit**

```bash
git add src/podcast_compactor/config.py tests/unit/test_config.py
git commit -m "Add LLM_BACKEND / Ollama config settings"
```

---

### Task 2: OllamaStructuredLLM adapter

**Files:**
- Modify: `src/podcast_compactor/ports/llm.py`
- Modify: `pyproject.toml` (add `langchain-ollama` to core deps, via `uv add`)
- Test: `tests/unit/ports/test_llm_ollama.py` (create)

**Interfaces:**
- Consumes: `StructuredLLM` protocol (`generate(system: str, user: str, schema: type[T]) -> T`) from `ports/llm.py`.
- Produces: `OllamaStructuredLLM(model: str, base_url: str)` with `.generate(system, user, schema) -> T`.

- [ ] **Step 1: Add the runtime dependency**

Run: `uv add langchain-ollama`
Expected: `pyproject.toml` gains `langchain-ollama` under `[project].dependencies`; `uv.lock` updates; install succeeds.

- [ ] **Step 2: Write the failing test**

Create `tests/unit/ports/test_llm_ollama.py`:

```python
import sys
import types

from podcast_compactor.models.domain import EpisodeSummary
from podcast_compactor.ports.llm import OllamaStructuredLLM, StructuredLLM


def test_ollama_satisfies_protocol():
    assert isinstance(OllamaStructuredLLM("m", "http://localhost:11434"), StructuredLLM)


def test_ollama_generate_wires_model_and_returns_structured(monkeypatch):
    calls = {}
    returned = EpisodeSummary(key_points=["hello"])

    class FakeStructured:
        def __init__(self, schema):
            self.schema = schema

        def invoke(self, messages):
            calls["messages"] = messages
            calls["schema"] = self.schema
            return returned

    class FakeChatOllama:
        def __init__(self, model, base_url):
            calls["model"] = model
            calls["base_url"] = base_url

        def with_structured_output(self, schema):
            return FakeStructured(schema)

    fake_module = types.ModuleType("langchain_ollama")
    fake_module.ChatOllama = FakeChatOllama
    monkeypatch.setitem(sys.modules, "langchain_ollama", fake_module)

    llm = OllamaStructuredLLM("qwen2.5-coder:7b", "http://gpu:11434")
    out = llm.generate("sys-prompt", "user-prompt", EpisodeSummary)

    assert out is returned
    assert calls["model"] == "qwen2.5-coder:7b"
    assert calls["base_url"] == "http://gpu:11434"
    assert calls["schema"] is EpisodeSummary
    assert calls["messages"] == [("system", "sys-prompt"), ("human", "user-prompt")]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/ports/test_llm_ollama.py -v`
Expected: FAIL — `ImportError: cannot import name 'OllamaStructuredLLM'`.

- [ ] **Step 4: Implement the adapter**

In `src/podcast_compactor/ports/llm.py`, add this class immediately after `AnthropicStructuredLLM` (before `FakeStructuredLLM`):

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
        result = structured.invoke([("system", system), ("human", user)])
        return result  # type: ignore[return-value]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/ports/test_llm_ollama.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/podcast_compactor/ports/llm.py tests/unit/ports/test_llm_ollama.py
git commit -m "Add OllamaStructuredLLM adapter via langchain-ollama"
```

---

### Task 3: Backend selection in the worker composition root

**Files:**
- Modify: `src/podcast_compactor/worker/main.py`
- Test: `tests/unit/worker/test_build_real_llms.py` (create)

**Interfaces:**
- Consumes: `Settings.llm_backend`, `Settings.ollama_model`, `Settings.ollama_base_url`, `Settings.map_model`, `Settings.reduce_model`, `Settings.anthropic_api_key` (Task 1); `OllamaStructuredLLM` (Task 2); existing `AnthropicStructuredLLM`.
- Produces: `_build_real_llms(settings: Settings) -> tuple[StructuredLLM, StructuredLLM]` returning `(llm_map, llm_reduce)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/worker/test_build_real_llms.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/worker/test_build_real_llms.py -v`
Expected: FAIL — `ImportError: cannot import name '_build_real_llms'`.

- [ ] **Step 3: Add the helper**

In `src/podcast_compactor/worker/main.py`, add the `StructuredLLM` import near the other `ports` imports at the top of the file:

```python
from podcast_compactor.ports.llm import StructuredLLM
```

Then add this function above `build_deps`:

```python
def _build_real_llms(settings: Settings) -> tuple[StructuredLLM, StructuredLLM]:
    """Return (llm_map, llm_reduce) for the real path per settings.llm_backend."""
    if settings.llm_backend == "ollama":
        from podcast_compactor.ports.llm import OllamaStructuredLLM

        llm = OllamaStructuredLLM(settings.ollama_model, settings.ollama_base_url)
        return llm, llm  # one local model serves both map and reduce
    from podcast_compactor.ports.llm import AnthropicStructuredLLM

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_BACKEND=anthropic")
    return (
        AnthropicStructuredLLM(settings.map_model, settings.anthropic_api_key),
        AnthropicStructuredLLM(settings.reduce_model, settings.anthropic_api_key),
    )
```

- [ ] **Step 4: Rewire `build_deps` to use the helper**

In the `else` (real) branch of `build_deps`, replace the Anthropic-specific import, the key check, and the two `AnthropicStructuredLLM(...)` assignments with a call to the helper. The block currently reads:

```python
        from podcast_compactor.ports.llm import AnthropicStructuredLLM
        from podcast_compactor.synth.cloning import PyannoteVoiceCloner
        from podcast_compactor.synth.f5_tts import F5TTS
        from podcast_compactor.synth.watermark import AudioSealWatermarker
        from podcast_compactor.transcribe.faster_whisper import FasterWhisperTranscriber

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when USE_FAKES=false")
        transcriber = FasterWhisperTranscriber(settings.whisper_model)
        llm_map = AnthropicStructuredLLM(settings.map_model, settings.anthropic_api_key)
        llm_reduce = AnthropicStructuredLLM(settings.reduce_model, settings.anthropic_api_key)
```

Change it to (drop the `AnthropicStructuredLLM` import and inline key check; construct the LLMs via the helper):

```python
        from podcast_compactor.synth.cloning import PyannoteVoiceCloner
        from podcast_compactor.synth.f5_tts import F5TTS
        from podcast_compactor.synth.watermark import AudioSealWatermarker
        from podcast_compactor.transcribe.faster_whisper import FasterWhisperTranscriber

        transcriber = FasterWhisperTranscriber(settings.whisper_model)
        llm_map, llm_reduce = _build_real_llms(settings)
```

Leave the rest of the real branch (`tts`, `voices`, `voice_cloner`, `watermarker`) unchanged.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/worker/test_build_real_llms.py -v`
Expected: PASS (all three tests).

- [ ] **Step 6: Run the full suite to confirm nothing regressed**

Run: `uv run pytest`
Expected: PASS (fake-mode compose test and all others unchanged).

- [ ] **Step 7: Lint**

Run: `uv run ruff check src/podcast_compactor/worker/main.py src/podcast_compactor/ports/llm.py src/podcast_compactor/config.py`
Expected: no errors (unused `AnthropicStructuredLLM` import removed from `build_deps`).

- [ ] **Step 8: Commit**

```bash
git add src/podcast_compactor/worker/main.py tests/unit/worker/test_build_real_llms.py
git commit -m "Select LLM backend via _build_real_llms in composition root"
```

---

### Task 4: Document the Ollama backend

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update `.env.example`**

In `.env.example`, in the "Models" section (just before the `WHISPER_MODEL` line), add:

```ini
# LLM backend. "anthropic" (default) needs ANTHROPIC_API_KEY above; "ollama" uses
# a local Ollama server and needs no key. On ollama, MAP_MODEL/REDUCE_MODEL are
# ignored and OLLAMA_MODEL is used for both stages.
LLM_BACKEND=anthropic
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_BASE_URL=http://localhost:11434
```

Also update the `ANTHROPIC_API_KEY` comment near the top from `# Anthropic API key (required when USE_FAKES=false)` to:

```ini
# Anthropic API key (required when USE_FAKES=false and LLM_BACKEND=anthropic).
```

- [ ] **Step 2: Update `README.md`**

Add this subsection under "## Run the service (fake mode)" area — place it immediately after the "### Two-host mode" section (before "### Voice cloning (opt-in)"):

```markdown
### Local LLM via Ollama (no Anthropic key)

The summarize/script stages default to the Claude API, but you can point them at
a local [Ollama](https://ollama.com) model instead — useful when you have a GPU
but no `ANTHROPIC_API_KEY`. Real STT/TTS are unaffected.

```bash
ollama pull qwen2.5-coder:7b        # or any model you prefer
# in .env:
#   USE_FAKES=false
#   LLM_BACKEND=ollama
#   OLLAMA_MODEL=qwen2.5-coder:7b
#   OLLAMA_BASE_URL=http://localhost:11434
```

One model serves both the per-episode summary and the arc/script stages
(`MAP_MODEL`/`REDUCE_MODEL` are ignored on Ollama). Small code-specialized models
produce valid output but weaker narratives than Claude; a general instruct model
of 7B+ summarizes better.
```

- [ ] **Step 3: Commit**

```bash
git add .env.example README.md
git commit -m "Document Ollama LLM backend"
```

---

## Self-Review

**Spec coverage:**
- Config (`llm_backend`, `ollama_model`, `ollama_base_url`) → Task 1. ✓
- `OllamaStructuredLLM` adapter via `ChatOllama.with_structured_output` → Task 2. ✓
- `_build_real_llms` seam + `build_deps` rewire + key check moved behind anthropic branch → Task 3. ✓
- `langchain-ollama` in core deps → Task 2 Step 1. ✓
- Docs (`.env.example`, `README.md`) → Task 4. ✓
- One model for both stages / map/reduce ignored on Ollama → Task 3 helper (`return llm, llm`) + docs. ✓
- Fake mode untouched → Task 3 only edits the `else` branch; full suite re-run in Step 6. ✓
- Tests via mocks, no server needed → Task 2 (`sys.modules` injection), Task 3 (construction only, adapters lazy-import). ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code and exact commands. ✓

**Type consistency:** `_build_real_llms(settings) -> tuple[StructuredLLM, StructuredLLM]` returns `(llm_map, llm_reduce)`, matching how `build_deps` assigns them and how `Deps` consumes `llm_map`/`llm_reduce`. `OllamaStructuredLLM(model, base_url)` constructor and `generate(system, user, schema)` signature match the port and the Task 2 test. `AnthropicStructuredLLM._model` accessed in Task 3 test matches its existing attribute. ✓
