import io
import json
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import httpx
import pytest
import respx

from podcast_compactor.ports.tts import Voice
from podcast_compactor.synth.openrouter_tts import _SEED_TEXT, OpenRouterTTS, OpenRouterTTSError

SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"


def _tiny_mp3() -> bytes:
    """A ~0.1s silent mp3, produced with ffmpeg from raw PCM."""
    pcm = struct.pack("<" + "h" * 2400, *([0] * 2400))  # 0.1s @ 24kHz mono s16le
    out = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "s16le",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-f",
            "mp3",
            "pipe:1",
        ],
        input=pcm,
        capture_output=True,
    )
    assert out.returncode == 0, out.stderr.decode()
    return out.stdout


def _wav_params(data: bytes) -> tuple[int, int, int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        return (w.getnchannels(), w.getsampwidth(), w.getframerate())


def _record_bodies(bodies: list):
    def _side_effect(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, content=_tiny_mp3(), headers={"content-type": "audio/mpeg"})

    return _side_effect


def _is_input_audio(part: dict) -> bool:
    return part["type"] == "input_audio" and part["input_audio"]["data"].startswith(
        "data:audio/wav;base64,"
    )


pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_synthesize_returns_24k_mono_wav():
    tts = OpenRouterTTS(api_key="sk-test", model="fish-audio/s2.1-pro")
    with respx.mock:
        respx.post(SPEECH_URL).respond(content=_tiny_mp3(), headers={"content-type": "audio/mpeg"})
        wav = tts.synthesize("Hello world.", Voice(name="narrator"))
    assert _wav_params(wav) == (1, 2, 24000)


def test_reference_voice_maps_to_input_references(tmp_path: Path):
    ref = tmp_path / "narrator.wav"
    with wave.open(str(ref), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 100)

    bodies: list = []
    tts = OpenRouterTTS(api_key="sk-test")
    voice = Voice(name="narrator", ref_audio_path=ref, ref_text="a transcript")
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_record_bodies(bodies))
        tts.synthesize("Hello.", voice)

    assert len(bodies) == 1  # a configured clip needs no seeding
    refs = bodies[0]["input_references"]
    assert any(_is_input_audio(p) for p in refs)
    assert {"type": "text", "text": "a transcript"} in refs


def test_bare_voice_sends_neither_references_nor_instructions():
    bodies: list = []
    tts = OpenRouterTTS(api_key="sk-test")
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_record_bodies(bodies))
        tts.synthesize("Hi.", Voice(name="narrator"))
    assert len(bodies) == 1
    assert "input_references" not in bodies[0]
    assert "instructions" not in bodies[0]


def test_described_voice_seeds_once_then_clones_for_consistency():
    """A stock/described voice generates one seed clip, then clones it every segment.

    This is the fix for a speaker's voice drifting between segments: the seed is
    created once (from the description) and reused, so all segments share it.
    """
    bodies: list = []
    tts = OpenRouterTTS(api_key="sk-test")
    voice = Voice(
        name="am_michael",
        kokoro_voice="am_michael",
        instructions="a deep, steady American male voice",
    )
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_record_bodies(bodies))
        tts.synthesize("First segment.", voice)
        tts.synthesize("Second segment.", voice)

    # 1 seed call + 2 segment calls; the seed is not regenerated.
    assert len(bodies) == 3
    seed = bodies[0]
    assert seed["input"] == _SEED_TEXT
    assert seed["instructions"] == "a deep, steady American male voice"
    assert "input_references" not in seed
    for seg in bodies[1:]:
        assert "instructions" not in seg  # identity comes from the seed clip
        assert any(_is_input_audio(p) for p in seg["input_references"])
    assert {b["input"] for b in bodies[1:]} == {"First segment.", "Second segment."}


def test_kokoro_id_without_instructions_seeds_from_derived_description():
    bodies: list = []
    tts = OpenRouterTTS(api_key="sk-test")
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_record_bodies(bodies))
        tts.synthesize("Hi.", Voice(name="bm_george", kokoro_voice="bm_george"))
    seed = bodies[0]
    assert "British" in seed["instructions"] and "male" in seed["instructions"]


def test_distinct_speakers_get_distinct_seeds():
    bodies: list = []
    tts = OpenRouterTTS(api_key="sk-test")
    host_a = Voice(name="host_a", instructions="a deep male host")
    host_b = Voice(name="host_b", instructions="a bright female host")
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_record_bodies(bodies))
        tts.synthesize("Line one.", host_a)
        tts.synthesize("Line two.", host_b)
    seeds = [b["instructions"] for b in bodies if "instructions" in b]
    assert seeds == ["a deep male host", "a bright female host"]  # one seed each, distinct


def test_stock_voice_with_bundled_sample_clones_without_seeding():
    """Hosted TTS must clone the catalog preview, not guess gender from text.

    Fish Audio's `instructions` nudge often still yields a male voice; the
    bundled female/male clip is the actual identity.
    """
    from podcast_compactor.synth.stock_voices import stock_voice

    voice = stock_voice("af_heart")
    assert voice.ref_audio_path is not None

    bodies: list = []
    tts = OpenRouterTTS(api_key="sk-test")
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_record_bodies(bodies))
        tts.synthesize("Hello from Heart.", voice)
        tts.synthesize("Second line.", voice)

    assert len(bodies) == 2  # no extra seed call
    for body in bodies:
        assert "instructions" not in body
        assert any(_is_input_audio(p) for p in body["input_references"])


def test_reference_voice_ignores_instructions_and_clones(tmp_path: Path):
    """A reference clip wins over instructions: clone it, don't seed from a description."""
    ref = tmp_path / "ref.wav"
    with wave.open(str(ref), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 100)

    bodies: list = []
    tts = OpenRouterTTS(api_key="sk-test")
    voice = Voice(
        name="narrator", ref_audio_path=ref, ref_text="hi", instructions="a robotic voice"
    )
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_record_bodies(bodies))
        tts.synthesize("Hi.", voice)
    assert len(bodies) == 1
    assert "input_references" in bodies[0]
    assert "instructions" not in bodies[0]


def test_json_error_response_raises():
    tts = OpenRouterTTS(api_key="sk-test")
    with respx.mock:
        respx.post(SPEECH_URL).respond(
            status_code=400,
            json={"error": {"message": "bad request", "code": 400}},
        )
        with pytest.raises(OpenRouterTTSError):
            tts.synthesize("x", Voice(name="narrator"))


def test_missing_api_key_rejected():
    with pytest.raises(ValueError):
        OpenRouterTTS(api_key="")


def test_release_clears_seed_cache():
    bodies: list = []
    tts = OpenRouterTTS(api_key="sk-test")
    voice = Voice(name="host_a", instructions="a deep male host")
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_record_bodies(bodies))
        tts.synthesize("One.", voice)  # seeds
        tts.release()  # drops the seed
        tts.synthesize("Two.", voice)  # must seed again
    seed_calls = [b for b in bodies if "instructions" in b]
    assert len(seed_calls) == 2
