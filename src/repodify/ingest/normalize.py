"""URL / query normalization, candidate merge, and ranking."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from repodify.models.domain import Candidate

_STOPWORDS = frozenset({"the", "a", "an", "podcast", "show", "feed", "official"})
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SLUG_STRIP_RE = re.compile(r"[^\w\s-]", re.UNICODE)
_SLUG_HYPHEN_RE = re.compile(r"[\s_]+")
_TRACKING = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "format"}
)


def normalize_feed_url(url: str) -> str:
    """Canonical merge key for a feed URL (not the stored `feed_url`)."""
    url = url.strip()
    parts = urlsplit(url)
    scheme = (parts.scheme or "https").lower()
    if scheme == "http":
        scheme = "https"
    host = (parts.hostname or "").lower()
    netloc = host
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"
    path = parts.path.rstrip("/")
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        low = key.lower()
        if low.startswith("utm_"):
            continue
        if low == "format" and value.lower() == "xml":
            continue
        if low in _TRACKING:
            continue
        kept.append((key, value))
    query = urlencode(kept)
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_query(q: str) -> str:
    """Lowercase, strip punctuation and directory-noise stopwords."""
    tokens = [t for t in _PUNCT_RE.sub(" ", q.lower()).split() if t and t not in _STOPWORDS]
    return " ".join(tokens)


def slug(value: str) -> str:
    value = _SLUG_STRIP_RE.sub("", value.lower().strip())
    return _SLUG_HYPHEN_RE.sub("-", value).strip("-")


def identity_keys(candidate: Candidate) -> list[str]:
    """Stable merge keys, strongest first."""
    keys: list[str] = []
    if candidate.itunes_id is not None:
        keys.append(f"itunes:{candidate.itunes_id}")
    if candidate.pi_feed_id is not None:
        keys.append(f"pi:{candidate.pi_feed_id}")
    if candidate.feed_url:
        keys.append(f"url:{normalize_feed_url(candidate.feed_url)}")
    if not keys:
        keys.append(f"slug:{slug(candidate.title)}:{slug(candidate.author)}")
    return keys


def merge_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Dedupe in arrival order; later hits update the existing row in place."""
    by_key: dict[str, Candidate] = {}
    ordered: list[Candidate] = []
    for raw in candidates:
        incoming = raw.model_copy(deep=True)
        existing = next((by_key[k] for k in identity_keys(incoming) if k in by_key), None)
        if existing is None:
            ordered.append(incoming)
            for key in identity_keys(incoming):
                by_key[key] = incoming
            continue
        _merge_into(existing, incoming)
        for key in identity_keys(existing):
            by_key[key] = existing
    return ordered


def rank(candidates: list[Candidate], query: str) -> list[Candidate]:
    """Sort dropdown rows: live, multi-source, relevant, recently updated."""
    q = query.lower().strip()

    def sort_key(c: Candidate) -> tuple:
        title = (c.title or "").lower()
        exact = 1 if title == q else 0
        fuzzy = SequenceMatcher(None, q, title).ratio() if q else 0.0
        return (
            1 if c.dead else 0,
            -len(c.sources),
            -exact,
            -fuzzy,
            -(c.newest_item or 0),
            -(c.episode_count or 0),
        )

    return sorted(candidates, key=sort_key)


def _merge_into(dst: Candidate, src: Candidate) -> None:
    dst.title = dst.title or src.title
    dst.author = dst.author or src.author
    if src.feed_url and (
        not dst.feed_url or (_is_feedburner(dst.feed_url) and not _is_feedburner(src.feed_url))
    ):
        dst.feed_url = src.feed_url
    dst.artwork = dst.artwork or src.artwork
    dst.itunes_id = dst.itunes_id or src.itunes_id
    dst.pi_feed_id = dst.pi_feed_id or src.pi_feed_id
    newest = [v for v in (dst.newest_item, src.newest_item) if v]
    dst.newest_item = max(newest) if newest else None
    if dst.episode_count is None:
        dst.episode_count = src.episode_count
    dst.language = dst.language or src.language
    dst.sources = sorted(set(dst.sources) | set(src.sources))
    dst.dead = bool(dst.dead or src.dead)
    dst.cached = bool(dst.cached and src.cached) if dst.sources and src.sources else dst.cached


def _is_feedburner(url: str) -> bool:
    return "feedburner.com" in url.lower()
