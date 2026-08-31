import pytest

from repodify.synth.stock_voices import (
    DEFAULT_STOCK_VOICE,
    SAMPLE_LINE,
    STOCK_VOICE_STYLES,
    STOCK_VOICES,
    bundled_sample_path,
    effective_stock_catalog,
    interleave_by_register,
    list_stock_voices,
    match_by_gender,
    stock_voice,
    stock_voice_display_name,
    stock_voice_gender,
    stock_voice_register,
)


def test_catalog_is_non_empty_and_includes_default():
    voices = list_stock_voices()
    assert voices
    assert DEFAULT_STOCK_VOICE in voices


def test_stock_voice_resolves_to_kokoro_voice():
    v = stock_voice(DEFAULT_STOCK_VOICE)
    assert v.kokoro_voice == DEFAULT_STOCK_VOICE
    assert v.name == DEFAULT_STOCK_VOICE
    sample = bundled_sample_path(DEFAULT_STOCK_VOICE)
    assert v.ref_audio_path == sample
    assert v.ref_text == SAMPLE_LINE
    assert sample.is_file(), "bundled catalog previews must ship with the app"


def test_every_catalog_voice_ships_a_preview_clip():
    import wave

    for name in STOCK_VOICES:
        path = bundled_sample_path(name)
        assert path.is_file(), f"missing preview for {name}"
        v = stock_voice(name)
        assert v.ref_audio_path == path
        assert v.ref_text == SAMPLE_LINE
        with wave.open(str(path), "rb") as w:
            duration = w.getnframes() / float(w.getframerate())
            assert w.getnchannels() == 1
            assert w.getframerate() == 24000
            assert 3.0 <= duration <= 8.0, f"{name} preview is {duration:.2f}s"


def test_unknown_stock_voice_raises():
    with pytest.raises(ValueError, match="unknown stock voice"):
        stock_voice("not_a_real_voice")


def test_every_stock_voice_carries_a_style_description():
    """Each catalog voice needs a description so hosted backends can voice it."""
    for name in STOCK_VOICES:
        assert STOCK_VOICE_STYLES.get(name), f"{name} has no style description"
    assert stock_voice(DEFAULT_STOCK_VOICE).instructions == STOCK_VOICE_STYLES[DEFAULT_STOCK_VOICE]


def test_stock_voice_register_reads_gender_from_kokoro_id():
    assert stock_voice_register("af_heart") == "high"  # American female
    assert stock_voice_register("bf_emma") == "high"  # British female
    assert stock_voice_register("am_michael") == "low"  # American male
    assert stock_voice_register("bm_george") == "low"  # British male
    assert stock_voice_register("weird") == "high"  # non-Kokoro name defaults high


def test_stock_voice_gender_reads_kokoro_id():
    assert stock_voice_gender("af_heart") == "female"
    assert stock_voice_gender("bf_emma") == "female"
    assert stock_voice_gender("am_adam") == "male"
    assert stock_voice_gender("bm_george") == "male"
    assert stock_voice_gender("weird") is None
    assert stock_voice_gender("x") is None


def test_stock_voice_display_name_uses_the_given_name():
    assert stock_voice_display_name("af_heart") == "Heart"
    assert stock_voice_display_name("am_adam") == "Adam"
    assert stock_voice_display_name("bf_emma") == "Emma"
    assert stock_voice_display_name("no_prefix") == "Prefix"
    assert stock_voice_display_name("heart") == "Heart"


def test_every_catalog_voice_has_a_known_gender():
    for name in STOCK_VOICES:
        assert stock_voice_gender(name) in ("female", "male"), name


def test_effective_stock_catalog_defaults_to_full_catalog():
    assert effective_stock_catalog(None) == list_stock_voices()
    assert effective_stock_catalog([]) == list_stock_voices()


def test_effective_stock_catalog_keeps_preferred_order_and_drops_unknown():
    assert effective_stock_catalog(["am_adam", "not_a_voice", "af_heart"]) == [
        "am_adam",
        "af_heart",
    ]


def test_effective_stock_catalog_falls_back_when_preferred_are_all_unknown():
    assert effective_stock_catalog(["nope"]) == list_stock_voices()


def test_interleave_alternates_register_and_keeps_default_first():
    order = interleave_by_register(list_stock_voices())
    registers = [stock_voice_register(n) for n in order]
    # Default (af_heart) stays first; it is the same voices, just reordered.
    assert order[0] == DEFAULT_STOCK_VOICE
    assert set(order) == set(list_stock_voices())
    # Registers strictly alternate until the smaller pool is exhausted.
    n_pairs = min(registers.count("high"), registers.count("low"))
    prefix = registers[: 2 * n_pairs]
    for a, b in zip(prefix, prefix[1:], strict=False):
        assert a != b


def test_two_host_assignment_gets_one_male_one_female():
    """A two-speaker cast over the interleaved catalog gets distinct registers."""
    order = interleave_by_register(list_stock_voices())
    first_two = order[:2]
    regs = {stock_voice_register(v) for v in first_two}
    assert regs == {"high", "low"}


def test_interleave_handles_single_register_and_empty():
    assert interleave_by_register([]) == []
    only_female = ["af_heart", "af_bella", "bf_emma"]
    assert interleave_by_register(only_female) == only_female  # nothing to alternate


def test_match_by_gender_assigns_same_register_voices():
    catalog = list_stock_voices()
    registers = {"S0": "high", "S1": "low"}
    got = match_by_gender(["S0", "S1"], registers, catalog)
    assert stock_voice_register(got["S0"]) == "high"
    assert stock_voice_register(got["S1"]) == "low"
    assert got["S0"] != got["S1"]


def test_match_by_gender_gives_distinct_voices_within_a_register():
    catalog = list_stock_voices()
    registers = {"S0": "high", "S1": "high"}  # two females
    got = match_by_gender(["S0", "S1"], registers, catalog)
    assert got["S0"] != got["S1"]
    assert all(stock_voice_register(v) == "high" for v in got.values())


def test_match_by_gender_skips_unknown_register():
    got = match_by_gender(["S0", "S1"], {"S0": "low"}, list_stock_voices())
    assert "S1" not in got  # no register known -> left for the caller to fall back
    assert stock_voice_register(got["S0"]) == "low"


def test_match_by_gender_skips_when_pool_exhausted():
    # Only one male voice in the catalog -> a second male speaker is left unassigned.
    catalog = ["af_heart", "am_adam"]
    got = match_by_gender(["S0", "S1"], {"S0": "low", "S1": "low"}, catalog)
    assert got["S0"] == "am_adam"
    assert "S1" not in got
