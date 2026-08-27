"""Enumerations shared across the pipeline and persistence layers."""

from __future__ import annotations

from enum import StrEnum


class StageName(StrEnum):
    """The pipeline stages, in execution order."""

    RESOLVE = "resolve"
    LIST = "list"
    DOWNLOAD = "download"
    TRANSCRIBE = "transcribe"
    DIARIZE = "diarize"
    SUMMARIZE = "summarize"
    ARC = "arc"
    SCRIPT = "script"
    TTS = "tts"
    ASSEMBLE = "assemble"


class JobStatus(StrEnum):
    """Overall lifecycle state of a job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageState(StrEnum):
    """State of an individual stage within a job."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"
