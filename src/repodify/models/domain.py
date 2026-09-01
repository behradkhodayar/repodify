"""Pydantic domain models — the vocabulary that flows through the pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_PROMPT_CHARS = 4000


def _fmt_mmss(seconds: float) -> str:
    """Format a start offset as [MM:SS]; minutes may exceed 59 (e.g. 73:04)."""
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


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


class Candidate(BaseModel):
    """A directory hit for the name-search dropdown.

    `feed_url` is the hand-off to the RSS fetcher. Directory-specific ids stay
    here so the episode picker never sees iTunes / Podcast Index types.
    """

    title: str
    author: str = ""
    feed_url: str
    artwork: str | None = None
    itunes_id: int | None = None
    pi_feed_id: int | None = None
    newest_item: int | None = None
    episode_count: int | None = None
    language: str | None = None
    sources: list[str] = Field(default_factory=list)
    dead: bool = False
    cached: bool = False


class TranscriptSegment(BaseModel):
    """A time-stamped span of transcribed speech.

    `speaker` is the diarization label (e.g. ``"SPEAKER_00"``) once the transcript
    has been speaker-labeled; it is ``None`` on a raw, speaker-agnostic transcript.
    """

    start: float
    end: float
    text: str
    speaker: str | None = None


class Speaker(BaseModel):
    """A distinct voice detected in an episode's audio via diarization."""

    id: str  # diarization label, e.g. "SPEAKER_00"
    label: str | None = None  # optional human-facing name
    speaking_seconds: float = 0.0
    gender: Literal["female", "male"] | None = None


class Transcript(BaseModel):
    """The full transcript of one episode."""

    episode_guid: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    speakers: list[Speaker] = Field(default_factory=list)

    @property
    def text(self) -> str:
        """The transcript as a single whitespace-joined string."""
        return " ".join(seg.text.strip() for seg in self.segments if seg.text.strip())

    @property
    def speaker_labeled_text(self) -> str:
        """Transcript grouped by speaker (``SPEAKER_00: …``), for the LLM to read.

        Consecutive segments by the same speaker are merged into one line. Falls
        back to plain `text` when no segment carries a speaker label.
        """
        labeled = [s for s in self.segments if s.text.strip()]
        if not any(s.speaker for s in labeled):
            return self.text
        lines: list[str] = []
        current_speaker: str | None = None  # no real speaker is None, so first differs
        for seg in labeled:
            speaker = seg.speaker or "UNKNOWN"
            if speaker != current_speaker:
                lines.append(f"{speaker}: {seg.text.strip()}")
                current_speaker = speaker
            else:
                lines[-1] += " " + seg.text.strip()
        return "\n".join(lines)

    def speaker_labeled_text_timestamped(self) -> str:
        """Like `speaker_labeled_text`, but each merged speaker turn is prefixed
        with its start time as ``[MM:SS]`` so the LLM can honor time references.

        When the transcript carries no speaker labels, each segment is emitted on
        its own timestamped line (keeping time granularity for cut instructions).
        """
        labeled = [s for s in self.segments if s.text.strip()]
        if not labeled:
            return ""
        has_speakers = any(s.speaker for s in labeled)
        lines: list[str] = []
        current_speaker: str | None = None
        for seg in labeled:
            ts = _fmt_mmss(seg.start)
            text = seg.text.strip()
            if not has_speakers:
                lines.append(f"[{ts}] {text}")
                continue
            speaker = seg.speaker or "UNKNOWN"
            if speaker != current_speaker:
                lines.append(f"[{ts}] {speaker}: {text}")
                current_speaker = speaker
            else:
                lines[-1] += " " + text
        return "\n".join(lines)


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
    synthetic: bool = False
    disclaimer: str | None = None


class VoiceAssignment(BaseModel):
    """How one detected speaker should be voiced in the output.

    `mode="clone"` clones the speaker's own voice from the source audio;
    `mode="stock"` uses the named catalog voice in `stock_voice`.
    """

    speaker_id: str  # diarization label, e.g. "SPEAKER_00"
    mode: Literal["clone", "stock"]
    stock_voice: str | None = None  # required when mode == "stock"
    display_name: str | None = None  # optional human name for show notes


class ExecutionChoice(BaseModel):
    """Local vs BYOK selection for one ML stage."""

    mode: Literal["local", "byok"]
    model: str | None = None
    backend: str | None = None  # LLM only: anthropic | ollama | openrouter


class JobOptions(BaseModel):
    """Per-run options chosen by the user."""

    episode_ids: list[str] = Field(default_factory=list)
    host_count: int = 1
    clone: bool = False
    target_minutes: int | None = 30
    voice_assignments: list[VoiceAssignment] = Field(default_factory=list)
    # Speaker-preserving digest: voice the digest as the real detected cast (each
    # speaker in their own cloned/stock voice). Overrides host_count when set.
    preserve_speakers: bool = False
    # Interactive review: pause after diarization so the user can assign a voice to
    # each detected speaker before the digest is written. Implies preserve_speakers.
    review_voices: bool = False
    assign_voices: bool = False
    use_original_voices: bool | None = None
    length_mode: Literal["manual", "smart"] = "manual"
    transcribe: ExecutionChoice | None = None
    diarize: ExecutionChoice | None = None
    llm: ExecutionChoice | None = None
    tts: ExecutionChoice | None = None
    narrator_voice: str | None = None

    # Free-text editorial guidance layered onto the built-in summarization
    # prompts. `custom_prompt` steers the whole digest (applied at every LLM
    # stage); `episode_prompts` maps an episode guid to guidance applied only to
    # that episode's summary.
    custom_prompt: str | None = Field(default=None, max_length=MAX_PROMPT_CHARS)
    episode_prompts: dict[str, str] = Field(default_factory=dict)

    @field_validator("episode_prompts")
    @classmethod
    def _clean_episode_prompts(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for guid, text in value.items():
            text = text.strip()
            if not text:
                continue
            if len(text) > MAX_PROMPT_CHARS:
                raise ValueError(f"episode prompt for {guid} exceeds {MAX_PROMPT_CHARS} chars")
            cleaned[guid] = text
        return cleaned
