from repodify.summarize.prompts import clean_prompt, with_guidance


def test_clean_prompt_strips_and_nullifies_empty():
    assert clean_prompt("  hi  ") == "hi"
    assert clean_prompt("   ") is None
    assert clean_prompt(None) is None


def test_with_guidance_no_guidance_returns_base_unchanged():
    base = "Base user prompt."
    assert with_guidance(base) is base
    assert with_guidance(base, whole="   ", episode=None) is base


def test_with_guidance_whole_only():
    out = with_guidance("BASE", whole="focus on funding")
    assert out.startswith("BASE")
    assert "Whole digest: focus on funding" in out
    assert "This episode:" not in out


def test_with_guidance_episode_only():
    out = with_guidance("BASE", episode="cut 4:20 to 6:09")
    assert "This episode: cut 4:20 to 6:09" in out
    assert "Whole digest:" not in out


def test_with_guidance_both_are_labeled():
    out = with_guidance("BASE", whole="skip ads", episode="keep the interview")
    assert "Whole digest: skip ads" in out
    assert "This episode: keep the interview" in out
