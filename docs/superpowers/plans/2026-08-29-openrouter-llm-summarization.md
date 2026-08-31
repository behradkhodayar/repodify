# OpenRouter LLM Summarization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenRouter as a third LLM summarization backend (alongside `anthropic` and `ollama`), selectable — backend and model — from the web Settings page, persisted server-side, overriding `.env`.

**Architecture:** The LLM backend stays behind the existing `StructuredLLM` port. A new persisted override layer (`app_settings` key/value table) beats `.env`; both the API (to display config) and the worker (to build the real LLMs) resolve through one shared `effective_llm(settings, overrides)` function. Secrets (`OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`) stay in `.env`; the DB holds the user-picked backend + model.

**Tech Stack:** Python 3, pydantic / pydantic-settings, SQLAlchemy 2.0, FastAPI, langchain-openai (new), React + TanStack Query + MSW (web).

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-29-openrouter-llm-summarization-design.md`.
- **Backend uniformity:** one backend serves the whole pipeline (map = per-episode summaries, reduce = arc + script). OpenRouter uses one model for both stages, exactly like `ollama`.
- **Never leak secrets:** no API endpoint may return `openrouter_api_key` / `anthropic_api_key` — only booleans about whether a key is configured.
- **Native form controls only** in the web app (`<select>`, `<input>`); shadcn-wrapped form controls break the tests.
- **Backend id set:** `("anthropic", "ollama", "openrouter")` — exact strings, verbatim.
- **Default OpenRouter model:** `openai/gpt-4o-mini` (a placeholder the user changes).
- **Python tests:** `uv run pytest <path> -v`. Lint/format: `uv run ruff check` / `uv run ruff format`. Ruff line-length 100.
- **Web tests:** `cd web && npx vitest run <file>`. Web lint: `cd web && npm run lint`. MSW runs with `onUnhandledRequest: 'error'` — every request a component makes must have a handler.
- **Commit messages:** imperative mood, what + why, no emojis, **no Claude co-authoring / trailers** (per user's global CLAUDE.md). Commit after each task's tests pass.

---

### Task 1: Config — add the `openrouter` backend and model

**Files:**
- Modify: `src/repodify/config.py:60` (the `llm_backend` Literal) and add `openrouter_llm_model`
- Modify: `.env.example`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `Settings.llm_backend: Literal["anthropic", "ollama", "openrouter"]`; `Settings.openrouter_llm_model: str` (default `"openai/gpt-4o-mini"`). Reuses existing `Settings.openrouter_api_key`, `Settings.openrouter_base_url`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_config.py`:

```python
def test_openrouter_is_a_valid_llm_backend():
    from repodify.config import Settings

    s = Settings(_env_file=None, llm_backend="openrouter")
    assert s.llm_backend == "openrouter"
    # Default model id is present and overridable.
    assert s.openrouter_llm_model == "openai/gpt-4o-mini"
    assert (
        Settings(_env_file=None, openrouter_llm_model="anthropic/claude-3.5-haiku").openrouter_llm_model
        == "anthropic/claude-3.5-haiku"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py::test_openrouter_is_a_valid_llm_backend -v`
Expected: FAIL — `llm_backend="openrouter"` fails validation (not in Literal) / `openrouter_llm_model` attribute missing.

- [ ] **Step 3: Implement the config change**

In `src/repodify/config.py`, change the `llm_backend` line (currently line ~60) and its comment, and add the model field right after the existing OpenRouter TTS block (keep it near the other `openrouter_*` settings):

```python
    # LLM backend selection. "anthropic" (default) uses the Claude API and needs
    # ANTHROPIC_API_KEY; "ollama" uses a local Ollama server and needs no key;
    # "openrouter" calls a hosted model on OpenRouter (OpenAI-compatible chat
    # completions) and reuses OPENROUTER_API_KEY / OPENROUTER_BASE_URL below.
    llm_backend: Literal["anthropic", "ollama", "openrouter"] = "anthropic"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_base_url: str = "http://localhost:11434"
```

Then add this field next to the existing `openrouter_tts_model` line:

