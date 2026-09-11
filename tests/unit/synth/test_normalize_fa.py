"""Persian TTS text folding: Arabic letters, harakat, digits."""

from __future__ import annotations

from repodify.synth.normalize_fa import normalize


def test_folds_arabic_yeh_and_kaf_to_persian():
    assert "ي" not in normalize("يك")
    assert "ك" not in normalize("يك")
    assert normalize("يك") == "یک"


def test_strips_harakat_and_keeps_zwnj():
    # tashdid / fatha should vanish; ZWNJ in می‌رود stays
    out = normalize("می‌رَوَد")
    assert "َ" not in out
    assert "‌" in out


def test_spells_persian_digits():
    out = normalize("سال ۱۴۰۲")
    assert "۱" not in out
    assert "۱۴۰۲" not in out
    assert "هزار" in out
