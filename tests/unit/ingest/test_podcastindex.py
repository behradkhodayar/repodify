import hashlib

import httpx
import respx

from repodify.ingest.podcastindex import pi_headers, search_podcastindex
from tests.unit.ingest.test_itunes import _mem_cache


def test_pi_headers_match_frozen_timestamp():
    key, secret, ts = "k", "s", 1_700_000_000.0
    headers = pi_headers(key, secret, now=ts)
    expect = hashlib.sha1(f"ks{int(ts)}".encode()).hexdigest()
    assert headers["Authorization"] == expect
    assert headers["X-Auth-Key"] == "k"
    assert headers["X-Auth-Date"] == "1700000000"
    assert "repodify" in headers["User-Agent"]


def test_search_maps_feeds_and_marks_dead():
    with respx.mock:
        respx.get("https://api.podcastindex.org/api/1.0/search/bytitle").respond(json={"feeds": []})
        respx.get("https://api.podcastindex.org/api/1.0/search/byterm").respond(
            json={
                "feeds": [
                    {
                        "id": 42,
                        "title": "Linear Digressions",
                        "author": "Katie",
                        "url": "https://canonical.example/feed.xml",
                        "artwork": "https://img.example/a.jpg",
                        "itunesId": 941219323,
                        "newestItemPubdate": 1_700_000_000,
                        "dead": 0,
                        "language": "en",
                    },
                    {
                        "id": 99,
                        "title": "Dead Show",
                        "author": "Z",
                        "url": "https://dead.example/feed.xml",
                        "dead": 1,
                    },
                ]
            }
        )
        with httpx.Client() as http:
            result = search_podcastindex(
                "Linear Digressions",
                http,
                key="k",
                secret="s",
                cache=_mem_cache(),
            )
    titles = {c.title: c for c in result.candidates}
    assert titles["Linear Digressions"].pi_feed_id == 42
    assert titles["Linear Digressions"].itunes_id == 941219323
    assert titles["Dead Show"].dead is True


def test_401_surfaces_clock_warning():
    with respx.mock:
        respx.get("https://api.podcastindex.org/api/1.0/search/bytitle").respond(401)
        respx.get("https://api.podcastindex.org/api/1.0/search/byterm").respond(401)
        with httpx.Client() as http:
            result = search_podcastindex(
                "x",
                http,
                key="k",
                secret="s",
                cache=_mem_cache(),
            )
    assert result.candidates == []
    assert result.warning == "check system clock / keys"
