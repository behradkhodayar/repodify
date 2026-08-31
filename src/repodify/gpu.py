"""Small GPU-memory helpers shared by the real ML adapters."""

from __future__ import annotations

import gc


def empty_cuda_cache() -> None:
    """Best-effort release of cached CUDA memory after a model is dropped.

    Run a garbage collection so any just-dereferenced model is finalized, then
    hand its cached allocator blocks back to the driver. No-op and never raises
    when torch or a CUDA device is absent (CPU/test hosts), so callers can free
    unconditionally between pipeline stages.
    """
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001 - freeing memory must never break a run
        pass
