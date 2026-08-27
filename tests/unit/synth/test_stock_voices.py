import pytest

from podcast_compactor.synth.stock_voices import (
    DEFAULT_STOCK_VOICE,
    STOCK_VOICE_STYLES,
    STOCK_VOICES,
    list_stock_voices,
    stock_voice,
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