```python
    # OpenRouter LLM model used when LLM_BACKEND=openrouter. Must support tool /
    # function calling (langchain's structured-output method). Picked at runtime
    # from the Settings page; this is only the fallback default.
    openrouter_llm_model: str = "openai/gpt-4o-mini"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: PASS (all config tests).

- [ ] **Step 5: Update `.env.example`**

Update the `LLM_BACKEND` comment to mention `openrouter`, add `OPENROUTER_LLM_MODEL`, and note the shared key. Replace the LLM block and extend the OpenRouter block:

```bash
# LLM backend. "anthropic" (default) needs ANTHROPIC_API_KEY above; "ollama" uses
# a local Ollama server and needs no key; "openrouter" calls a hosted model on
# OpenRouter and reuses OPENROUTER_API_KEY / OPENROUTER_BASE_URL below. On ollama,
# MAP_MODEL/REDUCE_MODEL are ignored and OLLAMA_MODEL is used for both stages; on
# openrouter, OPENROUTER_LLM_MODEL is used for both stages. The backend and model
# can also be picked at runtime from the web Settings page (that choice overrides
# these defaults).
LLM_BACKEND=anthropic
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_BASE_URL=http://localhost:11434
```

In the existing OpenRouter section (near `OPENROUTER_TTS_MODEL`), add:

```bash
# OPENROUTER_LLM_MODEL=openai/gpt-4o-mini   # used when LLM_BACKEND=openrouter
```

- [ ] **Step 6: Commit**

```bash
git add src/repodify/config.py .env.example tests/unit/test_config.py
git commit -m "Add openrouter as an llm_backend option and OPENROUTER_LLM_MODEL setting"
```

---

### Task 2: `OpenRouterStructuredLLM` port class + langchain-openai dependency

**Files:**
- Modify: `pyproject.toml` (dependencies) + `uv.lock`
- Modify: `src/repodify/ports/llm.py`
- Test: `tests/unit/ports/test_llm_openrouter.py` (create)

**Interfaces:**
- Produces: `OpenRouterStructuredLLM(model: str, api_key: str, base_url: str)` implementing the `StructuredLLM` protocol; stores `_model`, `_api_key`, `_base_url`.

- [ ] **Step 1: Add the dependency**

Run: `uv add "langchain-openai>=0.2"`
Expected: `pyproject.toml` gains `langchain-openai>=0.2` under `dependencies` and `uv.lock` updates.

- [ ] **Step 2: Write the failing test**

Create `tests/unit/ports/test_llm_openrouter.py`:

```python
from repodify.ports.llm import OpenRouterStructuredLLM, StructuredLLM


def test_openrouter_llm_stores_config_and_satisfies_the_port():
    llm = OpenRouterStructuredLLM(
        model="openai/gpt-4o-mini",
        api_key="sk-or-test",
        base_url="https://openrouter.ai/api/v1",
    )
    assert isinstance(llm, StructuredLLM)  # runtime_checkable Protocol
    assert llm._model == "openai/gpt-4o-mini"
    assert llm._api_key == "sk-or-test"
    assert llm._base_url == "https://openrouter.ai/api/v1"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/ports/test_llm_openrouter.py -v`
Expected: FAIL — `ImportError: cannot import name 'OpenRouterStructuredLLM'`.

- [ ] **Step 4: Implement the class**

In `src/repodify/ports/llm.py`, add after `OllamaStructuredLLM`:

```python
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

        chat = ChatOpenAI(
            model=self._model, api_key=self._api_key, base_url=self._base_url
        )
        structured = chat.with_structured_output(schema)
        result = structured.invoke([("system", system), ("human", user)])
        return result  # type: ignore[return-value]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/ports/test_llm_openrouter.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/repodify/ports/llm.py tests/unit/ports/test_llm_openrouter.py
git commit -m "Add OpenRouterStructuredLLM port backend (langchain-openai)"
```

---

### Task 3: Override model + `effective_llm` resolver

**Files:**
- Modify: `src/repodify/ports/llm.py`
- Test: `tests/unit/ports/test_effective_llm.py` (create)

**Interfaces:**
- Consumes: `Settings` (fields `llm_backend`, `openrouter_llm_model`, `ollama_model`, `map_model`, `reduce_model`).
- Produces:
  - `LLM_BACKENDS: tuple[str, ...] = ("anthropic", "ollama", "openrouter")`
  - `LlmOverrides(BaseModel)` with `llm_backend: str | None = None`, `openrouter_llm_model: str | None = None`, `ollama_model: str | None = None`
  - `EffectiveLlm(BaseModel)` with `backend`, `openrouter_model`, `ollama_model`, `anthropic_map_model`, `anthropic_reduce_model` (all `str`)
  - `effective_llm(settings: Settings, overrides: LlmOverrides) -> EffectiveLlm`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/ports/test_effective_llm.py`:

```python
from repodify.config import Settings
from repodify.ports.llm import LLM_BACKENDS, EffectiveLlm, LlmOverrides, effective_llm


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ports/test_effective_llm.py -v`
Expected: FAIL — cannot import `LLM_BACKENDS` / `LlmOverrides` / `EffectiveLlm` / `effective_llm`.

- [ ] **Step 3: Implement the resolver**

In `src/repodify/ports/llm.py`, add near the top (after the existing imports add `from repodify.config import Settings`; `BaseModel` is already imported):

```python
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
```

