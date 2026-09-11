"""Chatterbox Persian-Farsi synthesizer (real backend; needs the [gpu] extra).

PyPI `chatterbox-tts` pins an older Torch; this repo overrides that so the GPU
extra keeps a single CUDA 13 stack. resemble-perth's implicit watermarker is
optional — we fall back to its dummy if it cannot import.

Loads Resemble's multilingual Chatterbox, then overlays
``Thomcles/Chatterbox-TTS-Persian-Farsi`` T3 weights (``t3_fa.safetensors``).
Heavy imports are deferred to first use. Output is 24kHz mono 16-bit WAV.
"""

from __future__ import annotations

import array
import io
import os
import re
import sys
import tempfile
import wave
from collections.abc import Callable
from typing import Any

from repodify.gpu import empty_cuda_cache
from repodify.ports.tts import SAMPLE_RATE, Voice

DEFAULT_REPO = "Thomcles/Chatterbox-TTS-Persian-Farsi"
_T3_FILENAME = "t3_fa.safetensors"
# Chatterbox T3 is not a long-form model; chunk on sentence boundaries.
_MAX_CHARS = 300
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟؛\n])\s+")
# A 2.5s+ catalog clip plus a normal sentence trips s3gen ("out-of-range
# special tokens" / CUDA assert). 1.5s is enough to keep gender and stays
# inside the flow encoder's token budget.
_PROMPT_MAX_S = 1.5

Loader = Callable[..., Any]


def chunk_text(text: str, max_chars: int = _MAX_CHARS) -> list[str]:
    """Split `text` into pieces that fit `max_chars`, preferring sentence ends."""
    text = text.strip()
    if not text:
        return [""]
    if len(text) <= max_chars:
        return [text]
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for part in parts:
        if len(part) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(part), max_chars):
                chunks.append(part[i : i + max_chars])
            continue
        candidate = f"{buf} {part}".strip() if buf else part
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            chunks.append(buf)
            buf = part
    if buf:
        chunks.append(buf)
    return chunks or [text]


def _ensure_perth_watermarker() -> None:
    """Chatterbox always constructs `perth.PerthImplicitWatermarker()`.

    resemble-perth 1.0 leaves that name as None when its implicit net cannot
    import (e.g. missing `pkg_resources`). Fall back to the bundled dummy so
    load still succeeds; Repodify already watermarks cloned output itself.
    """
    import perth

    if getattr(perth, "PerthImplicitWatermarker", None) is None:
        perth.PerthImplicitWatermarker = perth.DummyWatermarker


def load_persian_chatterbox(
    *,
    repo_id: str,
    device: str,
    hf_token: str | None = None,
) -> Any:
    """Download T3 Farsi weights and load them into multilingual Chatterbox.

    Lazy: `chatterbox`, `huggingface_hub`, and `safetensors` stay out of the
    import graph so CPU tests never touch them.
    """
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # lazy: [gpu]
    from huggingface_hub import hf_hub_download
    from safetensors.torch import load_file as load_safetensors

    _ensure_perth_watermarker()
    model = ChatterboxMultilingualTTS.from_pretrained(device=device)
    path = hf_hub_download(repo_id=repo_id, filename=_T3_FILENAME, token=hf_token)
    t3_state = load_safetensors(path, device="cpu")
    model.t3.load_state_dict(t3_state)
    model.t3.to(device).eval()
    return model


