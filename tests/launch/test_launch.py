"""Unit tests for the pure helpers in ./launch, exercised via subcommands."""
from __future__ import annotations

import os
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


def test_have_tool_true_for_bash() -> None:
    out = run("__have-tool", "bash")
    assert out.returncode == 0


def test_have_tool_false_for_missing() -> None:
    out = run("__have-tool", "definitely-not-a-real-tool-xyz")
    assert out.returncode == 1


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


def test_byok_rerun_keeps_existing_keys(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "USE_FAKES=false\nLLM_BACKEND=anthropic\nANTHROPIC_API_KEY=sk-ant-keep\n"
        "TTS_BACKEND=openrouter\nOPENROUTER_API_KEY=sk-or-keep\nHF_TOKEN=hf-keep\n"
        "STT_BACKEND=local\nWHISPER_MODEL=small\n"
    )
    # All keys already set: the wizard should keep them. Feed blank lines in case
    # any prompt still fires; assert nothing was blanked.
    out = run("__byok", str(env), input="\n\n\n\n\n\n")
    assert out.returncode == 0, out.stderr
    m = _env_map(env)
    assert m["ANTHROPIC_API_KEY"] == "sk-ant-keep"
    assert m["OPENROUTER_API_KEY"] == "sk-or-keep"
    assert m["HF_TOKEN"] == "hf-keep"
    assert m["USE_FAKES"] == "false"


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
