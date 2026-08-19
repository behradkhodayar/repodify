"""faster-whisper transcriber (real backend; requires the [gpu] extra)."""

from __future__ import annotations

import ctypes
import glob
import os
import sysconfig
from pathlib import Path

from podcast_compactor.gpu import empty_cuda_cache
from podcast_compactor.models.domain import Transcript, TranscriptSegment


def _preload_cuda12_libs() -> None:
    """Preload the CUDA 12 cuBLAS runtime so CTranslate2 can find it.

    faster-whisper's CTranslate2 backend is built against CUDA 12 and dlopens
    ``libcublas.so.12``. A CUDA 13 PyTorch build only ships ``libcublas.so.13``,
    so the load fails with "Library libcublas.so.12 is not found or cannot be
    loaded". When the ``nvidia-cublas-cu12`` / ``nvidia-cuda-runtime-cu12`` wheels
    are installed (see the ``gpu`` extra), preload their libraries with
    ``RTLD_GLOBAL`` — in dependency order — so the sonames resolve without any
    ``LD_LIBRARY_PATH`` juggling.

    Best-effort and idempotent: silently does nothing when the libraries are
    absent (e.g. a CPU-only or CUDA 12 PyTorch environment that doesn't need it).
    """
    site_packages = sysconfig.get_paths()["purelib"]
    for soname in ("libcudart.so.12", "libcublasLt.so.12", "libcublas.so.12"):
        for lib in glob.glob(os.path.join(site_packages, "nvidia", "*", "lib", soname)):
            try:
                ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                break
            except OSError:
                continue


class FasterWhisperTranscriber:
    """Transcribes audio with faster-whisper (CTranslate2 Whisper).

    The model is loaded lazily on first `transcribe` — not at construction — so
    wiring the pipeline costs no VRAM, and `release()` can hand that VRAM back
    between stages. The heavy `faster_whisper` import is likewise deferred so the
    rest of the app and the test suite run without the GPU extra installed.
    """

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "float16",
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            _preload_cuda12_libs()  # must run before CTranslate2 is imported below
            from faster_whisper import WhisperModel  # lazy: needs the [gpu] extra

            self._model = WhisperModel(
                self._model_size, device=self._device, compute_type=self._compute_type
            )
        return self._model

    def transcribe(self, audio_path: Path, language: str = "en") -> Transcript:
        segments, _info = self._ensure_model().transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
        )
        return Transcript(
            episode_guid="",  # filled in by the caller
            segments=[
                TranscriptSegment(start=s.start, end=s.end, text=s.text)
                for s in segments
            ],
        )

    def release(self) -> None:
        """Drop the model so its VRAM is freed; reloads lazily on next transcribe."""
        self._model = None
        empty_cuda_cache()
