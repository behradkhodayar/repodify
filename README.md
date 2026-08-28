# Podcast Compactor

Turn a podcast — or a chosen chronological stretch of it — into a single
~30-minute digest episode. Paste a podcast link, pick which episodes to include,
and the service downloads the audio, transcribes it, summarizes it into a
chronological narrative, writes a spoken script, and synthesizes a new episode.

See the full [system architecture reference](docs/architecture.md), the designs
in [`docs/superpowers/specs/`](docs/superpowers/specs/), and the build plans in
[`docs/superpowers/plans/`](docs/superpowers/plans/).

## Architecture (Phase 1)

```
link → resolve → list episodes → [select] → download
     → transcribe (faster-whisper)
     → summarize per episode (Claude)  ─┐ map
     → synthesize chronological arc     ─┘ reduce (Claude)
     → write ~30-min script (Claude)
     → TTS (F5-TTS) → assemble → digest.wav + digest.mp3 + show notes
```

The pipeline is a LangGraph `StateGraph`. Each ML-heavy stage (STT, LLM, TTS)
sits behind a small port with a real implementation and a test fake, so the
whole pipeline runs on CPU in tests. A FastAPI app enqueues jobs onto arq/Redis;
a worker runs the graph and records per-stage progress. A single-user bearer
token guards the API, which also streams the finished digest (WAV or mp3, with
HTTP Range support) to web and mobile clients. See
[`docs/architecture.md`](docs/architecture.md) for the full reference architecture.

## Requirements

