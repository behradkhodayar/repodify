"""Pocket TTS Persian synthesizer (real backend; needs the [gpu] extra).

Loads `mehdi-hf/pocket-tts-farsi` via `pocket_tts.TTSModel`. Inference is CPU;
the extra still pulls torch. Heavy imports are deferred to first use. Output is
24kHz mono 16-bit WAV.
"""

from __future__ import annotations

import array
import io
import re
import sys
import wave
from collections.abc import Callable
from typing import Any

from repodify.gpu import empty_cuda_cache
from repodify.ports.tts import SAMPLE_RATE, Voice
from repodify.synth.normalize_fa import normalize

DEFAULT_REPO = "mehdi-hf/pocket-tts-farsi"
DEFAULT_CONFIG = "farsi.yaml"
# Pocket Farsi is short-form (~18 sentencepiece tokens). Char budget is a
# stand-in so tests stay tokenizer-free.
_MAX_CHARS = 48
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟؛\n])\s+")
_PAUSE_S = 0.15
_RUNAWAY_S = 4.0

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


def load_pocket_farsi(
    *,
    repo_id: str,
    hf_token: str | None = None,
    temp: float = 0.3,
) -> Any:
    """Load Pocket TTS from a Hugging Face repo. Lazy: `pocket_tts` stays out."""
    from pocket_tts import TTSModel  # lazy: [gpu]

    del hf_token  # HF hub uses the environment token when needed
    config = f"hf://{repo_id}/{DEFAULT_CONFIG}"
    return TTSModel.load_model(config=config, temp=temp)


class PocketPersianTTS:
    """Synthesizes Persian speech with Pocket TTS; returns 24kHz mono WAV bytes.

    `loader` is the model factory (overridable in tests). Construction loads
    nothing; `release()` drops the model.
    """

    def __init__(
        self,
        repo_id: str = DEFAULT_REPO,
        hf_token: str | None = None,
        sample_rate: int = SAMPLE_RATE,
        loader: Loader | None = None,
    ) -> None:
        self.model_id = repo_id
        self._repo_id = repo_id
        self._hf_token = hf_token
        self._sample_rate = sample_rate
        self._loader = loader or load_pocket_farsi
        self._model = None
        self._prompt_states: dict[str, Any] = {}

    def _ensure_model(self):
        if self._model is None:
            self._model = self._loader(repo_id=self._repo_id, hf_token=self._hf_token)
            self._prompt_states = {}
        return self._model

    def _state_for(self, prompt_path: str) -> Any:
        model = self._ensure_model()
        cached = self._prompt_states.get(prompt_path)
        if cached is not None:
            return cached
        state = model.get_state_for_audio_prompt(prompt_path)
        self._prompt_states[prompt_path] = state
        return state

    def synthesize(self, text: str, voice: Voice) -> bytes:
        if voice.ref_audio_path is None:
            raise ValueError("Pocket TTS requires voice.ref_audio_path")
        prompt = str(voice.ref_audio_path)
        folded = normalize(text)
        model = self._ensure_model()
        state = self._state_for(prompt)
        pieces: list[bytes] = []
        for chunk in chunk_text(folded):
            audio = self._generate_chunk(model, state, chunk)
            pieces.append(_audio_to_wav(audio, self._sample_rate))
        if len(pieces) == 1:
            return _resample_wav(pieces[0], self._sample_rate)
        paused = [_silence_wav(self._sample_rate, _PAUSE_S)]
        interleaved: list[bytes] = []
        for i, piece in enumerate(pieces):
            if i:
                interleaved.extend(paused)
            interleaved.append(piece)
        return _concat_wavs(interleaved, self._sample_rate)

    def _generate_chunk(self, model: Any, state: Any, text: str) -> Any:
        kwargs = {"frames_after_eos": 0}
        audio = model.generate_audio(state, text, **kwargs)
        if not _is_runaway(audio, self._sample_rate):
            return audio
        audio = model.generate_audio(state, text, **kwargs)
        if not _is_runaway(audio, self._sample_rate):
            return audio
        if len(text) < 8:
            return audio
        mid = max(1, len(text) // 2)
        left = self._generate_chunk(model, state, text[:mid].strip())
        right = self._generate_chunk(model, state, text[mid:].strip())
        return _as_float_list(left) + _as_float_list(right)

    def release(self) -> None:
        self._model = None
        self._prompt_states = {}
        empty_cuda_cache()


def _is_runaway(audio: Any, sample_rate: int) -> bool:
    samples = _as_float_list(audio)
    if not samples:
        return False
    return (len(samples) / float(sample_rate)) > _RUNAWAY_S


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


def _silence_wav(sample_rate: int, seconds: float) -> bytes:
    n = max(1, int(seconds * sample_rate))
    return _floats_to_wav([0.0] * n, sample_rate)


def _wav_params(data: bytes) -> tuple[int, int, int, int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        return (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes())


def _resample_wav(data: bytes, sample_rate: int) -> bytes:
    channels, width, rate, _frames = _wav_params(data)
    if (channels, width, rate) == (1, 2, sample_rate):
        return data
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