Note: importing `Settings` here is safe — `config.py` does not import `ports.llm`, so there is no cycle.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/ports/test_effective_llm.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/repodify/ports/llm.py tests/unit/ports/test_effective_llm.py
git commit -m "Add LlmOverrides and effective_llm resolver (DB overrides beat .env)"
```

---

### Task 4: `app_settings` table + `SettingsRepository`

**Files:**
- Modify: `src/repodify/models/db.py` (add `AppSetting`)
- Create: `src/repodify/persistence/settings_repo.py`
- Test: `tests/unit/persistence/test_settings_repo.py` (create)

**Interfaces:**
- Consumes: `LlmOverrides` (Task 3); `session_factory`, `make_engine`, `init_db` (existing).
- Produces:
  - ORM `AppSetting(key: str [PK], value: str)`, table `app_settings`.
  - `SettingsRepository(session_factory)` with `get_llm_overrides() -> LlmOverrides` and `set_llm_overrides(overrides: LlmOverrides) -> None`. `set_` writes only non-None fields (a None leaves the stored value untouched — partial update); missing keys read back as `None`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/persistence/test_settings_repo.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/persistence/test_settings_repo.py -v`
Expected: FAIL — cannot import `AppSetting` / `SettingsRepository`.

- [ ] **Step 3: Add the ORM model**

In `src/repodify/models/db.py`, add after the `Artifact` class:

```python
class AppSetting(Base):
    """A single application setting as a key/value row.

    Key/value (not typed columns) so new settings need no migration — the app has
    no Alembic and `create_all` only adds missing tables, not missing columns.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
```

- [ ] **Step 4: Implement the repository**

Create `src/repodify/persistence/settings_repo.py`:

```python
"""SettingsRepository: persisted app settings (currently the LLM overrides)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from repodify.models.db import AppSetting
from repodify.ports.llm import LlmOverrides

_LLM_KEYS = ("llm_backend", "openrouter_llm_model", "ollama_model")


class SettingsRepository:
    """Read/write the persisted LLM override settings over an `app_settings` table."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def get_llm_overrides(self) -> LlmOverrides:
        with self._sf() as s:
            rows = s.scalars(select(AppSetting).where(AppSetting.key.in_(_LLM_KEYS))).all()
            values = {r.key: r.value for r in rows}
        return LlmOverrides(
            llm_backend=values.get("llm_backend"),
            openrouter_llm_model=values.get("openrouter_llm_model"),
            ollama_model=values.get("ollama_model"),
        )

    def set_llm_overrides(self, overrides: LlmOverrides) -> None:
        updates = {
            "llm_backend": overrides.llm_backend,
            "openrouter_llm_model": overrides.openrouter_llm_model,
            "ollama_model": overrides.ollama_model,
        }
        with self._sf() as s:
            for key, value in updates.items():
                if value is None:
                    continue  # partial update: leave an unspecified field untouched
                row = s.get(AppSetting, key)
                if row is None:
                    s.add(AppSetting(key=key, value=value))
                else:
                    row.value = value
            s.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/persistence/test_settings_repo.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/repodify/models/db.py src/repodify/persistence/settings_repo.py tests/unit/persistence/test_settings_repo.py
git commit -m "Persist LLM overrides in an app_settings table via SettingsRepository"
```

---

### Task 5: Worker builds the OpenRouter LLM from the effective config

**Files:**
- Modify: `src/repodify/worker/main.py` (`_build_real_llms`, `build_deps`)
- Test: `tests/unit/worker/test_build_real_llms.py` (extend)

**Interfaces:**
- Consumes: `effective_llm`, `LlmOverrides`, `OpenRouterStructuredLLM`, `OllamaStructuredLLM`, `AnthropicStructuredLLM` (Tasks 2–3); `SettingsRepository` (Task 4).
- Produces: `_build_real_llms(settings: Settings, overrides: LlmOverrides | None = None) -> tuple[StructuredLLM, StructuredLLM]`. Existing single-arg callers keep working (`overrides` defaults to no override → env).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/worker/test_build_real_llms.py`:

```python
from repodify.ports.llm import LlmOverrides, OpenRouterStructuredLLM


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/worker/test_build_real_llms.py -v`
Expected: FAIL — `_build_real_llms` has no `openrouter` branch / no `overrides` parameter.

- [ ] **Step 3: Rewrite `_build_real_llms`**

Replace the body of `_build_real_llms` in `src/repodify/worker/main.py` with:

```python
def _build_real_llms(
    settings: Settings, overrides: LlmOverrides | None = None
) -> tuple[StructuredLLM, StructuredLLM]:
    """Return (llm_map, llm_reduce) for the real path per the effective backend.

    `overrides` (persisted, from the Settings page) beats `settings` (.env) per
    field; the default means "use .env".
    """
    from repodify.ports.llm import LlmOverrides, effective_llm

    effective = effective_llm(settings, overrides or LlmOverrides())

    if effective.backend == "ollama":
        from repodify.ports.llm import OllamaStructuredLLM

        llm = OllamaStructuredLLM(effective.ollama_model, settings.ollama_base_url)
        return llm, llm  # one local model serves both map and reduce

    if effective.backend == "openrouter":
        from repodify.ports.llm import OpenRouterStructuredLLM

        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required when LLM_BACKEND=openrouter")
        llm = OpenRouterStructuredLLM(
            effective.openrouter_model,
            settings.openrouter_api_key,
            settings.openrouter_base_url,
        )
        return llm, llm  # one hosted model serves both map and reduce

    from repodify.ports.llm import AnthropicStructuredLLM

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_BACKEND=anthropic")
    return (
        AnthropicStructuredLLM(effective.anthropic_map_model, settings.anthropic_api_key),
        AnthropicStructuredLLM(effective.anthropic_reduce_model, settings.anthropic_api_key),
    )
