"""Merge per-episode diarization speakers into cross-episode global identities.

Diarization runs independently on each episode, so pyannote's labels are only
consistent *within* a file: ``SPEAKER_00`` in episode 1 is not necessarily the
same person as ``SPEAKER_00`` in episode 2. For a multi-episode digest of one
show — where the hosts (say Katie and Ben) recur across every episode — we want
one stable identity (and therefore one voice) per real person.

`cluster_speakers` does that: given each per-episode speaker's voice embedding and
talk time, it agglomeratively clusters embeddings across episodes (cosine distance,
centroid linkage) under a **cannot-link** constraint — two speakers diarization
already separated within the *same* episode never merge, so we only ever unify
identities *across* episodes and never override pyannote's within-episode split.
The result maps each ``(episode, local_label)`` to a canonical global label, with
labels numbered by pooled talk time so the most prominent recurring speaker is
``SPEAKER_00``.

Pure NumPy; no models or I/O, so it is trivially testable with synthetic vectors.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import numpy as np


class LocalSpeaker(NamedTuple):
    """One speaker as diarization labeled them within a single episode."""

    episode: str  # episode guid
    label: str  # per-episode diarization label, e.g. "SPEAKER_00"
    embedding: Sequence[float]  # speaker centroid embedding from the diarizer
    weight: float  # talk time in seconds (for centroid weighting + label order)


class _Cluster:
    """A group of local speakers believed to be the same person across episodes."""

    __slots__ = ("members", "episodes", "weight", "centroid")

    def __init__(self, member: LocalSpeaker, unit: np.ndarray) -> None:
        self.members: list[LocalSpeaker] = [member]
        self.episodes: set[str] = {member.episode}
        self.weight: float = max(member.weight, 0.0)
        # Weighted, L2-normalized centroid of member embeddings (unit vectors).
        self.centroid: np.ndarray = unit * max(member.weight, 0.0)

    def can_merge(self, other: _Cluster) -> bool:
        """Two clusters may merge only if they share no episode (cannot-link)."""
        return self.episodes.isdisjoint(other.episodes)

    def merge(self, other: _Cluster) -> None:
        self.members.extend(other.members)
        self.episodes |= other.episodes
        self.weight += other.weight
        self.centroid = self.centroid + other.centroid  # sum of weighted unit vectors


def _unit(vec: Sequence[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float64)
    norm = float(np.linalg.norm(arr))
    return arr / norm if norm > 0 else arr


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 1.0
    return 1.0 - float(np.dot(a, b) / (na * nb))


def cluster_speakers(
    locals_: list[LocalSpeaker],
    threshold: float,
) -> dict[tuple[str, str], str]:
    """Map every ``(episode, local_label)`` to a cross-episode global label.

    Clusters are merged greedily by nearest centroid (cosine distance) while the
    closest mergeable pair is within ``threshold`` and shares no episode. Global
    labels (``SPEAKER_00`` …) are assigned by descending pooled talk time.

    With a single episode (or embeddings too far apart to merge) this is just a
    canonical relabeling — each local speaker keeps a distinct identity — so the
    speaker-preserving digest degrades gracefully to the per-episode behavior.
    """
    if not locals_:
        return {}

    clusters = [_Cluster(sp, _unit(sp.embedding)) for sp in locals_]

    while len(clusters) > 1:
        best: tuple[float, int, int] | None = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                if not clusters[i].can_merge(clusters[j]):
                    continue
                dist = _cosine_distance(clusters[i].centroid, clusters[j].centroid)
                if dist < threshold and (best is None or dist < best[0]):
                    best = (dist, i, j)
        if best is None:
            break
        _, i, j = best
        clusters[i].merge(clusters[j])
        clusters.pop(j)

    # Most-talkative recurring speaker first, so labels are stable and meaningful.
    clusters.sort(key=lambda c: c.weight, reverse=True)
    mapping: dict[tuple[str, str], str] = {}
    for idx, cluster in enumerate(clusters):
        global_label = f"SPEAKER_{idx:02d}"
        for member in cluster.members:
            mapping[(member.episode, member.label)] = global_label
    return mapping
