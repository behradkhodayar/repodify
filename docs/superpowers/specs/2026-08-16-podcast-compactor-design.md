# Podcast Compactor — Design Spec

**Date:** 2026-08-16
**Status:** Approved (pending spec review) → implementation planning next

## 1. Overview

Podcast Compactor turns a whole podcast (or a chosen stretch of it) into a single
~30-minute "digest" episode. A user hands the service a podcast link, picks which
episodes to include, and the service downloads the audio, transcribes it,
summarizes it, writes a spoken script, and synthesizes a new audio episode.

The distinctive goal is **chronological**: rather than summarizing one episode,
the digest lets a listener *live through the show's arc* — how the show (or the
topic it covers) evolved from the earliest episodes forward.

The system is a **long-running backend service** (not a CLI): jobs run in the
background on a queue, and clients track progress and fetch results via an API.

## 2. Goals & non-goals

### Goals
- Accept a podcast link (Castbox channel, Apple Podcasts, or a raw RSS URL) and
  resolve it to a standard RSS feed.
- Let the user browse the episode catalog and **select which episodes and how
  many** to include (oldest-first ordering).
- Produce one ~30-minute, episode-aware, chronological narrative audio digest
  plus show notes / chapters.
- Be resumable and observable: a crash mid-run resumes from the last completed
  stage, and per-stage progress is queryable.
- Keep each pipeline stage behind a clean interface so models/providers are
  swappable.

### Non-goals (for now)
- Non-English podcasts (F5-TTS is English-focused; see §11 phasing).
- Real-time / streaming transcription. Batch only.
- A polished web UI. The deliverable is the service + API; a UI can come later.
- Handling Castbox-exclusive shows with no RSS feed (deferred scraper fallback).

## 3. Primary user flow

1. **Resolve** — user submits a link. Service resolves it to an RSS feed and
   returns the episode catalog (oldest-first, with duration and a
   "likely trailer/short" flag on suspect items).
2. **Select** — user picks episode IDs (or a range) and options
   (host count, target length, opt-in cloning).
3. **Run** — service creates a background job and returns a `job_id`.
4. **Track** — user polls job status / per-stage progress (optional live stream).
5. **Fetch** — on completion, user downloads the digest audio + show notes.

## 4. Architecture

Three roles, so GPU-heavy work is isolated from the API:

```
        ┌──────────────┐        enqueue        ┌───────────────┐
client → │ API (FastAPI)│ ────────────────────→ │ Queue (Redis  │
         │  CPU         │ ←──────────────────── │  + arq)       │
         └──────┬───────┘   status / results     └──────┬────────┘
                │                                        │ dequeue
                │ read/write                             ▼
         ┌──────▼────────┐                        ┌──────────────┐
         │ Postgres      │ ◄───── state/progress ─│ Worker (GPU) │
         │ (jobs, meta,  │                        │  runs the    │
         │  checkpoints) │                        │  LangGraph   │
         └───────────────┘                        │  pipeline    │
                                                  └──────────────┘
```

- **API — FastAPI (CPU).** Resolve feeds, list episodes, create/track jobs, serve
  results. No ML runs here.
- **Queue — Redis + arq.** Async-native, lightweight durable hand-off between API
  and worker. (Celery is the heavier alternative; arq chosen for async-first fit
  with FastAPI.)
- **Worker — GPU.** Runs the pipeline. Both faster-whisper (STT) and F5-TTS (TTS)
  need the GPU, so the whole run executes in the worker.

The pipeline itself is a **LangGraph `StateGraph`** with a **Postgres
checkpointer**. This gives durable, resumable runs and a natural per-node place to
emit progress that the API surfaces.

## 5. Technology stack

| Concern            | Choice                                             |
|--------------------|----------------------------------------------------|
| Language           | Python 3.12+                                        |
| API                | FastAPI + Uvicorn                                   |
| Orchestration      | LangGraph (`StateGraph` + Postgres checkpointer)    |
| Job queue          | arq (Redis)                                         |
| Metadata store     | Postgres (SQLite for local dev, same interface)     |
| Object storage     | Local filesystem (phase 1) → S3-compatible later    |
| Feed parsing       | `feedparser` + custom link→RSS resolvers            |
| Audio download     | `httpx` (streamed)                                  |
| STT                | faster-whisper (CTranslate2), GPU, VAD, word ts     |
| LLM (summary+script)| Claude via `langchain-anthropic` (`ChatAnthropic`) |
| TTS + cloning      | F5-TTS (local, GPU)                                 |
| Diarization (P3)   | pyannote.audio                                      |
| Audio assembly     | `pydub` / `ffmpeg`, loudness norm via `ffmpeg` EBU  |
| Config             | `pydantic-settings` (env-driven)                    |
| Tests              | pytest                                              |

