# Repodify

Turn a list of episodes of podcast to a single tailored one, accoording to what
the user desires (e.g. summarizing multiple episodes into one, translate it to
their language of choice, augment the contents of original podcast, etc), on
their local machine/infra or by using their own keys (BYOK). This originally
started to address the following need:
Suppose u're new to ML in 2026 &  want to learn about the history or flow of how
the ML/DL space has evolved since beginning using the available podcasts on the
internet.
As using someone’s voice may have legal implications, this feature is intended
to be used only on the user’s local machine and for educational purposes.

Backend service (FastAPI + arq worker + LangGraph pipeline) with a React PWA.
Not a CLI.

How to run it: [`README.md`](README.md).
How it is built: [`docs/architecture.md`](docs/architecture.md).
Per-feature designs and plans: [`docs/superpowers/`](docs/superpowers/).

---

## Commands

From the repo root. Use `uv`, not pip.

```bash
uv sync                          # core + dev deps from uv.lock
uv sync --extra gpu              # CUDA host only — real STT/TTS/diarization
uv run pytest                    # CPU, no network; STT/LLM/TTS are faked
uv run ruff check src tests
uv run ruff format src tests

cd web && npm test               # Vitest + MSW
cd web && npm run lint           # tsc -b
cd web && npm run build          # web/dist/, served by the API at /app

./launch                         # or make run — API + worker + Vite + Redis
./launch --fake                  # keyless CPU
./launch --postgres              # also start Postgres
make stop                        # halt the compose containers
```

- Python 3.13 is pinned in `.python-version`; `requires-python >= 3.12`.
- Default tests must stay GPU-, network-, and ffmpeg-free. HTTP is mocked with
  `respx`; ML sits behind fakes in `ports/`.
- There is no CI yet (no `.github/`). Local `uv run pytest` plus `npm test` /
  `npm run lint` in `web/` are the gate.
- Do not start `./launch --real` or import `torch` just to verify a code change.

---

## Layout

| Path | Role |
|---|---|
| `src/repodify/api/` | FastAPI app, auth, request schemas, Range audio |
| `src/repodify/worker/` | arq worker + `build_deps` composition root |
| `src/repodify/pipeline/` | LangGraph graph, node closures, `Deps`, state |
| `src/repodify/ports/` | Protocols **and** fakes (STT, LLM, TTS, diarizer, cloner, watermarker, transcoder) |
| `ingest/` `transcribe/` `summarize/` `script/` `synth/` | Domain logic + **real** adapters |
| `src/repodify/persistence/` | `JobRepository`, `SettingsRepository`, engine — the only DB access |
| `src/repodify/models/` | pydantic domain (`domain.py`) vs SQLAlchemy (`db.py`) vs enums |
| `src/repodify/storage/` | `Storage` port + filesystem impl |
| `src/repodify/config.py` | pydantic-settings, project-root-anchored paths |
| `web/` | React + Vite PWA (`basename=/app`) |
| `tests/unit/` | mirrors the package layout |
| `tests/integration/` | full graph with fakes |
| `tests/launch/` | `./launch` helper tests |
| `assets/voice-samples/` | bundled Kokoro previews — the only wavs in git |
| `data/` | runtime artifacts + SQLite — gitignored |

Paths under `src/repodify/` in the table are abbreviated after the first
few rows.

---

## Architecture agents must not violate

Two processes. The API and the worker never call each other. They share Redis
(job ids), SQL (job / stage / artifact / settings), and the filesystem object
store.

**Composition roots only:**

- API: `api/app.py:create_app` / `build_default_app`
- Worker: `worker/main.py:build_deps` / `run_pipeline` / `run_review_digest`

The pipeline is a linear LangGraph (`pipeline/graph.py`). Nodes match the
tracked stages except `synth` also assembles and `voices` is a gate-only node.
Each ML stage `interrupt()`s until `POST /jobs/{id}/continue`. The worker uses a
SQLite checkpointer at `{DATA_DIR}/checkpoints.db` so a job can sit at a gate
across process restart. Progress is **polled** (`GET /jobs/{id}`). Do not add
SSE/WebSocket unless asked.

**Ports/adapters is the load-bearing convention.** New ML or hosted provider:

1. Add a `Protocol` + `Fake*` together in `ports/`.
2. Put the real adapter next to its domain (`transcribe/`, `synth/`, `ports/llm.py`).
3. Wire it in `build_deps`, behind `USE_FAKES`.
4. Lazy-import GPU/heavy SDKs inside the real adapter — never at package import.
5. Expose `release()` if it holds VRAM; the pipeline already calls it between
   stages and then `gpu.empty_cuda_cache()`.

Do not open SQLAlchemy sessions from the pipeline or API. Go through
`JobRepository` / `SettingsRepository`.

Domain vocabulary lives in `models/domain.py` (`Feed`, `Episode`, `Transcript`,
`EpisodeSummary`, `ArcOutline`, `Script`, `ShowNotes`, `JobOptions`,
`VoiceAssignment`). Persistence models are `models/db.py`. Keep them distinct.

