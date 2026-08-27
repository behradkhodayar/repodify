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
from podcast_compactor.synth.openrouter_tts import OpenRouterTTS, OpenRouterTTSError

SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"


def _tiny_mp3() -> bytes:
    """A ~0.1s silent mp3, produced with ffmpeg from raw PCM."""
    pcm = struct.pack("<" + "h" * 2400, *([0] * 2400))  # 0.1s @ 24kHz mono s16le
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0",
         "-f", "mp3", "pipe:1"],
        input=pcm, capture_output=True,
    )
    assert out.returncode == 0, out.stderr.decode()
    return out.stdout


def _wav_params(data: bytes) -> tuple[int, int, int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        return (w.getnchannels(), w.getsampwidth(), w.getframerate())


pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_synthesize_returns_24k_mono_wav():
    tts = OpenRouterTTS(api_key="sk-test", model="fish-audio/s2.1-pro")
    with respx.mock:
        respx.post(SPEECH_URL).respond(
            content=_tiny_mp3(), headers={"content-type": "audio/mpeg"}
        )
        wav = tts.synthesize("Hello world.", Voice(name="narrator"))
    assert _wav_params(wav) == (1, 2, 24000)


def test_reference_voice_maps_to_input_references(tmp_path: Path):
    ref = tmp_path / "narrator.wav"
    with wave.open(str(ref), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 100)

    captured = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, content=_tiny_mp3(), headers={"content-type": "audio/mpeg"})

    tts = OpenRouterTTS(api_key="sk-test")
    voice = Voice(name="narrator", ref_audio_path=ref, ref_text="a transcript")
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_capture)
        tts.synthesize("Hello.", voice)

    body = captured["body"]
    assert body["model"] == "fish-audio/s2.1-pro"
    assert body["input"] == "Hello."
    assert body["response_format"] == "mp3"
    refs = body["input_references"]
    assert any(p["type"] == "input_audio" for p in refs)
    audio = next(p for p in refs if p["type"] == "input_audio")
    assert audio["input_audio"]["data"].startswith("data:audio/wav;base64,")
    assert any(p == {"type": "text", "text": "a transcript"} for p in refs)


def _capture_body(captured: dict):
    def _side_effect(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, content=_tiny_mp3(), headers={"content-type": "audio/mpeg"})

    return _side_effect


def test_bare_voice_sends_neither_references_nor_instructions():
    captured = {}
    tts = OpenRouterTTS(api_key="sk-test")
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_capture_body(captured))
        tts.synthesize("Hi.", Voice(name="narrator"))
    assert "input_references" not in captured["body"]
    assert "instructions" not in captured["body"]


def test_stock_voice_maps_to_instructions_not_references():
    captured = {}
    tts = OpenRouterTTS(api_key="sk-test")
    voice = Voice(name="am_michael", kokoro_voice="am_michael",
                  instructions="a deep, steady American male voice")
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_capture_body(captured))
        tts.synthesize("Hi.", voice)
    assert "input_references" not in captured["body"]
    assert captured["body"]["instructions"] == "a deep, steady American male voice"


def test_kokoro_id_without_instructions_derives_fallback_description():
    captured = {}
    tts = OpenRouterTTS(api_key="sk-test")
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_capture_body(captured))
        tts.synthesize("Hi.", Voice(name="bm_george", kokoro_voice="bm_george"))
    instructions = captured["body"]["instructions"]
    assert "British" in instructions and "male" in instructions


def test_reference_voice_ignores_instructions_and_clones(tmp_path: Path):
    """A reference clip wins over instructions: clone, don't describe."""
    ref = tmp_path / "ref.wav"
    with wave.open(str(ref), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 100)

    captured = {}
    tts = OpenRouterTTS(api_key="sk-test")
    voice = Voice(name="narrator", ref_audio_path=ref, ref_text="hi",
                  instructions="a robotic voice")
    with respx.mock:
        respx.post(SPEECH_URL).mock(side_effect=_capture_body(captured))
        tts.synthesize("Hi.", voice)
    assert "input_references" in captured["body"]
    assert "instructions" not in captured["body"]


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


def test_release_is_a_noop():
    OpenRouterTTS(api_key="sk-test").release()  # must not raise
