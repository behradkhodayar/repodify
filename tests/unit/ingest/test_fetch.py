import httpx
import pytest
import respx

from repodify.ingest.cache import JsonCache
from repodify.ingest.fetch import (
    FeedFetchError,
    PrivateFeedError,
    SsrfBlocked,
    fetch_feed,
)


def _public_lookup(host, *args, **kwargs):
    return [(0, 0, 0, "", ("93.184.216.34", 0))]


def _fetch(url, http, **kwargs):
    kwargs.setdefault("lookup", _public_lookup)
    return fetch_feed(url, http, **kwargs)


def test_ssrf_blocks_loopback():
    with httpx.Client() as http:
        with pytest.raises(SsrfBlocked):
            fetch_feed("http://127.0.0.1/feed.xml", http)
        with pytest.raises(SsrfBlocked):
            fetch_feed("http://localhost/feed.xml", http)


def test_rejects_non_http_schemes():
    with httpx.Client() as http:
        with pytest.raises(FeedFetchError):
            fetch_feed("file:///etc/passwd", http)


def test_conditional_get_304_uses_cache(tmp_path):
    cache = JsonCache(tmp_path)
    url = "https://feeds.example.com/show.xml"
    body = b"<rss><channel><title>Show</title></channel></rss>"
    with respx.mock:
        respx.get(url).respond(
            content=body,
            headers={"ETag": '"v1"', "Last-Modified": "Wed, 01 Jan 2020 00:00:00 GMT"},
        )
        with httpx.Client() as http:
            first = _fetch(url, http, cache=cache)
    assert first.from_cache is False
    assert first.body == body

    with respx.mock:

        def _check(request):
            assert request.headers.get("if-none-match") == '"v1"'
            return httpx.Response(304)

        respx.get(url).mock(side_effect=_check)
        with httpx.Client() as http:
            second = _fetch(url, http, cache=cache)
    assert second.from_cache is True
    assert second.body == body
    assert second.url == url


def test_follows_new_feed_url_and_persists(tmp_path):
    cache = JsonCache(tmp_path)
    old = "https://feeds.example.com/old.xml"
    new = "https://feeds.example.com/new.xml"
    old_body = (
        b"<rss><channel>"
        b"<itunes:new-feed-url>https://feeds.example.com/new.xml</itunes:new-feed-url>"
        b"</channel></rss>"
    )
    new_body = b"<rss><channel><title>Moved</title></channel></rss>"
    with respx.mock:
        respx.get(old).respond(content=old_body)
        respx.get(new).respond(content=new_body)
        with httpx.Client() as http:
            got = _fetch(old, http, cache=cache)
    assert got.url == new
    assert got.body == new_body
    assert cache.get_feed(new) is not None


def test_follows_redirect_to_final_url(tmp_path):
    cache = JsonCache(tmp_path)
    src = "https://feeds.example.com/alias.xml"
    dst = "https://feeds.example.com/canonical.xml"
    body = b"<rss><channel><title>C</title></channel></rss>"
    with respx.mock:
        respx.get(src).respond(302, headers={"Location": dst})
        respx.get(dst).respond(content=body)
        with httpx.Client() as http:
            got = _fetch(src, http, cache=cache)
    assert got.url == dst
    assert got.body == body


def test_redirect_to_loopback_is_blocked():
    src = "https://feeds.example.com/alias.xml"
    with respx.mock:
        respx.get(src).respond(301, headers={"Location": "http://127.0.0.1/secret"})
        with httpx.Client() as http:
            with pytest.raises(SsrfBlocked):
                _fetch(src, http)


def test_private_host_and_401_are_explicit():
    with respx.mock:
        respx.get("https://members.patreon.com/rss").respond(401)
        with httpx.Client() as http:
            with pytest.raises(PrivateFeedError, match="Private feed unsupported"):
                _fetch("https://members.patreon.com/rss", http)


def test_retries_once_on_5xx():
    url = "https://feeds.example.com/show.xml"
    body = b"<rss/>"
    with respx.mock:
        route = respx.get(url).mock(
            side_effect=[httpx.Response(502), httpx.Response(200, content=body)]
        )
        with httpx.Client() as http:
            got = _fetch(url, http)
    assert got.body == body
    assert route.call_count == 2
