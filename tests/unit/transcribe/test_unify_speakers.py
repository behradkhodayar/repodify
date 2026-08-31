"""Tests for unify_speakers_across_episodes (relabel + pooled cast orchestration)."""

from __future__ import annotations

from repodify.ports.diarizer import DiarizationResult, SpeakerTurn
from repodify.transcribe.diarization import unify_speakers_across_episodes

# Two well-separated voices; small jitter keeps same-person vectors close.
A, A2 = [1.0, 0.0], [0.98, 0.05]
B, B2 = [0.0, 1.0], [0.05, 0.98]


def test_unify_collapses_swapped_labels_across_episodes():
    """The real pyannote failure mode: labels swap between episodes. After unifying,
    each real person carries one global id everywhere (and the busier one is 00)."""
    results = {
        "ep1": DiarizationResult(
            turns=[
                SpeakerTurn(start=0.0, end=60.0, speaker="SPEAKER_00"),  # person A
                SpeakerTurn(start=60.0, end=100.0, speaker="SPEAKER_01"),  # person B
            ],
            embeddings={"SPEAKER_00": A, "SPEAKER_01": B},
        ),
        "ep2": DiarizationResult(
            turns=[
                SpeakerTurn(start=0.0, end=40.0, speaker="SPEAKER_00"),  # person B (swap!)
                SpeakerTurn(start=40.0, end=100.0, speaker="SPEAKER_01"),  # person A
            ],
            embeddings={"SPEAKER_00": B2, "SPEAKER_01": A2},
        ),
    }
    relabeled, roster = unify_speakers_across_episodes(results, threshold=0.5)

    # Person A: SPEAKER_00 in ep1, SPEAKER_01 in ep2 -> one shared global id.
    a_ep1, a_ep2 = relabeled["ep1"][0].speaker, relabeled["ep2"][1].speaker
    b_ep1, b_ep2 = relabeled["ep1"][1].speaker, relabeled["ep2"][0].speaker
    assert a_ep1 == a_ep2
    assert b_ep1 == b_ep2
    assert a_ep1 != b_ep1

    # Pooled cast has two identities; A (120s) outranks B (80s) -> A is SPEAKER_00.
    assert [s.id for s in roster] == ["SPEAKER_00", "SPEAKER_01"]
    assert a_ep1 == "SPEAKER_00"


def test_unify_without_embeddings_keeps_per_episode_labels():
    """No embeddings (degraded backend) -> identity relabeling, per-episode labels."""
    results = {
        "ep1": DiarizationResult(
            turns=[SpeakerTurn(start=0.0, end=10.0, speaker="SPEAKER_00")],
            embeddings={},
        ),
    }
    relabeled, roster = unify_speakers_across_episodes(results, threshold=0.5)
    assert relabeled["ep1"][0].speaker == "SPEAKER_00"
    assert [s.id for s in roster] == ["SPEAKER_00"]
