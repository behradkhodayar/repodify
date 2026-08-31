import sys
import types

from repodify.models.domain import EpisodeSummary
from repodify.ports.llm import OllamaStructuredLLM, StructuredLLM


def test_ollama_satisfies_protocol():
    assert isinstance(OllamaStructuredLLM("m", "http://localhost:11434"), StructuredLLM)


def test_ollama_generate_wires_model_and_returns_structured(monkeypatch):
    calls = {}
    returned = EpisodeSummary(key_points=["hello"])

    class FakeStructured:
        def __init__(self, schema):
            self.schema = schema

        def invoke(self, messages):
            calls["messages"] = messages
            calls["schema"] = self.schema
            return returned

    class FakeChatOllama:
        def __init__(self, model, base_url, keep_alive=None):
            calls["model"] = model
            calls["base_url"] = base_url
            calls["keep_alive"] = keep_alive

        def with_structured_output(self, schema):
            return FakeStructured(schema)

    fake_module = types.ModuleType("langchain_ollama")
    fake_module.ChatOllama = FakeChatOllama
    monkeypatch.setitem(sys.modules, "langchain_ollama", fake_module)

    llm = OllamaStructuredLLM("qwen2.5-coder:7b", "http://gpu:11434")
    out = llm.generate("sys-prompt", "user-prompt", EpisodeSummary)

    assert out is returned
    assert calls["model"] == "qwen2.5-coder:7b"
    assert calls["base_url"] == "http://gpu:11434"
    assert calls["schema"] is EpisodeSummary
    assert calls["messages"] == [("system", "sys-prompt"), ("human", "user-prompt")]


def test_ollama_sets_keep_alive_zero_to_free_vram_after_generate(monkeypatch):
    # keep_alive=0 tells the Ollama daemon to unload the model right after the
    # call, so its VRAM is freed before the TTS stage instead of lingering.
    captured = {}

    class FakeStructured:
        def __init__(self, schema):
            pass

        def invoke(self, messages):
            return EpisodeSummary(key_points=["x"])

    class FakeChatOllama:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def with_structured_output(self, schema):
            return FakeStructured(schema)

    fake_module = types.ModuleType("langchain_ollama")
    fake_module.ChatOllama = FakeChatOllama
    monkeypatch.setitem(sys.modules, "langchain_ollama", fake_module)

    llm = OllamaStructuredLLM("qwen2.5-coder:7b", "http://gpu:11434")
    llm.generate("s", "u", EpisodeSummary)

    assert captured.get("keep_alive") == 0
