"""JSON-file cache for directory searches and RSS bodies."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from repodify.ingest.normalize import normalize_feed_url

SEARCH_TTL_S = 24 * 3600
SEARCH_STALE_TTL_S = 7 * 24 * 3600


class JsonCache:
    """Two stores under one directory: `search-*` payloads and `feed-*` bodies."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def get_search(
        self,
        key: str,
        ttl_s: float = SEARCH_TTL_S,
        stale_ttl_s: float | None = None,
        *,
        now: float | None = None,
    ) -> tuple[Any, bool] | None:
        """Return `(payload, stale)` if present and young enough."""
        path = self._search_path(key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        stored_at = float(data.get("stored_at") or 0)
        age = (now if now is not None else time.time()) - stored_at
        if age <= ttl_s:
            return data.get("payload"), False
        if stale_ttl_s is not None and age <= stale_ttl_s:
            return data.get("payload"), True
        return None

    def put_search(self, key: str, payload: Any, *, now: float | None = None) -> None:
        path = self._search_path(key)
        path.write_text(
            json.dumps({"stored_at": now if now is not None else time.time(), "payload": payload})
        )

    def get_feed(self, url: str) -> dict[str, Any] | None:
        path = self._feed_path(url)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        body_b64 = data.get("body_b64") or ""
        return {
            "etag": data.get("etag"),
            "last_modified": data.get("last_modified"),
            "body": base64.b64decode(body_b64) if body_b64 else b"",
            "final_url": data.get("final_url") or url,
            "fetched_at": data.get("fetched_at") or 0.0,
            "body_hash": data.get("body_hash") or "",
        }

    def put_feed(self, url: str, record: dict[str, Any]) -> None:
        path = self._feed_path(url)
        body: bytes = record.get("body") or b""
        path.write_text(
            json.dumps(
                {
                    "etag": record.get("etag"),
                    "last_modified": record.get("last_modified"),
                    "body_b64": base64.b64encode(body).decode("ascii"),
                    "final_url": record.get("final_url") or url,
                    "fetched_at": record.get("fetched_at") or time.time(),
                    "body_hash": record.get("body_hash") or hashlib.sha256(body).hexdigest(),
                }
            )
        )

    def rekey_feed(self, old_url: str, new_url: str) -> None:
        record = self.get_feed(old_url)
        if record is None:
            return
        self.put_feed(new_url, record)
        old = self._feed_path(old_url)
        if old.is_file() and normalize_feed_url(old_url) != normalize_feed_url(new_url):
            old.unlink()

    def _search_path(self, key: str) -> Path:
        return self.root / f"search-{_hash(key)}.json"

    def _feed_path(self, url: str) -> Path:
        return self.root / f"feed-{_hash(normalize_feed_url(url))}.json"


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
