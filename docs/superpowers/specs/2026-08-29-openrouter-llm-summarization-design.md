# OpenRouter LLM summarization backend

**Date:** 2026-08-29
**Status:** Approved (design)

## Goal

Add OpenRouter as a third LLM backend for summarization, alongside the existing
`anthropic` and `ollama` backends. The user picks the backend **and** the model
from the web Settings page; the choice is persisted server-side and overrides the
`.env` defaults. Secrets and infrastructure (`OPENROUTER_API_KEY`,
`OPENROUTER_BASE_URL`) stay in `.env`. Custom summarization prompts already flow
through the pipeline unchanged and require no work.

## Background (current state)

- The LLM backend sits behind the `StructuredLLM` port (`ports/llm.py`) with one
  class per backend (`AnthropicStructuredLLM`, `OllamaStructuredLLM`, plus fakes).
- `config.py` selects the backend via `llm_backend: Literal["anthropic", "ollama"]`.
- `worker/main.py:_build_real_llms(settings)` constructs the real `(llm_map,
  llm_reduce)` pair. For `ollama`, one model instance serves both stages.
- The pipeline uses the backend **uniformly**: `deps.llm_map` → per-episode
  summaries (map), `deps.llm_reduce` → arc synthesis (reduce) **and** script
  writing. OpenRouter follows the same rule (one model serves all stages), exactly
  like `ollama` today.
- OpenRouter is already used for TTS, so `openrouter_api_key`, `openrouter_base_url`
  settings and an `OpenRouterTTS` class already exist — this feature reuses the key
  and base URL and adds a separate `openrouter_llm_model`.
- The web Settings page (`web/src/routes/Settings.tsx`) is currently **client-side
  only** (the API bearer token in localStorage). There is no backend settings
  endpoint yet.
- Persistence is SQLite via SQLAlchemy `create_all` (no Alembic / migrations).

## Architecture: override precedence

A persisted override layer beats `.env`:

```
effective LLM config  =  DB overrides (app_settings)  ⟶ fall back to ⟶  .env Settings
```

Both callers resolve through the **same** function so they never drift:

- the API `GET /settings/llm` — to display the current effective config, and
- the worker `build_deps` — to build the real LLMs at job time.

`.env` holds secrets/infra; the DB holds the user-picked backend + model.

## Components

### 1. Config (`config.py`, `.env.example`)

- Extend `llm_backend: Literal["anthropic", "ollama", "openrouter"]`.
- Add `openrouter_llm_model: str = "openai/gpt-4o-mini"` (default; a placeholder
  model id the user is expected to change). Reuses the existing
  `openrouter_api_key` and `openrouter_base_url`.
- `.env.example`: document `openrouter` as an `LLM_BACKEND` option, add
  `OPENROUTER_LLM_MODEL`, and note that `OPENROUTER_API_KEY` / `OPENROUTER_BASE_URL`
  are shared with the TTS backend and required when `LLM_BACKEND=openrouter`.

### 2. Port class (`ports/llm.py`)

- `OpenRouterStructuredLLM(model, api_key, base_url)` →
  `langchain_openai.ChatOpenAI(model=…, base_url=…, api_key=…).with_structured_output(schema)`
  (lazy import, mirroring the other backends).
