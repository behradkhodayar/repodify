"""Pydantic domain models — the vocabulary that flows through the pipeline."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Episode(BaseModel):
    """A single podcast episode as parsed from an RSS feed."""

    guid: str
    title: str
    published_at: datetime | None = None
    duration_s: int | None = None
    audio_url: str
    order_index: int
    is_short_or_trailer: bool = False


class Feed(BaseModel):
    """A resolved podcast feed and its episodes (oldest-first)."""

    source_url: str
    rss_url: str
    title: str
    author: str | None = None
    episodes: list[Episode] = Field(default_factory=list)


class TranscriptSegment(BaseModel):
    """A time-stamped span of transcribed speech."""

    start: float
    end: float
    text: str


class Transcript(BaseModel):
    """The full transcript of one episode."""

    episode_guid: str
    segments: list[TranscriptSegment] = Field(default_factory=list)

    @property
    def text(self) -> str:
        """The transcript as a single whitespace-joined string."""
        return " ".join(seg.text.strip() for seg in self.segments if seg.text.strip())


class EpisodeSummary(BaseModel):
    """Structured summary of one episode (the map step output)."""

    episode_guid: str = ""
    title: str = ""
    order_index: int = 0
    key_points: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    notable_quotes: list[str] = Field(default_factory=list)
    timeline_markers: list[str] = Field(default_factory=list)


class ArcBeat(BaseModel):
    """One movement in the chronological narrative arc."""

    heading: str
    episode_guids: list[str] = Field(default_factory=list)
    narrative: str


class ArcOutline(BaseModel):
    """The chronological through-line across all selected episodes."""

    title: str
    throughline: str
    beats: list[ArcBeat] = Field(default_factory=list)


class ScriptSegment(BaseModel):
    """One spoken chunk, attributed to a speaker."""

    speaker: str
    text: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())


class Script(BaseModel):
    """The full spoken script for the digest episode."""

    segments: list[ScriptSegment] = Field(default_factory=list)

    @property
    def word_count(self) -> int:
        return sum(seg.word_count for seg in self.segments)

    def estimated_minutes(self, wpm: int) -> float:
        """Estimated spoken duration in minutes at the given words-per-minute."""
        if wpm <= 0:
            raise ValueError("wpm must be positive")
        return self.word_count / wpm


class Chapter(BaseModel):
    """A chapter marker in the output audio."""

    title: str
    start_s: float


class ShowNotes(BaseModel):
    """Human-readable notes accompanying the digest."""

    summary: str
    chapters: list[Chapter] = Field(default_factory=list)


class JobOptions(BaseModel):
    """Per-run options chosen by the user."""

    episode_ids: list[str] = Field(default_factory=list)
    host_count: int = 1
    clone: bool = False
    target_minutes: int = 30
