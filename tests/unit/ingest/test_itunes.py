import time

import httpx
import respx

from repodify.ingest.cache import JsonCache
from repodify.ingest.itunes import ItunesGate, lookup_itunes, search_itunes


def test_search_maps_hits_and_drops_missing_feed_url():
    with respx.mock:
        respx.get("https://itunes.apple.com/search").respond(
            json={
                "results": [
                    {
                        "collectionName": "Linear Digressions",
                        "artistName": "Katie & Ben",
                        "feedUrl": "https://feeds.feedburner.com/linear-digressions?format=xml",
                        "collectionId": 941219323,
                        "artworkUrl600": "https://img.example/600.jpg",
                        "trackCount": 400,
                        "releaseDate": "2024-06-01T00:00:00Z",
                    },
                    {"collectionName": "No Feed", "artistName": "X", "collectionId": 1},
                ]
            }
        )
        with httpx.Client() as http:
            result = search_itunes(
                "Linear Digressions",
                http,
                country="us",
                cache=_mem_cache(),
                gate=ItunesGate(now=lambda: 1000.0, min_interval=0),
            )
    assert len(result.candidates) == 1
    hit = result.candidates[0]
    assert hit.title == "Linear Digressions"
    assert hit.author == "Katie & Ben"
    assert hit.itunes_id == 941219323
    assert hit.feed_url.startswith("https://feeds.feedburner.com/")
    assert hit.newest_item is not None
    assert hit.episode_count == 400
    assert hit.sources == ["itunes"]
    assert result.degraded is False


def test_403_serves_stale_cache_and_backs_off(tmp_path):
    cache = JsonCache(tmp_path)
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    gate = ItunesGate(now=now, min_interval=0)
    with respx.mock:
        respx.get("https://itunes.apple.com/search").respond(
            json={
                "results": [
                    {
                        "collectionName": "Linear Digressions",
                        "artistName": "K",
                        "feedUrl": "https://feeds.example.com/show.xml",
                        "collectionId": 9,
                    }
                ]
            }
        )
        with httpx.Client() as http:
            first = search_itunes("Linear Digressions", http, cache=cache, gate=gate, now=now)
    assert first.candidates[0].title == "Linear Digressions"

    clock["t"] = 10.0
    with respx.mock:
        respx.get("https://itunes.apple.com/search").respond(403)
        with httpx.Client() as http:
            second = search_itunes("Linear Digressions", http, cache=cache, gate=gate, now=now)
    assert second.degraded is True
    assert second.candidates[0].title == "Linear Digressions"
    assert second.candidates[0].cached is True
    assert gate.cooling is True

    clock["t"] = 20.0
    with respx.mock:
        # Still cooling — must not hit the network.
        route = respx.get("https://itunes.apple.com/search").respond(200, json={"results": []})
        with httpx.Client() as http:
            third = search_itunes("Linear Digressions", http, cache=cache, gate=gate, now=now)
    assert route.call_count == 0
    assert third.candidates[0].cached is True


def test_lookup_by_collection_id():
    with respx.mock:
        respx.get("https://itunes.apple.com/lookup").respond(
            json={
                "results": [
                    {
                        "collectionName": "Linear Digressions",
                        "artistName": "K",
                        "feedUrl": "https://feeds.example.com/show.xml",
                        "collectionId": 941219323,
                    }
                ]
            }
        )
        with httpx.Client() as http:
            result = lookup_itunes(
                941219323,
                http,
                cache=_mem_cache(),
                gate=ItunesGate(now=lambda: 1.0, min_interval=0),
            )
    assert result.candidates[0].itunes_id == 941219323


def test_gate_enforces_min_interval():
    clock = {"t": 0.0}
    gate = ItunesGate(now=lambda: clock["t"], min_interval=4.0)
    assert gate.allow() is True
    clock["t"] = 2.0
    assert gate.allow() is False
    clock["t"] = 4.0
    assert gate.allow() is True


class _Mem:
    """Tiny cache stand-in used by tests that don't need disk."""

    def __init__(self) -> None:
        self._s: dict[str, tuple[object, float]] = {}

    def get_search(self, key, ttl_s=0, stale_ttl_s=None, *, now=None):
        item = self._s.get(key)
        if item is None:
            return None
        payload, stored_at = item
        age = (now if now is not None else time.time()) - stored_at
        if age <= ttl_s:
            return payload, False
        if stale_ttl_s is not None and age <= stale_ttl_s:
            return payload, True
        return None

    def put_search(self, key, payload, *, now=None):
        self._s[key] = (payload, now if now is not None else time.time())


def _mem_cache() -> _Mem:
    return _Mem()
