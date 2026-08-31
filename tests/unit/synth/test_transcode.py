import shutil
import struct
import wave
from pathlib import Path

import pytest

from repodify.synth.transcode import FfmpegTranscoder


def _tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(struct.pack("<" + "h" * 2400, *([0] * 2400)))  # 0.1s silence


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_ffmpeg_transcoder_produces_a_nonempty_mp3(tmp_path: Path):
    src = tmp_path / "digest.wav"
    _tiny_wav(src)
    dst = tmp_path / "out" / "digest.mp3"

    FfmpegTranscoder().to_mp3(src, dst)

    assert dst.exists()
    assert dst.stat().st_size > 0