### LLM model tiering (tunable)
- **Per-episode map summaries** (high volume, cheap): Haiku 4.5
  (`claude-haiku-4-5-20251001`).
- **Arc synthesis + scriptwriting** (quality-critical): Opus 4.8
  (`claude-opus-4-8`).

Exact IDs/tiers are finalized against the `claude-api` skill + current pricing at
implementation time; they live in config, not code.

## 6. Pipeline stages

Modeled as LangGraph nodes; state flows through and is checkpointed after each.

```
resolve_feed → list_episodes → [user selects] → download
   → transcribe        (faster-whisper, per episode)
   → summarize_episode (Claude map: per-episode structured summary)
   → synthesize_arc    (Claude reduce: chronological narrative outline)
   → write_script      (Claude: ~30-min spoken script)
   → tts               (F5-TTS: script → audio segments)
   → assemble          (stitch + intro/outro + loudness-normalize → mp3 + notes)
```

1. **resolve_feed** — link → RSS feed URL. Pluggable resolvers: Castbox, Apple
   Podcasts, raw-RSS passthrough. Input: `{url}`. Output: feed metadata + feed URL.
2. **list_episodes** — parse feed → episode catalog (title, publish date,
   duration, audio URL, `likely_trailer_or_short` flag). Oldest-first.
3. **download** — stream selected episodes' audio to storage. Per-episode; a
   failure is recorded and skipped, not fatal.
4. **transcribe** — faster-whisper per episode → transcript with segment (and
   optional word) timestamps. VAD trims silence. Cached by audio hash.
5. **summarize_episode (map)** — Claude condenses each transcript into a
   structured summary: key points, themes, notable quotes, timeline markers.
   Long transcripts handled via chunking → per-episode reduce.
6. **synthesize_arc (reduce)** — Claude combines per-episode summaries into a
   single **chronological narrative outline** for the batch — the "living through
   the show" arc.
7. **write_script** — Claude turns the outline into a spoken script. Length via
   word budget (~130 wpm × target minutes ≈ 3,900 words for 30 min). Phase 1:
   single-narrator monologue. Phase 2: 2-host dialogue with speaker turns.
8. **tts** — F5-TTS renders the script to audio. F5-TTS is zero-shot: every voice
   is a reference clip + its transcript. Phase 1: one bundled stock reference
   voice. Phase 2: two bundled reference voices, alternating by speaker turn.
   Phase 3: reference clips extracted from the real hosts (opt-in).
9. **assemble** — stitch segments, add intro/outro, EBU R128 loudness-normalize,
   export mp3 + show notes + chapter markers.

## 7. Data model

- **Feed** — `id`, `source_url`, `rss_url`, `title`, `author`, `resolved_at`.
- **Episode** — `id`, `feed_id`, `guid`, `title`, `published_at`, `duration_s`,
  `audio_url`, `is_short_or_trailer`, `order_index`.
- **Job** — `id`, `feed_id`, `episode_ids[]`, `options` (host_count,
  target_minutes, clone: bool), `status` (queued/running/completed/failed),
  `current_stage`, `created_at`, `finished_at`, `report` (warnings, skips).
- **StageStatus** — `job_id`, `stage`, `state`, `started_at`, `finished_at`,
  `detail`. Drives progress reporting.
- **Artifact** — `job_id`, `kind` (audio_download/transcript/summary/script/
  output_audio/show_notes), `episode_id?`, `storage_uri`, `created_at`.

LangGraph checkpoint state is stored in Postgres alongside these (its own tables).

## 8. Storage

A `Storage` interface abstracts blob I/O:
- Phase 1: local filesystem under `data/` (git-ignored), keyed by
  `job_id/stage/…`.
- Later: S3-compatible object storage, same interface.

Metadata (entities above) lives in Postgres; blobs (audio/transcripts/outputs)
live behind `Storage`.

## 9. API surface

