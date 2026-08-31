from repodify.ingest.feed import parse_feed


def test_parses_episodes_oldest_first(sample_feed_xml):
    feed = parse_feed(
        source_url="https://example.com/show",
        rss_url="https://example.com/feed.xml",
        data=sample_feed_xml,
    )

    assert feed.title == "My Test Show"
    assert feed.author == "Jane Host"

    # The no-enclosure "Bonus" item is dropped -> 3 episodes.
    assert [e.title for e in feed.episodes] == [
        "Trailer",
        "Episode 1: The Beginning",
        "Episode 2: The Middle",
    ]

    # order_index is contiguous and chronological.
    assert [e.order_index for e in feed.episodes] == [0, 1, 2]
    assert feed.episodes[0].published_at < feed.episodes[1].published_at


def test_trailer_and_short_flagged(sample_feed_xml):
    feed = parse_feed("s", "r", sample_feed_xml)
    trailer, ep1, ep2 = feed.episodes
    assert trailer.is_short_or_trailer is True  # 45s AND matches "trailer"
    assert ep1.is_short_or_trailer is False
    assert ep2.is_short_or_trailer is False


def test_duration_parsed_to_seconds(sample_feed_xml):
    feed = parse_feed("s", "r", sample_feed_xml)
    by_title = {e.title: e for e in feed.episodes}
    assert by_title["Episode 1: The Beginning"].duration_s == 40 * 60
    assert by_title["Episode 2: The Middle"].duration_s == 65 * 60
    assert by_title["Trailer"].duration_s == 45
