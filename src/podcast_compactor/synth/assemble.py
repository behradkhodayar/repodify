"""Synthesize a script to audio, stitch it, and build show notes."""

from __future__ import annotations

import io
import subprocess
import tempfile
import wave
from pathlib import Path

from podcast_compactor.models.domain import ArcOutline, Chapter, Script, ShowNotes
from podcast_compactor.ports.tts import TTS, Voice


def synthesize_script(
    script: Script,
    tts: TTS,
    voices: dict[str, Voice],
) -> list[bytes]:
    """Render each script segment to WAV bytes using its speaker's voice."""
    out: list[bytes] = []
    for seg in script.segments:
        if seg.speaker not in voices:
            raise KeyError(f"no voice configured for speaker {seg.speaker!r}")
        out.append(tts.synthesize(seg.text, voices[seg.speaker]))
    return out


def _wav_params(data: bytes) -> tuple[int, int, int, int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        return (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes())


def wav_duration_seconds(data: bytes) -> float:
    _channels, _width, rate, frames = _wav_params(data)
    return frames / rate if rate else 0.0


def assemble_wav(segments: list[bytes]) -> bytes:
    """Concatenate same-format WAV blobs into a single WAV."""
    if not segments:
        raise ValueError("no segments to assemble")

    first = _wav_params(segments[0])[:3]
    frames = bytearray()
    for seg in segments:
        params = _wav_params(seg)[:3]
        if params != first:
            raise ValueError(f"segment format {params} != {first}")
        with wave.open(io.BytesIO(seg), "rb") as w:
            frames.extend(w.readframes(w.getnframes()))

    channels, width, rate = first
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def build_show_notes(
    arc: ArcOutline,
    script: Script,
    segments: list[bytes],
) -> ShowNotes:
    """One chapter per arc beat, with start times from cumulative segment durations."""
    durations = [wav_duration_seconds(s) for s in segments]
    n_beats = len(arc.beats)
    chapters: list[Chapter] = []
    if n_beats:
        per = max(1, len(segments) // n_beats)
        for i, beat in enumerate(arc.beats):
            seg_index = min(i * per, len(durations))
            start = sum(durations[:seg_index])
            chapters.append(Chapter(title=beat.heading, start_s=start))
    return ShowNotes(summary=arc.throughline, chapters=chapters)


def wav_to_mp3(wav: bytes, out: Path) -> None:
    """Convert WAV bytes to an MP3 file via ffmpeg. Not exercised in unit tests."""
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(wav)
        tmp.flush()
        subprocess.run(
            ["ffmpeg", "-y", "-i", tmp.name, "-b:a", "128k", str(out)],
            check=True,
            capture_output=True,
        )
