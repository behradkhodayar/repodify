from repodify.ingest.input_detect import QueryKind, classify


def test_name_query():
    got = classify("Linear Digressions")
    assert got.kind is QueryKind.NAME
    assert got.raw == "Linear Digressions"
    assert got.url is None
    assert got.itunes_id is None


def test_https_rss_url():
    got = classify("https://feeds.feedburner.com/udacity-linear-digressions")
    assert got.kind is QueryKind.RSS_URL
    assert got.url == "https://feeds.feedburner.com/udacity-linear-digressions"


def test_scheme_less_feeds_host():
    got = classify("feeds.feedburner.com/linear-digressions")
    assert got.kind is QueryKind.RSS_URL
    assert got.url == "https://feeds.feedburner.com/linear-digressions"


def test_apple_podcasts_url_extracts_collection_id():
    got = classify("https://podcasts.apple.com/us/podcast/linear-digressions/id941219323")
    assert got.kind is QueryKind.APPLE_URL
    assert got.itunes_id == 941219323
    assert got.url and "podcasts.apple.com" in got.url


def test_itunes_apple_url():
    got = classify("https://itunes.apple.com/us/podcast/id123456789")
    assert got.kind is QueryKind.APPLE_URL
    assert got.itunes_id == 123456789


def test_bare_itunes_id():
    got = classify("941219323")
    assert got.kind is QueryKind.ITUNES_ID
    assert got.itunes_id == 941219323


def test_short_digits_are_a_name():
    got = classify("99")
    assert got.kind is QueryKind.NAME


def test_strips_whitespace():
    got = classify("  Linear Digressions  ")
    assert got.raw == "Linear Digressions"
    assert got.kind is QueryKind.NAME
