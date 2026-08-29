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
