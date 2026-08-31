import httpx
import respx
from fastapi.testclient import TestClient

from repodify.api.app import create_app
from repodify.config import Settings
from repodify.storage.filesystem import FilesystemStorage


def _resolve_fn(url, http):
    return url


def _client(repo, http, tmp_path, **settings_kw):
    storage = FilesystemStorage(tmp_path / "data")
    settings = Settings(_env_file=None, data_dir=tmp_path / "appdata", **settings_kw)
    return TestClient(create_app(repo, _resolve_fn, http, lambda j: None, storage, settings))


def test_search_name_returns_itunes_candidates(repo, tmp_path):
    with respx.mock:
        respx.get("https://itunes.apple.com/search").respond(
            json={
                "results": [
                    {
                        "collectionName": "Linear Digressions",
                        "artistName": "Katie & Ben",
                        "feedUrl": "https://feeds.example.com/ld.xml",
                        "collectionId": 941219323,
                        "artworkUrl100": "https://img.example/a.jpg",
                        "releaseDate": "2024-06-01T00:00:00Z",
                    }
                ]
            }
        )
        with httpx.Client() as http:
            client = _client(repo, http, tmp_path)
            resp = client.get("/feeds/search", params={"q": "Linear Digressions"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "name"
    assert body["candidates"][0]["title"] == "Linear Digressions"
    assert body["candidates"][0]["feed_url"].endswith("ld.xml")
    assert body["candidates"][0]["identity"].startswith("itunes:")


def test_search_short_query_skips_network(repo, tmp_path):
    with respx.mock:
        itunes = respx.get("https://itunes.apple.com/search").respond(json={"results": []})
        with httpx.Client() as http:
            client = _client(repo, http, tmp_path)
            resp = client.get("/feeds/search", params={"q": "ab"})
    assert resp.status_code == 200
    assert resp.json()["candidates"] == []
    assert itunes.call_count == 0


def test_resolve_follows_redirect_and_returns_final_url(repo, tmp_path, sample_feed_xml):
    with respx.mock:
        respx.get("https://feeds.example.com/alias.xml").respond(
            301, headers={"Location": "https://feeds.example.com/canonical.xml"}
        )
        respx.get("https://feeds.example.com/canonical.xml").respond(content=sample_feed_xml)
        with httpx.Client() as http:
            client = _client(repo, http, tmp_path)
            resp = client.post(
                "/feeds/resolve", json={"url": "https://feeds.example.com/alias.xml"}
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rss_url"] == "https://feeds.example.com/canonical.xml"
    assert body["feed_title"] == "My Test Show"
    assert len(body["episodes"]) == 3


def test_resolve_private_feed_is_422(repo, tmp_path):
    with respx.mock:
        respx.get("https://members.patreon.com/rss").respond(401)
        with httpx.Client() as http:
            client = _client(repo, http, tmp_path)
            resp = client.post("/feeds/resolve", json={"url": "https://members.patreon.com/rss"})
    assert resp.status_code == 422
    assert "Private feed unsupported" in resp.json()["detail"]


def test_resolve_ssrf_is_400(repo, tmp_path):
    with httpx.Client() as http:
        client = _client(repo, http, tmp_path)
        resp = client.post("/feeds/resolve", json={"url": "http://127.0.0.1/feed.xml"})
    assert resp.status_code == 400