```

Add the top-level import used by the annotation — at the top of `worker/main.py`, extend the existing llm import:

```python
from repodify.ports.llm import LlmOverrides, StructuredLLM
```

- [ ] **Step 4: Wire `build_deps` to load overrides**

In `build_deps`, change the engine/repo setup so the session factory is shared, and pass overrides into `_build_real_llms`. Replace:

```python
    engine = make_engine(settings.database_url)
    init_db(engine)
    repo = JobRepository(session_factory(engine))
```

with:

```python
    from repodify.persistence.settings_repo import SettingsRepository

    engine = make_engine(settings.database_url)
    init_db(engine)
    sf = session_factory(engine)
    repo = JobRepository(sf)
    settings_repo = SettingsRepository(sf)
```

and in the real (`else`) branch replace:

```python
        llm_map, llm_reduce = _build_real_llms(settings)
```

with:

```python
        llm_map, llm_reduce = _build_real_llms(settings, settings_repo.get_llm_overrides())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/worker/test_build_real_llms.py -v`
Expected: PASS — the three new tests plus the existing anthropic/ollama tests.

- [ ] **Step 6: Commit**

```bash
git add src/repodify/worker/main.py tests/unit/worker/test_build_real_llms.py
git commit -m "Build the summarization LLM from persisted overrides layered over .env"
```

---

### Task 6: API — `GET`/`PUT /settings/llm`

**Files:**
- Modify: `src/repodify/api/schemas.py` (two models)
- Modify: `src/repodify/api/app.py` (`create_app` gains `settings_repo`; two routes; `build_default_app` wiring)
- Test: `tests/unit/api/test_settings_llm.py` (create)

**Interfaces:**
- Consumes: `SettingsRepository` (Task 4), `effective_llm`, `LlmOverrides`, `LLM_BACKENDS` (Tasks 3).
- Produces:
  - `LlmSettingsResponse(BaseModel)`: `backend: str`, `openrouter_model: str`, `ollama_model: str`, `anthropic_map_model: str`, `anthropic_reduce_model: str`, `available_backends: list[str]`, `openrouter_configured: bool`.
  - `LlmSettingsUpdate(BaseModel)`: `backend: str | None = None`, `openrouter_model: str | None = None`, `ollama_model: str | None = None`.
  - `create_app(..., settings: Settings, static_dir=..., enqueue_resume=..., settings_repo: SettingsRepository | None = None)` — new **keyword-only, optional** collaborator. Routes `GET /settings/llm` and `PUT /settings/llm`. When `settings_repo` is None (unrelated tests that don't pass it), those two routes return 503.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/api/test_settings_llm.py`:

```python
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
        repo, _resolve_fn, httpx.Client(), lambda j: None, storage, settings,
        settings_repo=settings_repo,
    )
    return TestClient(app)


def test_get_settings_llm_returns_env_defaults(repo, tmp_path):
    settings = Settings(_env_file=None, llm_backend="anthropic", openrouter_api_key=None)
    client = _client(repo, tmp_path, settings)
    body = client.get("/settings/llm").json()
    assert body["backend"] == "anthropic"
    assert body["openrouter_model"] == "openai/gpt-4o-mini"
    assert body["available_backends"] == ["anthropic", "ollama", "openrouter"]
    assert body["openrouter_configured"] is False


def test_get_settings_llm_never_leaks_secrets(repo, tmp_path):
    settings = Settings(_env_file=None, openrouter_api_key="sk-or-secret", anthropic_api_key="sk-ant")
    client = _client(repo, tmp_path, settings)
    resp = client.get("/settings/llm")
    assert "sk-or-secret" not in resp.text
    assert "sk-ant" not in resp.text
    assert resp.json()["openrouter_configured"] is True


def test_put_persists_and_is_reflected(repo, tmp_path):
    settings = Settings(_env_file=None, openrouter_api_key="sk-or-secret")
    client = _client(repo, tmp_path, settings)
    resp = client.put(
        "/settings/llm", json={"backend": "openrouter", "openrouter_model": "anthropic/claude-3.5-haiku"}
    )
    assert resp.status_code == 200
    assert resp.json()["backend"] == "openrouter"
    assert client.get("/settings/llm").json()["openrouter_model"] == "anthropic/claude-3.5-haiku"


def test_put_openrouter_without_key_is_rejected(repo, tmp_path):
    settings = Settings(_env_file=None, openrouter_api_key=None)
    client = _client(repo, tmp_path, settings)
    resp = client.put("/settings/llm", json={"backend": "openrouter"})
    assert resp.status_code == 400
    assert "OPENROUTER_API_KEY" in resp.text


def test_put_rejects_unknown_backend(repo, tmp_path):
    settings = Settings(_env_file=None)
    client = _client(repo, tmp_path, settings)
    assert client.put("/settings/llm", json={"backend": "not-a-backend"}).status_code == 422
```

