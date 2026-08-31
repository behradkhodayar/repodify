"""Classify a search-box string as a name, RSS URL, Apple URL, or iTunes id."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel

_APPLE_HOSTS = ("podcasts.apple.com", "itunes.apple.com")
_ID_RE = re.compile(r"id(\d{6,12})", re.IGNORECASE)
_BARE_ID_RE = re.compile(r"^\d{6,12}$")
_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


class QueryKind(StrEnum):
    NAME = "name"
    RSS_URL = "rss_url"
    APPLE_URL = "apple_url"
    ITUNES_ID = "itunes_id"


class ClassifiedQuery(BaseModel):
    kind: QueryKind
    raw: str
    url: str | None = None
    itunes_id: int | None = None


def classify(q: str) -> ClassifiedQuery:
    """Return the typed interpretation of a search-box string."""
    raw = q.strip()
    if _looks_like_url(raw):
        url = raw if _SCHEME_RE.match(raw) else f"https://{raw}"
        low = url.lower()
        if any(host in low for host in _APPLE_HOSTS):
            match = _ID_RE.search(url)
            return ClassifiedQuery(
                kind=QueryKind.APPLE_URL,
                raw=raw,
                url=url,
                itunes_id=int(match.group(1)) if match else None,
            )
        return ClassifiedQuery(kind=QueryKind.RSS_URL, raw=raw, url=url)
    if _BARE_ID_RE.match(raw):
        return ClassifiedQuery(kind=QueryKind.ITUNES_ID, raw=raw, itunes_id=int(raw))
    return ClassifiedQuery(kind=QueryKind.NAME, raw=raw)


def _looks_like_url(q: str) -> bool:
    low = q.lower()
    if _SCHEME_RE.match(low):
        return True
    if any(host in low for host in _APPLE_HOSTS):
        return True
    if low.startswith("feeds.") or "feedburner.com" in low:
        return True
    return False
