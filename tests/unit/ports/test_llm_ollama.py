import sys
import types

from podcast_compactor.models.domain import EpisodeSummary
from podcast_compactor.ports.llm import OllamaStructuredLLM, StructuredLLM


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
        def __init__(self, model, base_url):
            calls["model"] = model
            calls["base_url"] = base_url

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