Note: the `repo` fixture is provided by `tests/conftest.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/api/test_settings_llm.py -v`
Expected: FAIL — `create_app()` has no `settings_repo` kwarg / no `/settings/llm` routes.

- [ ] **Step 3: Add the schemas**

In `src/repodify/api/schemas.py`, append:

```python
class LlmSettingsResponse(BaseModel):
    backend: str
    openrouter_model: str
    ollama_model: str
    anthropic_map_model: str
    anthropic_reduce_model: str
    available_backends: list[str]
    openrouter_configured: bool


class LlmSettingsUpdate(BaseModel):
    backend: str | None = None
    openrouter_model: str | None = None
    ollama_model: str | None = None
```

- [ ] **Step 4: Add the routes and the collaborator**

In `src/repodify/api/app.py`:

Extend the schema import list with `LlmSettingsResponse` and `LlmSettingsUpdate`, and add near the other imports:

```python
from repodify.persistence.settings_repo import SettingsRepository
from repodify.ports.llm import LLM_BACKENDS, LlmOverrides, effective_llm
```

Change the `create_app` signature to add the keyword-only optional param (keep the existing params/order; append at the end):

```python
def create_app(
    repo: JobRepository,
    resolve_fn: ResolveFn,
    http: httpx.Client,
    enqueue: EnqueueFn,
    storage: Storage,
    settings: Settings,
    static_dir: Path | None = None,
    enqueue_resume: EnqueueFn | None = None,
    settings_repo: SettingsRepository | None = None,
) -> FastAPI:
```

Add a small helper inside `create_app` (before the routes) and the two routes, placing them alongside the other `router` routes (e.g. right after the `/voices` route):

```python
    def _llm_settings_response() -> LlmSettingsResponse:
        eff = effective_llm(settings, settings_repo.get_llm_overrides())
        return LlmSettingsResponse(
            backend=eff.backend,
            openrouter_model=eff.openrouter_model,
            ollama_model=eff.ollama_model,
            anthropic_map_model=eff.anthropic_map_model,
            anthropic_reduce_model=eff.anthropic_reduce_model,
            available_backends=list(LLM_BACKENDS),
            openrouter_configured=bool(settings.openrouter_api_key),
        )

    @router.get("/settings/llm", response_model=LlmSettingsResponse)
    def get_llm_settings() -> LlmSettingsResponse:
        if settings_repo is None:
            raise HTTPException(status_code=503, detail="settings store unavailable")
        return _llm_settings_response()

    @router.put("/settings/llm", response_model=LlmSettingsResponse)
    def put_llm_settings(req: LlmSettingsUpdate) -> LlmSettingsResponse:
        if settings_repo is None:
            raise HTTPException(status_code=503, detail="settings store unavailable")
        if req.backend is not None and req.backend not in LLM_BACKENDS:
            raise HTTPException(status_code=422, detail=f"unknown backend: {req.backend}")
        if req.backend == "openrouter" and not settings.openrouter_api_key:
            raise HTTPException(
                status_code=400, detail="OPENROUTER_API_KEY is not configured on the server"
            )
        for field in (req.openrouter_model, req.ollama_model):
            if field is not None and not field.strip():
                raise HTTPException(status_code=422, detail="model id must not be empty")
        settings_repo.set_llm_overrides(
            LlmOverrides(
                llm_backend=req.backend,
                openrouter_llm_model=req.openrouter_model,
                ollama_model=req.ollama_model,
            )
        )
        return _llm_settings_response()
```

- [ ] **Step 5: Wire `build_default_app`**

In `build_default_app`, construct a `SettingsRepository` from the same engine and pass it. Replace:

```python
    repo = JobRepository(session_factory(engine))
```

with:

```python
    sf = session_factory(engine)
    repo = JobRepository(sf)
    settings_repo = SettingsRepository(sf)
```

