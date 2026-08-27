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

# Natural-language descriptions of each stock voice, used by hosted backends that
# have no reference clip (e.g. Fish Audio via OpenRouter) to synthesize a voice
# that approximates the Kokoro catalog voice's gender/accent/character. Local
# Kokoro ignores these and renders the exact catalog voice by id.
# Descriptions lead with an explicit pitch/register cue ("high-pitched" /
# "low-pitched, deep") because Fish Audio's style control responds to pitch words
# far more reliably than to abstract character words — this is what keeps male and
# female stock speakers audibly distinct without reference clips.
STOCK_VOICE_STYLES: dict[str, str] = {
    "af_heart": "a high-pitched, warm and friendly American female voice",
    "af_bella": "a high-pitched, smooth and expressive American female voice",
    "af_nicole": "a high-pitched, soft and gentle American female voice",
    "am_adam": "a low-pitched, clear and confident American male voice",
    "am_michael": "a deep, low-pitched, steady American male voice",
    "bf_emma": "a high-pitched, bright and articulate British female voice",
    "bm_george": "a deep, low-pitched, refined British male voice",
}


def list_stock_voices() -> list[str]:
    """The stock voice names available for assignment."""
    return list(STOCK_VOICES)


def stock_voice(name: str) -> Voice:
    """Resolve a stock voice name to a `Voice`. Raises on an unknown name."""
    if name not in STOCK_VOICES:
        raise ValueError(f"unknown stock voice {name!r}; choose from {list(STOCK_VOICES)}")
    return Voice(name=name, kokoro_voice=name, instructions=STOCK_VOICE_STYLES.get(name))
