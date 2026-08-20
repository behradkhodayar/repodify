from pathlib import Path

from podcast_compactor.ports.transcoder import FakeTranscoder


def test_fake_transcoder_writes_a_nonempty_stub(tmp_path: Path):
    src = tmp_path / "digest.wav"
    src.write_bytes(b"RIFF....WAVE")
    dst = tmp_path / "out" / "digest.mp3"

    FakeTranscoder().to_mp3(src, dst)

    assert dst.exists()
    assert dst.read_bytes()  # non-empty
