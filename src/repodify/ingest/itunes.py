"""Apple iTunes Search / Lookup — zero-key default directory."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import httpx

from repodify.ingest.cache import SEARCH_STALE_TTL_S, SEARCH_TTL_S
from repodify.ingest.identity import USER_AGENT
from repodify.models.domain import Candidate

logger = logging.getLogger(__name__)

ITUNES_SEARCH = "https://itunes.apple.com/search"
ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
ITUNES_TIMEOUT = 8.0


class SearchCache(Protocol):
    def get_search(
        self,
        key: str,
        ttl_s: float = SEARCH_TTL_S,
        stale_ttl_s: float | None = None,
        *,
        now: float | None = None,
    ) -> tuple[Any, bool] | None: ...

    def put_search(self, key: str, payload: Any, *, now: float | None = None) -> None: ...


@dataclass
class ProviderResult:
    candidates: list[Candidate] = field(default_factory=list)
    degraded: bool = False
    cached: bool = False
    warning: str | None = None


class ItunesGate:
    """One in-flight-friendly rate limit + exponential 403 cooldown."""

    def __init__(
        self,
        now: Callable[[], float],
        min_interval: float = 4.0,
        initial_backoff: float = 60.0,
        max_backoff: float = 15 * 60,
    ) -> None:
        self._now = now
        self._min_interval = min_interval
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._lock = threading.Lock()
        self._next_ok = 0.0
        self._backoff = initial_backoff
        self.cooling = False

    def allow(self) -> bool:
        with self._lock:
            now = self._now()
            if now < self._next_ok:
                return False
            self._next_ok = now + self._min_interval
            self.cooling = False
            return True

    def on_403(self) -> None:
        with self._lock:
            self.cooling = True
            self._next_ok = self._now() + self._backoff
            self._backoff = min(self._backoff * 2, self._max_backoff)

    def on_success(self) -> None:
        with self._lock:
            self.cooling = False
            self._backoff = self._initial_backoff


_DEFAULT_GATE = ItunesGate(now=time.monotonic)


def search_itunes(
    term: str,
    http: httpx.Client,
    *,
    country: str = "us",
    cache: SearchCache,
    gate: ItunesGate | None = None,
    now: Callable[[], float] | None = None,
) -> ProviderResult:
    key = f"itunes:search:{country}:{term.lower().strip()}"
    params = {
        "media": "podcast",
        "entity": "podcast",
        "term": term,
        "limit": "8",
        "country": country,
    }
    return _itunes_get(
        ITUNES_SEARCH,
        params,
        key,
        http,
        cache=cache,
        gate=gate,
        now=now,
    )


def lookup_itunes(
    collection_id: int,
    http: httpx.Client,
    *,
    cache: SearchCache,
    gate: ItunesGate | None = None,
    now: Callable[[], float] | None = None,
) -> ProviderResult:
    key = f"itunes:lookup:{collection_id}"
    return _itunes_get(
        ITUNES_LOOKUP,
        {"id": str(collection_id)},
        key,
        http,
        cache=cache,
        gate=gate,
        now=now,
    )


def _itunes_get(
    url: str,
    params: dict[str, str],
    cache_key: str,
    http: httpx.Client,
    *,
    cache: SearchCache,
    gate: ItunesGate | None,
    now: Callable[[], float] | None,
) -> ProviderResult:
    gate = gate or _DEFAULT_GATE
    clock = now or time.time
    ts = clock()

    def from_cache(*, allow_stale: bool) -> ProviderResult | None:
        hit = cache.get_search(
            cache_key,
            ttl_s=SEARCH_TTL_S,
            stale_ttl_s=SEARCH_STALE_TTL_S if allow_stale else None,
            now=ts,
        )
        if hit is None:
            return None
        payload, stale = hit
        candidates = _map_results(payload)
        for candidate in candidates:
            candidate.cached = True
        return ProviderResult(
            candidates=candidates,
            degraded=stale or allow_stale,
            cached=True,
        )

    if not gate.allow():
        cached = from_cache(allow_stale=True)
        return cached or ProviderResult(degraded=True)

    try:
        resp = http.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=ITUNES_TIMEOUT,
        )
    except httpx.HTTPError:
        logger.info("iTunes request failed; serving cache if any")
        cached = from_cache(allow_stale=True)
        return cached or ProviderResult(degraded=True)

    if resp.status_code == 403:
        gate.on_403()
        cached = from_cache(allow_stale=True)
        return cached or ProviderResult(degraded=True)

    if not resp.is_success:
        cached = from_cache(allow_stale=True)
        return cached or ProviderResult(degraded=True)

    gate.on_success()
    payload = resp.json()
    cache.put_search(cache_key, payload, now=ts)
    return ProviderResult(candidates=_map_results(payload))


def _map_results(payload: Any) -> list[Candidate]:
    rows = payload.get("results") if isinstance(payload, dict) else None
    hits: list[Candidate] = []
    for item in rows or []:
        feed_url = item.get("feedUrl")
        if not feed_url:
            continue
        hits.append(
            Candidate(
                title=item.get("collectionName") or "",
                author=item.get("artistName") or "",
                feed_url=feed_url,
                artwork=item.get("artworkUrl600") or item.get("artworkUrl100"),
                itunes_id=item.get("collectionId"),
                newest_item=_parse_release(item.get("releaseDate")),
                episode_count=item.get("trackCount"),
                sources=["itunes"],
            )
        )
    return hits


def _parse_release(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None
