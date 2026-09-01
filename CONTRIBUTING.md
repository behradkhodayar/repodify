# Contributing to Repodify

Thanks for your interest in improving Repodify. This guide covers local setup, the
test loop, and the pull-request workflow. For the deeper "why" behind the
structure, read the [**architecture reference**](docs/architecture.md); for the
hard invariants the codebase depends on, read [**`AGENTS.md`**](AGENTS.md).

## Setup

```bash
uv sync                 # Python core + dev deps (creates .venv from uv.lock)
uv sync --extra gpu     # only on a CUDA host, for real STT/TTS/diarization
cp .env.example .env    # optional; defaults run in keyless fake mode

cd web && npm install   # web client deps
```

You do **not** need a GPU, API keys, or ffmpeg to develop and test. Everything
runs in fake mode by default.

## The test loop

```bash
uv run pytest                    # whole pipeline + API on CPU, no network
uv run ruff check src tests
uv run ruff format src tests

cd web && npm test               # Vitest + MSW component/hook tests
cd web && npm run lint           # tsc -b
```

The default Python suite **must stay GPU-, network-, and ffmpeg-free.** HTTP is
mocked with `respx`; every ML dependency sits behind a fake in `ports/`. Prefer
extending a fake over reaching for the network or a real model. Construct
`Settings(_env_file=None)` in tests so a developer's local `.env` can't leak in.

There is no CI yet, so a green `uv run pytest` plus `npm test` / `npm run lint`
in `web/` is the gate before you open a PR.

## Architectural rules worth knowing before you code

These are the conventions that keep the project testable and swappable; breaking
them tends to break the CPU test path. Full detail in [`AGENTS.md`](AGENTS.md).

- **Two processes, shared state.** The API and the worker never call each other —
  they share Redis (job ids), the SQL DB (job/stage/artifact/settings), and the
  filesystem object store. Use the composition roots (`api/app.py`,
  `worker/main.py`); don't wire dependencies elsewhere.
- **Ports & adapters.** To add an ML or hosted backend: (1) add a `Protocol` +
  `Fake*` together in `ports/`; (2) put the real adapter next to its domain
  (`transcribe/`, `synth/`, `ports/llm.py`); (3) wire it in `build_deps` behind
  `USE_FAKES`; (4) **lazy-import** heavy/GPU SDKs *inside* the adapter, never at
  module import; (5) expose `release()` if it holds VRAM.
- **DB access is repository-only.** Go through `JobRepository` /
  `SettingsRepository`; never open a SQLAlchemy session in a node or route.
- **Keep the domain and persistence models distinct** (`models/domain.py` vs
  `models/db.py`).
- **Cloning guardrails are non-optional.** Any cloned output must be labeled
  synthetic, carry a spoken disclaimer, and be watermarked. Do not add a path that
  clones without them.

## Pull-request workflow

1. Branch off the default branch: `feat|fix|chore|docs|refactor|test|ci/<slug>`.
2. Make one logical change per PR. Land several small, meaningful commits rather
   than one mega-commit.
3. Commit messages: imperative mood, *what + why*, no emojis. Reference issues with
   `Closes #N` when applicable.
4. Ensure the test loop above is green, then open the PR with a Summary + Test plan.
   PR title ≤ 70 chars; details go in the body.

## Reporting bugs & requesting features

Open a GitHub issue. For bugs, include the run mode (fake / real-gpu / real-byok),
what you did, what you expected, and what happened. For features, check the
[Roadmap](README.md#roadmap) first.
