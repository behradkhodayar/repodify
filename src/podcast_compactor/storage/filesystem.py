"""Filesystem-backed Storage implementation."""

from __future__ import annotations

import shutil
from pathlib import Path


class FilesystemStorage:
    """Stores blobs as files under a root directory."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def local_path(self, key: str) -> Path:
        # Absolute so callers can do `local_path(...).as_uri()` — `Path.as_uri()`
        # raises on relative paths, and `root` may be relative (e.g. DATA_DIR=data).
        return (self.root / key).absolute()

    def _ensure_parent(self, key: str) -> Path:
        path = self.local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put_bytes(self, key: str, data: bytes) -> str:
        path = self._ensure_parent(key)
        path.write_bytes(data)
        return path.resolve().as_uri()

    def get_bytes(self, key: str) -> bytes:
        return self.local_path(key).read_bytes()

    def put_file(self, key: str, src: Path) -> str:
        path = self._ensure_parent(key)
        shutil.copyfile(src, path)
        return path.resolve().as_uri()

    def exists(self, key: str) -> bool:
        return self.local_path(key).exists()
