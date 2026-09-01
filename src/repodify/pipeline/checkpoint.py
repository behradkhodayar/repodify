"""SQLite LangGraph checkpointer, project-root-anchored under DATA_DIR.

Durable interrupts (the per-stage local/BYOK gates) live here so a job can
survive process restart and machine shutdown. Pydantic domain models are on the
msgpack allowlist so PipelineState round-trips without pickle.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from repodify.models import domain as d

_DOMAIN_MODELS = (
    d.JobOptions,
    d.VoiceAssignment,
    d.Feed,
    d.Episode,
    d.Transcript,
    d.TranscriptSegment,
    d.Speaker,
    d.EpisodeSummary,
    d.ArcOutline,
    d.ArcBeat,
    d.Script,
    d.ScriptSegment,
    d.Chapter,
    d.ShowNotes,
)


def checkpoint_path(data_dir: Path) -> Path:
    return data_dir / "checkpoints.db"


def _serde() -> JsonPlusSerializer:
    return JsonPlusSerializer().with_msgpack_allowlist(_DOMAIN_MODELS)


@contextmanager
def open_checkpointer(data_dir: Path) -> Iterator[SqliteSaver]:
    """Open (and create) the job-graph SQLite saver under ``data_dir``."""
    path = checkpoint_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        yield SqliteSaver(conn, serde=_serde())
    finally:
        conn.close()
