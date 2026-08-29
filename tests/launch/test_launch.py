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
