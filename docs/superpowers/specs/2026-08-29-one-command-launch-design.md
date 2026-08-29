# One-command launch — design

## Goal

A single command that stands up the entire cutcast stack — infrastructure,
Python API, worker, and the web PWA — on a developer or user machine, doing
whatever first-time setup is required along the way. It must be robust to the
common real-world snags: no GPU, missing API keys, and occupied ports.

Canonical invocation:

```bash
./launch
```

with `make run` as an equivalent wrapper.

## Requirements (from brainstorming)

1. **One command covers everything** — setup (deps, `.env`, container infra) and
   run, idempotently. Re-running is safe and fast.
2. **GPU-aware mode selection** — detect a CUDA GPU and run the real *local*
   backends (F5-TTS, faster-whisper, Kokoro, pyannote). With no GPU, guide the
   user through a **BYOK** (bring-your-own-key) setup for hosted services and run
   real. Fake mode is a dev-only escape hatch (`--fake`), not the default —
   "no one wants fake use" — but it must remain available.
3. **Web served both ways** — build `web/dist` (served by the API at `/app`) *and*
   run the Vite dev server (hot reload). Both are up after launch.
4. **Port-conflict tolerant** — if a required port is occupied, pick the next free
   port, tell the user, use it, and thread the new value through every consumer.

## Non-goals

- Containerizing the API/worker/web themselves (host-native `uv` flow is the
  verified GPU path; see `no-gpu-dev-environment` memory).
- A production process supervisor / systemd units. This is a launch/dev command.
- Implementing a hosted STT backend. The launcher *surfaces the option*; the
  backend itself is a follow-up task (see "Hosted STT" below).

## Entry points & flags

- `./launch` — bash orchestrator, executable, repo root. The one command.
- `Makefile` — thin front door:
  - `make` / `make run` → `./launch`
  - `make fake` → `./launch --fake`
  - `make stop` → stop the container infra (`docker compose stop`)
- Flags on `./launch`:
  - `--fake` — force fake mode (CPU, instant, no keys). Dev path.
  - `--real` — force real mode even if GPU detection is inconclusive.
  - `--postgres` — also start Postgres and set `DATABASE_URL` to it (default run
    uses SQLite and only needs Redis).
  - `--help` — usage.

Mode precedence: explicit `--fake`/`--real` flag > GPU auto-detect.

## Execution phases

The script runs these in order; each is idempotent.

### 1. Preflight

Verify required tools are on PATH and print a targeted install hint + exit on any
miss:

- `uv` (required), `node` + `npm` (required), a container engine (`docker` or
  `podman compose`; auto-pick).
- `ffmpeg` — **warn only** (real runs transcode to mp3 and extract reference
  clips; fake mode skips it).
- `nvidia-smi` — absence is not an error; it drives mode detection.

### 2. Resolve run mode

1. `--fake` → `USE_FAKES=true`, skip GPU/BYOK entirely.
2. `--real` → real mode, keep going.
3. Otherwise probe the GPU: `nvidia-smi -L` succeeds and lists a device → **real,
   local GPU backends**. No GPU → **real via BYOK wizard** (§4).

### 3. `.env` bootstrap

If `.env` is absent, copy `.env.example` → `.env`. Never overwrite an existing
`.env`. All subsequent writes are surgical key upserts (see §4).

### 4. BYOK wizard (no-GPU real path only)

Runs only when real mode is selected without a GPU. Explains up front: local
F5-TTS / faster-whisper / pyannote need a CUDA GPU, so this machine will use
hosted services where possible. Prompts **only for values not already present**
in `.env`, with masked input for secrets, and upserts each answer into `.env`.
Sets `USE_FAKES=false`.

Prompts:

- **LLM backend** — choose `anthropic` | `openrouter` | `ollama`.
  - `anthropic` → prompt `ANTHROPIC_API_KEY`.
  - `openrouter` → prompt `OPENROUTER_API_KEY`, set `LLM_BACKEND=openrouter`.
  - `ollama` → confirm `OLLAMA_BASE_URL` reachable; no key.
- **TTS backend** — hosted `openrouter` (local F5 needs a GPU). Prompt/reuse
  `OPENROUTER_API_KEY`; set `TTS_BACKEND=openrouter`.
- **STT backend** — menu:
  - `local` faster-whisper on **CPU** — real but slow; installs the ML extra;
    sets a small `WHISPER_MODEL`. Warned.
  - `hosted (BYOK)` — **surfaced now, not yet wired up**. Selecting it captures
    its BYOK field into `.env` (forward-looking key) and, for this task, warns
    "hosted STT not yet implemented — using CPU Whisper meanwhile" and falls back
    to the `local` behavior. The real backend arrives in a follow-up task.