and add `settings_repo=settings_repo,` to the `create_app(...)` call's keyword arguments.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/api/test_settings_llm.py tests/unit/api -v`
Expected: PASS — new settings tests plus the whole existing api suite (unchanged create_app callers still work: `settings_repo` defaults to None).

- [ ] **Step 7: Commit**

```bash
git add src/repodify/api/schemas.py src/repodify/api/app.py tests/unit/api/test_settings_llm.py
git commit -m "Expose GET/PUT /settings/llm for backend + model selection"
```

---

### Task 7: Web API layer — types, client, queries

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/api/queries.ts`
- Test: `web/src/api/client.test.ts` (extend)

**Interfaces:**
- Produces:
  - Types `LlmSettingsResponse`, `LlmSettingsUpdate`.
  - `api.getLlmSettings(): Promise<LlmSettingsResponse>`, `api.updateLlmSettings(body: LlmSettingsUpdate): Promise<LlmSettingsResponse>`.
  - Hooks `useLlmSettings()`, `useUpdateLlmSettings()`.

- [ ] **Step 1: Write the failing test**

Look at `web/src/api/client.test.ts` for its existing pattern (it uses the shared MSW `server`). Add:

```ts
import { http, HttpResponse } from 'msw'
import { server } from '../test/msw'
import { api } from './client'

// ... inside the existing describe (or a new one):
it('gets and updates llm settings', async () => {
  server.use(
    http.get('/settings/llm', () =>
      HttpResponse.json({
        backend: 'anthropic',
        openrouter_model: 'openai/gpt-4o-mini',
        ollama_model: 'qwen2.5-coder:7b',
        anthropic_map_model: 'claude-haiku-4-5-20251001',
        anthropic_reduce_model: 'claude-opus-4-8',
        available_backends: ['anthropic', 'ollama', 'openrouter'],
        openrouter_configured: true,
      }),
    ),
    http.put('/settings/llm', async ({ request }) => {
      const body = (await request.json()) as { backend?: string }
      return HttpResponse.json({
        backend: body.backend ?? 'anthropic',
        openrouter_model: 'openai/gpt-4o-mini',
        ollama_model: 'qwen2.5-coder:7b',
        anthropic_map_model: 'claude-haiku-4-5-20251001',
        anthropic_reduce_model: 'claude-opus-4-8',
        available_backends: ['anthropic', 'ollama', 'openrouter'],
        openrouter_configured: true,
      })
    }),
  )
  expect((await api.getLlmSettings()).backend).toBe('anthropic')
  expect((await api.updateLlmSettings({ backend: 'openrouter' })).backend).toBe('openrouter')
})
```

If `client.test.ts` doesn't yet import `http`/`HttpResponse`/`server`, add those imports at the top (mirror `Jobs.test.tsx`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/api/client.test.ts`
Expected: FAIL — `api.getLlmSettings` / `api.updateLlmSettings` are not functions.

- [ ] **Step 3: Add the types**

In `web/src/api/types.ts`, append:

```ts
export interface LlmSettingsResponse {
  backend: string
  openrouter_model: string
  ollama_model: string
  anthropic_map_model: string
  anthropic_reduce_model: string
  available_backends: string[]
  openrouter_configured: boolean
}

export interface LlmSettingsUpdate {
  backend?: string
  openrouter_model?: string
  ollama_model?: string
}
```

- [ ] **Step 4: Add the client methods**

In `web/src/api/client.ts`, extend the type import list with `LlmSettingsResponse, LlmSettingsUpdate`, and add to the `api` object:

```ts
  getLlmSettings: () => apiFetch<LlmSettingsResponse>('/settings/llm'),
  updateLlmSettings: (body: LlmSettingsUpdate) =>
    apiFetch<LlmSettingsResponse>('/settings/llm', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
```

- [ ] **Step 5: Add the query hooks**

In `web/src/api/queries.ts`, extend the type import with `LlmSettingsUpdate` and append:

```ts
export function useLlmSettings() {
  return useQuery({ queryKey: ['llm-settings'], queryFn: () => api.getLlmSettings() })
}

export function useUpdateLlmSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: LlmSettingsUpdate) => api.updateLlmSettings(body),
    onSuccess: (data) => qc.setQueryData(['llm-settings'], data),
  })
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd web && npx vitest run src/api/client.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/api/types.ts web/src/api/client.ts web/src/api/queries.ts web/src/api/client.test.ts
git commit -m "Add web API client + hooks for /settings/llm"
```

---

### Task 8: Web Settings page — Summarization LLM card

**Files:**
- Modify: `web/src/routes/Settings.tsx`
- Modify: `web/src/routes/Settings.test.tsx`

**Interfaces:**
- Consumes: `useLlmSettings`, `useUpdateLlmSettings` (Task 7).
- Produces: a "Summarization LLM" card with a native `<select>` labelled "LLM backend", a native `<input>` labelled "Model", and a "Save LLM settings" button.

