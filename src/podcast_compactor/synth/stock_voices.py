"""The stock (catalog) voice registry — a thin layer over Kokoro's built-in voices.

A stock voice needs no reference clip: it is just a `Voice` naming a Kokoro voice.
Used when a speaker shouldn't or can't be cloned. See `synth.kokoro.KokoroTTS`.
"""

from __future__ import annotations

from typing import Literal

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


def stock_voice_gender(name: str) -> Literal["female", "male"] | None:
    """A stock voice's gender, from the Kokoro id (``a/b`` accent, ``f/m`` gender).

    Returns ``None`` when the id doesn't look like a Kokoro voice.
    """
    if len(name) < 2:
        return None
    return {"f": "female", "m": "male"}.get(name[1])


def stock_voice_display_name(name: str) -> str:
    """Human label for a catalog id, e.g. ``af_heart`` → ``Heart``."""
    _, sep, rest = name.partition("_")
    label = rest if sep else name
    if not label:
        return name
    return label[0].upper() + label[1:]


def effective_stock_catalog(preferred: list[str] | None = None) -> list[str]:
    """The catalog gender-matching and round-robin assignment should use.

    A non-empty ``preferred`` list (Settings) is treated as an ordered subset of
    the built-in catalog; unknown ids are dropped. Empty/unset preferred, or a
    list that survives filtering as empty, falls back to the full catalog so a
    misconfigured setting can't leave the pipeline with no voices.
    """
    full = list_stock_voices()
    if not preferred:
        return full
    known = set(full)
    chosen = [v for v in preferred if v in known]
    return chosen or full


def stock_voice_register(name: str) -> Literal["high", "low"]:
    """A stock voice's vocal register, from its Kokoro id (``a/b`` accent, ``f/m``).

    ``m`` (male) voices are ``"low"``, ``f`` (female) are ``"high"``; anything that
    doesn't look like a Kokoro id defaults to ``"high"``.
    """
    return "low" if len(name) >= 2 and name[1] == "m" else "high"


def match_by_gender(
    ordered_ids: list[str],
    registers: dict[str, str],
    catalog: list[str],
) -> dict[str, str]:
    """Assign each speaker a distinct same-register stock voice, where known.

    ``registers`` maps a speaker id to ``"high"``/``"low"`` (from pitch); speakers
    absent from it, or once a register's pool is exhausted, are left unassigned so
    the caller can fall back (e.g. to `interleave_by_register`). Voices are handed
    out in catalog order within each register, so distinct speakers stay distinct.
    """
    pools: dict[str, list[str]] = {
        "high": [v for v in catalog if stock_voice_register(v) == "high"],
        "low": [v for v in catalog if stock_voice_register(v) == "low"],
    }
    used: dict[str, int] = {"high": 0, "low": 0}
    assigned: dict[str, str] = {}
    for sid in ordered_ids:
        reg = registers.get(sid)
        if reg in pools and used[reg] < len(pools[reg]):
            assigned[sid] = pools[reg][used[reg]]
            used[reg] += 1
    return assigned


def interleave_by_register(names: list[str]) -> list[str]:
    """Reorder a catalog so consecutive voices alternate register (high/low).

    Round-robin assignment over this order gives adjacent cast speakers audibly
    distinct voices — a male and a female for a two-host show — instead of, say,
    two similar female voices from a female-heavy catalog. The first name's
    register leads, so the catalog's default voice stays first.
    """
    if not names:
        return []
    high = [n for n in names if stock_voice_register(n) == "high"]
    low = [n for n in names if stock_voice_register(n) == "low"]
    first, second = (high, low) if stock_voice_register(names[0]) == "high" else (low, high)
    out: list[str] = []
    for i in range(max(len(first), len(second))):
        if i < len(first):
            out.append(first[i])
        if i < len(second):
            out.append(second[i])
    return out


def stock_voice(name: str) -> Voice:
    """Resolve a stock voice name to a `Voice`. Raises on an unknown name."""
    if name not in STOCK_VOICES:
        raise ValueError(f"unknown stock voice {name!r}; choose from {list(STOCK_VOICES)}")
    return Voice(name=name, kokoro_voice=name, instructions=STOCK_VOICE_STYLES.get(name))