class ChatterboxPersianTTS:
    """Synthesizes Persian speech; returns 24kHz mono 16-bit WAV bytes.

    `loader` is the model factory (overridable in tests). Construction loads
    nothing; `release()` drops the model so VRAM can go to the next stage.
    """

    def __init__(
        self,
        repo_id: str = DEFAULT_REPO,
        hf_token: str | None = None,
        device: str = "cuda",
        sample_rate: int = SAMPLE_RATE,
        loader: Loader | None = None,
    ) -> None:
        self.model_id = repo_id
        self._repo_id = repo_id
        self._hf_token = hf_token
        self._device = device
        self._sample_rate = sample_rate
        self._loader = loader or load_persian_chatterbox
        self._model = None
        self._trimmed_prompts: dict[str, str] = {}

    def _ensure_model(self):
        if self._model is None:
            self._model = self._loader(
                repo_id=self._repo_id,
                device=self._device,
                hf_token=self._hf_token,
            )
        return self._model

    def synthesize(self, text: str, voice: Voice) -> bytes:
        model = self._ensure_model()
        prompt = (
            _trimmed_prompt_path(str(voice.ref_audio_path), self._trimmed_prompts)
            if voice.ref_audio_path is not None
            else None
        )
        pieces: list[bytes] = []
        for chunk in chunk_text(text):
            kwargs: dict[str, Any] = {"language_id": None}
            if prompt:
                kwargs["audio_prompt_path"] = prompt
            audio = model.generate(chunk, **kwargs)
            pieces.append(_audio_to_wav(audio, getattr(model, "sr", self._sample_rate)))
        if len(pieces) == 1:
            return _resample_wav(pieces[0], self._sample_rate)
        return _concat_wavs(pieces, self._sample_rate)

    def release(self) -> None:
        self._model = None
        for src, dest in self._trimmed_prompts.items():
            if dest != src:
                try:
                    os.unlink(dest)
                except OSError:
                    pass
        self._trimmed_prompts = {}
        empty_cuda_cache()


def _trimmed_prompt_path(path: str, cache: dict[str, str], max_s: float = _PROMPT_MAX_S) -> str:
    """Return `path`, or a temp WAV of the first `max_s` seconds if longer."""
    cached = cache.get(path)
    if cached is not None:
        return cached
    try:
        with wave.open(path, "rb") as w:
            rate = w.getframerate()
            n_frames = w.getnframes()
            max_frames = int(rate * max_s)
            if n_frames <= max_frames:
                cache[path] = path
                return path
            params = w.getparams()
            frames = w.readframes(max_frames)
    except wave.Error:
        cache[path] = path
        return path
    fd, dest = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(dest, "wb") as w:
        w.setparams(params)
        w.writeframes(frames)
    cache[path] = dest
    return dest


def _as_float_list(audio: Any) -> list[float]:
    for attr in ("detach", "cpu", "squeeze"):
        fn = getattr(audio, attr, None)
        if callable(fn):
            audio = fn()
    numpy = getattr(audio, "numpy", None)
    if callable(numpy):
        audio = numpy()
    to_list = getattr(audio, "tolist", None)
    if callable(to_list):
        data = to_list()
        if data and isinstance(data[0], list):
            data = data[0]
        return [float(x) for x in data]
    return [float(x) for x in list(audio)]


def _floats_to_wav(samples: list[float], sample_rate: int) -> bytes:
    pcm = array.array("h", (max(-32768, min(32767, int(x * 32767.0))) for x in samples))
    if sys.byteorder == "big":
        pcm.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _audio_to_wav(audio: Any, sample_rate: int) -> bytes:
    return _floats_to_wav(_as_float_list(audio), sample_rate)


def _wav_params(data: bytes) -> tuple[int, int, int, int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        return (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes())


def _resample_wav(data: bytes, sample_rate: int) -> bytes:
    channels, width, rate, _frames = _wav_params(data)
    if (channels, width, rate) == (1, 2, sample_rate):
        return data
    # Chatterbox is 24kHz; if a stub uses another rate, wrap at the requested rate
    # without interpolating — tests and the real model already match SAMPLE_RATE.
    with wave.open(io.BytesIO(data), "rb") as w:
        frames = w.readframes(w.getnframes())
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(frames)
    return buf.getvalue()


def _concat_wavs(segments: list[bytes], sample_rate: int) -> bytes:
    frames = bytearray()
    for seg in segments:
        aligned = _resample_wav(seg, sample_rate)
        with wave.open(io.BytesIO(aligned), "rb") as w:
            frames.extend(w.readframes(w.getnframes()))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()
