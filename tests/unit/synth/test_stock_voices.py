import pytest

from podcast_compactor.synth.stock_voices import (
    DEFAULT_STOCK_VOICE,
    STOCK_VOICE_STYLES,
    STOCK_VOICES,
    interleave_by_register,
    list_stock_voices,
    stock_voice,
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
    assert v.ref_audio_path is None  # catalog voice needs no reference clip


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
