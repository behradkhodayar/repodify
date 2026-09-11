# Local Persian TTS engines (Pocket default, Chatterbox optional)

## Goal

Local Farsi synthesis uses **Pocket TTS** (`mehdi-hf/pocket-tts-farsi`) by
default, with **Chatterbox** remaining a first-class option. The user picks the
engine in Settings (job default) and can override it at the TTS gate. Neda
(female) and Arman (male) stay the Persian catalog; bundled reference clips
make those names actually sound different (today both fall through to
Chatterbox’s default male speaker).

## Non-goals

- Voice cloning of English hosts into Persian (still out of v1).
- A third local Persian engine, or treating the HF repo string as the engine.
- Running Pocket TTS in `./launch --fake` (fake mode still uses `FakeTTS`).
- Putting `pocket-tts` on the base extra (tests stay torch-free).
- Changing English local TTS (Kokoro / F5) or OpenRouter BYOK.

## Architecture

Local Persian TTS is an **engine enum**, not a Hugging Face id.

| Layer | Behavior |
| --- | --- |
| Settings | `persian_tts_engine`: `pocket` (default) \| `chatterbox` |
| TTS gate | Local vs BYOK; Farsi Local adds Pocket \| Chatterbox, defaulting from Settings |
| Worker | `_build_real_tts` / `apply_job_backends` construct `PocketPersianTTS` or `ChatterboxPersianTTS` |
| Voices | Same `fa_neda` / `fa_arman` catalog; both engines clone from bundled WAVs |

English is unchanged. BYOK Farsi is still OpenRouter (`openrouter_tts_model_fa`).
An unrecognized engine **raises**; no silent fallthrough.

## Components

### Config (`src/repodify/config.py`)

- `persian_tts_engine: Literal["pocket", "chatterbox"] = "pocket"`
- `pocket_persian_model: str = "mehdi-hf/pocket-tts-farsi"`
- `chatterbox_persian_model` unchanged (`Thomcles/Chatterbox-TTS-Persian-Farsi`)

Env: `PERSIAN_TTS_ENGINE`, `POCKET_PERSIAN_MODEL`, existing
`CHATTERBOX_PERSIAN_MODEL`. All three persist in `OVERRIDE_FIELDS`.

### `PocketPersianTTS` (`src/repodify/synth/pocket_tts.py`)

Same `TTS` port as Chatterbox: `synthesize(text, voice) -> 24 kHz mono WAV`,
`release()` drops the model. Construction loads nothing.

- Lazy-import `pocket_tts`. Tests inject a `loader`.
- Load `hf://{pocket_persian_model}/farsi.yaml` (temp 0.3).
- Voice prompt: `voice.ref_audio_path` via `get_state_for_audio_prompt`.
- Normalize text with a vendored copy of the model’s MIT `normalize_fa`
  (library functions only; no typer CLI).
- Chunk on Persian punctuation to ~18 sentencepiece tokens (char budget ~48);
  join with ~0.15 s silence. On a no-EOS runaway: retry once, then split the
  chunk in half.
- `frames_after_eos=0`. Output resampled to `SAMPLE_RATE` (24 kHz).

`pocket-tts` is a `[gpu]` extra only, even though inference is CPU.

### Chatterbox

Unchanged loader. It already passes `audio_prompt_path` when
`voice.ref_audio_path` is set, so bundled clips fix gender without an API
change.

### Stock voices

Bundle:

- `assets/voice-samples/fa_neda.wav` — Pocket TTS `example_voice.wav` (female,
  24 kHz mono, ~2.5 s, CC0-compatible prompt from the model repo).
- `assets/voice-samples/fa_arman.wav` — Common Voice 13 fa, self-declared male,
  twenties, CC0; converted to 24 kHz mono 16-bit, ≤5 s.

`stock_voice()` always attaches those paths. Persian `ref_text` is a short
Farsi line, not the English Kokoro preview. A unit test fails if either clip
is missing. `/voices/{id}/sample` then works for Farsi.

### Settings page

Local → Text to speech:

- Engine select: Pocket TTS (default) | Chatterbox.
- Model field follows the engine (Pocket repo vs Chatterbox T3 repo).
- Copy no longer says Persian is always Chatterbox.

### TTS gate

- Local label: “Local · Pocket TTS” or “Local · Chatterbox” from the selected
  engine.
- Farsi + Local: Pocket | Chatterbox toggle, default `gate_info.persian_tts_engine`.
- Continue payload: `{ mode, backend, narrator_voice }` (`backend` is
  `pocket` \| `chatterbox` only when local + fa). BYOK omits `backend`.

`ExecutionChoice.backend` is reused (already on the model). Gate validation
allows `pocket`/`chatterbox` on the TTS gate without loosening LLM backends.

### Worker

`_build_real_tts`: `fa` + not OpenRouter → Pocket or Chatterbox per
`settings.persian_tts_engine`. Unknown engine raises.

`apply_job_backends` local Farsi: `options.tts.backend` or settings default.
Fake mode still returns immediately.

`gate_info` adds `persian_tts_engine` and `pocket_persian_model`.

## Data flow

1. Settings (or env) set the default engine.
2. At the TTS gate the user may override `backend` for this job.
3. `apply_gate_payload` stores `ExecutionChoice(mode="local", backend=...)`.
4. On resume, `apply_job_backends` builds the matching adapter.
5. `synth_node` still calls `stock_voice()` / `voices_for_job()`; those now
   carry `ref_audio_path` for Neda/Arman.
6. The adapter clones from that clip. OpenRouter still uses clip +
   `instructions`.

## Error handling

- Unknown `persian_tts_engine` or TTS `backend`: raise (`RuntimeError` in the
  worker, `GateError` on continue). No fallthrough to Chatterbox.
- PUT `/settings` rejects an engine other than `pocket`/`chatterbox`.
- Pocket TTS missing `ref_audio_path` on a real synthesize: raise
  `ValueError` (catalog voices always have a clip after this change).
- Missing `[gpu]` extra / import failure: the existing lazy-import pattern
  (error at first `synthesize`, not at worker import).

## Testing

CPU, no network, no torch:

- `test_build_real_tts`: default Farsi local is Pocket; `persian_tts_engine=
  chatterbox` still constructs Chatterbox; unknown engine raises; BYOK
  unchanged.
- `test_pocket_tts.py`: lazy load, 24 kHz WAV, chunking, prompt path, release,
  runaway retry — all via a stub loader.
- `test_normalize_fa.py`: ي→ی, digit folding, harakat strip.
- `test_stock_voices.py`: Persian catalog voices ship clips; `ref_text` is
  Farsi.
- `test_gates.py`: TTS continue accepts `backend=pocket|chatterbox`, rejects
  junk; LLM backends unchanged.
- `test_settings.py`: GET/PUT engine + pocket model.
- Web: Settings engine select; Farsi TTS gate offers Pocket and Chatterbox
  and posts `backend`.

## Neda-as-male (fixed here)

There were no `fa_neda.wav` / `fa_arman.wav`. Local Chatterbox only changes
speaker when `ref_audio_path` is set; otherwise it uses the checkpoint default
(male). `instructions` are for hosted backends only. Bundled clips + a test
that they exist is the fix for both engines.
