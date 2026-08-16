"""The Storage port: where the pipeline reads and writes blobs."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Storage(Protocol):
    """A content-addressable-ish blob store keyed by string paths.

    Implementations return a storage URI from write methods. `local_path`
    exposes a real filesystem path for tools (ffmpeg, model loaders) that need
    a file on disk.
    """

    def put_bytes(self, key: str, data: bytes) -> str:
        """Write bytes under `key`; return the storage URI."""
        ...

    def get_bytes(self, key: str) -> bytes:
        """Read the bytes stored under `key`."""
        ...

    def put_file(self, key: str, src: Path) -> str:
        """Copy the file at `src` to `key`; return the storage URI."""
        ...

    def local_path(self, key: str) -> Path:
        """Return a local filesystem path for `key` (may not yet exist)."""
        ...

    def exists(self, key: str) -> bool:
        """Whether an object exists under `key`."""
        ...
