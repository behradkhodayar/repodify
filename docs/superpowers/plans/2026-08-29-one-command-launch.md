# One-command launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single command (`./launch`) that sets up and runs the entire repodify stack — Redis, API, worker, and the web PWA — with GPU-aware mode selection, an interactive BYOK wizard when there's no GPU, and automatic port-conflict handling.

**Architecture:** A single bash orchestrator at the repo root. Pure helpers (free-port selection, `.env` upsert, mode resolution, stale-check) are exposed as hidden `__subcommands` so they're unit-testable via `uv run pytest` shelling out to the script; the side-effecting orchestration phases (deps, infra, running the three processes) are composed from those helpers and verified with explicit manual smoke steps. A thin `Makefile` wraps the script.

**Tech Stack:** Bash (bash-only features: `/dev/tcp`, `read -rs`, traps), `uv`, `docker compose`, `npm`/Vite, pytest (for the helper tests, shelling out via `subprocess`).

## Global Constraints

- **Never commit to `main`.** Work happens on branch `feat/one-command-launch` (already created and checked out).
- **Commit messages:** imperative mood, what + why. **No emojis. No `Co-Authored-By` / Claude trailers** (user rule overrides the harness default).
- **Test runner:** `uv run pytest`. Helper tests live under `tests/launch/` and shell out to `./launch` via `subprocess`, so they need no `[gpu]` extra and run on CPU.
- **`launch` must be `shellcheck`-clean** and start with `#!/usr/bin/env bash` + `set -euo pipefail`.
- **`.env` is sacred:** never overwrite an existing `.env`; only surgical key upserts. Ephemeral ports/URLs are **exported into the environment**, never written to `.env`.
- **`.env` keys** touched are uppercase identifiers (`[A-Z0-9_]+`), safe to match as regex anchors.
- **Testability seam:** GPU detection honors `REPODIFY_GPU_OVERRIDE` (`1`/`0`) when set, so tests force either branch without hardware.

---

## File Structure

- **Create `launch`** (repo root, executable) — the whole orchestrator: pure helpers + orchestration phases + a dispatch `case` that routes `__subcommands` to helpers and everything else to `main`.
- **Create `Makefile`** (repo root) — `run` / `fake` / `stop` targets wrapping `./launch`.
- **Create `tests/launch/test_launch.py`** — pytest unit tests for the pure helpers, shelling out to `./launch __…`.
- **Modify `web/vite.config.ts`** — proxy target from `process.env.API_PROXY_TARGET || 'http://localhost:8000'`.
- **Modify `docker-compose.yml`** — parameterize host port mappings via `${REDIS_HOST_PORT:-6379}` / `${POSTGRES_HOST_PORT:-5432}`.
- **Modify `README.md`** — add a "Quick start: one command" section.

The `launch` script is one file by design: bash orchestration reads best top-to-bottom in a single unit, and the helpers/phases are already small, named functions. Splitting into sourced files would add path-resolution complexity for no clarity gain.

---

## Task 1: `launch` skeleton — dispatch, flag parsing, `--help`

**Files:**
- Create: `launch`
- Test: manual (usage/exit-code smoke)

**Interfaces:**
- Produces: an executable `./launch` with a dispatch `case`; flags `--fake`, `--real`, `--postgres`, `--help`; sets global vars `MODE_FLAG` (`fake|real|""`), `WITH_POSTGRES` (`0|1`). Later tasks add `__subcommand` branches and phase functions and flesh out `main`.

- [ ] **Step 1: Create the script skeleton**

Create `launch`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# repodify one-command launcher. Runs from the repo root regardless of CWD.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

MODE_FLAG=""       # "fake" | "real" | "" (auto-detect)
WITH_POSTGRES=0

usage() {
  cat <<'EOF'
repodify launcher — set up and run the whole stack with one command.

Usage: ./launch [options]

Options:
  --fake        Force fake mode (CPU, instant, no keys). Dev path.
  --real        Force real mode even if GPU detection is inconclusive.
  --postgres    Also start Postgres and use it (default run uses SQLite + Redis).
  --help        Show this help.

With no flags: detect a CUDA GPU and run real local backends; with no GPU,
run the BYOK setup wizard for hosted services. Occupied ports are remapped
automatically.
EOF
}

parse_flags() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --fake)     MODE_FLAG="fake" ;;
      --real)     MODE_FLAG="real" ;;
      --postgres) WITH_POSTGRES=1 ;;
      --help|-h)  usage; exit 0 ;;
      *) echo "launch: unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
  done
}

main() {
  parse_flags "$@"
  echo "launch: mode_flag='${MODE_FLAG}' with_postgres=${WITH_POSTGRES} (skeleton)"
}

# Dispatch: hidden __subcommands route to helpers (used by tests); everything
# else runs the full launcher.
case "${1:-}" in
  *) main "$@" ;;
