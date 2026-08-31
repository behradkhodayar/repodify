import json
import time

from repodify.ingest.cache import JsonCache


def test_search_roundtrip_and_ttl(tmp_path):
    cache = JsonCache(tmp_path)
    cache.put_search("itunes:us:linear", {"results": [1]})
    hit = cache.get_search("itunes:us:linear", ttl_s=24 * 3600)
    assert hit is not None
    payload, stale = hit
    assert payload == {"results": [1]}
    assert stale is False


def test_search_expired_is_stale_not_missing(tmp_path):
    cache = JsonCache(tmp_path)
    cache.put_search("itunes:us:old", {"results": [2]})
    key_path = next(tmp_path.glob("search-*.json"))
    data = json.loads(key_path.read_text())
    data["stored_at"] = time.time() - 8 * 24 * 3600
    key_path.write_text(json.dumps(data))

    assert cache.get_search("itunes:us:old", ttl_s=24 * 3600) is None
    hit = cache.get_search("itunes:us:old", ttl_s=24 * 3600, stale_ttl_s=10 * 24 * 3600)
    assert hit is not None
    payload, stale = hit
    assert payload == {"results": [2]}
    assert stale is True


def test_feed_roundtrip_and_rekey(tmp_path):
    cache = JsonCache(tmp_path)
    cache.put_feed(
        "https://old.example/feed",
        {
            "etag": '"abc"',
            "last_modified": "Wed, 01 Jan 2020 00:00:00 GMT",
            "body": b"<rss/>",
            "final_url": "https://old.example/feed",
            "fetched_at": 1.0,
        },
    )
    got = cache.get_feed("https://old.example/feed")
    assert got is not None
    assert got["etag"] == '"abc"'
    assert got["body"] == b"<rss/>"

    cache.rekey_feed("https://old.example/feed", "https://new.example/feed")
    assert cache.get_feed("https://old.example/feed") is None
    moved = cache.get_feed("https://new.example/feed")
    assert moved is not None
    assert moved["final_url"] == "https://old.example/feed"
