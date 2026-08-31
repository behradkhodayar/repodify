"""Name / URL / Apple-id resolution into ranked `Candidate` rows."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import httpx

from repodify.config import Settings
from repodify.ingest.input_detect import QueryKind, classify
from repodify.ingest.itunes import (
    ItunesGate,
    ProviderResult,
    SearchCache,
    lookup_itunes,
    search_itunes,
)
from repodify.ingest.normalize import merge_candidates, normalize_query, rank
from repodify.ingest.podcastindex import podcasts_by_feed_url, search_podcastindex
from repodify.ingest.resolvers import UnresolvableFeedError, resolve
from repodify.models.domain import Candidate

_MIN_CHARS = 3


@dataclass
class SearchResult:
    query: str
    kind: str
    candidates: list[Candidate] = field(default_factory=list)
    degraded: bool = False
    cached: bool = False
    warning: str | None = None


def search_podcasts(
    q: str,
    http: httpx.Client,
    *,
    settings: Settings,
    cache: SearchCache,
    gate: ItunesGate | None = None,
    min_chars: int = _MIN_CHARS,
) -> SearchResult:
    """Classify `q` and return ranked candidates. Never hits iTunes below min_chars."""
    classified = classify(q)
    kind = classified.kind.value
    limit = min_chars if min_chars is not None else settings.search_min_chars
    if classified.kind is QueryKind.NAME and len(classified.raw) < limit:
        return SearchResult(query=classified.raw, kind=kind)

    if classified.kind in {QueryKind.APPLE_URL, QueryKind.ITUNES_ID}:
        if classified.itunes_id is None:
            return SearchResult(query=classified.raw, kind=kind)
        result = lookup_itunes(classified.itunes_id, http, cache=cache, gate=gate)
        return _finish(classified.raw, kind, result.candidates, result)

    if classified.kind is QueryKind.RSS_URL:
        return _from_pasted_url(classified.raw, classified.url or classified.raw, http, settings)

    return _name_search(classified.raw, http, settings=settings, cache=cache, gate=gate)


def _name_search(
    term: str,
    http: httpx.Client,
    *,
    settings: Settings,
    cache: SearchCache,
    gate: ItunesGate | None,
) -> SearchResult:
    result = _providers(term, http, settings=settings, cache=cache, gate=gate, bytitle=True)
    if result.candidates:
        return _finish(term, QueryKind.NAME.value, result.candidates, result)

    normalized = normalize_query(term)
    if normalized and normalized != term.lower().strip():
        result = _providers(
            normalized, http, settings=settings, cache=cache, gate=gate, bytitle=True
        )
        if result.candidates:
            return _finish(term, QueryKind.NAME.value, result.candidates, result)
        author_term = normalized
    else:
        author_term = term

    result = _providers(author_term, http, settings=settings, cache=cache, gate=gate, bytitle=False)
    return _finish(term, QueryKind.NAME.value, result.candidates, result)


def _providers(
    term: str,
    http: httpx.Client,
    *,
    settings: Settings,
    cache: SearchCache,
    gate: ItunesGate | None,
    bytitle: bool,
) -> ProviderResult:
    country = settings.itunes_country
    pi_key = settings.podcastindex_api_key
    pi_secret = settings.podcastindex_api_secret

    def itunes_call() -> ProviderResult:
        return search_itunes(term, http, country=country, cache=cache, gate=gate)

    def pi_call() -> ProviderResult:
        return search_podcastindex(
            term,
            http,
            key=pi_key or "",
            secret=pi_secret or "",
            cache=cache,
            bytitle=bytitle,
        )

    if pi_key and pi_secret:
        with ThreadPoolExecutor(max_workers=2) as pool:
            itunes_f = pool.submit(itunes_call)
            pi_f = pool.submit(pi_call)
            itunes_result = itunes_f.result()
            pi_result = pi_f.result()
        candidates = merge_candidates([*itunes_result.candidates, *pi_result.candidates])
        return ProviderResult(
            candidates=candidates,
            degraded=itunes_result.degraded or pi_result.degraded,
            cached=bool(
                (itunes_result.cached or not itunes_result.candidates)
                and (pi_result.cached or not pi_result.candidates)
                and (itunes_result.cached or pi_result.cached)
            ),
            warning=itunes_result.warning or pi_result.warning,
        )

    itunes_result = itunes_call()
    return ProviderResult(
        candidates=merge_candidates(itunes_result.candidates),
        degraded=itunes_result.degraded,
        cached=itunes_result.cached,
        warning=itunes_result.warning,
    )


def _from_pasted_url(
    raw: str,
    url: str,
    http: httpx.Client,
    settings: Settings,
) -> SearchResult:
    try:
        rss = resolve(url, http)
    except UnresolvableFeedError:
        rss = url
    candidate = Candidate(title=rss, author="", feed_url=rss, sources=["url"])
    key, secret = settings.podcastindex_api_key, settings.podcastindex_api_secret
    if key and secret:
        meta = podcasts_by_feed_url(rss, http, key=key, secret=secret)
        if meta is not None:
            candidate = merge_candidates([candidate, meta])[0]
    return SearchResult(query=raw, kind=QueryKind.RSS_URL.value, candidates=[candidate])


def _finish(
    query: str,
    kind: str,
    candidates: list[Candidate],
    provider: ProviderResult,
) -> SearchResult:
    ranked = rank(candidates, query)
    cached = bool(ranked) and all(c.cached for c in ranked) or provider.cached
    return SearchResult(
        query=query,
        kind=kind,
        candidates=ranked,
        degraded=provider.degraded,
        cached=cached,
        warning=provider.warning,
    )