- [ ] **Step 1: Write the failing tests**

Replace `web/src/routes/Settings.test.tsx` with (wraps in a QueryClient provider — now required — and registers MSW handlers because MSW errors on unhandled requests):

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/msw'
import { Settings } from './Settings'

const LLM = {
  backend: 'anthropic',
  openrouter_model: 'openai/gpt-4o-mini',
  ollama_model: 'qwen2.5-coder:7b',
  anthropic_map_model: 'claude-haiku-4-5-20251001',
  anthropic_reduce_model: 'claude-opus-4-8',
  available_backends: ['anthropic', 'ollama', 'openrouter'],
  openrouter_configured: true,
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Settings />
    </QueryClientProvider>,
  )
}

describe('Settings', () => {
  it('saves the token to localStorage', async () => {
    server.use(http.get('/settings/llm', () => HttpResponse.json(LLM)))
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText(/api token/i), 'secret')
    await user.click(screen.getByRole('button', { name: /^save$/i }))
    expect(localStorage.getItem('api_token')).toBe('secret')
  })

  it('selects the openrouter backend + model and saves it', async () => {
    let putBody: unknown = null
    server.use(
      http.get('/settings/llm', () => HttpResponse.json(LLM)),
      http.put('/settings/llm', async ({ request }) => {
        putBody = await request.json()
        return HttpResponse.json({ ...LLM, backend: 'openrouter', openrouter_model: 'x/y' })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    // Wait for the card to hydrate from the GET.
    await waitFor(() => expect(screen.getByLabelText(/llm backend/i)).toHaveValue('anthropic'))
    await user.selectOptions(screen.getByLabelText(/llm backend/i), 'openrouter')
    const model = screen.getByLabelText(/^model$/i)
    await user.clear(model)
    await user.type(model, 'x/y')
    await user.click(screen.getByRole('button', { name: /save llm settings/i }))
    await waitFor(() =>
      expect(putBody).toEqual({ backend: 'openrouter', openrouter_model: 'x/y', ollama_model: 'qwen2.5-coder:7b' }),
    )
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/routes/Settings.test.tsx`
Expected: FAIL — no "LLM backend"/"Model" controls; `useLlmSettings` not wired.

- [ ] **Step 3: Add the card to `Settings.tsx`**

Extend `web/src/routes/Settings.tsx`. Add imports and a second card. The model field edits `openrouter_model` when backend is `openrouter`, `ollama_model` when `ollama`, and is read-only (shows the two Anthropic models) when `anthropic`. Full new file:

```tsx
import { Check, Cpu, KeyRound, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLlmSettings, useUpdateLlmSettings } from '../api/queries'
import { PageHeader } from '../components/PageHeader'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { useToken } from '../lib/useToken'

export function Settings() {
  const { token, setToken } = useToken()
  const [value, setValue] = useState(token)
  const [saved, setSaved] = useState(false)

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <PageHeader title="Settings" description="Configure how the web client talks to the repodify API." />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="size-[18px] text-primary" /> API token
          </CardTitle>
          <CardDescription>
            Sent as a Bearer token with every request. Leave blank if the API is open.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">API token</span>
            <Input
              aria-label="API token"
              type="password"
              value={value}
              onChange={(e) => {
                setValue(e.target.value)
                setSaved(false)
              }}
              placeholder="leave blank if the API is open"
            />
          </label>
          <div className="flex items-center gap-3">
            <Button
              onClick={() => {
                setToken(value)
                setSaved(true)
              }}
            >
              <Save /> Save
            </Button>
            {saved && (
              <span className="flex items-center gap-1.5 text-sm text-status-done">
                <Check className="size-4" /> Saved
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <LlmCard />
    </div>
  )
}

function LlmCard() {
  const { data } = useLlmSettings()
  const update = useUpdateLlmSettings()
  const [backend, setBackend] = useState('anthropic')
  const [openrouterModel, setOpenrouterModel] = useState('')
  const [ollamaModel, setOllamaModel] = useState('')
  const [saved, setSaved] = useState(false)

  // Hydrate local form state once the server config loads.
  useEffect(() => {
    if (!data) return
    setBackend(data.backend)
    setOpenrouterModel(data.openrouter_model)
    setOllamaModel(data.ollama_model)
  }, [data])

  if (!data) return null

  const modelValue = backend === 'openrouter' ? openrouterModel : ollamaModel
  const setModelValue = backend === 'openrouter' ? setOpenrouterModel : setOllamaModel
  const editable = backend === 'openrouter' || backend === 'ollama'
  const needsKey = backend === 'openrouter' && !data.openrouter_configured

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Cpu className="size-[18px] text-primary" /> Summarization LLM
        </CardTitle>
        <CardDescription>
          Pick which model summarizes episodes. Saved on the server; overrides the .env default.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">LLM backend</span>
          <select
            aria-label="LLM backend"
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
            value={backend}
            onChange={(e) => {
              setBackend(e.target.value)
              setSaved(false)
            }}
          >
            {data.available_backends.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </label>

        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Model</span>
          <Input
            aria-label="Model"
            value={editable ? modelValue : `${data.anthropic_map_model} / ${data.anthropic_reduce_model}`}
            disabled={!editable}
            onChange={(e) => {
              setModelValue(e.target.value)
              setSaved(false)
            }}
            placeholder="e.g. openai/gpt-4o-mini"
          />
          {!editable && (
            <span className="text-xs text-muted-foreground">
              Anthropic uses MAP_MODEL / REDUCE_MODEL from .env.
            </span>
          )}
          {needsKey && (
            <span className="text-xs text-status-failed">Set OPENROUTER_API_KEY in .env to use OpenRouter.</span>
          )}
        </label>

        <div className="flex items-center gap-3">
          <Button
            disabled={update.isPending}
            onClick={() => {
              update.mutate(
                { backend, openrouter_model: openrouterModel, ollama_model: ollamaModel },
                { onSuccess: () => setSaved(true) },
              )
            }}
          >
            <Save /> Save LLM settings
          </Button>
          {saved && (
            <span className="flex items-center gap-1.5 text-sm text-status-done">
              <Check className="size-4" /> Saved
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
```

Note: if `text-status-failed` / `text-muted-foreground` classes don't exist in the theme, drop them — they're cosmetic. Confirm `Cpu` is exported by `lucide-react` (it is); otherwise use `Bot`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/routes/Settings.test.tsx`
Expected: PASS (both the token test and the openrouter-select test).

- [ ] **Step 5: Run the full web suite + lint**

Run: `cd web && npx vitest run && npm run lint`
Expected: PASS, no type errors.

- [ ] **Step 6: Commit**

```bash
git add web/src/routes/Settings.tsx web/src/routes/Settings.test.tsx
git commit -m "Add Summarization LLM card to the Settings page"
```

---

### Task 9: Full-suite verification + docs

**Files:**
- Modify: `README.md` if it documents LLM backends (optional — only if a backends list exists)

- [ ] **Step 1: Run the entire Python suite**

Run: `uv run pytest`
Expected: PASS (no regressions).

- [ ] **Step 2: Lint + format Python**

Run: `uv run ruff check && uv run ruff format --check`
Expected: clean. If `ruff format --check` reports diffs, run `uv run ruff format` and re-commit.

- [ ] **Step 3: Run the entire web suite + lint**

Run: `cd web && npx vitest run && npm run lint`
Expected: PASS.

- [ ] **Step 4: If README lists LLM backends, add OpenRouter**

Search: `grep -n "LLM_BACKEND\|ollama\|Ollama\|backend" README.md`. If there's a backends list/table, add an OpenRouter row mirroring the Ollama row (env vars: `LLM_BACKEND=openrouter`, `OPENROUTER_API_KEY`, `OPENROUTER_LLM_MODEL`); note it's also selectable from the Settings page. If no such section exists, skip.

- [ ] **Step 5: Commit any doc/format changes**

```bash
git add -A
git commit -m "Document OpenRouter summarization backend"
```

(Skip if nothing changed.)

---

## Self-Review

**Spec coverage:**
- OpenRouter backend + model in config → Task 1. ✅
- `OpenRouterStructuredLLM` port + langchain-openai → Task 2. ✅
- Override precedence (`effective_llm`) → Task 3. ✅
- Persisted store (`app_settings` + `SettingsRepository`) → Task 4. ✅
- Worker builds from overrides, one model for map+reduce, key required → Task 5. ✅
- API `GET/PUT /settings/llm`, no secret leak, 400 without key, invalid backend rejected → Task 6. ✅
- Web client/hooks → Task 7; Settings card with native controls → Task 8. ✅
- `.env.example` updated → Task 1. ✅
- Full verification → Task 9. ✅
- Non-goals (Anthropic dual-model read-only, no catalog fetch, one model per pipeline) honored: model field is read-only for Anthropic (Task 8); model is a free-text input (Task 8); one model serves map+reduce (Task 5). ✅

**Placeholder scan:** No TBD/TODO; every code step has concrete code; commands have expected output.

**Type consistency:** `LlmOverrides`, `EffectiveLlm`, `effective_llm`, `LLM_BACKENDS`, `SettingsRepository.get_llm_overrides/set_llm_overrides`, `_build_real_llms(settings, overrides=None)`, `LlmSettingsResponse`/`LlmSettingsUpdate` field names, and the web `LlmSettingsResponse`/`LlmSettingsUpdate` shapes match across tasks and mirror the Python schemas. PUT body `{ backend, openrouter_model, ollama_model }` matches `LlmSettingsUpdate` on both sides.