- Add **`langchain-openai`** to `pyproject.toml` dependencies; sync `uv.lock`.
- **Constraint (documented):** the chosen OpenRouter model must support tool /
  function calling (langchain's default structured-output method). Models without
  it will fail at call time; this is a runtime error surfaced to the job, not
  something we validate up front.

### 3. Settings store (persistence)

- New key/value table `app_settings(key TEXT PRIMARY KEY, value TEXT)`. Key/value
  (not typed columns) so future settings need no migration — `create_all` adds
  missing *tables* but not missing *columns*, and there is no Alembic.
- `SettingsRepository` (new, `persistence/settings_repo.py`) over the same
  `session_factory`:
  - `get_llm_overrides() -> LlmOverrides`
  - `set_llm_overrides(overrides: LlmOverrides) -> None` (upsert; only non-null
    fields are written, so an unset field falls through to `.env`).
- `LlmOverrides` — a pydantic model with nullable `llm_backend`,
  `openrouter_llm_model`, `ollama_model` (all `str | None`).

### 4. Effective-config resolver

- `effective_llm(settings: Settings, overrides: LlmOverrides) -> EffectiveLlm`,
  living in `ports/llm.py` next to the backend classes (so the worker keeps its
  single existing import site for LLM construction).
- `EffectiveLlm` carries the resolved `backend`, `openrouter_model`,
  `ollama_model`, `anthropic_map_model`, `anthropic_reduce_model`.
- Precedence: each field is `override if not None else settings.<field>`.

### 5. API (`api/app.py`, `api/schemas.py`)

- `GET /settings/llm` → effective config for display:
  `{ backend, openrouter_model, ollama_model, anthropic_map_model,
     anthropic_reduce_model, available_backends, openrouter_configured: bool }`.
  **Never returns secrets** — only `openrouter_configured` (whether the key is set).
- `PUT /settings/llm` ← `{ backend?, openrouter_model?, ollama_model? }`:
  - validates `backend` ∈ the allowed set and any provided model is non-empty,
  - rejects `backend == "openrouter"` when no API key is configured (HTTP 400),
  - persists via `SettingsRepository.set_llm_overrides`, returns the new effective
    config (same shape as GET).
- Both routes sit behind the existing bearer-token dependency.
- `create_app` gains access to a `SettingsRepository` (constructed in
  `build_default_app` from the same `session_factory`).

### 6. Worker (`worker/main.py`)

- `build_deps` loads overrides via `SettingsRepository` (it already builds a
  `JobRepository` from the same engine) and passes the resolved `EffectiveLlm`
  into `_build_real_llms`.
- `_build_real_llms` grows an `openrouter` branch: requires `openrouter_api_key`
  (raises `RuntimeError` with a clear message otherwise), builds one
  `OpenRouterStructuredLLM(effective.openrouter_model, key, base_url)` that serves
  both map and reduce (mirrors the ollama branch).

### 7. Frontend (`web/src/routes/Settings.tsx`, `web/src/api/*`)

- New **"Summarization LLM"** card below the API-token card:
  - native `<select>` provider dropdown (anthropic / ollama / openrouter),
  - native model text input (used by ollama & openrouter; for anthropic, shown
    disabled with a note that map/reduce models come from `.env`),
  - Save button; a small hint when `openrouter` is selected but
    `openrouter_configured` is false ("set OPENROUTER_API_KEY in .env").
- Wired via React Query: a query for `GET /settings/llm` and a mutation for
  `PUT /settings/llm`, added to `web/src/api/client.ts`, `queries.ts`, `types.ts`.
- **Native form controls** (`<select>`, `<input>`) per the existing convention —
  shadcn-wrapped controls break the tests.

## Data flow

1. User opens Settings → `GET /settings/llm` → card shows effective backend + model.
2. User picks `openrouter` + a model, Saves → `PUT /settings/llm` persists overrides.
3. Next job: worker `build_deps` reads overrides, `effective_llm` resolves
   `openrouter` + model, `_build_real_llms` builds `OpenRouterStructuredLLM`, and
   the whole summarization pipeline runs on OpenRouter.

## Error handling

- `PUT` with `backend=openrouter` and no configured key → 400 with a clear message.
- `PUT` with an unknown backend or empty model → 422/400 (validation).
- Worker with `openrouter` backend and no key → `RuntimeError` fails the job with a
  clear message (consistent with the existing anthropic-key check).
- An OpenRouter model that lacks tool/function-calling support → the langchain call
  raises at job time; surfaced as a failed stage.

## Testing

- **Unit — `_build_real_llms`:** openrouter case builds `OpenRouterStructuredLLM`
  with `openrouter_llm_model` + base_url; missing key raises; existing
  anthropic/ollama cases still pass.
- **Unit — settings store:** `SettingsRepository` get/set round-trip; unset fields
  return `None`; upsert overwrites.
- **Unit — `effective_llm`:** env default when no override; override wins per field;
  mixed (backend overridden, model from env) resolves correctly.
- **Unit — config:** `openrouter` is an accepted `llm_backend`; `openrouter_llm_model`
  default present.
- **API:** `GET /settings/llm` defaults; `PUT` persists and is reflected in a
  follow-up `GET`; secret (`openrouter_api_key`) never appears in any response;
  `PUT backend=openrouter` without a key → 400; invalid backend rejected.
- **Frontend (`Settings.test.tsx`):** the card renders the current backend/model;
  changing the provider and clicking Save issues the `PUT` with the right body.

## Non-goals (YAGNI)

- Editing Anthropic's dual map/reduce models from the UI (shown read-only from
  `.env`).
- Fetching the live OpenRouter model catalog for a dropdown (free-text id for now).
- Different models per pipeline stage (one model serves map + reduce + script,
  matching ollama).