esac
```

- [ ] **Step 2: Make it executable and smoke-test**

Run:
```bash
chmod +x launch
./launch --help; echo "exit=$?"
./launch --fake --postgres
./launch --bogus; echo "exit=$?"
```
Expected: `--help` prints usage and `exit=0`; `--fake --postgres` prints `mode_flag='fake' with_postgres=1 (skeleton)`; `--bogus` prints an unknown-option error and `exit=2`.

- [ ] **Step 3: Shellcheck**

Run: `shellcheck launch || echo "shellcheck not installed — skip"`
Expected: no warnings (or the skip line if shellcheck is absent).

- [ ] **Step 4: Commit**

```bash
git add launch
git commit -m "Add launch script skeleton with flag parsing and help"
```

---

## Task 2: free-port helper

**Files:**
- Modify: `launch` (add `port_in_use`, `free_port`, `__freeport` dispatch branch)
- Test: `tests/launch/test_launch.py`

**Interfaces:**
- Produces: `free_port <preferred>` prints the preferred port if free, else the next free port scanning upward. Exposed as `./launch __freeport <preferred>`.

- [ ] **Step 1: Write the failing test**

Create `tests/launch/test_launch.py`:

```python
"""Unit tests for the pure helpers in ./launch, exercised via subcommands."""
from __future__ import annotations

import socket
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCH = REPO_ROOT / "launch"


def run(*args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(LAUNCH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        **kwargs,
    )


def test_free_port_returns_preferred_when_free() -> None:
    # Bind a socket, learn a definitely-free port, release it, then ask for it.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    out = run("__freeport", str(free))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == str(free)


def test_free_port_skips_occupied_port() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        occupied = s.getsockname()[1]
        out = run("__freeport", str(occupied))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() != str(occupied)
    assert int(out.stdout.strip()) > occupied
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/launch/test_launch.py -v`
Expected: FAIL — `__freeport` falls through to `main`, so stdout is the skeleton line, not a port number.

- [ ] **Step 3: Add the helper and dispatch branch**

In `launch`, add these functions before `main`:

```bash
# True if something is listening on 127.0.0.1:<port>. Uses bash /dev/tcp, no deps.
port_in_use() {
  local port="$1"
  if (exec 3<>"/dev/tcp/127.0.0.1/${port}") 2>/dev/null; then
    exec 3>&- 3<&-
    return 0
  fi
  return 1
}

# Print <preferred> if free, else the next free port scanning upward.
free_port() {
  local port="$1"
  while port_in_use "$port"; do
    port=$((port + 1))
  done
  printf '%s\n' "$port"
}
```

Change the dispatch `case` to:

```bash
case "${1:-}" in
  __freeport) shift; free_port "$@" ;;
  *) main "$@" ;;
esac
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/launch/test_launch.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add launch tests/launch/test_launch.py
git commit -m "Add free-port helper for automatic port remapping"
```

---

## Task 3: `.env` upsert helpers

**Files:**
- Modify: `launch` (add `env_get`, `env_upsert`, `__env-get`/`__env-set` branches)
- Test: `tests/launch/test_launch.py`

**Interfaces:**
- Produces: `env_get <file> <key>` prints the value (empty if absent); `env_upsert <file> <key> <value>` sets the key, updating in place if present else appending, preserving all other lines. Exposed as `./launch __env-get <file> <key>` and `./launch __env-set <file> <key> <value>`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/launch/test_launch.py`:

```python
def test_env_upsert_appends_new_key(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("EXISTING=1\n")
    assert run("__env-set", str(env), "API_TOKEN", "abc").returncode == 0
    text = env.read_text()
    assert "EXISTING=1\n" in text
    assert "API_TOKEN=abc\n" in text


def test_env_upsert_updates_in_place_without_duplicating(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("USE_FAKES=true\nKEEP=yes\n")
    assert run("__env-set", str(env), "USE_FAKES", "false").returncode == 0
    text = env.read_text()
    assert text.count("USE_FAKES=") == 1
    assert "USE_FAKES=false\n" in text
    assert "KEEP=yes\n" in text


def test_env_upsert_preserves_values_with_equals_signs(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("")
    url = "postgresql+psycopg://u:p@localhost:5432/db?x=1"
    assert run("__env-set", str(env), "DATABASE_URL", url).returncode == 0
    assert run("__env-get", str(env), "DATABASE_URL").stdout.strip() == url


def test_env_get_missing_key_is_empty(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("A=1\n")
    out = run("__env-get", str(env), "NOPE")
    assert out.returncode == 0
    assert out.stdout.strip() == ""
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/launch/test_launch.py -k env -v`
Expected: FAIL (subcommands fall through to `main`).

- [ ] **Step 3: Implement the helpers and branches**

Add to `launch` before `main`:

