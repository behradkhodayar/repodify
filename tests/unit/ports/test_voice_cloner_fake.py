import io
import wave
from pathlib import Path

from podcast_compactor.ports.voice_cloner import FakeVoiceCloner, VoiceCloner
from podcast_compactor.storage.filesystem import FilesystemStorage


def test_fake_cloner_builds_a_voice_per_speaker(tmp_path):
    store = FilesystemStorage(tmp_path)
    cloner = FakeVoiceCloner()

    voices = cloner.clone([Path("ep0.mp3")], ["host_a", "host_b"], store, "job1")

    assert set(voices) == {"host_a", "host_b"}
    for key, voice in voices.items():
        assert voice.name == key
        assert voice.ref_text
        # The reference clip exists and is a valid WAV.
        assert voice.ref_audio_path.exists()
        with wave.open(io.BytesIO(voice.ref_audio_path.read_bytes()), "rb") as w:
            assert w.getnframes() > 0
    assert cloner.calls[0][1] == ["host_a", "host_b"]


def test_fake_cloner_satisfies_protocol():
    assert isinstance(FakeVoiceCloner(), VoiceCloner)
