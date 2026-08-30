from podcast_compactor.models.domain import Transcript
from podcast_compactor.ports.diarizer import FakeDiarizer
from podcast_compactor.ports.llm import (
    AnthropicStructuredLLM,
    FakeStructuredLLM,
    LocalStubLLM,
    OllamaStructuredLLM,
    OpenRouterStructuredLLM,
)
from podcast_compactor.ports.transcriber import FakeTranscriber
from podcast_compactor.ports.tts import FakeTTS
from podcast_compactor.synth.openrouter_tts import OpenRouterTTS
from podcast_compactor.synth.routing_tts import RoutingTTS
from podcast_compactor.transcribe.diarization import PyannoteDiarizer
from podcast_compactor.transcribe.faster_whisper import FasterWhisperTranscriber


def test_fakes_have_empty_model_id():
    t = FakeTranscriber(Transcript(episode_guid="", segments=[]))
    assert t.model_id is None
    assert FakeDiarizer().model_id is None
    assert FakeTTS().model_id is None
    assert LocalStubLLM().model_id is None
    assert FakeStructuredLLM([]).model_id is None


def test_real_backends_expose_model_id():
    assert FasterWhisperTranscriber("small").model_id == "small"
    assert PyannoteDiarizer(None, "pyannote/speaker-diarization-community-1").model_id == (
        "pyannote/speaker-diarization-community-1"
    )
    assert AnthropicStructuredLLM("claude-haiku", "key").model_id == "claude-haiku"
    assert OllamaStructuredLLM("qwen", "http://localhost").model_id == "qwen"
    assert OpenRouterStructuredLLM("gpt-4o-mini", "key", "http://x").model_id == "gpt-4o-mini"
    assert OpenRouterTTS(api_key="k", model="fish-audio/s2.1-pro").model_id == "fish-audio/s2.1-pro"
    assert RoutingTTS(FakeTTS(), FakeTTS()).model_id == "f5+kokoro"