```bash
# Print the value of <key> in <file>, or nothing if absent (first match wins).
env_get() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 0
  awk -v k="$key" 'index($0, k "=") == 1 { print substr($0, length(k) + 2); exit }' "$file"
}

# Set <key>=<value> in <file>: update the line in place if present, else append.
# Keys are uppercase identifiers, safe to anchor. Values may contain '='.
env_upsert() {
  local file="$1" key="$2" value="$3" tmp
  touch "$file"
  tmp="$(mktemp)"
  awk -v k="$key" -v v="$value" '
    index($0, k "=") == 1 { print k "=" v; found = 1; next }
    { print }
    END { if (!found) print k "=" v }
  ' "$file" >"$tmp"
  mv "$tmp" "$file"
}
```

Extend the dispatch `case`:

```bash
  __env-get) shift; env_get "$@" ;;
  __env-set) shift; env_upsert "$@" ;;
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/launch/test_launch.py -k env -v`
Expected: PASS (all four).

- [ ] **Step 5: Commit**

```bash
git add launch tests/launch/test_launch.py
git commit -m "Add .env upsert/get helpers for surgical config writes"
```

---

## Task 4: mode resolution + GPU detection seam

**Files:**
- Modify: `launch` (add `gpu_available`, `resolve_mode`, `__resolve-mode` branch)
- Test: `tests/launch/test_launch.py`

