from podcast_compactor.models.domain import JobOptions, VoiceAssignment
from podcast_compactor.synth.voice_assignment import resolve_voice_assignments

CATALOG = ["voice_a", "voice_b"]


def _resolve(speaker_ids, options):
    return resolve_voice_assignments(speaker_ids, options, CATALOG, "voice_a")


def test_clone_true_clones_every_detected_speaker():
    resolved = _resolve(["SPEAKER_00", "SPEAKER_01"], JobOptions(clone=True))
    assert {k: v.mode for k, v in resolved.items()} == {
        "SPEAKER_00": "clone",
        "SPEAKER_01": "clone",
    }


def test_no_clone_assigns_stock_round_robin():
    resolved = _resolve(["S0", "S1", "S2"], JobOptions(clone=False))
    assert [resolved[s].mode for s in ["S0", "S1", "S2"]] == ["stock"] * 3
    # Round-robins over the catalog, wrapping after it is exhausted.
    assert [resolved[s].stock_voice for s in ["S0", "S1", "S2"]] == [
        "voice_a", "voice_b", "voice_a",
    ]


def test_explicit_assignment_wins():
    options = JobOptions(
        clone=True,
        voice_assignments=[
            VoiceAssignment(speaker_id="S0", mode="stock", stock_voice="voice_b")
        ],
    )
    resolved = _resolve(["S0", "S1"], options)
    assert resolved["S0"].mode == "stock"
    assert resolved["S0"].stock_voice == "voice_b"
    assert resolved["S1"].mode == "clone"  # default (clone=True) for the rest


def test_explicit_stock_without_voice_gets_default():
    options = JobOptions(
        voice_assignments=[VoiceAssignment(speaker_id="S0", mode="stock")]
    )
    resolved = _resolve(["S0"], options)
    assert resolved["S0"].stock_voice == "voice_a"  # default_stock_voice


def test_empty_catalog_falls_back_to_default():
    resolved = resolve_voice_assignments(["S0"], JobOptions(), [], "fallback")
    assert resolved["S0"].stock_voice == "fallback"
