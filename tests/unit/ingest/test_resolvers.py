import httpx
import pytest
import respx

from repodify.ingest.resolvers import (
    UnresolvableFeedError,
    resolve,
)


def test_raw_rss_passthrough():
    with httpx.Client() as http:
        assert (
            resolve("https://feeds.example.com/show.xml", http)
            == "https://feeds.example.com/show.xml"
        )


def test_apple_lookup_returns_feed_url():
    with respx.mock:
        respx.get("https://itunes.apple.com/lookup").respond(
            json={"results": [{"feedUrl": "https://feeds.example.com/show.xml"}]}
        )
        with httpx.Client() as http:
            got = resolve("https://podcasts.apple.com/us/podcast/foo/id123456", http)
    assert got == "https://feeds.example.com/show.xml"


def test_castbox_scrapes_rss_link():
    html = (
        '<html><head>'
        '<link type="application/rss+xml" href="https://rss.castbox.fm/everest/abc.xml">'
        '</head></html>'
    )
    with respx.mock:
        respx.get("https://castbox.fm/channel/id999").respond(text=html)
        with httpx.Client() as http:
            got = resolve("https://castbox.fm/channel/id999", http)
    assert got == "https://rss.castbox.fm/everest/abc.xml"


def test_castbox_falls_back_to_json_feed_url():
    # No <link rss> on the page, but an embedded JSON blob carries the feed URL.
    html = (
        '<html><body><script>window.__INITIAL_STATE__='
        '{"channel":{"feed_url":"https://rss.castbox.fm/everest/xyz.xml"}}'
        '</script></body></html>'
    )
    with respx.mock:
        respx.get("https://castbox.fm/channel/id777").respond(text=html)
        with httpx.Client() as http:
            got = resolve("https://castbox.fm/channel/id777", http)
    assert got == "https://rss.castbox.fm/everest/xyz.xml"


def test_unresolvable_raises():
    with httpx.Client() as http:
        with pytest.raises(UnresolvableFeedError):
            resolve("https://unknown.example.com/page", http)
