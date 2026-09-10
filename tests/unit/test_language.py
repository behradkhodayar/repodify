"""Target-language helpers: codes, WPM, disclaimers, prompt instructions."""

from __future__ import annotations

import pytest

from repodify.language import (
    clone_disclaimer,
    is_rtl,
    language_instruction,
    normalize_language,
    wpm_for,
)
from repodify.models.domain import JobOptions


def test_normalize_language_defaults_english():
    assert normalize_language(None) == "en"
    assert normalize_language("") == "en"
    assert normalize_language("  ") == "en"


def test_normalize_language_accepts_english_and_persian_aliases():
    assert normalize_language("en") == "en"
    assert normalize_language("English") == "en"
    assert normalize_language("fa") == "fa"
    assert normalize_language("FA") == "fa"
    assert normalize_language("persian") == "fa"
    assert normalize_language("Farsi") == "fa"


def test_normalize_language_rejects_unknown():
    with pytest.raises(ValueError, match="unsupported"):
        normalize_language("de")


def test_job_options_default_language_is_english():
    opts = JobOptions(episode_ids=["ep-1"])
    assert opts.target_language == "en"


def test_job_options_normalizes_persian_alias():
    opts = JobOptions(episode_ids=["ep-1"], target_language="farsi")
    assert opts.target_language == "fa"


def test_job_options_rejects_unknown_language():
    with pytest.raises(ValueError):
        JobOptions(episode_ids=["ep-1"], target_language="de")


def test_persian_is_rtl_english_is_not():
    assert is_rtl("fa") is True
    assert is_rtl("en") is False


def test_persian_wpm_differs_from_english():
    assert wpm_for("en") == 130
    assert wpm_for("fa") != wpm_for("en")
    assert wpm_for("fa") > 0


def test_clone_disclaimer_is_localized():
    en = clone_disclaimer("en")
    fa = clone_disclaimer("fa")
    assert "synthetic" in en.lower() or "AI" in en
    assert fa != en
    assert any("\u0600" <= ch <= "\u06ff" for ch in fa)


def test_language_instruction_only_for_non_english():
    assert language_instruction("en") is None
    fa = language_instruction("fa")
    assert fa is not None
    assert "Persian" in fa or "Farsi" in fa