**Interfaces:**
- Consumes: `MODE_FLAG` global.
- Produces: `gpu_available` returns 0/1 (honors `REPODIFY_GPU_OVERRIDE` when set, else `nvidia-smi -L`); `resolve_mode` prints exactly one of `fake` | `real-gpu` | `real-byok`. Exposed as `./launch __resolve-mode` (respects `--fake`/`--real` args and `REPODIFY_GPU_OVERRIDE`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/launch/test_launch.py`:

```python
import os


def run_env(*args: str, env_extra: dict[str, str]):
    env = {**os.environ, **env_extra}
    return subprocess.run(
        [str(LAUNCH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_resolve_mode_fake_flag_wins() -> None:
    out = run_env("__resolve-mode", "--fake", env_extra={"REPODIFY_GPU_OVERRIDE": "1"})
    assert out.stdout.strip() == "fake"


def test_resolve_mode_gpu_present_is_real_gpu() -> None:
    out = run_env("__resolve-mode", env_extra={"REPODIFY_GPU_OVERRIDE": "1"})
    assert out.stdout.strip() == "real-gpu"


def test_resolve_mode_no_gpu_is_real_byok() -> None:
    out = run_env("__resolve-mode", env_extra={"REPODIFY_GPU_OVERRIDE": "0"})
    assert out.stdout.strip() == "real-byok"


def test_resolve_mode_real_flag_without_gpu_is_real_byok() -> None:
    out = run_env("__resolve-mode", "--real", env_extra={"REPODIFY_GPU_OVERRIDE": "0"})
    assert out.stdout.strip() == "real-byok"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/launch/test_launch.py -k resolve_mode -v`
Expected: FAIL.

- [ ] **Step 3: Implement and wire the branch**

Add to `launch` before `main`:

```bash
# 0 (true) if a CUDA GPU is available. REPODIFY_GPU_OVERRIDE forces the answer
# for tests: "1" => available, "0" => not.
gpu_available() {
  if [[ -n "${REPODIFY_GPU_OVERRIDE:-}" ]]; then
    [[ "$REPODIFY_GPU_OVERRIDE" == "1" ]]
    return
  fi
  command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1
}

# Print the resolved run mode: fake | real-gpu | real-byok.
resolve_mode() {
  if [[ "$MODE_FLAG" == "fake" ]]; then
    printf 'fake\n'
  elif gpu_available; then
    printf 'real-gpu\n'
  else
    printf 'real-byok\n'
  fi
}
```

The `__resolve-mode` branch must parse flags first (so `--fake`/`--real` are honored). Add to the dispatch `case`:

```bash
  __resolve-mode) shift; parse_flags "$@"; resolve_mode ;;
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/launch/test_launch.py -k resolve_mode -v`
Expected: PASS (all four).

- [ ] **Step 5: Commit**

```bash
git add launch tests/launch/test_launch.py
git commit -m "Add GPU-aware run-mode resolution with a test override seam"
```

---

## Task 5: preflight tool checks

**Files:**
- Modify: `launch` (add `have_tool`, `require_tool`, `preflight`, `__have-tool` branch)
- Test: `tests/launch/test_launch.py`

**Interfaces:**
- Produces: `have_tool <name>` returns 0/1; `require_tool <name> <hint>` exits 1 with a hint if missing; `preflight` checks `uv`, `node`, `npm`, a container engine, and warns on missing `ffmpeg`. Exposed as `./launch __have-tool <name>`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/launch/test_launch.py`:

```python
def test_have_tool_true_for_bash() -> None:
    out = run("__have-tool", "bash")
    assert out.returncode == 0


def test_have_tool_false_for_missing() -> None:
    out = run("__have-tool", "definitely-not-a-real-tool-xyz")
    assert out.returncode == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/launch/test_launch.py -k have_tool -v`
Expected: FAIL (fall-through to `main` returns 0 for both).

- [ ] **Step 3: Implement**

Add to `launch` before `main`:

```bash
have_tool() { command -v "$1" >/dev/null 2>&1; }

require_tool() {
  local name="$1" hint="$2"
  if ! have_tool "$name"; then
    echo "launch: required tool '$name' not found. $hint" >&2
    exit 1
  fi
}

# Detect a container engine; echo the command to use ("docker" or "podman").
container_cmd() {
  if have_tool docker; then echo "docker";
  elif have_tool podman; then echo "podman";
  else return 1; fi
}

preflight() {
  require_tool uv "Install uv: https://docs.astral.sh/uv/"
  require_tool node "Install Node.js 20+: https://nodejs.org/"
  require_tool npm "npm ships with Node.js: https://nodejs.org/"
  if ! container_cmd >/dev/null; then
    echo "launch: need docker or podman for Redis. Install Docker: https://docs.docker.com/get-docker/" >&2
    exit 1
  fi
  if ! have_tool ffmpeg; then
    echo "launch: warning — ffmpeg not found; real runs transcode to mp3 and need it." >&2
  fi
}
```

Add the dispatch branch:

```bash
  __have-tool) shift; have_tool "$1" ;;
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/launch/test_launch.py -k have_tool -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add launch tests/launch/test_launch.py
git commit -m "Add preflight tool checks with install hints"
```

---

## Task 6: source edits — Vite proxy env + compose port params

**Files:**
- Modify: `web/vite.config.ts:29-36`
- Modify: `docker-compose.yml`
- Test: manual (`docker compose config`) + existing web test suite

**Interfaces:**
- Produces: Vite proxy target read from `process.env.API_PROXY_TARGET` (default unchanged); compose host ports read from `REDIS_HOST_PORT` / `POSTGRES_HOST_PORT` (defaults unchanged).

- [ ] **Step 1: Edit the Vite proxy**

In `web/vite.config.ts`, replace the hardcoded `server.proxy` block. Add near the top of the config factory (inside `defineConfig`, before `plugins` is fine to compute a const above the returned object — restructure to a function body):

```ts
const apiTarget = process.env.API_PROXY_TARGET || 'http://localhost:8000'
```

and set:

```ts
  server: {
    proxy: {
      '/feeds': apiTarget,
      '/jobs': apiTarget,
      '/voices': apiTarget,
      '/health': apiTarget,
    },
  },
```

To introduce `apiTarget`, change `export default defineConfig({ … })` to:

```ts
export default defineConfig(() => {
  const apiTarget = process.env.API_PROXY_TARGET || 'http://localhost:8000'
  return {
    base: '/app/',
    plugins: [ /* unchanged */ ],
    server: {
      proxy: {
        '/feeds': apiTarget,
        '/jobs': apiTarget,
        '/voices': apiTarget,
        '/health': apiTarget,
      },
    },
    test: { /* unchanged */ },
  }
})
```

- [ ] **Step 2: Verify the web build/tests still pass**

Run: `cd web && npm run build && npm test && cd ..`
Expected: build succeeds; Vitest suite passes (config change is backward-compatible).

- [ ] **Step 3: Parameterize compose ports**

In `docker-compose.yml`, change the two `ports:` mappings:

```yaml
  redis:
    ...
    ports:
      - "${REDIS_HOST_PORT:-6379}:6379"
  postgres:
    ...
    ports:
      - "${POSTGRES_HOST_PORT:-5432}:5432"
```

- [ ] **Step 4: Verify compose interpolation**

Run:
```bash
REDIS_HOST_PORT=6390 docker compose config | grep -E '6390:6379'
docker compose config | grep -E '6379:6379'
```
Expected: first prints the remapped mapping; second confirms the default is preserved when the var is unset.

- [ ] **Step 5: Commit**

```bash
git add web/vite.config.ts docker-compose.yml
git commit -m "Make Vite proxy target and compose host ports env-configurable"
```

---

## Task 7: BYOK wizard

**Files:**
- Modify: `launch` (add `prompt_choice`, `prompt_secret`, `byok_wizard`, `__byok` branch)
- Test: `tests/launch/test_launch.py`

**Interfaces:**
- Consumes: `env_upsert`, `env_get`.
- Produces: `byok_wizard <envfile>` interactively collects hosted-service config into `<envfile>`, sets `USE_FAKES=false`, reuses one OpenRouter key across LLM+TTS, and treats hosted STT as "coming soon" (captures the field, warns, falls back to local). Exposed as `./launch __byok <envfile>` reading answers from stdin.

- [ ] **Step 1: Write the failing tests**

Append to `tests/launch/test_launch.py`:

```python
def _env_map(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            out[k] = v
    return out


def test_byok_openrouter_llm_and_tts_share_one_key(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("")
    # answers: LLM backend = openrouter(2), OpenRouter key, STT = local(1), skip HF token
    answers = "2\nsk-or-shared\n1\n\n"
    out = run("__byok", str(env), input=answers)
    assert out.returncode == 0, out.stderr
    m = _env_map(env)
    assert m["USE_FAKES"] == "false"
    assert m["LLM_BACKEND"] == "openrouter"
    assert m["TTS_BACKEND"] == "openrouter"
    assert m["OPENROUTER_API_KEY"] == "sk-or-shared"


def test_byok_anthropic_llm_with_openrouter_tts(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("")
    # LLM = anthropic(1), anthropic key, OpenRouter key (for TTS), STT = local(1), HF token
    answers = "1\nsk-ant-xyz\nsk-or-tts\n1\nhf_abc\n"
    out = run("__byok", str(env), input=answers)
    assert out.returncode == 0, out.stderr
    m = _env_map(env)
    assert m["LLM_BACKEND"] == "anthropic"
    assert m["ANTHROPIC_API_KEY"] == "sk-ant-xyz"
    assert m["TTS_BACKEND"] == "openrouter"
    assert m["OPENROUTER_API_KEY"] == "sk-or-tts"
    assert m["HF_TOKEN"] == "hf_abc"


def test_byok_hosted_stt_warns_and_falls_back(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("")
    # LLM = openrouter(2), key, STT = hosted(2), skip HF token
    answers = "2\nsk-or-shared\n2\n\n"
    out = run("__byok", str(env), input=answers)
    assert out.returncode == 0, out.stderr
    assert "not yet implemented" in (out.stdout + out.stderr).lower()
    m = _env_map(env)
    # Forward-looking marker captured, but effective backend stays local for now.
    assert m.get("STT_BACKEND", "local") == "local"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/launch/test_launch.py -k byok -v`
Expected: FAIL.

- [ ] **Step 3: Implement the wizard**

Add to `launch` before `main`:

```bash
# Prompt for a numbered choice; echo the chosen number. Args: prompt, then options.
prompt_choice() {
  local prompt="$1"; shift
  local i=1
  echo "$prompt" >&2
  for opt in "$@"; do echo "  $i) $opt" >&2; i=$((i + 1)); done
  local ans
  read -r ans
  printf '%s\n' "$ans"
}

# Prompt for a secret without echoing; echo the entered value.
prompt_secret() {
  local prompt="$1" val
  printf '%s: ' "$prompt" >&2
  read -rs val
  echo >&2
  printf '%s\n' "$val"
}

byok_wizard() {
  local env="$1"
  echo "No CUDA GPU detected — configuring hosted services (BYOK)." >&2
  echo "Local F5-TTS / faster-whisper / pyannote need a GPU; using hosted where possible." >&2
  env_upsert "$env" USE_FAKES false

  # LLM backend
  local llm
  llm="$(prompt_choice "Choose an LLM backend:" anthropic openrouter ollama)"
  case "$llm" in
    1) env_upsert "$env" LLM_BACKEND anthropic
       env_upsert "$env" ANTHROPIC_API_KEY "$(prompt_secret 'ANTHROPIC_API_KEY')" ;;
    2) env_upsert "$env" LLM_BACKEND openrouter
       env_upsert "$env" OPENROUTER_API_KEY "$(prompt_secret 'OPENROUTER_API_KEY')" ;;
    3) env_upsert "$env" LLM_BACKEND ollama ;;
    *) echo "launch: invalid LLM choice '$llm'" >&2; return 1 ;;
  esac

  # TTS backend — hosted OpenRouter (local F5 needs a GPU). Reuse the key if set.
  env_upsert "$env" TTS_BACKEND openrouter
  if [[ -z "$(env_get "$env" OPENROUTER_API_KEY)" ]]; then
    env_upsert "$env" OPENROUTER_API_KEY "$(prompt_secret 'OPENROUTER_API_KEY (for hosted TTS)')"
  fi

  # STT backend — local CPU whisper, or hosted (coming soon → falls back).
  local stt
  stt="$(prompt_choice "Choose an STT backend:" "local faster-whisper (CPU, slow)" "hosted (BYOK) — coming soon")"
  case "$stt" in
    1) env_upsert "$env" STT_BACKEND local
       env_upsert "$env" WHISPER_MODEL small
       echo "launch: STT will run faster-whisper on CPU — transcription is slow." >&2 ;;
    2) env_upsert "$env" STT_BACKEND local
       env_upsert "$env" WHISPER_MODEL small
       echo "launch: hosted STT is not yet implemented — using CPU Whisper meanwhile." >&2 ;;
    *) echo "launch: invalid STT choice '$stt'" >&2; return 1 ;;
  esac

  # Diarization (optional) — HF token for pyannote. Blank to skip.
  local hf
  hf="$(prompt_secret 'HF_TOKEN for diarization (optional, Enter to skip)')"
  if [[ -n "$hf" ]]; then env_upsert "$env" HF_TOKEN "$hf"; fi
}
```

Add the dispatch branch:

```bash
  __byok) shift; byok_wizard "$@" ;;
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/launch/test_launch.py -k byok -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add launch tests/launch/test_launch.py
git commit -m "Add BYOK setup wizard for no-GPU hosted backends"
```

---

## Task 8: dependency sync helpers

**Files:**
- Modify: `launch` (add `npm_install_needed`, `sync_deps`, `__npm-needed` branch)
- Test: `tests/launch/test_launch.py`

**Interfaces:**
- Consumes: resolved mode string.
- Produces: `npm_install_needed <webdir>` returns 0 (needed) if `node_modules` is missing or `package-lock.json` is newer than the install marker; `sync_deps <mode>` runs `uv sync` (+ `--extra gpu` unless `fake`), conditional `npm install`, and `npm run build`. Exposed as `./launch __npm-needed <webdir>`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/launch/test_launch.py`:

```python
def test_npm_install_needed_when_node_modules_absent(tmp_path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "package-lock.json").write_text("{}")
    out = run("__npm-needed", str(web))
    assert out.returncode == 0  # 0 == install needed


def test_npm_install_not_needed_when_marker_fresh(tmp_path) -> None:
    web = tmp_path / "web"
    (web / "node_modules").mkdir(parents=True)
    lock = web / "package-lock.json"
    lock.write_text("{}")
    marker = web / "node_modules" / ".package-lock.json"
    marker.write_text("{}")
    # Make the marker newer than the lockfile.
    import os
    import time
    now = time.time()
    os.utime(lock, (now - 10, now - 10))
    os.utime(marker, (now, now))
    out = run("__npm-needed", str(web))
    assert out.returncode == 1  # 1 == up to date
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/launch/test_launch.py -k npm_install -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add to `launch` before `main`:

```bash
# Return 0 (needed) if web deps must be (re)installed, else 1 (up to date).
npm_install_needed() {
  local web="$1" marker="$1/node_modules/.package-lock.json"
  [[ -d "$web/node_modules" ]] || return 0
  [[ -f "$marker" ]] || return 0
  [[ "$web/package-lock.json" -nt "$marker" ]] && return 0
  return 1
}

sync_deps() {
  local mode="$1"
  echo "==> Syncing Python deps" >&2
  if [[ "$mode" == "fake" ]]; then
    uv sync
  else
    uv sync --extra gpu
  fi
  if npm_install_needed web; then
    echo "==> Installing web deps" >&2
    npm --prefix web install
  fi
  echo "==> Building web/dist" >&2
  npm --prefix web run build
}
```

Add the dispatch branch:

```bash
  __npm-needed) shift; npm_install_needed "$@" ;;
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/launch/test_launch.py -k npm_install -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add launch tests/launch/test_launch.py
git commit -m "Add dependency sync with stale-aware npm install"
```

---

## Task 9: port scan orchestration + summary

**Files:**
- Modify: `launch` (add `scan_ports`, `print_summary`, `__scanports` branch)
- Test: `tests/launch/test_launch.py`

**Interfaces:**
- Consumes: `free_port`, `WITH_POSTGRES`.
- Produces: `scan_ports` sets and exports `API_PORT`, `VITE_PORT`, `REDIS_HOST_PORT`, `API_PROXY_TARGET`, `REDIS_URL` (and `POSTGRES_HOST_PORT`, `DATABASE_URL` when `WITH_POSTGRES=1`), printing any substitutions. Exposed as `./launch __scanports` (prints the four resolved values as `KEY=value` lines).

- [ ] **Step 1: Write the failing test**

Append to `tests/launch/test_launch.py`:

```python
def test_scanports_remaps_occupied_api_port() -> None:
    # Occupy 8000 so the API port must move; parse the KEY=value output.
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", 8000))
        except OSError:
            import pytest
            pytest.skip("port 8000 unavailable to bind for the test")
        s.listen()
        out = run("__scanports")
    assert out.returncode == 0, out.stderr
    kv = dict(
        line.split("=", 1)
        for line in out.stdout.splitlines()
        if "=" in line
    )
    assert kv["API_PORT"] != "8000"
    assert kv["API_PROXY_TARGET"] == f"http://localhost:{kv['API_PORT']}"
    assert kv["REDIS_URL"] == f"redis://localhost:{kv['REDIS_HOST_PORT']}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/launch/test_launch.py -k scanports -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add to `launch` before `main`:

```bash
# Announce a port substitution to stderr.
_note_port() {
  local name="$1" want="$2" got="$3"
  if [[ "$want" != "$got" ]]; then
    echo "launch: $name port $want is busy — using $got instead." >&2
  fi
}

scan_ports() {
  local want_api=8000 want_vite=5173 want_redis=6379 want_pg=5432
  API_PORT="$(free_port "$want_api")";       _note_port API "$want_api" "$API_PORT"
  VITE_PORT="$(free_port "$want_vite")";      _note_port Vite "$want_vite" "$VITE_PORT"
  REDIS_HOST_PORT="$(free_port "$want_redis")"; _note_port Redis "$want_redis" "$REDIS_HOST_PORT"
  API_PROXY_TARGET="http://localhost:${API_PORT}"
  REDIS_URL="redis://localhost:${REDIS_HOST_PORT}"
  export API_PORT VITE_PORT REDIS_HOST_PORT API_PROXY_TARGET REDIS_URL
  if [[ "${WITH_POSTGRES:-0}" == "1" ]]; then
    POSTGRES_HOST_PORT="$(free_port "$want_pg")"; _note_port Postgres "$want_pg" "$POSTGRES_HOST_PORT"
    DATABASE_URL="postgresql+psycopg://repodify:repodify@localhost:${POSTGRES_HOST_PORT}/repodify"
    export POSTGRES_HOST_PORT DATABASE_URL
  fi
}

print_summary() {
  local mode="$1"
  cat >&2 <<EOF

  repodify is up — mode: ${mode}
  ------------------------------------------------------------
  API           http://localhost:${API_PORT}
  Built app     http://localhost:${API_PORT}/app/
  Vite dev      http://localhost:${VITE_PORT}/app/
  Redis         localhost:${REDIS_HOST_PORT}
  ------------------------------------------------------------
  Press Ctrl-C to stop the app (Redis stays up; 'make stop' halts it).
EOF
}
```

Add the dispatch branch (parse flags so `--postgres` is honored):

```bash
  __scanports) shift; parse_flags "$@"; scan_ports
                printf 'API_PORT=%s\nVITE_PORT=%s\nREDIS_HOST_PORT=%s\nAPI_PROXY_TARGET=%s\nREDIS_URL=%s\n' \
                  "$API_PORT" "$VITE_PORT" "$REDIS_HOST_PORT" "$API_PROXY_TARGET" "$REDIS_URL" ;;
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/launch/test_launch.py -k scanports -v`
Expected: PASS.

- [ ] **Step 5: Run the whole helper suite + shellcheck**

Run:
```bash
uv run pytest tests/launch/test_launch.py -v
shellcheck launch || echo "shellcheck not installed — skip"
```
Expected: all tests PASS; shellcheck clean.

- [ ] **Step 6: Commit**

```bash
git add launch tests/launch/test_launch.py
git commit -m "Add port-scan orchestration and launch summary"
```

---

## Task 10: infra + run wiring, Makefile, README

**Files:**
- Modify: `launch` (add `start_infra`, `run_processes`, flesh out `main`)
- Create: `Makefile`
- Modify: `README.md`
- Test: manual smoke (documented below)

**Interfaces:**
- Consumes: every helper/phase above.
- Produces: a fully wired `main`; `make run`/`make fake`/`make stop`.

- [ ] **Step 1: Implement infra + run + main**

Add to `launch` before `main`, and replace the skeleton `main`:

```bash
start_infra() {
  local services=("redis")
  [[ "${WITH_POSTGRES:-0}" == "1" ]] && services+=("postgres")
  echo "==> Starting infra: ${services[*]}" >&2
  docker compose up -d "${services[@]}"
  echo "==> Waiting for Redis to be healthy" >&2
  local tries=0
  until [[ "$(docker compose ps -q redis | xargs -r docker inspect -f '{{.State.Health.Status}}' 2>/dev/null)" == "healthy" ]]; do
    tries=$((tries + 1))
    if (( tries > 60 )); then
      echo "launch: Redis did not become healthy in time." >&2
      docker compose ps >&2
      docker compose logs --tail=40 redis >&2
      exit 1
    fi
    sleep 1
  done
}

# Prefix each line of a stream with a colored [label].
_prefix() {
  local label="$1" color="$2" reset=$'\033[0m'
  while IFS= read -r line; do printf '%b[%s]%b %s\n' "$color" "$label" "$reset" "$line"; done
}

run_processes() {
  local pids=()
  # shellcheck disable=SC2064
  trap 'echo; echo "launch: stopping…" >&2; kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null; exit 0' INT TERM

  ( uv run uvicorn --factory repodify.api.app:build_default_app \
      --port "$API_PORT" 2>&1 | _prefix api $'\033[36m' ) &
  pids+=($!)

  ( uv run arq repodify.worker.main.WorkerSettings 2>&1 | _prefix worker $'\033[35m' ) &
  pids+=($!)

  ( npm --prefix web run dev -- --port "$VITE_PORT" --strictPort 2>&1 | _prefix web $'\033[32m' ) &
  pids+=($!)

  wait
}

main() {
  parse_flags "$@"
  preflight
  local mode; mode="$(resolve_mode)"
  echo "==> Run mode: $mode" >&2
  [[ -f .env ]] || { echo "==> Creating .env from .env.example" >&2; cp .env.example .env; }
  if [[ "$mode" == "fake" ]]; then
    env_upsert .env USE_FAKES true
  elif [[ "$mode" == "real-byok" ]]; then
    byok_wizard .env
  else
    env_upsert .env USE_FAKES false
  fi
  sync_deps "$mode"
  scan_ports
  start_infra
  print_summary "$mode"
  run_processes
}
```

- [ ] **Step 2: Create the Makefile**

Create `Makefile` (tabs, not spaces, for recipe lines):

```makefile
.PHONY: run fake stop

run:
	./launch

fake:
	./launch --fake

stop:
	docker compose stop
```

- [ ] **Step 3: Add the README quick-start**

In `README.md`, add immediately after the intro paragraph (before "## Architecture (Phase 1)"):

```markdown
## Quick start: one command

```bash
./launch          # or: make run
```

Sets up and runs everything: syncs deps, builds the web app, starts Redis, and
runs the API, worker, and Vite dev server together. It detects a CUDA GPU and
runs the real local backends; with no GPU it walks you through a BYOK setup for
hosted services. Occupied ports are remapped automatically and reported. Use
`./launch --fake` for a keyless CPU dev run, `--postgres` to add Postgres, and
`make stop` to halt the containers. Press Ctrl-C to stop the app processes.
```

- [ ] **Step 4: Manual smoke test — fake mode**

Run: `./launch --fake`
Expected: `.env` gets `USE_FAKES=true`; deps sync; `web/dist` builds; Redis starts and reports healthy; three prefixed log streams (`[api]` cyan, `[worker]` magenta, `[web]` green) appear; the summary prints the URLs. Then in another shell:
```bash
curl -s "localhost:${API_PORT:-8000}/health"    # -> ok/health JSON
curl -sI "localhost:${API_PORT:-8000}/app/" | head -1   # -> 200
```
Open the Vite dev URL from the summary — the app loads. Press Ctrl-C in the launch shell: all three streams stop cleanly and the prompt returns.

- [ ] **Step 5: Manual smoke test — port remap**

In one shell: `python3 -c "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',8000)); s.listen(); time.sleep(120)"`
In another: `./launch --fake`
Expected: the summary reports `API port 8000 is busy — using 8001 instead.` (or next free), the Vite proxy still reaches the API, and `curl -sI localhost:<new_api_port>/app/ | head -1` returns `200`. Ctrl-C both.

- [ ] **Step 6: Full regression + shellcheck**

Run:
```bash
uv run pytest -q
shellcheck launch || echo "shellcheck not installed — skip"
```
Expected: full suite passes; shellcheck clean.

- [ ] **Step 7: Commit**

```bash
git add launch Makefile README.md
git commit -m "Wire launch orchestration, add Makefile and README quick-start"
```

---

## Self-Review notes

- **Spec coverage:** one-command entry (Task 1, 10) · GPU-aware mode + BYOK (Task 4, 7, 10) · fake escape hatch (Task 4, 10) · web served both ways — build + Vite dev (Task 8 build, Task 10 dev + summary) · port-conflict tolerance + threading (Task 9, source edits Task 6) · Redis-only default / Postgres opt-in (Task 9, 10) · `.env` bootstrap + surgical upserts (Task 3, 10) · preflight (Task 5) · hosted-STT surfaced-but-deferred (Task 7) · clean Ctrl-C teardown (Task 10). All spec sections map to a task.
- **Env threading:** `scan_ports` exports `REDIS_URL`/`DATABASE_URL`/`API_PROXY_TARGET` so pydantic-settings (env > `.env`) and the Vite proxy pick them up; BYOK secrets are the only persisted `.env` writes — matches the spec.
- **Type/name consistency:** helper names (`free_port`, `env_get`, `env_upsert`, `resolve_mode`, `gpu_available`, `npm_install_needed`, `scan_ports`, `byok_wizard`) and the exported vars (`API_PORT`, `VITE_PORT`, `REDIS_HOST_PORT`, `POSTGRES_HOST_PORT`, `API_PROXY_TARGET`, `REDIS_URL`, `DATABASE_URL`) are used identically across tasks and match the compose (`REDIS_HOST_PORT`/`POSTGRES_HOST_PORT`) and Vite (`API_PROXY_TARGET`) edits in Task 6.
- **Deferred by design:** hosted STT backend implementation (separate task, per spec).
