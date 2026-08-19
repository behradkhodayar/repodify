from podcast_compactor.transcribe.faster_whisper import _preload_cuda12_libs


def test_preload_cuda12_libs_is_safe_and_idempotent():
    # Must never raise, even when the CUDA 12 wheels are absent (CPU/test host),
    # and must be safe to call more than once.
    _preload_cuda12_libs()
    _preload_cuda12_libs()
