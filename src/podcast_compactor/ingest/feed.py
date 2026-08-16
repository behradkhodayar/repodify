"""Parse RSS bytes into the domain `Feed` / `Episode` models."""

from __future__ import annotations

import calendar
import re
from datetime import UTC, datetime

import feedparser

from podcast_compactor.models.domain import Episode, Feed

_TRAILER_RE = re.compile(r"\b(trailer|teaser|bonus|intro)\b", re.IGNORECASE)
_SHORT_SECONDS = 120


def _first_enclosure_url(entry) -> str | None:
    for enc in getattr(entry, "enclosures", []) or []:
        href = enc.get("href") or enc.get("url")
        if href:
            return href
    return None


def _to_datetime(struct) -> datetime | None:
    if not struct:
        return None
    return datetime.fromtimestamp(calendar.timegm(struct), tz=UTC)


def _parse_duration(raw: str | None) -> int | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    parts = raw.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    seconds = 0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds


def _is_short_or_trailer(title: str, duration_s: int | None) -> bool:
    if duration_s is not None and duration_s < _SHORT_SECONDS:
        return True
    return bool(_TRAILER_RE.search(title))


def parse_feed(source_url: str, rss_url: str, data: bytes) -> Feed:
    """Parse raw RSS `data` into a `Feed` with oldest-first episodes.

    Entries without an audio enclosure are dropped. Episodes are sorted
    chronologically and assigned a contiguous `order_index`.
    """
    parsed = feedparser.parse(data)
    feed_title = parsed.feed.get("title", "")
    author = parsed.feed.get("author") or parsed.feed.get("itunes_author")

    raw_episodes: list[tuple[datetime | None, dict]] = []
    for entry in parsed.entries:
        audio_url = _first_enclosure_url(entry)
        if not audio_url:
            continue
        title = entry.get("title", "")
        duration_s = _parse_duration(entry.get("itunes_duration"))
        published_at = _to_datetime(entry.get("published_parsed"))
        raw_episodes.append(
            (
                published_at,
                {
                    "guid": entry.get("id") or entry.get("guid") or audio_url,
                    "title": title,
                    "published_at": published_at,
                    "duration_s": duration_s,
                    "audio_url": audio_url,
                },
            )
        )

    _EPOCH = datetime.fromtimestamp(0, tz=UTC)
    raw_episodes.sort(key=lambda pair: (pair[0] is None, pair[0] or _EPOCH))

    episodes = [
        Episode(
            order_index=i,
            is_short_or_trailer=_is_short_or_trailer(fields["title"], fields["duration_s"]),
            **fields,
        )
        for i, (_, fields) in enumerate(raw_episodes)
    ]

    return Feed(
        source_url=source_url,
        rss_url=rss_url,
        title=feed_title,
        author=author,
        episodes=episodes,
    )