- `POST /feeds/resolve` — `{url}` → feed metadata + episode catalog
  (oldest-first, trailer/short flags).
- `POST /jobs` — `{feed_url, episode_ids[], options{host_count, clone,
  target_minutes}}` → `{job_id}`.
- `GET /jobs/{id}` — `{status, current_stage, stages[], report}`.
- `GET /jobs/{id}/result` — `{output_audio_uri, show_notes, chapters}`.
- *(optional)* `GET /jobs/{id}/events` — SSE/WebSocket live progress.

## 10. Cross-cutting concerns

### Progress & observability
Each LangGraph node transition writes a `StageStatus` row and a checkpoint. The
API derives `current_stage` + per-stage timeline from these. Structured logging
throughout; correlation by `job_id`.

### Error handling & resumability
- Each stage is **idempotent and retriable** (caching by content hash where
  applicable — e.g. transcripts by audio hash).
- **Partial failures don't kill the run**: one episode failing to download or
  transcribe is skipped with a warning recorded in `Job.report`.
- LangGraph checkpointing enables **resume from the last completed stage** after a
  crash.
- Backoff/retry on feed fetches, audio downloads, and Claude API calls; respect
  rate limits.

### Configuration & secrets
`pydantic-settings`, env-driven. Secrets (Anthropic API key, DB/Redis URLs) via
`.env` (git-ignored) with a committed `.env.example`. GPU device selection, model
IDs, word-budget/wpm, and default host count are all config.

## 11. Phasing

- **Phase 1 — vertical slice (build first).** RSS ingest + interactive selection
  → download → faster-whisper transcribe → Claude map-reduce summary → **single-
  narrator** script → F5-TTS **single stock voice** → assemble → 30-min mp3 +
  show notes. Full service (FastAPI + arq + Postgres + LangGraph). Proves the
  hard chain end to end.
- **Phase 2 — two hosts.** 2-host dialogue script + two distinct **stock**
  reference voices, alternating by speaker turn.
- **Phase 3 — opt-in voice cloning.** pyannote diarization auto-extracts each
  host's reference clip from the downloaded episodes → F5-TTS clones them.
  Plus a Castbox scraper fallback for RSS-less exclusive shows.

### Voice-cloning constraints (Phase 3 — hard requirements)
1. **Opt-in only** — never the default; explicit per-job flag.
2. **Labeled synthetic** — output metadata + show notes clearly mark the audio as
   AI-generated, and it must never be presented as the real host.
3. **Watermarked** — an audible spoken disclaimer plus an inaudible watermark
   (candidate: AudioSeal) on cloned output.
4. **Nothing illegal / no ToS violations** — respect right-of-publicity and
   platform terms; skip rather than cross a line.

## 12. Testing strategy

- **Per-node unit tests** with fixtures: sample RSS XML, a short audio clip,
  canned transcripts, and a **mocked Claude** client (deterministic).
- **One integration test** end-to-end on a single short real episode.
- **Golden tests** asserting script length (word budget) and structure
  (chronological, episode-aware), and that assembly produces a valid ~30-min mp3.
- Resolver tests per platform (Castbox / Apple / raw RSS).

## 13. Repository layout (proposed)

```
src/podcast_compactor/
  ingest/        # resolvers, feedparser, download
  transcribe/    # faster-whisper wrapper
  summarize/     # map (per-episode) + reduce (arc) Claude chains
  script/        # scriptwriter (mono / dialogue)
  synth/         # F5-TTS wrapper, assembly, watermarking (P3)
  pipeline/      # LangGraph StateGraph + node definitions + state schema
  api/           # FastAPI app, routers, schemas
  worker/        # arq worker + job entrypoint
  storage/       # Storage interface + filesystem/S3 impls
  models/        # pydantic + DB models
  config.py      # pydantic-settings
docs/superpowers/specs/
tests/
```

## 14. Open / deferred decisions

- **Queue**: arq (chosen) vs Celery — revisit only if arq proves limiting.
- **Metadata store**: Postgres in prod, SQLite in dev — confirm at setup.
- **Exact LLM model tiers/IDs** — finalize against `claude-api` skill + pricing.
- **Inaudible watermark library** (Phase 3) — AudioSeal is the leading candidate;
  confirm licensing/quality when we get there.
- **Web UI** — out of scope now; API is UI-ready.
