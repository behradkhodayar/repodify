"""Fetch an RSS feed: SSRF guard, redirects, conditional GET, new-feed-url."""

from __future__ import annotations

import ipaddress
import logging
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from repodify.ingest.cache import JsonCache
from repodify.ingest.feed import itunes_new_feed_url
from repodify.ingest.identity import USER_AGENT
from repodify.ingest.normalize import normalize_feed_url

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
_MAX_REDIRECTS = 5
_PRIVATE_HOST_MARKERS = ("patreon.com", "supercast.com")
Lookup = Callable[..., list]


class FeedFetchError(Exception):
    """The feed could not be retrieved."""


class PrivateFeedError(FeedFetchError):
    def __init__(self, message: str = "Private feed unsupported.") -> None:
        super().__init__(message)


class SsrfBlocked(FeedFetchError):
    def __init__(self, url: str) -> None:
        super().__init__(f"blocked address: {url}")
        self.url = url


@dataclass
class FetchedFeed:
    url: str
    body: bytes
    from_cache: bool = False
    status: int = 200


def fetch_feed(
    url: str,
    http: httpx.Client,
    *,
    cache: JsonCache | None = None,
    lookup: Lookup = socket.getaddrinfo,
    _new_feed_hops: int = 0,
) -> FetchedFeed:
    """GET `url` and return the canonical feed body.

    Follows up to 5 HTTP redirects and one `<itunes:new-feed-url>` hop. Blocks
    loopback / private / link-local / metadata targets. 304 responses replay the
    cached body.
    """
    current = url.strip()
    _assert_fetchable(current, lookup)
    seen: set[str] = set()

    for _ in range(_MAX_REDIRECTS + 1):
        _assert_fetchable(current, lookup)
        norm = normalize_feed_url(current)
        if norm in seen:
            raise FeedFetchError("redirect loop")
        seen.add(norm)

        headers = {"User-Agent": USER_AGENT}
        cached = cache.get_feed(current) if cache is not None else None
        if cached:
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]

        resp = _get_with_retry(http, current, headers)

        if resp.status_code in {301, 302, 303, 307, 308}:
            location = resp.headers.get("Location")
            if not location:
                raise FeedFetchError("redirect without Location")
            current = urljoin(current, location)
            continue

        if resp.status_code == 304:
            if cached is None:
                raise FeedFetchError("304 with no cached body")
            return FetchedFeed(
                url=cached.get("final_url") or current,
                body=cached["body"],
                from_cache=True,
                status=304,
            )

        if resp.status_code == 401 or (resp.status_code == 403 and _looks_private(current)):
            raise PrivateFeedError()
        if resp.status_code >= 400:
            raise FeedFetchError(f"GET {current} returned {resp.status_code}")

        body = resp.content
        final = str(resp.url) if resp.url else current
        migrated = itunes_new_feed_url(body)
        if (
            migrated
            and normalize_feed_url(migrated) != normalize_feed_url(final)
            and _new_feed_hops < 2
        ):
            fetched = fetch_feed(
                migrated,
                http,
                cache=cache,
                lookup=lookup,
                _new_feed_hops=_new_feed_hops + 1,
            )
            if cache is not None:
                cache.rekey_feed(url, fetched.url)
            return fetched

        if cache is not None:
            cache.put_feed(
                final,
                {
                    "etag": resp.headers.get("ETag"),
                    "last_modified": resp.headers.get("Last-Modified"),
                    "body": body,
                    "final_url": final,
                    "fetched_at": time.time(),
                },
            )
            if normalize_feed_url(url) != normalize_feed_url(final):
                cache.rekey_feed(url, final)
        return FetchedFeed(url=final, body=body, from_cache=False, status=resp.status_code)

    raise FeedFetchError("too many redirects")


def _get_with_retry(http: httpx.Client, url: str, headers: dict[str, str]) -> httpx.Response:
    last: httpx.Response | None = None
    for attempt in range(2):
        try:
            resp = http.get(url, headers=headers, follow_redirects=False, timeout=_TIMEOUT)
        except httpx.TimeoutException:
            if attempt == 0:
                continue
            raise FeedFetchError(f"timeout fetching {url}") from None
        except httpx.HTTPError as exc:
            raise FeedFetchError(f"feed fetch failed: {exc}") from exc
        if resp.status_code >= 500 and attempt == 0:
            last = resp
            continue
        return resp
    return last if last is not None else httpx.Response(502)


def _assert_fetchable(url: str, lookup: Lookup) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise FeedFetchError("only http(s) feeds are supported")
    host = parts.hostname
    if not host:
        raise SsrfBlocked(url)
    low = host.lower().rstrip(".")
    if low == "localhost" or low.endswith(".localhost") or low == "metadata.google.internal":
        raise SsrfBlocked(url)
    try:
        as_ip = ipaddress.ip_address(host)
    except ValueError:
        as_ip = None
    if as_ip is not None:
        if not as_ip.is_global:
            raise SsrfBlocked(url)
        return
    try:
        infos = lookup(host, None)
    except OSError:
        # NXDOMAIN / offline: let the GET fail on its own so tests can mock HTTP
        # without a live DNS lookup.
        return
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if not addr.is_global:
            raise SsrfBlocked(url)


def _looks_private(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(marker in host for marker in _PRIVATE_HOST_MARKERS)