- **Diarization** — optional `HF_TOKEN` (pyannote), needed only for speaker /
  cloning features; note these are GPU-preferred.

Idempotency: on a re-run, values already in `.env` are shown as "keeping
existing" and not re-prompted. A `--reconfigure` escape hatch is out of scope for
v1 (edit `.env` directly).

### 5. Dependencies

- `uv sync` — always. Add `--extra gpu` in real mode (GPU or no-GPU-real, since
  faster-whisper lives in that extra).
- `npm install` in `web/` — only if `node_modules` is missing or
  `package-lock.json` is newer than `node_modules/.package-lock.json` (stale
  check), to keep re-runs fast.
- `npm run build` in `web/` — emit `web/dist` for the API to serve at `/app`.

### 6. Port scan & threading

For each required port, check if it is free; if occupied, select the next free
port (scan upward), record it, and print the substitution. Ports:

- **API** — default 8000. Threaded to: `uvicorn --port`, `API_PROXY_TARGET`
  (`http://localhost:<api_port>`) for the Vite proxy, and printed URLs.
- **Vite** — default 5173. Threaded to `vite --port <n> --strictPort`.
- **Redis** — default 6379. Threaded to `REDIS_HOST_PORT` (compose host mapping)
  and exported `REDIS_URL=redis://localhost:<n>`.
- **Postgres** — default 5432, only with `--postgres`. Threaded to
  `POSTGRES_HOST_PORT` and the exported `DATABASE_URL`.

Threading mechanism: ephemeral values (ports/URLs) are **exported into the
environment** of the launched processes, not written to `.env`. pydantic-settings
gives env vars precedence over the `.env` file, so `REDIS_URL` / `DATABASE_URL`
exports win for the API and worker; the compose port mappings read the exported
`*_HOST_PORT` vars; Vite reads `API_PROXY_TARGET`. BYOK secrets (§4) are the only
things persisted to `.env`.

Free-port check: a small portable probe (Python `socket` one-liner or bash
`/dev/tcp`), no dependency on `lsof`/`ss` being present.

### 7. Infrastructure

`docker compose up -d redis` (and `postgres` when `--postgres`). Poll the
compose health status until `healthy` (bounded timeout, clear error on failure).

### 8. Run processes

Start concurrently, each piped through a colored `[label]` prefixer so logs
interleave readably:

- `[api]` — `uv run uvicorn --factory podcast_compactor.api.app:build_default_app --port <api_port>`
- `[worker]` — `uv run arq podcast_compactor.worker.main.WorkerSettings`
- `[web]` — `npm --prefix web run dev -- --port <vite_port> --strictPort`

A `trap` on `INT`/`TERM`/`EXIT` tears down all three (kill the process group).
Container infra is left running for fast subsequent launches; `make stop` stops
it.

### 9. Summary

Print resolved mode, chosen ports (with any substitutions called out), and the
live URLs:

- API: `http://localhost:<api_port>`
- Built app (API-served): `http://localhost:<api_port>/app/`
- Vite dev (hot reload): `http://localhost:<vite_port>/app/`

## Source changes required

Minimal, backward-compatible edits so the launcher can thread config:

1. `web/vite.config.ts` — proxy target from
   `process.env.API_PROXY_TARGET || 'http://localhost:8000'` (defaults preserve
   current behavior).
2. `docker-compose.yml` — parameterize host port mappings:
   `${REDIS_HOST_PORT:-6379}:6379` and `${POSTGRES_HOST_PORT:-5432}:5432`.
3. `README.md` — add a "Quick start: one command" section pointing at `./launch`.

## New files

- `launch` — bash orchestrator (executable), repo root.
- `Makefile` — `run` / `fake` / `stop` targets.

## Error handling

- Missing required tool → precise install hint, non-zero exit.
- Missing `ffmpeg` in real mode → warn, continue (transcode/reference-clip steps
  will surface their own errors if hit).
- Container infra fails to become healthy within timeout → print `docker compose
  ps` + `logs` tail, exit non-zero.
- No free port found in a bounded scan window → clear error naming the service.
- `Ctrl-C` at any point during the run phase → clean teardown via the trap.

## Testing / verification

This is an orchestration script; verification is by exercising it:

- `./launch --fake` on this box brings the stack up, all three logs stream, the
  built app loads at `/app/`, the Vite dev URL loads, and `Ctrl-C` tears
  everything down.
- Occupy 8000 (and/or 5173, 6379) beforehand and confirm the launcher reports the
  substitution and the app still works end to end on the new ports.
- `./launch` (real) on the GPU box selects real mode and `--extra gpu` sync.
- Shellcheck-clean `launch`.

## Open follow-ups (separate tasks)

- Implement the hosted STT backend that this launcher already surfaces as an
  option.
