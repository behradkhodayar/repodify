from pathlib import Path

import httpx
import pytest
import respx

from repodify.transcribe.openrouter import OpenRouterTranscriber

URL = "https://openrouter.ai/api/v1/audio/transcriptions"


def test_transcribe_parses_verbose_segments(tmp_path: Path):
    audio = tmp_path / "ep.mp3"
    audio.write_bytes(b"AUDIO")
    stt = OpenRouterTranscriber(api_key="sk-test", model="openai/whisper-large-v3")
    with respx.mock:
        respx.post(URL).respond(
            json={
                "text": "hello world",
                "segments": [
                    {"start": 0.0, "end": 1.2, "text": "hello"},
                    {"start": 1.2, "end": 2.0, "text": "world"},
                ],
            }
        )
        transcript = stt.transcribe(audio)
    assert [s.text for s in transcript.segments] == ["hello", "world"]
    assert transcript.segments[0].start == 0.0
    assert transcript.segments[1].end == 2.0


def test_transcribe_falls_back_to_single_segment_when_no_timestamps(tmp_path: Path):
    audio = tmp_path / "ep.mp3"
    audio.write_bytes(b"AUDIO")
    stt = OpenRouterTranscriber(api_key="sk-test")
    with respx.mock:
        respx.post(URL).respond(json={"text": "just text"})
        transcript = stt.transcribe(audio)
    assert len(transcript.segments) == 1
    assert transcript.segments[0].text == "just text"


def test_transcribe_raises_on_http_error(tmp_path: Path):
    audio = tmp_path / "ep.mp3"
    audio.write_bytes(b"AUDIO")
    stt = OpenRouterTranscriber(api_key="sk-test")
    with respx.mock:
        respx.post(URL).respond(status_code=401, json={"error": "nope"})
        with pytest.raises(httpx.HTTPStatusError):
            stt.transcribe(audio)