Settings are env-driven (`config.py`, `.env.example`). Relative `DATA_DIR` and
SQLite `DATABASE_URL` are **anchored to the project root**, not the process CWD
(issue #27) — otherwise the API, worker, and an ad-hoc run each get a private
`data/app.db`. The web Settings page persists LLM backend/model and preferred
stock voices in `app_settings`; those values **override** `.env` via
`effective_llm` (`ports/llm.py`).

---

## Job modes

| Mode | Trigger | Notes |
|---|---|---|
| Single narrator | diarize gate: assign voices off | One stock/narrator voice, chosen at the TTS gate |
| Original cast | voices gate: original | Clone all detected speakers; guardrails always on |
| Stock replacements | voices gate: replace | Per-speaker stock catalog voice; gender-tagged |
| Per-stage local/BYOK | each ML gate | Local GPU adapters or OpenRouter / pyannoteAI |

Cloning guardrails are **non-optional**: `synthetic: true` plus a disclaimer in
the show notes, a spoken disclaimer prepended in a non-cloned voice, and an
AudioSeal watermark. Do not add a path that clones without them.

Custom editorial guidance: `JobOptions.custom_prompt` (whole digest) and
`episode_prompts` (per episode guid). Cap is `MAX_PROMPT_CHARS` (4000).

---

## Python

- `from __future__ import annotations` at the top of modules.
- Ruff: line length 100, select `E,F,I,UP,B`, target py312.
- Type hints on public APIs; pydantic models for anything that crosses a seam.
- Tests live at `tests/unit/<module>/test_*.py`, mirroring src. Integration tests
  inject a `Deps` of fakes — copy `tests/integration/test_pipeline_end_to_end.py`.
- Prefer extending a fake over hitting the network or GPU.
- Construct `Settings(_env_file=None)` in tests so the developer's `.env` cannot
  leak in.
- `numpy` is a **base** dependency: cross-episode speaker clustering is imported
  even in fake mode (`./launch --fake` runs `uv sync` without `[gpu]`). Do not
  move that import behind the extra.

---

## Web (`web/`)

React 19 + Vite 8 + Tailwind + TanStack Query + React Router (`basename="/app"`).

- API client: `web/src/api/client.ts` — same-origin `fetch`, bearer from
  `localStorage.api_token`.
- Types in `web/src/api/types.ts` must stay aligned with `api/schemas.py`.
- Tests co-located as `*.test.ts` / `*.test.tsx`. MSW lives in
  `web/src/test/msw.ts` and is configured `onUnhandledRequest: 'error'`.
- Vite `base: '/app/'`. The dev server proxies `/feeds`, `/jobs`, `/voices`,
  `/settings`, `/health` to the API (`API_PROXY_TARGET`, default
  `http://localhost:8000`).
- UI primitives: `web/src/components/ui/`. Routes: `web/src/routes/`.
- After UI changes, run `npm test` and exercise the flow in the browser (or say
  what could not be verified). Check desktop and mobile viewports when layout
  changes.

---

## GPU / real-mode traps

- Default `USE_FAKES=true`. Real STT/TTS need CUDA and the `[gpu]` extra.
- On 8 GB (RTX 4060 class) set `WHISPER_MODEL=small`. `large-v3` will not fit
  beside F5-TTS. `config.py`'s unset default is `large-v3`; `.env.example`
  recommends `small` — do not "fix" one to match the other without checking VRAM.
- Faster-whisper's CTranslate2 is CUDA 12. A CUDA 13 PyTorch build only ships
  libcublas 13, so the `[gpu]` extra includes `nvidia-cublas-cu12` /
  `nvidia-cuda-runtime-cu12` and `FasterWhisperTranscriber` preloads them. Do not
  "fix" this with `LD_LIBRARY_PATH`.
- `ffmpeg` is required for real transcode and reference-clip extraction; fake
  mode skips it.
- Ollama is unloaded after each call (`keep_alive=0`) so it does not sit on VRAM
  for the default five minutes.

---

## Do not

- Commit on `main`. Branch `feat|fix|chore|docs|refactor|test|ci/<slug>`, open a
  PR, stop — do not self-merge.
- Commit `data/`, `.env`, model caches, or generated audio. Exception:
  `assets/voice-samples/*.wav`.
- Import `torch`, `faster_whisper`, `f5_tts`, `kokoro`, `pyannote`, or
  `audioseal` at module import time.
- Bypass `JobRepository` / `SettingsRepository` or write SQL in nodes/routes.
- Duplicate pipeline business rules in the PWA.
- Silently fall through an unrecognized `LLM_BACKEND` / `TTS_BACKEND` in new
  code. `_build_real_llms` currently falls through to Anthropic on a junk
  backend (only reachable via DB tampering; the API validates). Do not widen
  that gap — the README roadmap wants it to raise.
- Present cloned audio as the original hosts.

---

## Git

This is `github.com/behradkhodayar/repodify`. One PR per logical unit. On the
feature branch, land several small meaningful commits (one per logical step or
TDD task) rather than a single mega-commit — PR #49 is the model, not PR #48.
Imperative commit messages (what + why), no emojis, PR title ≤ 70 chars; details
go in the body. Reference issues with `Closes #N` when applicable.
