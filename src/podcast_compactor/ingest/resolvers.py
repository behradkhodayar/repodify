"""Resolve a user-supplied link to an underlying RSS feed URL.

The input may be a raw RSS URL, an Apple Podcasts page, or a Castbox channel.
Each platform has a small resolver; `resolve` tries them in order.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

import httpx


class UnresolvableFeedError(Exception):
    """Raised when no resolver can turn a link into an RSS feed URL."""


@runtime_checkable
class Resolver(Protocol):
    """Turns one class of link into an RSS feed URL."""

    def matches(self, url: str) -> bool: ...

    def resolve(self, url: str, http: httpx.Client) -> str: ...


class RawRssResolver:
    """Passes through URLs that already point at an RSS/Atom feed."""

    _SUFFIXES = (".xml", ".rss")

    def matches(self, url: str) -> bool:
        lowered = url.split("?", 1)[0].lower()
        return lowered.endswith(self._SUFFIXES) or "/feed" in lowered or "/rss" in lowered

    def resolve(self, url: str, http: httpx.Client) -> str:
        return url


class ApplePodcastsResolver:
    """Resolves podcasts.apple.com links via the iTunes lookup API."""

    _ID_RE = re.compile(r"id(\d+)")

    def matches(self, url: str) -> bool:
        return "podcasts.apple.com" in url

    def resolve(self, url: str, http: httpx.Client) -> str:
        match = self._ID_RE.search(url)
        if not match:
            raise UnresolvableFeedError(f"No podcast id in Apple URL: {url}")
        podcast_id = match.group(1)
        resp = http.get(
            "https://itunes.apple.com/lookup",
            params={"id": podcast_id, "entity": "podcast"},
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        for item in results:
            feed_url = item.get("feedUrl")
            if feed_url:
                return feed_url
        raise UnresolvableFeedError(f"Apple lookup returned no feedUrl for id {podcast_id}")


class CastboxResolver:
    """Resolves castbox.fm channel pages by scraping the embedded RSS link."""

    _LINK_RE = re.compile(
        r'<link[^>]+type=["\']application/rss\+xml["\'][^>]+href=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    _JSON_RE = re.compile(r'"(?:rss|feed_url|feedUrl)"\s*:\s*"([^"]+)"', re.IGNORECASE)

    def matches(self, url: str) -> bool:
        return "castbox.fm" in url

    def resolve(self, url: str, http: httpx.Client) -> str:
        resp = http.get(url, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        for pattern in (self._LINK_RE, self._JSON_RE):
            match = pattern.search(html)
            if match:
                return match.group(1).replace("\\/", "/")
        raise UnresolvableFeedError(f"No RSS link found on Castbox page: {url}")


# Registry order matters: platform-specific resolvers before the raw fallback.
DEFAULT_RESOLVERS: tuple[Resolver, ...] = (
    ApplePodcastsResolver(),
    CastboxResolver(),
    RawRssResolver(),
)


def resolve(
    url: str,
    http: httpx.Client,
    resolvers: tuple[Resolver, ...] = DEFAULT_RESOLVERS,
) -> str:
    """Return the RSS feed URL for `url`, trying each resolver in order."""
    for resolver in resolvers:
        if resolver.matches(url):
            return resolver.resolve(url, http)
    raise UnresolvableFeedError(f"No resolver matched: {url}")
