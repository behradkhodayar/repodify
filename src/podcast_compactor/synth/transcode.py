"""ffmpeg-backed Transcoder (real adapter; requires the `ffmpeg` binary)."""

from __future__ import annotations

import subprocess
from pathlib import Path


class FfmpegTranscoder:
    """Transcodes WAV to a small mono mp3 via the system ffmpeg binary."""

    def to_mp3(self, src_wav: Path, dst_mp3: Path) -> None:
        dst_mp3.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(src_wav),
                "-c:a", "libmp3lame", "-b:a", "64k", "-ac", "1",
                str(dst_mp3),
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg transcode failed ({result.returncode}): "
                f"{result.stderr.decode(errors='replace')[-500:]}"
            )
