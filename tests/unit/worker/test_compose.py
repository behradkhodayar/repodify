from podcast_compactor.config import Settings
from podcast_compactor.ports.llm import LocalStubLLM
from podcast_compactor.ports.transcriber import FakeTranscriber
from podcast_compactor.ports.tts import FakeTTS
from podcast_compactor.ports.voice_cloner import FakeVoiceCloner
from podcast_compactor.ports.watermarker import FakeWatermarker
from podcast_compactor.worker.main import build_deps


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
        assert isinstance(deps.tts, FakeTTS)
        assert isinstance(deps.llm_map, LocalStubLLM)
        assert isinstance(deps.llm_reduce, LocalStubLLM)
        assert {"narrator", "host_a", "host_b"} <= set(deps.voices)
        assert isinstance(deps.voice_cloner, FakeVoiceCloner)
        assert isinstance(deps.watermarker, FakeWatermarker)
    finally:
        deps.http.close()
