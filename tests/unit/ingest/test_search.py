import httpx
import respx

from repodify.config import Settings
from repodify.ingest.itunes import ItunesGate
from repodify.ingest.search import search_podcasts
from tests.unit.ingest.test_itunes import _mem_cache


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def _gate() -> ItunesGate:
    return ItunesGate(now=lambda: 1_000.0, min_interval=0)


def test_name_search_uses_itunes_without_keys():
    with respx.mock:
        respx.get("https://itunes.apple.com/search").respond(
            json={
                "results": [
                    {
                        "collectionName": "Linear Digressions",
                        "artistName": "Katie & Ben",
                        "feedUrl": "https://feeds.example.com/ld.xml",
                        "collectionId": 941219323,
                    }
                ]
            }
        )
        with httpx.Client() as http:
            result = search_podcasts(
                "Linear Digressions",
                http,
                settings=_settings(),
                cache=_mem_cache(),
                gate=_gate(),
            )
    assert result.kind == "name"
    assert result.candidates[0].title == "Linear Digressions"
    assert result.candidates[0].feed_url.endswith("ld.xml")


def test_short_name_does_not_hit_network():
    with respx.mock:
        itunes = respx.get("https://itunes.apple.com/search").respond(json={"results": []})
        with httpx.Client() as http:
            result = search_podcasts(
                "ab",
                http,
                settings=_settings(),
                cache=_mem_cache(),
                gate=_gate(),
            )
    assert result.candidates == []
    assert itunes.call_count == 0


def test_apple_url_uses_lookup():
    with respx.mock:
        respx.get("https://itunes.apple.com/lookup").respond(
            json={
                "results": [
                    {
                        "collectionName": "Linear Digressions",
                        "artistName": "K",
                        "feedUrl": "https://feeds.example.com/ld.xml",
                        "collectionId": 941219323,
                    }
                ]
            }
        )
        with httpx.Client() as http:
            result = search_podcasts(
                "https://podcasts.apple.com/us/podcast/linear-digressions/id941219323",
                http,
                settings=_settings(),
                cache=_mem_cache(),
                gate=_gate(),
            )
    assert result.kind == "apple_url"
    assert result.candidates[0].itunes_id == 941219323


def test_rss_url_returns_one_confirming_candidate():
    with httpx.Client() as http:
        result = search_podcasts(
            "https://feeds.feedburner.com/udacity-linear-digressions",
            http,
            settings=_settings(),
            cache=_mem_cache(),
            gate=_gate(),
        )
    assert result.kind == "rss_url"
    assert len(result.candidates) == 1
    assert result.candidates[0].feed_url.endswith("udacity-linear-digressions")
    assert "url" in result.candidates[0].sources


def test_merge_itunes_and_podcastindex_by_itunes_id():
    settings = _settings(podcastindex_api_key="k", podcastindex_api_secret="s")
    with respx.mock:
        respx.get("https://itunes.apple.com/search").respond(
            json={
                "results": [
                    {
                        "collectionName": "Linear Digressions",
                        "artistName": "K",
                        "feedUrl": "https://feeds.feedburner.com/linear-digressions?format=xml",
                        "collectionId": 941219323,
                    }
                ]
            }
        )
        respx.get("https://api.podcastindex.org/api/1.0/search/bytitle").respond(json={"feeds": []})
        respx.get("https://api.podcastindex.org/api/1.0/search/byterm").respond(
            json={
                "feeds": [
                    {
                        "id": 7,
                        "title": "Linear Digressions",
                        "author": "K",
                        "url": "https://canonical.example/ld.xml",
                        "itunesId": 941219323,
                        "newestItemPubdate": 1_700_000_000,
                    }
                ]
            }
        )
        with httpx.Client() as http:
            result = search_podcasts(
                "Linear Digressions",
                http,
                settings=settings,
                cache=_mem_cache(),
                gate=_gate(),
            )
    assert len(result.candidates) == 1
    hit = result.candidates[0]
    assert set(hit.sources) == {"itunes", "podcastindex"}
    assert hit.pi_feed_id == 7
    assert "feedburner.com" not in hit.feed_url


def test_itunes_403_falls_through_to_podcastindex():
    settings = _settings(podcastindex_api_key="k", podcastindex_api_secret="s")
    with respx.mock:
        respx.get("https://itunes.apple.com/search").respond(403)
        respx.get("https://api.podcastindex.org/api/1.0/search/bytitle").respond(json={"feeds": []})
        respx.get("https://api.podcastindex.org/api/1.0/search/byterm").respond(
            json={
                "feeds": [
                    {
                        "id": 1,
                        "title": "Linear Digressions",
                        "url": "https://canonical.example/ld.xml",
                    }
                ]
            }
        )
        with httpx.Client() as http:
            result = search_podcasts(
                "Linear Digressions",
                http,
                settings=settings,
                cache=_mem_cache(),
                gate=_gate(),
            )
    assert result.degraded is True
    assert result.candidates[0].title == "Linear Digressions"


def test_zero_results_retry_stripped_query(tmp_path):
    del tmp_path
    with respx.mock:

        def itunes(request):
            term = request.url.params.get("term")
            if term == "linear digressions":
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "collectionName": "Linear Digressions",
                                "artistName": "K",
                                "feedUrl": "https://feeds.example.com/ld.xml",
                                "collectionId": 1,
                            }
                        ]
                    },
                )
            return httpx.Response(200, json={"results": []})

        respx.get("https://itunes.apple.com/search").mock(side_effect=itunes)
        with httpx.Client() as http:
            result = search_podcasts(
                "The Official Linear Digressions Podcast",
                http,
                settings=_settings(),
                cache=_mem_cache(),
                gate=_gate(),
            )
    assert result.candidates[0].title == "Linear Digressions"
