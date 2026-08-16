"""Enumerations shared across the pipeline and persistence layers."""

from __future__ import annotations

from enum import Enum


class StageName(str, Enum):
    """The pipeline stages, in execution order."""

    RESOLVE = "resolve"
    LIST = "list"
    DOWNLOAD = "download"
    TRANSCRIBE = "transcribe"
    SUMMARIZE = "summarize"
    ARC = "arc"
    SCRIPT = "script"
    TTS = "tts"
    ASSEMBLE = "assemble"


class JobStatus(str, Enum):
    """Overall lifecycle state of a job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageState(str, Enum):
    """State of an individual stage within a job."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"
