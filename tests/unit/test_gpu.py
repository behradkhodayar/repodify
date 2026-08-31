from repodify.gpu import empty_cuda_cache


def test_empty_cuda_cache_is_safe_and_idempotent():
    # Must never raise, whether or not torch/CUDA is present (CPU/test hosts),
    # and must be safe to call more than once.
    empty_cuda_cache()
    empty_cuda_cache()
