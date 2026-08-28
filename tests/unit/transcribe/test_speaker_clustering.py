"""Tests for cross-episode speaker clustering (pure, synthetic embeddings)."""

from __future__ import annotations

from podcast_compactor.transcribe.speaker_clustering import LocalSpeaker, cluster_speakers

# Two well-separated voice "directions" in embedding space. Small per-episode
# jitter keeps same-person vectors close (cosine distance well under threshold)
# while different people stay ~orthogonal (distance ~1.0).
KATIE = [1.0, 0.0, 0.0]
KATIE_J = [0.98, 0.05, 0.0]
KATIE_JJ = [0.97, 0.0, 0.06]
BEN = [0.0, 1.0, 0.0]
BEN_J = [0.03, 0.98, 0.0]
BEN_JJ = [0.0, 0.99, 0.04]

THRESHOLD = 0.5


def test_empty_input_returns_empty_mapping():
    assert cluster_speakers([], THRESHOLD) == {}


def test_single_episode_is_identity_relabeling():
    """One episode: speakers stay distinct (cannot-link), just canonically labeled."""
    locals_ = [
        LocalSpeaker("ep1", "SPEAKER_00", KATIE, weight=60.0),
        LocalSpeaker("ep1", "SPEAKER_01", BEN, weight=40.0),
    ]
    mapping = cluster_speakers(locals_, THRESHOLD)
    # Two distinct global ids, most-talkative first.
    assert mapping[("ep1", "SPEAKER_00")] == "SPEAKER_00"
    assert mapping[("ep1", "SPEAKER_01")] == "SPEAKER_01"
    assert len(set(mapping.values())) == 2


def test_same_person_across_episodes_merges():
    locals_ = [
        LocalSpeaker("ep1", "SPEAKER_00", KATIE, weight=50.0),
        LocalSpeaker("ep2", "SPEAKER_00", KATIE_J, weight=50.0),
    ]
    mapping = cluster_speakers(locals_, THRESHOLD)
    assert mapping[("ep1", "SPEAKER_00")] == mapping[("ep2", "SPEAKER_00")]
    assert len(set(mapping.values())) == 1


def test_distant_speakers_stay_distinct_across_episodes():
    locals_ = [
        LocalSpeaker("ep1", "SPEAKER_00", KATIE, weight=50.0),
        LocalSpeaker("ep2", "SPEAKER_00", BEN, weight=50.0),
    ]
    mapping = cluster_speakers(locals_, THRESHOLD)
    assert mapping[("ep1", "SPEAKER_00")] != mapping[("ep2", "SPEAKER_00")]


def test_cannot_link_same_episode_speakers_never_merge():
    """Even with near-identical embeddings, two speakers split within one episode
    stay separate — we never override pyannote's within-episode decision."""
    locals_ = [
        LocalSpeaker("ep1", "SPEAKER_00", KATIE, weight=30.0),
        LocalSpeaker("ep1", "SPEAKER_01", KATIE_J, weight=30.0),  # ~identical, same ep
    ]
    mapping = cluster_speakers(locals_, THRESHOLD)
    assert mapping[("ep1", "SPEAKER_00")] != mapping[("ep1", "SPEAKER_01")]


def test_katie_and_ben_swapped_labels_across_three_episodes():
    """The real scenario: per-episode labels are inconsistent (swapped in ep2),
    but clustering unifies each real person into one global identity everywhere."""
    locals_ = [
        # ep1: 00=Katie, 01=Ben
        LocalSpeaker("ep1", "SPEAKER_00", KATIE, weight=70.0),
        LocalSpeaker("ep1", "SPEAKER_01", BEN, weight=30.0),
        # ep2: labels SWAPPED -> 00=Ben, 01=Katie
        LocalSpeaker("ep2", "SPEAKER_00", BEN_J, weight=25.0),
        LocalSpeaker("ep2", "SPEAKER_01", KATIE_J, weight=75.0),
        # ep3: 00=Katie, 01=Ben
        LocalSpeaker("ep3", "SPEAKER_00", KATIE_JJ, weight=65.0),
        LocalSpeaker("ep3", "SPEAKER_01", BEN_JJ, weight=35.0),
    ]
    mapping = cluster_speakers(locals_, THRESHOLD)

    # Exactly two global identities across all three episodes.
    assert len(set(mapping.values())) == 2

    katie_ids = {
        mapping[("ep1", "SPEAKER_00")],
        mapping[("ep2", "SPEAKER_01")],
        mapping[("ep3", "SPEAKER_00")],
    }
    ben_ids = {
        mapping[("ep1", "SPEAKER_01")],
        mapping[("ep2", "SPEAKER_00")],
        mapping[("ep3", "SPEAKER_01")],
    }
    # Each real person collapses to a single global label...
    assert len(katie_ids) == 1
    assert len(ben_ids) == 1
    # ...and the two people are different labels.
    assert katie_ids != ben_ids
    # Katie talks more overall, so she is SPEAKER_00.
    assert katie_ids == {"SPEAKER_00"}
    assert ben_ids == {"SPEAKER_01"}


def test_global_labels_ordered_by_pooled_talk_time():
    """A speaker quiet in every single episode but present in all still outranks a
    one-off louder guest once talk time is pooled across episodes."""
    locals_ = [
        LocalSpeaker("ep1", "SPEAKER_00", KATIE, weight=20.0),
        LocalSpeaker("ep2", "SPEAKER_00", KATIE_J, weight=20.0),
        LocalSpeaker("ep3", "SPEAKER_00", KATIE_JJ, weight=20.0),  # pooled 60
        LocalSpeaker("ep1", "SPEAKER_01", BEN, weight=45.0),  # one-off guest, 45
    ]
    mapping = cluster_speakers(locals_, THRESHOLD)
    assert mapping[("ep1", "SPEAKER_00")] == "SPEAKER_00"  # recurring host wins
    assert mapping[("ep1", "SPEAKER_01")] == "SPEAKER_01"


def test_zero_norm_embedding_does_not_crash_and_stays_distinct():
    locals_ = [
        LocalSpeaker("ep1", "SPEAKER_00", [0.0, 0.0, 0.0], weight=10.0),
        LocalSpeaker("ep2", "SPEAKER_00", KATIE, weight=10.0),
    ]
    mapping = cluster_speakers(locals_, THRESHOLD)
    # Degenerate embedding is max-distance from everything -> never merges.
    assert mapping[("ep1", "SPEAKER_00")] != mapping[("ep2", "SPEAKER_00")]
