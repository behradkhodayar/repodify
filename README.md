# Podcast Compactor

Turn a podcast — or a chosen chronological stretch of it — into a single
~30-minute digest episode. Paste a podcast link, pick which episodes to include,
and the service downloads the audio, transcribes it, summarizes it into a
chronological narrative, writes a spoken script, and synthesizes a new episode.

See the design in [`docs/superpowers/specs/`](docs/superpowers/specs/) and the
Phase 1 build plan in [`docs/superpowers/plans/`](docs/superpowers/plans/).

## Architecture (Phase 1)

```
link → resolve → list episodes → [select] → download
     → transcribe (faster-whisper)
     → summarize per episode (Claude)  ─┐ map
     → synthesize chronological arc     ─┘ reduce (Claude)
     → write ~30-min script (Claude)
     → TTS (F5-TTS) → assemble → digest.wav + show notes
```

The pipeline is a LangGraph `StateGraph`. Each ML-heavy stage (STT, LLM, TTS)
sits behind a small port with a real implementation and a test fake, so the
whole pipeline runs on CPU in tests. A FastAPI app enqueues jobs onto arq/Redis;
a worker runs the graph and records per-stage progress.

## Requirements

- Python 3.12+
- For real STT/TTS: a CUDA GPU and the `[gpu]` extra (`torch`, `faster-whisper`,
  `f5-tts`, `pyannote.audio`). Without it, run in **fake mode** (`USE_FAKES=true`).
- `ffmpeg` on PATH (for MP3 export).
- Redis and (optionally) Postgres for a production-like run.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"        # core + test deps
# On a GPU host, also: pip install -e ".[gpu]"
cp .env.example .env
```

## Run the tests

```bash
pytest
```

The default test suite runs entirely on CPU with no network — STT/LLM/TTS are faked.

## Run the service (fake mode)

```bash
docker compose up -d                                              # Redis (+ Postgres)
uvicorn --factory podcast_compactor.api.app:build_default_app     # API
arq podcast_compactor.worker.main.WorkerSettings                  # worker
```

Then:

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

# 3. Track progress, then fetch the result
curl -s localhost:8000/jobs/<job_id>
curl -s localhost:8000/jobs/<job_id>/result
```

### Two-host mode

Set `"host_count": 2` on a job to get a two-host dialogue (speakers `host_a` and
`host_b`) instead of a single narrator. In real mode, give each host a stock
reference voice via `HOST_A_REF_AUDIO`/`HOST_A_REF_TEXT` and
`HOST_B_REF_AUDIO`/`HOST_B_REF_TEXT` (see `.env.example`); fake mode needs no
assets.

## Status

Phases 1 (single-narrator digest) and 2 (two-host dialogue) are implemented.
Opt-in, watermarked voice cloning is Phase 3 (see the spec).