- [uv](https://docs.astral.sh/uv/) for dependency and environment management.
- Python 3.13 (pinned in `.python-version`; uv installs it for you). `>=3.12` works.
- For real STT/TTS: a CUDA GPU and the `[gpu]` extra (`torch`, `faster-whisper`,
  `f5-tts`, `pyannote.audio`, `audioseal`). Without it, run in **fake mode**
  (`USE_FAKES=true`).
- `ffmpeg` on PATH — real runs transcode each digest to a compact mp3, and
  reference-clip extraction uses it too. (Fake mode skips transcoding.)
- Redis and (optionally) Postgres for a production-like run.

## Setup

```bash
uv sync                 # creates .venv, installs core + dev deps from uv.lock
uv sync --extra gpu     # on a GPU host, add the real ML backends
cp .env.example .env
```

## Run the tests

```bash
uv run pytest
```

The default test suite runs entirely on CPU with no network — STT/LLM/TTS are faked.

## Run the service (fake mode)

```bash
docker compose up -d                                                   # Redis (+ Postgres)
uv run uvicorn --factory podcast_compactor.api.app:build_default_app   # API
uv run arq podcast_compactor.worker.main.WorkerSettings                # worker
```

When `API_TOKEN` is set, send `-H "Authorization: Bearer $API_TOKEN"` on every
request except `GET /health`. Then:

```bash
# 1. Resolve a feed and list episodes
curl -s -X POST localhost:8000/feeds/resolve \
  -H 'content-type: application/json' \
  -d '{"url": "https://example.com/feed.xml"}'

# 2. Create a job for the episodes you want (oldest-first)
#    host_count: 1 = single narrator (default), 2 = two-host dialogue
curl -s -X POST localhost:8000/jobs \
  -H 'content-type: application/json' \
  -d '{"feed_url": "https://example.com/feed.xml", "episode_ids": ["ep-1","ep-2"], "host_count": 2, "target_minutes": 30}'

# 3. Track progress, then fetch the result (audio URLs + summary + chapters)
curl -s localhost:8000/jobs/<job_id>
curl -s localhost:8000/jobs/<job_id>/result

# 4. Stream/download the finished digest (mp3 or wav; supports HTTP Range)
curl -s -o digest.mp3 "localhost:8000/jobs/<job_id>/audio?format=mp3"

# List recent jobs; liveness probe
curl -s "localhost:8000/jobs?limit=20"
curl -s localhost:8000/health
```

### Two-host mode

Set `"host_count": 2` on a job to get a two-host dialogue (speakers `host_a` and
`host_b`) instead of a single narrator. In real mode, give each host a stock
reference voice via `HOST_A_REF_AUDIO`/`HOST_A_REF_TEXT` and
`HOST_B_REF_AUDIO`/`HOST_B_REF_TEXT` (see `.env.example`); fake mode needs no
assets.

### Local LLM via Ollama (no Anthropic key)

The summarize/script stages default to the Claude API, but you can point them at
a local [Ollama](https://ollama.com) model instead — useful when you have a GPU
but no `ANTHROPIC_API_KEY`. Real STT/TTS are unaffected.

```bash
ollama pull qwen2.5-coder:7b        # or any model you prefer
# in .env:
#   USE_FAKES=false
#   LLM_BACKEND=ollama
#   OLLAMA_MODEL=qwen2.5-coder:7b
#   OLLAMA_BASE_URL=http://localhost:11434
```

One model serves both the per-episode summary and the arc/script stages
(`MAP_MODEL`/`REDUCE_MODEL` are ignored on Ollama). Small code-specialized models
produce valid output but weaker narratives than Claude; a general instruct model
of 7B+ summarizes better.

### Voice cloning (opt-in)

Set `"clone": true` on a job to synthesize the digest in the **cloned voices of
the original hosts**, extracted from the downloaded episodes via speaker
diarization. Cloning is **off by default** and always carries these guardrails:

- **Labeled synthetic** — the show notes are flagged `synthetic: true` and carry
  a disclaimer; the output must never be presented as the real hosts.
- **Audible disclaimer** — a spoken disclaimer (configurable via
  `CLONE_DISCLAIMER`) is prepended to the audio.
- **Inaudible watermark** — the output is watermarked (AudioSeal in real mode).

Real cloning needs the `[gpu]` extra and a Hugging Face token for pyannote
diarization (`HF_TOKEN`); fake mode exercises the whole flow with no assets.

```bash
curl -s -X POST localhost:8000/jobs \
  -H 'content-type: application/json' \
  -d '{"feed_url": "https://example.com/feed.xml", "episode_ids": ["ep-1","ep-2"], "host_count": 2, "clone": true}'
```

Only clone voices you have the right to use — respect right-of-publicity and each
platform's terms.

### Speaker-preserving digest (opt-in)

Set `"preserve_speakers": true` to voice the digest as the show's **real detected
cast** instead of a single narrator or two generic hosts. Diarization identifies
each speaker; the script becomes a multi-speaker dialogue attributed to them; and
each speaker is voiced by their assigned voice — their **own clone** or a **stock
catalog voice** (`GET /voices`). Assign them explicitly per speaker, or let it
default (clone everyone with `"clone": true`, otherwise stock voices):

```bash
curl -s -X POST localhost:8000/jobs \
  -H 'content-type: application/json' \
  -d '{"feed_url": "https://example.com/feed.xml", "episode_ids": ["ep-1"], "preserve_speakers": true,
       "voice_assignments": [{"speaker_id": "SPEAKER_00", "mode": "clone"},
                             {"speaker_id": "SPEAKER_01", "mode": "stock", "stock_voice": "af_heart"}]}'
```

When any voice is cloned the same guardrails apply (synthetic label, spoken
disclaimer, watermark). Stock voices use Kokoro-82M; cloned voices use F5-TTS.

Because the detected speaker ids aren't known until diarization runs, set
`"review_voices": true` to have the job **pause after diarization** for review:

1. Create the job with `"review_voices": true`. It runs resolve → download →
   transcribe → diarize, then stops at status `awaiting_review`.
2. `GET /jobs/{id}/speakers` returns the detected cast (ids + talk time).
3. `POST /jobs/{id}/voices` with a `voice_assignments` array resumes the job into
   a speaker-preserving digest using the voices you chose.

## Web client (PWA)

A React + Vite PWA lives in `web/` and is served same-origin by the API at `/app`.

```bash
cd web && npm install          # once
npm run dev                    # dev server on :5173, proxies API calls to :8000
npm run build                  # emit web/dist/, which the API serves at /app
npm test                       # Vitest + MSW component/hook tests
```

With `web/dist` built, open the app at `http://localhost:8000/app/` (or use the
Vite dev server during development). Set the token in **Settings** if the API is
protected by `API_TOKEN`.

## Status

Phases 1 (single-narrator digest), 2 (two-host dialogue), and 3 (opt-in,
watermarked, labeled voice cloning) are implemented, plus speaker-aware
transcription, a Kokoro stock-voice catalog, a speaker-preserving digest that
voices the real detected cast (each in their own cloned or stock voice), and an
interactive review that pauses after diarization to assign a voice per speaker.

## Roadmap

- [x] Cross-episode speaker identity — recognize the same host/guest across
  multiple episodes and merge their diarized speakers into one voice (was
  per-episode; now clustered by voice embedding).
- [x] Match stock voices to speaker gender by default — infer each speaker's
  gender from their diarized audio (median F0) and assign a same-gender catalog
  voice, so a male host gets a male voice even without cloning. The default; the
  user can override it, and an ambiguous pitch falls back to register-alternation.
- [ ] Let user choose their preferred stock speakers — a general selection menu
  under settings, with a playable audio sample chunk in front of each name
  (the per-speaker override for the gender-matching default above).
