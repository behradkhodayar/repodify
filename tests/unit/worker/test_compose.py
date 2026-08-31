from repodify.config import Settings
from repodify.ports.diarizer import FakeDiarizer
from repodify.ports.llm import LocalStubLLM
from repodify.ports.transcriber import FakeTranscriber
from repodify.ports.tts import FakeTTS
from repodify.ports.voice_cloner import FakeVoiceCloner
from repodify.ports.watermarker import FakeWatermarker
from repodify.worker.main import build_deps


def test_build_deps_uses_fakes_in_fake_mode(tmp_path):
    settings = Settings(
        _env_file=None,
        use_fakes=True,
        database_url=f"sqlite:///{tmp_path / 'w.db'}",
        data_dir=tmp_path / "data",
    )
    deps = build_deps(settings)
    try:
        assert isinstance(deps.transcriber, FakeTranscriber)
        assert isinstance(deps.diarizer, FakeDiarizer)
        assert isinstance(deps.tts, FakeTTS)
        assert isinstance(deps.llm_map, LocalStubLLM)
        assert isinstance(deps.llm_reduce, LocalStubLLM)
        assert {"narrator", "host_a", "host_b"} <= set(deps.voices)
        assert isinstance(deps.voice_cloner, FakeVoiceCloner)
        assert isinstance(deps.watermarker, FakeWatermarker)
    finally:
        deps.http.close()
