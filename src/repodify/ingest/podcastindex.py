"""Podcast Index API — optional BYOK upgrade over iTunes search."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import httpx

from repodify.ingest.identity import USER_AGENT
from repodify.ingest.itunes import ProviderResult, SearchCache
from repodify.models.domain import Candidate

logger = logging.getLogger(__name__)

PI_BASE = "https://api.podcastindex.org/api/1.0"
PI_TIMEOUT = 8.0


def pi_headers(key: str, secret: str, *, now: float | None = None) -> dict[str, str]:
    """Build the per-request auth headers (5-minute validity window)."""
    ts = str(int(now if now is not None else time.time()))
    auth = hashlib.sha1(f"{key}{secret}{ts}".encode()).hexdigest()
    return {
        "User-Agent": USER_AGENT,
        "X-Auth-Key": key,
        "X-Auth-Date": ts,
        "Authorization": auth,
    }


def search_podcastindex(
    term: str,
    http: httpx.Client,
    *,
    key: str,
    secret: str,
    cache: SearchCache,
    bytitle: bool = True,
    now: float | None = None,
) -> ProviderResult:
    """Query `/search/bytitle` (optional) and `/search/byterm`, then concatenate."""
    hits: list[Candidate] = []
    warning: str | None = None
    cached = True
    if bytitle:
        title = _pi_get(
            "/search/bytitle",
            {"q": term, "max": "8"},
            f"pi:bytitle:{term.lower().strip()}",
            http,
            key=key,
            secret=secret,
            cache=cache,
            now=now,
        )
        if title.warning:
            warning = title.warning
        hits.extend(title.candidates)
        cached = cached and title.cached if title.candidates or title.cached else cached
        if not title.cached:
            cached = False
    term_result = _pi_get(
        "/search/byterm",
        {"q": term, "max": "8"},
        f"pi:byterm:{term.lower().strip()}",
        http,
        key=key,
        secret=secret,
        cache=cache,
        now=now,
    )
    if term_result.warning:
        warning = term_result.warning
    hits.extend(term_result.candidates)
    if not term_result.cached:
        cached = False
    if not hits:
        cached = term_result.cached
    return ProviderResult(candidates=hits, cached=cached, warning=warning)


def podcasts_by_feed_url(
    url: str,
    http: httpx.Client,
    *,
    key: str,
    secret: str,
) -> Candidate | None:
    try:
        resp = http.get(
            f"{PI_BASE}/podcasts/byfeedurl",
            params={"url": url},
            headers=pi_headers(key, secret),
            timeout=PI_TIMEOUT,
        )
    except httpx.HTTPError:
        return None
    if not resp.is_success:
        return None
    feed = (resp.json() or {}).get("feed") or {}
    return _map_feed(feed)


def add_by_feed_url(
    url: str,
    http: httpx.Client,
    *,
    key: str,
    secret: str,
) -> None:
    """Best-effort index insert. Failures are logged, never raised."""
    try:
        resp = http.get(
            f"{PI_BASE}/add/byfeedurl",
            params={"url": url},
            headers=pi_headers(key, secret),
            timeout=PI_TIMEOUT,
        )
        if not resp.is_success:
            logger.info("Podcast Index add/byfeedurl returned %s", resp.status_code)
    except httpx.HTTPError:
        logger.info("Podcast Index add/byfeedurl failed", exc_info=True)


def _pi_get(
    path: str,
    params: dict[str, str],
    cache_key: str,
    http: httpx.Client,
    *,
    key: str,
    secret: str,
    cache: SearchCache,
    now: float | None,
) -> ProviderResult:
    from repodify.ingest.cache import SEARCH_TTL_S

    ts = now if now is not None else time.time()
    hit = cache.get_search(cache_key, ttl_s=SEARCH_TTL_S, now=ts)
    if hit is not None:
        payload, _stale = hit
        return ProviderResult(candidates=_map_payload(payload), cached=True)

    try:
        resp = http.get(
            f"{PI_BASE}{path}",
            params=params,
            headers=pi_headers(key, secret, now=ts),
            timeout=PI_TIMEOUT,
        )
    except httpx.HTTPError:
        return ProviderResult(degraded=True)

    if resp.status_code == 401:
        return ProviderResult(warning="check system clock / keys")
    if not resp.is_success:
        return ProviderResult(degraded=True)

    payload = resp.json()
    cache.put_search(cache_key, payload, now=ts)
    return ProviderResult(candidates=_map_payload(payload))


def _map_payload(payload: Any) -> list[Candidate]:
    feeds = payload.get("feeds") if isinstance(payload, dict) else None
    return [c for f in feeds or [] if (c := _map_feed(f)) is not None]


def _map_feed(feed: dict) -> Candidate | None:
    url = feed.get("url") or feed.get("originalUrl")
    if not url:
        return None
    dead_raw = feed.get("dead") or 0
    try:
        dead = int(dead_raw) != 0
    except (TypeError, ValueError):
        dead = bool(dead_raw)
    return Candidate(
        title=feed.get("title") or "",
        author=feed.get("author") or "",
        feed_url=url,
        artwork=feed.get("artwork") or feed.get("image"),
        itunes_id=feed.get("itunesId") or None,
        pi_feed_id=feed.get("id"),
        newest_item=feed.get("newestItemPubdate") or None,
        language=feed.get("language"),
        sources=["podcastindex"],
        dead=dead,
    )
