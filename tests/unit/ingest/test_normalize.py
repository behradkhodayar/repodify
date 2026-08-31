from repodify.ingest.normalize import identity_keys, merge_candidates, normalize_feed_url, rank
from repodify.models.domain import Candidate


def test_normalize_strips_slash_port_fragment_and_upgrades_http():
    assert (
        normalize_feed_url("HTTP://Feeds.Example.com:443/show/") == "https://feeds.example.com/show"
    )


def test_normalize_drops_format_xml_and_utm_from_dedupe_key():
    assert (
        normalize_feed_url("https://feeds.example.com/show?format=xml&utm_source=foo&keep=1")
        == "https://feeds.example.com/show?keep=1"
    )


def test_http_and_https_share_a_dedupe_key():
    a = normalize_feed_url("http://feeds.example.com/show")
    b = normalize_feed_url("https://feeds.example.com/show/")
    assert a == b == "https://feeds.example.com/show"


def test_merge_dedupes_by_normalized_url():
    merged = merge_candidates(
        [
            Candidate(
                title="Show",
                author="A",
                feed_url="http://feeds.example.com/show/",
                sources=["itunes"],
            ),
            Candidate(
                title="Show",
                author="A",
                feed_url="https://feeds.example.com/show?format=xml",
                sources=["podcastindex"],
            ),
        ]
    )
    assert len(merged) == 1
    assert set(merged[0].sources) == {"itunes", "podcastindex"}


def test_merge_dedupes_feedburner_and_canonical_by_itunes_id():
    merged = merge_candidates(
        [
            Candidate(
                title="Linear Digressions",
                author="UD",
                feed_url="https://feeds.feedburner.com/linear-digressions?format=xml",
                itunes_id=941219323,
                sources=["itunes"],
            ),
            Candidate(
                title="Linear Digressions",
                author="UD",
                feed_url="https://example.com/canonical.xml",
                itunes_id=941219323,
                pi_feed_id=42,
                newest_item=1_700_000_000,
                sources=["podcastindex"],
            ),
        ]
    )
    assert len(merged) == 1
    assert merged[0].itunes_id == 941219323
    assert merged[0].pi_feed_id == 42
    assert merged[0].newest_item == 1_700_000_000
    assert set(merged[0].sources) == {"itunes", "podcastindex"}


def test_identity_prefers_itunes_then_pi_then_url():
    c = Candidate(
        title="T",
        author="A",
        feed_url="https://feeds.example.com/show",
        itunes_id=1,
        pi_feed_id=2,
    )
    keys = identity_keys(c)
    assert keys[0] == "itunes:1"
    assert "pi:2" in keys
    assert any(k.startswith("url:") for k in keys)


def test_rank_prefers_more_sources_then_newest():
    dual = Candidate(
        title="Show",
        feed_url="https://a.example/x",
        sources=["itunes", "podcastindex"],
        newest_item=10,
    )
    fresh = Candidate(
        title="Show",
        feed_url="https://b.example/x",
        sources=["itunes"],
        newest_item=99,
    )
    stale = Candidate(
        title="Show",
        feed_url="https://c.example/x",
        sources=["itunes"],
        newest_item=None,
    )
    ranked = rank([stale, fresh, dual], query="Show")
    assert ranked[0].feed_url == dual.feed_url
    assert ranked[1].feed_url == fresh.feed_url


def test_rank_boosts_exact_title_and_sinks_dead():
    dead = Candidate(
        title="Linear Digressions",
        feed_url="https://dead.example/x",
        sources=["podcastindex"],
        newest_item=99,
        dead=True,
    )
    exact = Candidate(
        title="Linear Digressions",
        feed_url="https://live.example/x",
        sources=["itunes"],
        newest_item=1,
    )
    other = Candidate(
        title="Digressions Weekly",
        feed_url="https://other.example/x",
        sources=["itunes"],
        newest_item=50,
    )
    ranked = rank([other, dead, exact], query="Linear Digressions")
    assert ranked[0].feed_url == exact.feed_url
    assert ranked[-1].dead is True


def test_rank_fuzzy_lifts_typo_query():
    target = Candidate(title="Linear Digressions", feed_url="https://a.example/x")
    other = Candidate(title="Linear Algebra Cast", feed_url="https://b.example/x")
    ranked = rank([other, target], query="Linera Digressions")
    assert ranked[0].title == "Linear Digressions"
