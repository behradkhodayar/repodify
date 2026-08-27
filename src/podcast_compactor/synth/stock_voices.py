"""The stock (catalog) voice registry — a thin layer over Kokoro's built-in voices.

A stock voice needs no reference clip: it is just a `Voice` naming a Kokoro voice.
Used when a speaker shouldn't or can't be cloned. See `synth.kokoro.KokoroTTS`.
"""

from __future__ import annotations

from podcast_compactor.ports.tts import Voice

# Curated, stable Kokoro voice ids we expose. Kokoro ships more; this is a
# sensible, gender-balanced default set (a*/b* = American/British, f/m = voice).
STOCK_VOICES: tuple[str, ...] = (
    "af_heart",
    "af_bella",
    "af_nicole",
    "am_adam",
    "am_michael",
    "bf_emma",
    "bm_george",
)

DEFAULT_STOCK_VOICE = "af_heart"


def list_stock_voices() -> list[str]:
    """The stock voice names available for assignment."""
    return list(STOCK_VOICES)


def stock_voice(name: str) -> Voice:
    """Resolve a stock voice name to a `Voice`. Raises on an unknown name."""
    if name not in STOCK_VOICES:
        raise ValueError(f"unknown stock voice {name!r}; choose from {list(STOCK_VOICES)}")
    return Voice(name=name, kokoro_voice=name)
